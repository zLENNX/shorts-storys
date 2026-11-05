"""Zentrale Einstellungen. Werte kommen aus der Datei .env im Projektordner."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA = ROOT / "data"
CACHE = DATA / "cache"
OUTPUT = DATA / "output"
TOKENS = DATA / "tokens"
LIBRARY = ROOT / "library"
MUSIC = ROOT / "music"
for p in (DATA, CACHE, CACHE / "clips", OUTPUT, TOKENS, LIBRARY, MUSIC):
    p.mkdir(parents=True, exist_ok=True)

PORT = int(os.getenv("PORT", "8000"))
BASE_URL = f"http://localhost:{PORT}"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")

TIKTOK_CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY", "")
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET", "")

GOOGLE_CLIENT_SECRET_FILE = ROOT / os.getenv("GOOGLE_CLIENT_SECRET_FILE", "client_secret.json")

POST_TIME = os.getenv("POST_TIME", "18:00")  # HH:MM, lokale Zeit
TIMEZONE = os.getenv("TIMEZONE", "Europe/Berlin")
YT_MAX_UPLOADS_PER_DAY = int(os.getenv("YT_MAX_UPLOADS_PER_DAY", "5"))

DEFAULT_VOICE = os.getenv("DEFAULT_VOICE", "de-DE-ConradNeural")
DEFAULT_RATE = os.getenv("DEFAULT_RATE", "+8%")
PIPER_EXE = os.getenv("PIPER_EXE", "")
PIPER_MODEL = os.getenv("PIPER_MODEL", "")

SUB_FONT = os.getenv("SUB_FONT", "Arial Black")
MUSIC_VOLUME = float(os.getenv("MUSIC_VOLUME", "0.12"))

VOICES = [
    ("de-DE-ConradNeural", "Conrad (männlich, ruhig)"),
    ("de-DE-KillianNeural", "Killian (männlich, jung)"),
    ("de-DE-FlorianMultilingualNeural", "Florian (männlich, erzählend)"),
    ("de-DE-KatjaNeural", "Katja (weiblich, klar)"),
    ("de-DE-AmalaNeural", "Amala (weiblich, warm)"),
    ("de-DE-SeraphinaMultilingualNeural", "Seraphina (weiblich, erzählend)"),
    ("piper", "Piper (lokal, Ersatzstimme)"),
]

MOODS = ["spannung", "horror", "traurig", "ruhig", "episch"]
