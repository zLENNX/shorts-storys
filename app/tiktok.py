"""TikTok: Konto verbinden (Login Kit, Desktop-Variante mit PKCE) und Videos als Entwurf
in die TikTok-Inbox schicken (Content Posting API, Scope video.upload)."""
import hashlib
import json
import secrets
import time
import urllib.parse
from pathlib import Path

import httpx

from . import config

AUTH = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN = "https://open.tiktokapis.com/v2/oauth/token/"
API = "https://open.tiktokapis.com/v2"
REDIRECT = f"{config.BASE_URL}/auth/tiktok/callback"
SCOPES = "user.info.basic,video.upload"
TOKEN_FILE = config.TOKENS / "tiktok.json"
_pending: dict[str, str] = {}  # state -> code_verifier


def configured() -> bool:
    return bool(config.TIKTOK_CLIENT_KEY and config.TIKTOK_CLIENT_SECRET)


def auth_url() -> str:
    state = secrets.token_urlsafe(16)
    verifier = secrets.token_urlsafe(48)[:64]
    # TikTok (Desktop) erwartet den SHA256-Hash als Hex-String
    challenge = hashlib.sha256(verifier.encode()).hexdigest()
    _pending[state] = verifier
    params = {
        "client_key": config.TIKTOK_CLIENT_KEY, "scope": SCOPES, "response_type": "code",
        "redirect_uri": REDIRECT, "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256",
    }
    return AUTH + "?" + urllib.parse.urlencode(params)


def _save(tok: dict):
    tok["obtained_at"] = int(time.time())
    TOKEN_FILE.write_text(json.dumps(tok), encoding="utf-8")


def finish_auth(code: str, state: str):
    verifier = _pending.pop(state, None)
    if verifier is None:
        raise RuntimeError("Anmeldung abgelaufen, bitte erneut auf 'Verbinden' klicken.")
    r = httpx.post(TOKEN, data={
        "client_key": config.TIKTOK_CLIENT_KEY, "client_secret": config.TIKTOK_CLIENT_SECRET,
        "code": code, "grant_type": "authorization_code", "redirect_uri": REDIRECT, "code_verifier": verifier,
    }, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
    tok = r.json()
    if "access_token" not in tok:
        raise RuntimeError(f"TikTok-Anmeldung fehlgeschlagen: {tok}")
    _save(tok)


def _token() -> str:
    if not TOKEN_FILE.exists():
        raise RuntimeError("TikTok ist nicht verbunden.")
    tok = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    if time.time() > tok["obtained_at"] + tok.get("expires_in", 0) - 300:
        r = httpx.post(TOKEN, data={
            "client_key": config.TIKTOK_CLIENT_KEY, "client_secret": config.TIKTOK_CLIENT_SECRET,
            "grant_type": "refresh_token", "refresh_token": tok["refresh_token"],
        }, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
        new = r.json()
        if "access_token" not in new:
            raise RuntimeError("TikTok-Verbindung abgelaufen, bitte neu verbinden.")
        _save(new)
        tok = new
    return tok["access_token"]


def status() -> dict:
    if not configured():
        return {"connected": False, "info": "TIKTOK_CLIENT_KEY/SECRET fehlen (siehe docs/TIKTOK.md)"}
    if not TOKEN_FILE.exists():
        return {"connected": False, "info": "nicht verbunden"}
    try:
        r = httpx.get(f"{API}/user/info/", params={"fields": "display_name"},
                      headers={"Authorization": f"Bearer {_token()}"}, timeout=30).json()
        return {"connected": True, "info": r.get("data", {}).get("user", {}).get("display_name", "verbunden")}
    except Exception as e:
        return {"connected": False, "info": f"Fehler: {e}"}


def disconnect():
    TOKEN_FILE.unlink(missing_ok=True)


def send_draft(path: str) -> str:
    """Lädt das Video in die TikTok-Inbox. Du bekommst in der TikTok-App eine Benachrichtigung
    und veröffentlichst dort mit einem Tipp (Text/Hashtags kannst du dort einfügen)."""
    size = Path(path).stat().st_size
    chunk = size if size <= 64 * 1024 * 1024 else 10 * 1024 * 1024
    count = 1 if chunk == size else size // chunk  # letzter Chunk nimmt den Rest auf
    headers = {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json; charset=UTF-8"}
    r = httpx.post(f"{API}/post/publish/inbox/video/init/", headers=headers, timeout=60, json={
        "source_info": {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": chunk, "total_chunk_count": count}
    }).json()
    if r.get("error", {}).get("code") not in (None, "ok"):
        raise RuntimeError(f"TikTok: {r['error']}")
    upload_url, publish_id = r["data"]["upload_url"], r["data"]["publish_id"]
    with open(path, "rb") as f:
        for i in range(count):
            start = i * chunk
            length = chunk if i < count - 1 else size - start
            f.seek(start)
            data = f.read(length)
            up = httpx.put(upload_url, content=data, timeout=300, headers={
                "Content-Type": "video/mp4", "Content-Length": str(length),
                "Content-Range": f"bytes {start}-{start + length - 1}/{size}",
            })
            if up.status_code not in (200, 201, 206):
                raise RuntimeError(f"TikTok-Upload fehlgeschlagen ({up.status_code}): {up.text[:300]}")
    return publish_id
