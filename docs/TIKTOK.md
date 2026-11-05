# TikTok verbinden (ca. 20–30 Minuten, einmalig)

Die App nutzt die offizielle **Content Posting API** im Modus **„Upload“**: Das Video landet als
Entwurf in deiner TikTok-App (Benachrichtigung in der Inbox). Dort fügst du den Text ein
(in der App: Plan → „📋 TikTok-Text“), aktivierst „KI-generierte Inhalte“ und tippst auf **Posten**.

1. Öffne https://developers.tiktok.com/ und melde dich mit deinem TikTok-Konto an.
2. **Manage apps → Connect an app** → Name z. B. `Story Shorts`.
3. In der App-Konfiguration:
   - **Platform:** *Desktop* auswählen.
   - **Products hinzufügen:** *Login Kit* und *Content Posting API*.
   - Bei *Login Kit* als **Redirect URI** eintragen: `http://localhost:8000/auth/tiktok/callback`
   - **Scopes:** `user.info.basic` und `video.upload`.
   - Beschreibung/Icon/Datenschutz-Links ausfüllen (für den Sandbox-Modus reichen einfache Angaben).
4. Oben auf **Sandbox** wechseln und unter **Target users** dein eigenes TikTok-Konto hinzufügen.
   So funktioniert alles sofort für dich, ohne Prüfung durch TikTok.
5. **Client key** und **Client secret** kopieren und in `.env` eintragen:
   ```
   TIKTOK_CLIENT_KEY=...
   TIKTOK_CLIENT_SECRET=...
   ```
6. App neu starten (`start.bat`) → **Einstellungen → Mit TikTok verbinden** → erlauben.

## Später: komplett automatisch posten
Für direktes Veröffentlichen ohne Tippen braucht es den Scope `video.publish` und ein
**App-Review/Audit** durch TikTok. Ohne Audit sind direkt gepostete Videos nur privat sichtbar –
deshalb nutzt die App vorerst den Entwurfs-Modus.

## Wenn die Anmeldung scheitert
- Fehlermeldung zur Redirect-URI: Die URI muss **exakt** `http://localhost:8000/auth/tiktok/callback` lauten.
- Fehler zu `code_challenge`: Prüfe, dass als Plattform *Desktop* gewählt ist.
- TikTok ändert seine Developer-Oberfläche öfter – die Begriffe können leicht abweichen.
