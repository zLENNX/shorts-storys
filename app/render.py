"""Videoschnitt mit FFmpeg: Szenen-Clips, Stimme, Musik, Untertitel Wort für Wort, 'Teil X/Y'."""
import re
import subprocess
from pathlib import Path

from . import config

W, H, FPS = 1080, 1920, 30


class RenderError(Exception):
    pass


def _run(args: list[str], cwd: Path | None = None):
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    if p.returncode != 0:
        raise RenderError("FFmpeg-Fehler:\n" + p.stderr[-1500:])


def probe_duration(path: str) -> float:
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", path], capture_output=True, text=True)
    try:
        return float(p.stdout.strip())
    except ValueError:
        return 0.0


def _norm(w: str) -> str:
    return re.sub(r"[^\wäöüß]", "", w.lower())


def scene_timings(scenes: list[dict], words: list[dict], total: float) -> list[tuple[float, float]]:
    """Ordnet jeder Szene Start/Ende zu, anhand der Wort-Zeitstempel der Stimme."""
    counts = [len([w for w in s["text"].split() if _norm(w)]) for s in scenes]
    n_text = sum(counts) or 1
    n_audio = len(words)
    bounds, acc = [], 0
    for c in counts:
        i = min(int(round(acc * n_audio / n_text)), max(n_audio - 1, 0))
        start = words[i]["start"] if words else total * acc / n_text
        bounds.append(start)
        acc += c
    bounds[0] = 0.0
    out = []
    for k, start in enumerate(bounds):
        end = bounds[k + 1] if k + 1 < len(bounds) else total
        out.append((start, max(end, start + 0.5)))
    return out


def _ass_time(t: float) -> str:
    t = max(t, 0)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _esc(s: str) -> str:
    return s.replace("\\", "").replace("{", "(").replace("}", ")")


def build_ass(words: list[dict], label: str, fiction: bool, total: float, path: Path):
    font = config.SUB_FONT
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 2", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        # Farben im ASS-Format &HAABBGGRR
        f"Style: Sub,{font},96,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,7,3,5,60,60,0,1",
        f"Style: Label,{font},58,&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,1,0,0,0,100,100,0,0,3,2,0,8,40,40,150,1",
        f"Style: Note,{font},34,&H00DDDDDD,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,0,2,40,40,120,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        f"Dialogue: 1,{_ass_time(0)},{_ass_time(total)},Label,,0,0,0,,{_esc(label)}",
    ]
    if fiction:
        lines.append(f"Dialogue: 1,{_ass_time(0)},{_ass_time(4)},Note,,0,0,0,,Fiktive Geschichte")
    # Wörter in Gruppen von bis zu 3 anzeigen, das aktuelle Wort gelb hervorheben
    groups, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) == 3 or re.search(r"[.!?,;:]$", w["word"]):
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    for gi, g in enumerate(groups):
        g_end = groups[gi + 1][0]["start"] if gi + 1 < len(groups) else g[-1]["end"] + 0.3
        for wi, w in enumerate(g):
            start = w["start"]
            end = g[wi + 1]["start"] if wi + 1 < len(g) else g_end
            if end <= start:
                continue
            parts = []
            for wj, x in enumerate(g):
                txt = _esc(x["word"].upper())
                parts.append(r"{\c&H0000E5FF&\fscx110\fscy110}" + txt + r"{\c&H00FFFFFF&\fscx100\fscy100}" if wj == wi else txt)
            pop = r"{\fad(0,0)}"
            lines.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Sub,,0,0,0,,{pop}{' '.join(parts)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _segment(src: str, dur: float, out: Path):
    """Schneidet einen Clip auf 'dur' Sekunden, 9:16, ohne Ton. Kurze Clips werden geloopt."""
    src_dur = probe_duration(src)
    offset = 0.0
    if src_dur > dur + 1:
        offset = min(src_dur * 0.2, src_dur - dur - 0.5)
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
          f"fps={FPS},setsar=1,eq=brightness=-0.06:saturation=0.9,format=yuv420p")
    _run(["ffmpeg", "-y", "-v", "error", "-stream_loop", "-1", "-ss", f"{offset:.2f}", "-i", src,
          "-t", f"{dur:.3f}", "-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(out)])


def render_part(work: Path, scenes: list[dict], audio: Path, words: list[dict],
                label: str, fiction: bool, music: str | None, out: Path):
    work.mkdir(parents=True, exist_ok=True)
    total = probe_duration(str(audio)) + 0.6
    timings = scene_timings(scenes, words, total)

    seg_files = []
    for i, (scene, (start, end)) in enumerate(zip(scenes, timings)):
        clip = scene.get("clip")
        if not clip or not Path(clip["path"]).exists():
            raise RenderError(f"Szene {i + 1} hat keinen Clip.")
        seg = work / f"seg_{i:02d}.mp4"
        _segment(clip["path"], end - start, seg)
        seg_files.append(seg)

    concat_list = work / "segments.txt"
    concat_list.write_text("".join(f"file '{p.name}'\n" for p in seg_files), encoding="utf-8")
    _run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", "segments.txt",
          "-c", "copy", "video.mp4"], cwd=work)

    build_ass(words, label, fiction, total, work / "subs.ass")

    inputs = ["-i", "video.mp4", "-i", str(audio.resolve())]
    if music:
        inputs += ["-stream_loop", "-1", "-i", str(Path(music).resolve())]
        afilter = (f"[1:a]aresample=44100,apad=pad_dur=0.6[v];"
                   f"[2:a]aresample=44100,volume={config.MUSIC_VOLUME},afade=t=out:st={max(total - 1.5, 0):.2f}:d=1.5[m];"
                   f"[v][m]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]")
    else:
        afilter = "[1:a]aresample=44100,apad=pad_dur=0.6[a]"
    # Untertitel relativ zum Arbeitsordner (vermeidet Pfadprobleme unter Windows)
    _run(["ffmpeg", "-y", "-v", "error", *inputs,
          "-filter_complex", f"[0:v]ass=subs.ass[vout];{afilter}",
          "-map", "[vout]", "-map", "[a]", "-t", f"{total:.3f}",
          "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out.resolve())], cwd=work)
