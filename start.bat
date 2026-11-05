@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Story Shorts

where python >nul 2>nul
if errorlevel 1 (
  echo [FEHLER] Python ist nicht installiert. Installiere Python 3.11+ von https://www.python.org/downloads/
  echo          Beim Installieren "Add python.exe to PATH" anhaken!
  pause
  exit /b 1
)

where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo [FEHLER] FFmpeg fehlt. Installiere es mit:  winget install Gyan.FFmpeg
  echo          Danach dieses Fenster schliessen und start.bat erneut starten.
  pause
  exit /b 1
)

if not exist ".venv" (
  echo Erster Start: richte Python-Umgebung ein ...
  python -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install -q --upgrade pip >nul
python -m pip install -q -r requirements.txt

if not exist ".env" (
  copy .env.example .env >nul
  echo.
  echo Die Datei .env wurde angelegt. Trage dort deine Schluessel ein ^(mindestens ANTHROPIC_API_KEY^).
  notepad .env
)

echo.
echo Story Shorts laeuft auf http://localhost:8000  (Fenster offen lassen!)
python -m app.main
pause
