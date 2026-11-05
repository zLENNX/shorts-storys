"""Sprachausgabe: Edge-TTS (Standard) mit Wort-Zeitstempeln, Piper als lokaler Ersatz."""
import asyncio
import json
import subprocess
import wave
from pathlib import Path

import edge_tts

from . import config


class TTSError(Exception):
    pass


async def _edge(text: str, voice: str, rate: str, out_mp3: Path) -> list[dict]:
    comm = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    words = []
    with open(out_mp3, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                # offset/duration in 100-ns-Einheiten
                words.append({
                    "word": chunk["text"],
                    "start": chunk["offset"] / 1e7,
                    "end": (chunk["offset"] + chunk["duration"]) / 1e7,
                })
    return words


def _audio_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(json.loads(out)["format"]["duration"])


def _piper(text: str, out_wav: Path) -> list[dict]:
    if not (config.PIPER_EXE and config.PIPER_MODEL):
        raise TTSError("Piper ist nicht eingerichtet (PIPER_EXE / PIPER_MODEL in .env).")
    subprocess.run(
        [config.PIPER_EXE, "--model", config.PIPER_MODEL, "--output_file", str(out_wav)],
        input=text.encode("utf-8"), check=True, capture_output=True,
    )
    with wave.open(str(out_wav)) as w:
        dur = w.getnframes() / w.getframerate()
    return estimate_words(text, dur)


def estimate_words(text: str, duration: float) -> list[dict]:
    """Ohne echte Zeitstempel: Wortzeiten anhand der Wortlänge schätzen."""
    tokens = text.split()
    weights = [len(t) + 2 for t in tokens]
    total = sum(weights) or 1
    t, words = 0.0, []
    for tok, wgt in zip(tokens, weights):
        d = duration * wgt / total
        words.append({"word": tok.strip(",.!?;:\"'„“…"), "start": t, "end": t + d})
        t += d
    return words


def synthesize(text: str, voice: str, rate: str, out_base: Path) -> tuple[Path, list[dict]]:
    """Erzeugt die Audiodatei und gibt (pfad, wortliste) zurück."""
    if voice != "piper":
        out = out_base.with_suffix(".mp3")
        try:
            words = asyncio.run(_edge(text, voice, rate, out))
            if out.exists() and out.stat().st_size > 0:
                if not words:
                    words = estimate_words(text, _audio_duration(out))
                return out, words
        except Exception as e:  # Edge-TTS nicht erreichbar → Piper versuchen
            if not (config.PIPER_EXE and config.PIPER_MODEL):
                raise TTSError(f"Edge-TTS fehlgeschlagen ({e}) und Piper ist nicht eingerichtet.")
    out = out_base.with_suffix(".wav")
    return out, _piper(text, out)


def audio_duration(path: Path) -> float:
    return _audio_duration(path)
