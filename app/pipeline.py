"""Ablauf: Serie anlegen → Clips suchen → Stimme → Video rendern."""
import shutil
import threading
import traceback

from . import config, db, media, render, story, tts

_jobs_lock = threading.Lock()
_running: set[str] = set()


def _bg(key: str, fn, *args):
    with _jobs_lock:
        if key in _running:
            return False
        _running.add(key)

    def run():
        try:
            fn(*args)
        finally:
            with _jobs_lock:
                _running.discard(key)

    threading.Thread(target=run, daemon=True).start()
    return True


def is_busy(key: str) -> bool:
    with _jobs_lock:
        return key in _running


# ---------- Serie anlegen ----------

def create_series(idea_id: int, wish: str = "") -> int:
    idea = db.one("SELECT * FROM ideas WHERE id=?", (idea_id,))
    if not idea:
        raise ValueError("Idee nicht gefunden")
    sid = db.execute(
        "INSERT INTO series (data, voice, rate, status, created_at) VALUES (?,?,?,?,?)",
        (db.dumps({"title": idea["data"]["title"], "genre": idea["data"]["genre"], "parts": []}),
         config.DEFAULT_VOICE, config.DEFAULT_RATE, "schreibt", db.now()),
    )
    db.execute("UPDATE ideas SET used=1 WHERE id=?", (idea_id,))
    _bg(f"series-{sid}", _write_and_render, sid, idea["data"], wish)
    return sid


def _write_and_render(sid: int, idea: dict, wish: str):
    try:
        data = story.generate_series(idea, wish)
        parts = data.pop("parts")
        db.execute("UPDATE series SET data=?, status='rendert', error=NULL WHERE id=?", (db.dumps(data), sid))
        for i, p in enumerate(parts):
            db.execute("INSERT INTO parts (series_id, idx, data) VALUES (?,?,?)", (sid, i, db.dumps(p)))
        _render_all(sid)
    except Exception as e:
        traceback.print_exc()
        db.execute("UPDATE series SET status='fehler', error=? WHERE id=?", (str(e), sid))


# ---------- Rendern ----------

def _render_all(sid: int):
    for p in db.query("SELECT id FROM parts WHERE series_id=? ORDER BY idx", (sid,)):
        _render_part(p["id"])
    _update_series_status(sid)


def _update_series_status(sid: int):
    s = db.one("SELECT status FROM series WHERE id=?", (sid,))
    if s and s["status"] in ("freigegeben", "fertig"):
        return
    states = {p["status"] for p in db.query("SELECT status FROM parts WHERE series_id=?", (sid,))}
    status = "fehler" if "fehler" in states else ("bereit" if states == {"gerendert"} else "rendert")
    db.execute("UPDATE series SET status=? WHERE id=?", (status, sid))


def _render_part(pid: int, fresh_audio: bool = True):
    part = db.one("SELECT * FROM parts WHERE id=?", (pid,))
    series = db.one("SELECT * FROM series WHERE id=?", (part["series_id"],))
    total = db.one("SELECT COUNT(*) AS n FROM parts WHERE series_id=?", (part["series_id"],))["n"]
    db.execute("UPDATE parts SET status='rendert', error=NULL WHERE id=?", (pid,))
    try:
        data = part["data"]
        sdata = series["data"]
        work = config.CACHE / "work" / f"s{series['id']}_p{part['idx'] + 1}"
        work.mkdir(parents=True, exist_ok=True)

        # 1) Clips je Szene (bereits gewählte bleiben erhalten)
        used = set()
        for sc in data["scenes"]:
            if sc.get("clip"):
                used.add(sc["clip"]["id"])
        for sc in data["scenes"]:
            if not sc.get("clip"):
                clip = media.find_clip(sc["keywords"], used | set(sc.get("rejected", [])))
                if not clip:
                    raise RuntimeError("Keine Clips gefunden. Trage PEXELS_API_KEY (oder PIXABAY_API_KEY) in .env ein "
                                       "oder lege eigene Clips in den Ordner library/.")
                sc["clip"] = {k: clip[k] for k in ("source", "id", "path", "credit")}
                used.add(clip["id"])

        # 2) Stimme
        text = " ".join(sc["text"].strip() for sc in data["scenes"])
        audio_info = data.get("audio")
        if fresh_audio or not audio_info or not (work / audio_info["file"]).exists():
            audio, words = tts.synthesize(text, series["voice"], series["rate"], work / "voice")
            data["audio"] = {"file": audio.name, "words": words}
        audio = work / data["audio"]["file"]
        words = data["audio"]["words"]

        # 3) Video
        music = media.pick_music(sdata.get("mood", "spannung"))
        out = config.OUTPUT / f"serie{series['id']}_teil{part['idx'] + 1}.mp4"
        render.render_part(work, data["scenes"], audio, words, f"Teil {part['idx'] + 1}/{total}",
                           bool(sdata.get("is_fiction")), music, out)
        db.execute("UPDATE parts SET data=?, video_path=?, status='gerendert' WHERE id=?",
                   (db.dumps(data), str(out), pid))
    except Exception as e:
        traceback.print_exc()
        db.execute("UPDATE parts SET status='fehler', error=? WHERE id=?", (str(e)[:2000], pid))


def rerender_part(pid: int, fresh_audio: bool = True) -> bool:
    part = db.one("SELECT series_id FROM parts WHERE id=?", (pid,))

    def job():
        _render_part(pid, fresh_audio)
        _update_series_status(part["series_id"])

    return _bg(f"part-{pid}", job)


def rerender_series(sid: int) -> bool:
    return _bg(f"series-{sid}", _render_all, sid)


def swap_clip(pid: int, scene_idx: int) -> bool:
    part = db.one("SELECT * FROM parts WHERE id=?", (pid,))
    data = part["data"]
    sc = data["scenes"][scene_idx]
    if sc.get("clip"):
        sc.setdefault("rejected", []).append(sc["clip"]["id"])
        sc["clip"] = None
    db.execute("UPDATE parts SET data=? WHERE id=?", (db.dumps(data), pid))
    return rerender_part(pid, fresh_audio=False)


def regenerate_part(pid: int, wish: str = "") -> bool:
    part = db.one("SELECT * FROM parts WHERE id=?", (pid,))
    series = db.one("SELECT * FROM series WHERE id=?", (part["series_id"],))

    def job():
        try:
            db.execute("UPDATE parts SET status='rendert', error=NULL WHERE id=?", (pid,))
            all_parts = db.query("SELECT data FROM parts WHERE series_id=? ORDER BY idx", (series["id"],))
            sdata = dict(series["data"], parts=[p["data"] for p in all_parts])
            new = story.regenerate_part(sdata, part["idx"], wish)
            db.execute("UPDATE parts SET data=? WHERE id=?", (db.dumps(new), pid))
            _render_part(pid)
        except Exception as e:
            db.execute("UPDATE parts SET status='fehler', error=? WHERE id=?", (str(e), pid))
        _update_series_status(series["id"])

    return _bg(f"part-{pid}", job)


def delete_series(sid: int):
    for p in db.query("SELECT * FROM parts WHERE series_id=?", (sid,)):
        if p["video_path"]:
            try:
                from pathlib import Path
                Path(p["video_path"]).unlink(missing_ok=True)
            except OSError:
                pass
        shutil.rmtree(config.CACHE / "work" / f"s{sid}_p{p['idx'] + 1}", ignore_errors=True)
    db.execute("DELETE FROM parts WHERE series_id=?", (sid,))
    db.execute("DELETE FROM series WHERE id=?", (sid,))
