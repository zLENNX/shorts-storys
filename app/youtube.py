"""YouTube: Konto verbinden (OAuth), Shorts hochladen und zeitgesteuert veröffentlichen, Playlists."""
import json
import os
from datetime import datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from . import config

# OAuth über http://localhost erlauben (nur lokal)
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube"]
REDIRECT = f"{config.BASE_URL}/auth/youtube/callback"
TOKEN_FILE = config.TOKENS / "youtube.json"
_flows: dict[str, Flow] = {}


class QuotaExceeded(Exception):
    pass


def configured() -> bool:
    return config.GOOGLE_CLIENT_SECRET_FILE.exists()


def auth_url() -> str:
    flow = Flow.from_client_secrets_file(str(config.GOOGLE_CLIENT_SECRET_FILE), scopes=SCOPES, redirect_uri=REDIRECT)
    url, state = flow.authorization_url(access_type="offline", prompt="consent", include_granted_scopes="true")
    _flows[state] = flow
    return url


def finish_auth(full_url: str, state: str):
    flow = _flows.pop(state, None)
    if not flow:
        raise RuntimeError("Anmeldung abgelaufen, bitte erneut auf 'Verbinden' klicken.")
    flow.fetch_token(authorization_response=full_url)
    TOKEN_FILE.write_text(flow.credentials.to_json(), encoding="utf-8")


def _creds() -> Credentials | None:
    if not TOKEN_FILE.exists():
        return None
    creds = Credentials.from_authorized_user_info(json.loads(TOKEN_FILE.read_text(encoding="utf-8")), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _api():
    creds = _creds()
    if not creds:
        raise RuntimeError("YouTube ist nicht verbunden.")
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def status() -> dict:
    if not configured():
        return {"connected": False, "info": "client_secret.json fehlt (siehe docs/YOUTUBE.md)"}
    if not TOKEN_FILE.exists():
        return {"connected": False, "info": "nicht verbunden"}
    try:
        r = _api().channels().list(part="snippet", mine=True).execute()
        name = r["items"][0]["snippet"]["title"] if r.get("items") else "(kein Kanal)"
        return {"connected": True, "info": name}
    except Exception as e:
        return {"connected": False, "info": f"Fehler: {e}"}


def disconnect():
    TOKEN_FILE.unlink(missing_ok=True)


def _call(req):
    try:
        return req.execute()
    except HttpError as e:
        if e.resp.status == 403 and b"quota" in (e.content or b"").lower():
            raise QuotaExceeded()
        raise


def create_playlist(title: str, description: str) -> str:
    r = _call(_api().playlists().insert(part="snippet,status", body={
        "snippet": {"title": title[:150], "description": description[:5000], "defaultLanguage": "de"},
        "status": {"privacyStatus": "public"},
    }))
    return r["id"]


def add_to_playlist(playlist_id: str, video_id: str):
    _call(_api().playlistItems().insert(part="snippet", body={
        "snippet": {"playlistId": playlist_id, "resourceId": {"kind": "youtube#video", "videoId": video_id}}
    }))


def upload(path: str, title: str, description: str, tags: list[str], publish_at: datetime) -> str:
    body = {
        "snippet": {
            "title": title[:100], "description": description[:5000], "tags": tags[:15],
            "categoryId": "24", "defaultLanguage": "de", "defaultAudioLanguage": "de",
        },
        "status": {
            # 'private' + publishAt = geplante Veröffentlichung
            "privacyStatus": "private",
            "publishAt": publish_at.astimezone().isoformat(),
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,  # KI-Stimme → Kennzeichnung
        },
    }
    media = MediaFileUpload(path, mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    req = _api().videos().insert(part="snippet,status", body=body, media_body=media)
    try:
        resp = None
        while resp is None:
            _, resp = req.next_chunk()
    except HttpError as e:
        if e.resp.status == 403 and b"quota" in (e.content or b"").lower():
            raise QuotaExceeded()
        raise
    return resp["id"]
