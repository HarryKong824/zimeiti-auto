from __future__ import annotations

import subprocess
from pathlib import Path

from . import cues, fonts
from .config import STYLE

VIDEO = STYLE.get("video", {})
FPS = int(VIDEO.get("fps", 30))
CRF = str(VIDEO.get("crf", 20))
PRESET = str(VIDEO.get("preset", "veryfast"))


def _run(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=str(cwd), check=True, capture_output=True)


def _motion(motion: str, frames: int) -> str:
    center_x = "x='iw/2-(iw/zoom/2)'"
    center_y = "y='ih/2-(ih/zoom/2)'"
    if motion == "zoom_in":
        return f"z='min(1.0+0.0012*on,1.18)':{center_x}:{center_y}"
    if motion == "zoom_out":
        return f"z='max(1.18-0.0012*on,1.0)':{center_x}:{center_y}"
    if motion == "pan_right":
        return f"z='1.12':x='(iw-iw/zoom)*on/{max(frames - 1, 1)}':{center_y}"
    if motion == "pan_left":
        return f"z='1.12':x='(iw-iw/zoom)*(1-on/{max(frames - 1, 1)})':{center_y}"
    return f"z='min(1.0+0.0007*on,1.07)':{center_x}:{center_y}"


def _segment(
    image: Path, duration: float, motion: str, out: Path, cwd: Path, width: int, height: int
) -> None:
    frames = max(int(round(duration * FPS)), 2)
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        f"zoompan={_motion(motion, frames)}:d={frames}:s={width}x{height}:fps={FPS},"
        f"format=yuv420p"
    )
    _run(
        [
            "ffmpeg", "-y", "-i", str(image),
            "-vf", vf,
            "-frames:v", str(frames),
            "-c:v", "libx264", "-preset", PRESET, "-crf", CRF,
            "-an", str(out),
        ],
        cwd,
    )


def _ass_time(seconds: float) -> str:
    seconds = max(seconds, 0)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours}:{minutes:02d}:{secs:05.2f}"


def _split_lines(text: str, limit: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    lines, current = [], ""
    for index, char in enumerate(text):
        current += char
        following = text[index + 1] if index + 1 < len(text) else ""
        if char in "，。！？；、,.!?;":
            lines.append(current.strip())
            current = ""
        elif len(current) >= limit and not (
            char.isascii() and char.isalnum() and following.isascii() and following.isalnum()
        ):
            lines.append(current.strip())
            current = ""
    if current.strip():
        lines.append(current.strip())
    return [line for line in lines if line]


def build_ass(
    transcript: dict, out: Path, width: int, height: int, sub: dict
) -> bool:
    limit = int(sub.get("chars_per_line", 16))
    font = sub.get("font") or fonts.ass_family()
    size = int(sub.get("size", 58))
    outline = int(sub.get("outline", 3))
    margin_v = int(sub.get("margin_v", 220))

    events = []
    for cue in cues.build(transcript.get("segments", []), sub):
        start, end = cue["start"], cue["end"]
        lines = _split_lines(cue.get("text", ""), limit)
        if not lines:
            continue
        total_chars = sum(len(line) for line in lines) or 1
        cursor = start
        for line in lines:
            span = (end - start) * len(line) / total_chars
            line_end = min(cursor + span, end)
            events.append(
                f"Dialogue: 0,{_ass_time(cursor)},{_ass_time(line_end)},Default,,0,0,0,,{line}"
            )
            cursor = line_end

    if not events:
        return False

    content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,{outline},1,2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(events) + "\n"

    out.write_text(content, encoding="utf-8")
    return True


def compose(
    shots: list[dict],
    images: list[Path],
    transcript: dict,
    job_dir: Path,
    width: int = 1080,
    height: int = 1920,
    subtitle: dict | None = None,
) -> Path:
    sub = dict(STYLE.get("subtitle", {}))
    sub.update(subtitle or {})

    seg_dir = job_dir / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)

    names = []
    for shot, image in zip(shots, images):
        duration = max(float(shot["end"]) - float(shot["start"]), 1.0)
        name = f"seg_{shot['index']:03d}.mp4"
        _segment(image, duration, shot.get("motion", "none"), seg_dir / name, job_dir, width, height)
        names.append(f"segments/{name}")

    (job_dir / "concat.txt").write_text(
        "\n".join(f"file '{name}'" for name in names) + "\n", encoding="utf-8"
    )
    _run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "concat.txt",
         "-c", "copy", "video_only.mp4"],
        job_dir,
    )

    has_subs = build_ass(transcript, job_dir / "subs.ass", width, height, sub)
    args = ["ffmpeg", "-y", "-i", "video_only.mp4", "-i", "audio.wav"]
    if has_subs:
        args += ["-vf", "ass=subs.ass"]
    args += [
        "-c:v", "libx264", "-preset", PRESET, "-crf", CRF,
        "-c:a", "aac", "-b:a", "192k", "-shortest", "final.mp4",
    ]
    _run(args, job_dir)
    return job_dir / "final.mp4"
