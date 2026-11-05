"""Webserver mit Oberfläche unter http://localhost:8000"""
import shutil
import webbrowser
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, db, media, pipeline, scheduler, story, tiktok, youtube

app = FastAPI(title="Story Shorts")
STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.on_event("startup")
def _startup():
    # Nach Absturz hängengebliebene Zustände zurücksetzen
    db.execute("UPDATE parts SET status='fehler', error='Abgebrochen (App wurde beendet)' WHERE status='rendert'")
    db.execute("UPDATE series SET status='fehler', error='Abgebrochen (App wurde beendet)' WHERE status IN ('schreibt','rendert')")
    scheduler.start()


@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC / "index.html").read_text(encoding="utf-8")


# ---------- System ----------

@app.get("/api/status")
def api_status():
    return {
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "claude": bool(config.ANTHROPIC_API_KEY),
        "pexels": bool(config.PEXELS_API_KEY),
        "pixabay": bool(config.PIXABAY_API_KEY),
        "piper": bool(config.PIPER_EXE and config.PIPER_MODEL),
        "youtube": youtube.status(),
        "tiktok": tiktok.status(),
        "post_time": config.POST_TIME,
        "voices": config.VOICES,
        "library_count": len(media.library_clips()),
        "music_count": sum(1 for p in config.MUSIC.rglob("*") if p.suffix.lower() in {".mp3", ".wav", ".m4a", ".ogg"}),
        "log": scheduler.recent_log(),
    }


# ---------- Ideen ----------

class IdeaReq(BaseModel):
    count: int = 8
    genres: str = ""


@app.get("/api/ideas")
def list_ideas():
    return db.query("SELECT * FROM ideas WHERE used=0 ORDER BY id DESC")


@app.post("/api/ideas")
def make_ideas(req: IdeaReq):
    avoid = [r["data"]["title"] for r in db.query("SELECT data FROM ideas")]
    try:
        ideas = story.generate_ideas(max(3, min(10, req.count)), req.genres, avoid)
    except story.StoryError as e:
        raise HTTPException(400, str(e))
    for i in ideas:
        db.execute("INSERT INTO ideas (data, created_at) VALUES (?,?)", (db.dumps(i), db.now()))
    return list_ideas()


@app.delete("/api/ideas/{iid}")
def drop_idea(iid: int):
    db.execute("DELETE FROM ideas WHERE id=?", (iid,))
    return {"ok": True}


class SeriesReq(BaseModel):
    idea_id: int
    wish: str = ""


@app.post("/api/series")
def new_series(req: SeriesReq):
    if not config.ANTHROPIC_API_KEY:
        raise HTTPException(400, "ANTHROPIC_API_KEY fehlt in .env")
    return {"id": pipeline.create_series(req.idea_id, req.wish)}


# ---------- Serien ----------

def _series_full(sid: int):
    s = db.one("SELECT * FROM series WHERE id=?", (sid,))
    if not s:
        raise HTTPException(404, "Serie nicht gefunden")
    s["parts"] = db.query("SELECT * FROM parts WHERE series_id=? ORDER BY idx", (sid,))
    s["busy"] = pipeline.is_busy(f"series-{sid}") or any(pipeline.is_busy(f"part-{p['id']}") for p in s["parts"])
    for p in s["parts"]:
        if p["data"].get("audio"):
            p["data"]["audio"] = {"file": p["data"]["audio"]["file"]}  # Wortliste nicht mitschicken
    return s


@app.get("/api/series")
def list_series():
    out = []
    for s in db.query("SELECT * FROM series ORDER BY id DESC"):
        parts = db.query("SELECT status, scheduled_date, yt_video_id, tiktok_publish_id FROM parts WHERE series_id=?", (s["id"],))
        s["n_parts"] = len(parts)
        s["n_done"] = sum(1 for p in parts if p["status"] == "gerendert")
        out.append(s)
    return out


@app.get("/api/series/{sid}")
def get_series(sid: int):
    return _series_full(sid)


class SeriesUpdate(BaseModel):
    voice: str | None = None
    rate: str | None = None
    title: str | None = None


@app.put("/api/series/{sid}")
def update_series(sid: int, req: SeriesUpdate):
    s = db.one("SELECT * FROM series WHERE id=?", (sid,))
    if req.voice:
        db.execute("UPDATE series SET voice=? WHERE id=?", (req.voice, sid))
    if req.rate:
        db.execute("UPDATE series SET rate=? WHERE id=?", (req.rate, sid))
    if req.title:
        d = s["data"]
        d["title"] = req.title
        db.execute("UPDATE series SET data=? WHERE id=?", (db.dumps(d), sid))
    return _series_full(sid)


@app.post("/api/series/{sid}/rerender")
def rerender_series(sid: int):
    db.execute("UPDATE series SET status='rendert', error=NULL WHERE id=?", (sid,))
    pipeline.rerender_series(sid)
    return {"ok": True}


@app.post("/api/series/{sid}/approve")
def approve(sid: int):
    try:
        scheduler.approve(sid)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _series_full(sid)


@app.post("/api/series/{sid}/unapprove")
def unapprove(sid: int):
    scheduler.unapprove(sid)
    return _series_full(sid)


@app.delete("/api/series/{sid}")
def delete_series(sid: int):
    pipeline.delete_series(sid)
    return {"ok": True}


# ---------- Teile ----------

class PartUpdate(BaseModel):
    scenes: list[dict] | None = None
    yt_title: str | None = None
    description: str | None = None
    hashtags: list[str] | None = None


def _part(pid: int):
    p = db.one("SELECT * FROM parts WHERE id=?", (pid,))
    if not p:
        raise HTTPException(404, "Teil nicht gefunden")
    return p


@app.put("/api/parts/{pid}")
def update_part(pid: int, req: PartUpdate):
    p = _part(pid)
    d = p["data"]
    text_changed = False
    if req.scenes is not None:
        for old, new in zip(d["scenes"], req.scenes):
            if new.get("text", old["text"]).strip() != old["text"].strip():
                text_changed = True
            old["text"] = new.get("text", old["text"])
            if new.get("keywords") is not None and new["keywords"] != old["keywords"]:
                old["keywords"] = new["keywords"]
                old["clip"] = None  # neue Suchbegriffe → neuen Clip suchen
                text_changed = True
    for k in ("yt_title", "description", "hashtags"):
        v = getattr(req, k)
        if v is not None:
            d[k] = v
    db.execute("UPDATE parts SET data=? WHERE id=?", (db.dumps(d), pid))
    return {"ok": True, "needs_render": text_changed}


@app.post("/api/parts/{pid}/render")
def render_part(pid: int):
    _part(pid)
    pipeline.rerender_part(pid, fresh_audio=True)
    return {"ok": True}


@app.post("/api/parts/{pid}/scenes/{idx}/swap")
def swap(pid: int, idx: int):
    _part(pid)
    pipeline.swap_clip(pid, idx)
    return {"ok": True}


class Wish(BaseModel):
    wish: str = ""


@app.post("/api/parts/{pid}/regenerate")
def regenerate(pid: int, req: Wish):
    _part(pid)
    pipeline.regenerate_part(pid, req.wish)
    return {"ok": True}


@app.post("/api/parts/{pid}/tiktok_now")
def tiktok_now(pid: int):
    p = _part(pid)
    try:
        pub = tiktok.send_draft(p["video_path"])
    except Exception as e:
        raise HTTPException(400, str(e))
    db.execute("UPDATE parts SET tiktok_publish_id=?, tiktok_error=NULL WHERE id=?", (pub, pid))
    return {"ok": True}


@app.get("/video/{pid}")
def video(pid: int):
    p = _part(pid)
    if not p["video_path"] or not Path(p["video_path"]).exists():
        raise HTTPException(404)
    return FileResponse(p["video_path"], media_type="video/mp4")


# ---------- Plan ----------

@app.get("/api/schedule")
def schedule():
    rows = db.query("SELECT p.id, p.idx, p.data, p.scheduled_date, p.yt_video_id, p.yt_error, p.tiktok_publish_id, "
                    "p.tiktok_error, s.id AS sid, s.data AS sdata FROM parts p JOIN series s ON s.id=p.series_id "
                    "WHERE p.scheduled_date IS NOT NULL ORDER BY p.scheduled_date, p.idx")
    import json
    return [{
        "id": r["id"], "date": r["scheduled_date"], "title": r["data"].get("yt_title"),
        "series": json.loads(r["sdata"])["title"], "sid": r["sid"],
        "yt": r["yt_video_id"], "yt_error": r["yt_error"],
        "tiktok": r["tiktok_publish_id"], "tiktok_error": r["tiktok_error"],
        "hashtags": r["data"].get("hashtags", []), "description": r["data"].get("description", ""),
    } for r in rows]


@app.post("/api/schedule/run")
def run_now():
    scheduler.run_now()
    return {"ok": True}


# ---------- Konten verbinden ----------

@app.get("/auth/youtube")
def yt_login():
    if not youtube.configured():
        raise HTTPException(400, "client_secret.json fehlt im Projektordner (siehe docs/YOUTUBE.md)")
    return RedirectResponse(youtube.auth_url())


@app.get("/auth/youtube/callback")
def yt_callback(request: Request, state: str = ""):
    try:
        youtube.finish_auth(str(request.url), state)
    except Exception as e:
        return HTMLResponse(f"<h3>YouTube-Verbindung fehlgeschlagen</h3><p>{e}</p><a href='/'>Zurück</a>")
    return RedirectResponse("/#einstellungen")


@app.get("/auth/tiktok")
def tt_login():
    if not tiktok.configured():
        raise HTTPException(400, "TIKTOK_CLIENT_KEY/SECRET fehlen in .env (siehe docs/TIKTOK.md)")
    return RedirectResponse(tiktok.auth_url())


@app.get("/auth/tiktok/callback")
def tt_callback(code: str = "", state: str = "", error: str = "", error_description: str = ""):
    if error:
        return HTMLResponse(f"<h3>TikTok: {error}</h3><p>{error_description}</p><a href='/'>Zurück</a>")
    try:
        tiktok.finish_auth(code, state)
    except Exception as e:
        return HTMLResponse(f"<h3>TikTok-Verbindung fehlgeschlagen</h3><p>{e}</p><a href='/'>Zurück</a>")
    return RedirectResponse("/#einstellungen")


@app.post("/api/disconnect/{platform}")
def disconnect(platform: str):
    {"youtube": youtube.disconnect, "tiktok": tiktok.disconnect}[platform]()
    return {"ok": True}


def run():
    import threading
    import uvicorn
    threading.Timer(1.5, lambda: webbrowser.open(config.BASE_URL)).start()
    uvicorn.run(app, host="127.0.0.1", port=config.PORT, log_level="warning")


if __name__ == "__main__":
    run()
