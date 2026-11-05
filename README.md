# 📖 Story Shorts

Lokale App für **Storytelling-Serien als Shorts** (TikTok & YouTube Shorts):
Claude schreibt fesselnde Mehrteiler, die App vertont sie, schneidet passende Clips darunter,
setzt Untertitel Wort für Wort – du prüfst alles und klickst auf **Freigeben**.
Danach erscheint **jeden Tag ein Teil** (Standard 18:00 Uhr).

```
Ideen (mit Hook-Score) → Serie schreiben → Clips + Stimme + Musik + Untertitel → Review → Freigeben
                                                                                    ↓
                                           YouTube: automatisch geplant · TikTok: Entwurf in deiner App
```

## Schnellstart (Windows)

1. **Python 3.11+** installieren: https://www.python.org/downloads/ (Haken bei *Add python.exe to PATH*).
2. **FFmpeg** installieren – Eingabeaufforderung öffnen und eingeben:
   ```
   winget install Gyan.FFmpeg
   ```
3. Diesen Ordner herunterladen (GitHub → *Code* → *Download ZIP*, oder `git clone`).
4. **`start.bat`** doppelklicken. Beim ersten Start öffnet sich `.env` im Editor:
   - `ANTHROPIC_API_KEY` – von https://console.anthropic.com (Pflicht, ca. 10–30 Cent pro Serie)
   - `PEXELS_API_KEY` und/oder `PIXABAY_API_KEY` – kostenlos, für die Hintergrundvideos
5. Speichern, Editor schließen. Der Browser öffnet http://localhost:8000.
6. Konten verbinden: **Einstellungen** → siehe [docs/YOUTUBE.md](docs/YOUTUBE.md) und [docs/TIKTOK.md](docs/TIKTOK.md).
7. Musik in die Ordner unter `music/` legen → [docs/MUSIK.md](docs/MUSIK.md).

> Das Fenster von `start.bat` muss offen bleiben, solange die App läuft. TikTok-Entwürfe werden nur
> verschickt, wenn die App läuft – YouTube-Videos werden vorab hochgeladen und erscheinen auch bei
> ausgeschaltetem PC.

## So benutzt du die App

| Tab | Was passiert |
|---|---|
| **Ideen** | „Ideen erzeugen“ → Claude liefert 5–10 Ideen mit Hook-Score (1–10). „Serie erstellen“ bei der besten. Optional einen Wunsch eintragen. |
| **Serien** | Die Serie wird geschrieben (1–2 Min.) und alle Teile gerendert. Du kannst pro Teil Text, Titel, Beschreibung, Hashtags ändern, einzelne Szenen-Clips tauschen (🔀), den Teil neu vertonen oder komplett neu schreiben lassen. Stimme und Tempo wählst du oben. Passt alles: **✅ Serie freigeben**. |
| **Plan** | Welcher Teil an welchem Tag kommt, YouTube- und TikTok-Status. „📋 TikTok-Text“ kopiert Titel + Hashtags für die TikTok-App. |
| **Einstellungen** | Konten verbinden, Systemcheck. |

### Eigene Clips (z. B. Gameplay)
Lege Videos in `library/`. Dateiname und Ordnername dienen als Suchbegriffe
(z. B. `library/minecraft/parkour_nacht.mp4`). Optional daneben eine Textdatei mit gleichem Namen:
```
tags: forest, night, dark, wald
quelle: Eigene Aufnahme
```
Passende eigene Clips werden vor Stock-Videos bevorzugt. Nur Material verwenden, an dem du die Rechte hast!

### Stimmen
- Standard: **Edge-TTS** (Microsoft-Neural-Stimmen, kostenlos, inoffizieller Zugang – kann sich jederzeit ändern).
- Ersatz: **Piper** (läuft lokal, offiziell frei nutzbar). Einrichtung:
  1. Piper für Windows laden: https://github.com/rhasspy/piper/releases (`piper_windows_amd64.zip`), entpacken z. B. nach `C:\piper`.
  2. Deutsche Stimme laden (`.onnx` + `.onnx.json`), z. B. *thorsten high*: https://huggingface.co/rhasspy/piper-voices/tree/main/de/de_DE/thorsten/high
  3. In `.env`: `PIPER_EXE=C:\piper\piper.exe` und `PIPER_MODEL=C:\piper\de_DE-thorsten-high.onnx`
  Fällt Edge-TTS aus, nimmt die App automatisch Piper. In der Serie kannst du auch direkt „Piper“ wählen.

## Regeln, die die App einhält (schützt deine Accounts)
- Keine fremden Videos von YouTube & Co. – nur Stock-Videos (Pexels/Pixabay) und deine eigenen Clips, mit Quellenangabe in der Beschreibung.
- Stories sind original von Claude geschrieben; erfundene Geschichten werden als **„Fiktive Geschichte“** markiert (im Video und in der Beschreibung).
- True Crime: keine echten Namen von Opfern, keine erfundenen „Fakten“.
- YouTube-Uploads werden als KI-Inhalt gekennzeichnet (KI-Stimme).
- Bei TikTok bitte beim Posten in der App die Option **„KI-generierte Inhalte“** aktivieren.

## Kosten
- Claude-API: je nach Modell ca. 10–30 Cent pro Serie (mit `CLAUDE_MODEL=claude-sonnet-5-5` günstiger).
- Alles andere kostenlos.

## Technik
Python (FastAPI) + FFmpeg, Oberfläche im Browser, Daten in `data/` (SQLite, Videos in `data/output/`).
Start manuell: `python -m app.main`.
