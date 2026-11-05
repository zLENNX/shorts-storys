"""Warteschlange: freigegebene Serien bekommen Tagestermine; ein Hintergrund-Thread
lädt bei YouTube geplant hoch und schickt TikTok-Entwürfe am jeweiligen Tag."""
import json
import threading
import time
import traceback
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from . import config, db, tiktok, youtube

TZ = ZoneInfo(config.TIMEZONE)
_wake = threading.Event()
_last_log: list[str] = []


def log(msg: str):
    line = f"{datetime.now(TZ):%d.%m. %H:%M} {msg}"
    print(line)
    _last_log.append(line)
    del _last_log[:-50]


def recent_log() -> list[str]:
    return list(reversed(_last_log))


def _post_dt(d: date) -> datetime:
    h, m = map(int, config.POST_TIME.split(":"))
    return datetime(d.year, d.month, d.day, h, m, tzinfo=TZ)


def approve(sid: int):
    parts = db.query("SELECT * FROM parts WHERE series_id=? ORDER BY idx", (sid,))
    if not parts or any(p["status"] != "gerendert" for p in parts):
        raise ValueError("Alle Teile müssen fertig gerendert sein.")
    last = db.one("SELECT MAX(scheduled_date) AS d FROM parts WHERE scheduled_date IS NOT NULL")
    now = datetime.now(TZ)
    # Erster freier Tag: heute (wenn Postzeit in >1h), sonst morgen; nach bereits geplanten Serien
    first = now.date() if _post_dt(now.date()) - now > timedelta(hours=1) else now.date() + timedelta(days=1)
    if last and last["d"]:
        first = max(first, date.fromisoformat(last["d"]) + timedelta(days=1))
    for i, p in enumerate(parts):
        db.execute("UPDATE parts SET scheduled_date=? WHERE id=?", ((first + timedelta(days=i)).isoformat(), p["id"]))
    db.execute("UPDATE series SET status='freigegeben' WHERE id=?", (sid,))
    log(f"Serie {sid} freigegeben, Start {first:%d.%m.%Y}")
    _wake.set()


def unapprove(sid: int):
    """Plan zurücknehmen (nur Teile, die noch nirgends hochgeladen wurden)."""
    db.execute("UPDATE parts SET scheduled_date=NULL WHERE series_id=? AND yt_video_id IS NULL AND tiktok_publish_id IS NULL", (sid,))
    db.execute("UPDATE series SET status='bereit' WHERE id=?", (sid,))


def _description(part: dict, series: dict, prev_video: str | None) -> str:
    d, s = part["data"], series["data"]
    lines = [d.get("description", "")]
    if prev_video:
        lines.append(f"\n⬅️ Vorheriger Teil: https://youtube.com/shorts/{prev_video}")
    if series.get("yt_playlist_id"):
        lines.append(f"▶️ Alle Teile: https://www.youtube.com/playlist?list={series['yt_playlist_id']}")
    if s.get("is_fiction"):
        lines.append("\nDiese Geschichte ist frei erfunden. Ähnlichkeiten mit realen Personen sind zufällig.")
    credits = sorted({sc["clip"]["credit"] for sc in d["scenes"] if sc.get("clip") and sc["clip"].get("credit")})
    if credits:
        lines.append("\nVideomaterial: " + ", ".join(credits))
    lines.append("Stimme: KI-generiert.")
    lines.append("\n" + " ".join("#" + h.lstrip("#").replace(" ", "") for h in d.get("hashtags", [])))
    return "\n".join(lines)


def _youtube_tick():
    if not youtube.TOKEN_FILE.exists():
        return
    counter = config.DATA / "yt_uploads_today.json"
    today = date.today().isoformat()
    try:
        c = json.loads(counter.read_text())
        uploads_today = c["count"] if c["date"] == today else 0
    except (OSError, ValueError, KeyError):
        uploads_today = 0
    pending = db.query(
        "SELECT p.*, s.id AS sid FROM parts p JOIN series s ON s.id=p.series_id "
        "WHERE p.scheduled_date IS NOT NULL AND p.yt_video_id IS NULL ORDER BY p.scheduled_date, p.idx")
    for p in pending:
        if uploads_today >= config.YT_MAX_UPLOADS_PER_DAY:
            break
        series = db.one("SELECT * FROM series WHERE id=?", (p["sid"],))
        publish_at = _post_dt(date.fromisoformat(p["scheduled_date"]))
        if publish_at < datetime.now(TZ) + timedelta(minutes=15):
            publish_at = datetime.now(TZ) + timedelta(minutes=20)
        try:
            if not series["yt_playlist_id"]:
                pl = youtube.create_playlist(series["data"].get("playlist_title") or series["data"]["title"],
                                             f"Alle Teile von „{series['data']['title']}“ der Reihe nach.")
                db.execute("UPDATE series SET yt_playlist_id=? WHERE id=?", (pl, series["id"]))
                series["yt_playlist_id"] = pl
            prev = db.one("SELECT yt_video_id FROM parts WHERE series_id=? AND idx=?", (series["id"], p["idx"] - 1))
            vid = youtube.upload(p["video_path"], p["data"]["yt_title"],
                                 _description(p, series, prev["yt_video_id"] if prev else None),
                                 p["data"].get("hashtags", []), publish_at)
            db.execute("UPDATE parts SET yt_video_id=?, yt_error=NULL WHERE id=?", (vid, p["id"]))
            youtube.add_to_playlist(series["yt_playlist_id"], vid)
            uploads_today += 1
            counter.write_text(json.dumps({"date": today, "count": uploads_today}))
            log(f"YouTube: {p['data']['yt_title']} geplant für {publish_at:%d.%m. %H:%M}")
        except youtube.QuotaExceeded:
            log("YouTube: Tageskontingent der API erreicht, weiter morgen.")
            return
        except Exception as e:
            db.execute("UPDATE parts SET yt_error=? WHERE id=?", (str(e)[:500], p["id"]))
            log(f"YouTube-Fehler: {e}")
            return


def _tiktok_tick():
    if not tiktok.TOKEN_FILE.exists():
        return
    now = datetime.now(TZ)
    due = db.query("SELECT * FROM parts WHERE scheduled_date IS NOT NULL AND tiktok_publish_id IS NULL "
                   "AND scheduled_date <= ? ORDER BY scheduled_date, idx", (now.date().isoformat(),))
    for p in due:
        if _post_dt(date.fromisoformat(p["scheduled_date"])) > now:
            continue
        try:
            pub = tiktok.send_draft(p["video_path"])
            db.execute("UPDATE parts SET tiktok_publish_id=?, tiktok_error=NULL WHERE id=?", (pub, p["id"]))
            log(f"TikTok: {p['data']['yt_title']} als Entwurf gesendet – jetzt in der TikTok-App posten!")
        except Exception as e:
            db.execute("UPDATE parts SET tiktok_error=? WHERE id=?", (str(e)[:500], p["id"]))
            log(f"TikTok-Fehler: {e}")
            return


def _finish_series():
    for s in db.query("SELECT id FROM series WHERE status='freigegeben'"):
        open_ = db.one("SELECT COUNT(*) AS n FROM parts WHERE series_id=? AND (yt_video_id IS NULL OR tiktok_publish_id IS NULL)",
                       (s["id"],))
        if open_["n"] == 0:
            db.execute("UPDATE series SET status='fertig' WHERE id=?", (s["id"],))


def loop():
    while True:
        try:
            _youtube_tick()
            _tiktok_tick()
            _finish_series()
        except Exception:
            traceback.print_exc()
        _wake.wait(300)
        _wake.clear()


def start():
    threading.Thread(target=loop, daemon=True).start()


def run_now():
    _wake.set()
