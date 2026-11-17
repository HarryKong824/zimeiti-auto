from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

from .config import WORK
from .ffmpeg import ffmpeg_exe, media_duration


def ffprobe_duration(path: Path) -> float:
    return media_duration(path)


def prepare(source: str | Path, job_id: str | None = None) -> tuple[Path, dict]:
    """建立任务目录，抽取 16k 单声道音频。"""
    src = Path(source).resolve()
    if not src.exists():
        raise FileNotFoundError(f"找不到素材：{src}")

    job_id = job_id or time.strftime("%Y%m%d-%H%M%S")
    job_dir = WORK / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    dst = job_dir / f"source{src.suffix.lower()}"
    if src != dst:
        shutil.copy2(src, dst)

    audio = job_dir / "audio.wav"
    subprocess.run(
        [
            ffmpeg_exe(), "-y", "-i", str(dst),
            "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
            str(audio),
        ],
        capture_output=True,
        check=True,
    )

    meta = {
        "job_id": job_id,
        "source": str(dst),
        "audio": str(audio),
        "duration": round(ffprobe_duration(audio), 3),
    }
    (job_dir / "job.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return job_dir, meta
