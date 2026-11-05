"""Hintergrund-Clips: eigene Bibliothek (Ordner library/) und Stock-Videos von Pexels/Pixabay."""
import hashlib
import random
import re
from pathlib import Path

import httpx

from . import config

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm"}


def _words(s: str) -> set[str]:
    return {w for w in re.split(r"[^a-z0-9äöüß]+", s.lower()) if len(w) > 2}


def library_clips() -> list[dict]:
    """Eigene Clips. Optional daneben eine gleichnamige .txt mit
    'tags: wald, nacht, nebel' und 'quelle: Name / Link'."""
    clips = []
    for p in sorted(config.LIBRARY.rglob("*")):
        if p.suffix.lower() not in VIDEO_EXT:
            continue
        tags, credit = _words(p.stem) | _words(p.parent.name), ""
        side = p.with_suffix(".txt")
        if side.exists():
            for line in side.read_text(encoding="utf-8", errors="ignore").splitlines():
                key, _, val = line.partition(":")
                if key.strip().lower() == "tags":
                    tags |= _words(val)
                elif key.strip().lower() == "quelle":
                    credit = val.strip()
        clips.append({"source": "eigene", "id": str(p.relative_to(config.LIBRARY)), "path": str(p),
                      "tags": sorted(tags), "credit": credit})
    return clips


def _pexels(query: str) -> list[dict]:
    if not config.PEXELS_API_KEY:
        return []
    r = httpx.get(
        "https://api.pexels.com/videos/search",
        params={"query": query, "orientation": "portrait", "per_page": 12, "size": "medium"},
        headers={"Authorization": config.PEXELS_API_KEY}, timeout=30,
    )
    r.raise_for_status()
    out = []
    for v in r.json().get("videos", []):
        files = [f for f in v.get("video_files", []) if f.get("link") and f.get("height")]
        if not files:
            continue
        # Datei nahe 1920 px Höhe bevorzugen, aber nicht riesig
        files.sort(key=lambda f: abs(f["height"] - 1920))
        out.append({"source": "pexels", "id": f"pexels-{v['id']}", "url": files[0]["link"],
                    "duration": v.get("duration", 0),
                    "credit": f"{v.get('user', {}).get('name', 'Pexels')} (Pexels)"})
    return out


def _pixabay(query: str) -> list[dict]:
    if not config.PIXABAY_API_KEY:
        return []
    r = httpx.get("https://pixabay.com/api/videos/",
                  params={"key": config.PIXABAY_API_KEY, "q": query, "per_page": 12, "safesearch": "true"},
                  timeout=30)
    r.raise_for_status()
    out = []
    for h in r.json().get("hits", []):
        vids = h.get("videos", {})
        v = vids.get("large") or vids.get("medium") or {}
        if not v.get("url"):
            continue
        out.append({"source": "pixabay", "id": f"pixabay-{h['id']}", "url": v["url"],
                    "duration": h.get("duration", 0), "credit": f"{h.get('user', 'Pixabay')} (Pixabay)"})
    return out


def _download(clip: dict) -> str:
    name = hashlib.sha1(clip["id"].encode()).hexdigest()[:16] + ".mp4"
    dest = config.CACHE / "clips" / name
    if not dest.exists():
        tmp = dest.with_suffix(".part")
        with httpx.stream("GET", clip["url"], timeout=120, follow_redirects=True) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_bytes(1 << 16):
                    f.write(chunk)
        tmp.replace(dest)
    return str(dest)


def find_clip(keywords: list[str], exclude: set[str]) -> dict | None:
    """Sucht einen passenden Clip. Eigene Clips mit passenden Tags werden bevorzugt."""
    kw = set()
    for k in keywords:
        kw |= _words(k)
    own = [c for c in library_clips() if c["id"] not in exclude]
    scored = sorted(((len(kw & set(c["tags"])), c) for c in own), key=lambda x: -x[0])
    if scored and scored[0][0] > 0:
        best = [c for s, c in scored if s == scored[0][0]]
        return random.choice(best)

    queries = [" ".join(keywords[:2])] + list(keywords)
    for q in queries:
        if not q.strip():
            continue
        candidates = []
        for fn in (_pexels, _pixabay):
            try:
                candidates += fn(q)
            except httpx.HTTPError:
                pass
        candidates = [c for c in candidates if c["id"] not in exclude and (c.get("duration") or 99) >= 3]
        if candidates:
            clip = random.choice(candidates[:6])
            clip["path"] = _download(clip)
            return clip

    # Notlösung: irgendein eigener Clip
    if own:
        return random.choice(own)
    return None


def pick_music(mood: str) -> str | None:
    folder = config.MUSIC / mood
    files = [p for p in folder.glob("*") if p.suffix.lower() in {".mp3", ".wav", ".m4a", ".ogg"}] if folder.exists() else []
    if not files:
        files = [p for p in config.MUSIC.rglob("*") if p.suffix.lower() in {".mp3", ".wav", ".m4a", ".ogg"}]
    return str(random.choice(files)) if files else None
