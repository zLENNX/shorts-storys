"""Story-Ideen und Serien-Skripte mit der Claude-API erzeugen."""
import json

import anthropic

from . import config

SYSTEM = """Du bist Autor und Showrunner für deutschsprachige Storytelling-Shorts (TikTok, YouTube Shorts).
Deine Serien bestehen aus mehreren Teilen à 60–90 Sekunden gesprochenem Text (ca. 150–220 Wörter pro Teil).

Regeln:
- Fesselnd: Der erste Satz jedes Teils ist ein Hook, der zum Weiterschauen zwingt. Jeder Teil außer dem letzten endet mit einem echten Cliffhanger. Der letzte Teil löst auf.
- Ab Teil 2 beginnt der Teil mit einem Rückblick von höchstens 2 kurzen Sätzen ("Was bisher geschah: ...").
- Gesprochene Sprache: kurze Sätze, keine Klammern, keine Emojis, keine Regieanweisungen, Zahlen ausgeschrieben, wenn es beim Vorlesen hilft.
- Inhalte sind originell. Kopiere niemals fremde Texte, Reddit-Posts, Creepypastas oder Bücher wörtlich. Gemeinfreie Stoffe darfst du frei nacherzählen.
- Erfundene Geschichten werden als Fiktion markiert (is_fiction = true).
- True Crime und historische Ereignisse: nur gesicherte Fakten, keine erfundenen Details als Tatsache. Nenne keine echten Namen von Opfern oder nicht verurteilten Personen, anonymisiere sie (z. B. "eine 34-jährige Frau"). Kein voyeuristisches Ausschlachten von Gewalt.
- Keine Inhalte, die gegen die Community-Richtlinien von TikTok oder YouTube verstoßen (keine expliziten Gewaltdetails, keine Selbstverletzungsanleitungen, nichts Sexuelles mit Minderjährigen, keine Hetze).
"""

IDEA_SCHEMA = {
    "type": "object",
    "properties": {
        "ideas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "genre": {"type": "string", "description": "z. B. Mystery, Horror, True Crime, Historisch, Alltagsdrama"},
                    "pitch": {"type": "string", "description": "Ein Satz"},
                    "hook": {"type": "string", "description": "Der erste Satz von Teil 1"},
                    "cliffhanger_plan": {"type": "string", "description": "Wie die Teile jeweils enden"},
                    "parts_count": {"type": "integer", "description": "3 bis 6"},
                    "hook_score": {"type": "integer", "description": "1 bis 10, ehrliche Einschätzung"},
                    "is_fiction": {"type": "boolean"},
                },
                "required": ["title", "genre", "pitch", "hook", "cliffhanger_plan", "parts_count", "hook_score", "is_fiction"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["ideas"],
    "additionalProperties": False,
}

PART_PROPS = {
    "part_title": {"type": "string"},
    "scenes": {
        "type": "array",
        "description": "Der komplette Sprechtext des Teils, aufgeteilt in Szenen von je 1–2 Sätzen (ca. 4–6 Sekunden). Aneinandergereiht ergeben die Szenentexte exakt den Sprechtext.",
        "items": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "2–4 ENGLISCHE Suchbegriffe für Stock-Videos (Pexels), visuell und konkret, z. B. 'foggy forest night'. Keine Personen-Namen.",
                },
            },
            "required": ["text", "keywords"],
            "additionalProperties": False,
        },
    },
    "yt_title": {"type": "string", "description": "Max. 80 Zeichen, mit 'Teil X/Y', neugierig machend, kein Clickbait-Lügen"},
    "description": {"type": "string", "description": "2–3 Sätze, deutsch"},
    "hashtags": {"type": "array", "items": {"type": "string"}, "description": "5–8 Hashtags ohne #"},
}
PART_SCHEMA = {
    "type": "object",
    "properties": PART_PROPS,
    "required": list(PART_PROPS),
    "additionalProperties": False,
}

SERIES_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "genre": {"type": "string"},
        "mood": {"type": "string", "enum": config.MOODS},
        "is_fiction": {"type": "boolean"},
        "playlist_title": {"type": "string"},
        "parts": {"type": "array", "items": PART_SCHEMA},
    },
    "required": ["title", "genre", "mood", "is_fiction", "playlist_title", "parts"],
    "additionalProperties": False,
}


class StoryError(Exception):
    pass


def _client() -> anthropic.Anthropic:
    if not config.ANTHROPIC_API_KEY:
        raise StoryError("ANTHROPIC_API_KEY fehlt in der .env-Datei.")
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


def _ask(prompt: str, schema: dict, effort: str, max_tokens: int = 32000) -> dict:
    client = _client()
    try:
        with client.beta.messages.stream(
            model=config.CLAUDE_MODEL,
            max_tokens=max_tokens,
            system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            # Falls eine Anfrage abgelehnt wird, versucht die API automatisch ein passendes anderes Modell.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            msg = stream.get_final_message()
    except anthropic.AuthenticationError:
        raise StoryError("Claude-API-Key ungültig. Prüfe ANTHROPIC_API_KEY in der .env.")
    except anthropic.RateLimitError:
        raise StoryError("Claude-API: Limit erreicht, bitte kurz warten.")
    except anthropic.APIStatusError as e:
        raise StoryError(f"Claude-API-Fehler {e.status_code}: {e.message}")
    except anthropic.APIConnectionError:
        raise StoryError("Keine Verbindung zur Claude-API.")

    if msg.stop_reason == "refusal":
        raise StoryError("Claude hat diese Anfrage abgelehnt. Versuche ein anderes Thema.")
    if msg.stop_reason == "max_tokens":
        raise StoryError("Antwort war zu lang und wurde abgeschnitten. Bitte erneut versuchen.")
    text = next((b.text for b in msg.content if b.type == "text"), None)
    if not text:
        raise StoryError("Leere Antwort von Claude.")
    return json.loads(text)


def generate_ideas(count: int = 8, genres: str = "", avoid: list[str] | None = None) -> list[dict]:
    prompt = (
        f"Erzeuge {count} unterschiedliche Ideen für Storytelling-Serien.\n"
        f"Genres: {genres or 'gemischt aus Mystery, Horror, True Crime, unglaubliche historische Ereignisse, Alltagsdrama'}.\n"
        "Bewerte jede Idee ehrlich mit hook_score (1–10): Wie stark zieht sie in den ersten 3 Sekunden "
        "und wie sehr will man Teil 2 sehen? Sortiere absteigend nach hook_score."
    )
    if avoid:
        prompt += "\nDiese Titel gab es schon, wiederhole sie nicht: " + "; ".join(avoid[-60:])
    return _ask(prompt, IDEA_SCHEMA, effort="medium")["ideas"]


def generate_series(idea: dict, wish: str = "") -> dict:
    n = max(3, min(6, int(idea.get("parts_count", 4))))
    prompt = (
        "Schreibe die komplette Serie zu dieser Idee:\n"
        + json.dumps(idea, ensure_ascii=False, indent=2)
        + f"\n\nGenau {n} Teile. Jeder Teil 150–220 Wörter Sprechtext. Titel mit 'Teil X/{n}'."
    )
    if wish:
        prompt += f"\nZusätzlicher Wunsch: {wish}"
    data = _ask(prompt, SERIES_SCHEMA, effort="high")
    if not data.get("parts"):
        raise StoryError("Claude hat keine Teile geliefert.")
    return data


def regenerate_part(series: dict, idx: int, wish: str = "") -> dict:
    total = len(series["parts"])
    others = [
        {"teil": i + 1, "text": " ".join(s["text"] for s in p["scenes"])}
        for i, p in enumerate(series["parts"])
    ]
    prompt = (
        f"Serie: {series['title']} ({series['genre']}). Fiktion: {series['is_fiction']}.\n"
        f"Alle Teile bisher:\n{json.dumps(others, ensure_ascii=False, indent=1)}\n\n"
        f"Schreibe Teil {idx + 1}/{total} komplett neu, passend zu den anderen Teilen. "
        f"{'Er muss mit einem Cliffhanger enden.' if idx + 1 < total else 'Er ist das Finale und löst auf.'}"
    )
    if wish:
        prompt += f"\nWunsch: {wish}"
    return _ask(prompt, PART_SCHEMA, effort="high", max_tokens=16000)
