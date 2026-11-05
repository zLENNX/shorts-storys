# YouTube verbinden (ca. 15 Minuten, einmalig)

1. Öffne https://console.cloud.google.com/ und melde dich mit dem Google-Konto deines YouTube-Kanals an.
2. Oben **Projekt auswählen → Neues Projekt** → Name z. B. `story-shorts` → Erstellen.
3. **APIs & Dienste → Bibliothek** → nach **YouTube Data API v3** suchen → **Aktivieren**.
4. **APIs & Dienste → OAuth-Zustimmungsbildschirm** (bzw. „Google Auth Platform“):
   - Nutzertyp **Extern**, App-Name `Story Shorts`, deine E-Mail eintragen.
   - Unter **Testnutzer / Zielgruppe** deine eigene Google-Mail hinzufügen.
5. **APIs & Dienste → Anmeldedaten → Anmeldedaten erstellen → OAuth-Client-ID**:
   - Anwendungstyp: **Webanwendung**
   - Autorisierte Weiterleitungs-URI: `http://localhost:8000/auth/youtube/callback`
   - Erstellen → **JSON herunterladen**.
6. Die Datei in den Projektordner legen und in **`client_secret.json`** umbenennen.
7. App starten → **Einstellungen → Mit YouTube verbinden** → Konto wählen → Warnung „Google hat diese App nicht überprüft“ → *Erweitert → Weiter* (es ist deine eigene App) → Zugriff erlauben.

## Wichtig: Videos bleiben zuerst privat
Google sperrt Uploads von **ungeprüften** API-Projekten auf „privat“ – auch geplante Videos werden
dann nicht automatisch öffentlich. Damit die geplante Veröffentlichung funktioniert:

- Beantrage die Prüfung über das **YouTube API Services – Audit and Quota Extension Form**:
  https://support.google.com/youtube/contact/yt_api_form
  (Zweck angeben: „Upload eigener Videos auf den eigenen Kanal mit geplanter Veröffentlichung“.)
- Bis dahin: Videos im YouTube Studio manuell auf „Öffentlich“ bzw. „Planen“ stellen – sie sind schon hochgeladen.

## Kontingent
Die API erlaubt ca. 6 Uploads pro Tag. Die App lädt höchstens `YT_MAX_UPLOADS_PER_DAY` (Standard 5)
pro Tag hoch und macht am nächsten Tag weiter – bei einem Teil pro Tag reicht das locker.
