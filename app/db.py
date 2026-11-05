"""Kleine SQLite-Datenbank für Ideen, Serien und Teile."""
import json
import sqlite3
import threading
from datetime import datetime

from .config import DATA

_lock = threading.Lock()
_conn = sqlite3.connect(DATA / "app.db", check_same_thread=False)
_conn.row_factory = sqlite3.Row

_conn.executescript(
    """
CREATE TABLE IF NOT EXISTS ideas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT NOT NULL,
    used INTEGER DEFAULT 0,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS series (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT NOT NULL,
    voice TEXT,
    rate TEXT,
    status TEXT DEFAULT 'entwurf',  -- entwurf | rendert | bereit | freigegeben | fertig | fehler
    yt_playlist_id TEXT,
    error TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS parts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id INTEGER NOT NULL,
    idx INTEGER NOT NULL,
    data TEXT NOT NULL,
    video_path TEXT,
    status TEXT DEFAULT 'offen',     -- offen | rendert | gerendert | fehler
    error TEXT,
    scheduled_date TEXT,             -- YYYY-MM-DD
    yt_video_id TEXT,
    yt_error TEXT,
    tiktok_publish_id TEXT,
    tiktok_error TEXT
);
"""
)
_conn.commit()


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def execute(sql: str, params=()) -> int:
    with _lock:
        cur = _conn.execute(sql, params)
        _conn.commit()
        return cur.lastrowid


def query(sql: str, params=()) -> list[dict]:
    with _lock:
        rows = _conn.execute(sql, params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if "data" in d and isinstance(d["data"], str):
            d["data"] = json.loads(d["data"])
        out.append(d)
    return out


def one(sql: str, params=()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)
