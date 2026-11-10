from __future__ import annotations

import os
import re
from pathlib import Path

SRT_TIME = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)")


def _seconds(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse_srt(path: Path) -> dict:
    blocks = re.split(r"\n\s*\n", path.read_text(encoding="utf-8").strip())
    segments = []
    for block in blocks:
        match = SRT_TIME.search(block)
        if not match:
            continue
        lines = block.splitlines()
        text = " ".join(
            line.strip() for line in lines if line.strip() and not SRT_TIME.search(line) and not line.strip().isdigit()
        )
        if not text:
            continue
        start = _seconds(*match.group(1, 2, 3, 4))
        end = _seconds(*match.group(5, 6, 7, 8))
        segments.append({"start": start, "end": end, "text": text})
    return {
        "language": "zh",
        "segments": segments,
        "text": "".join(s["text"] for s in segments),
        "source": "srt",
    }


def _decode(audio: Path) -> "object":
    """用 ffmpeg 解成 16k 单声道 float32，绕开 av 的版本兼容问题。"""
    import subprocess

    import numpy as np

    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-threads", "0", "-i", str(audio),
         "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
        capture_output=True,
        check=True,
    )
    return np.frombuffer(proc.stdout, dtype=np.float32)


def transcribe(audio: Path, srt_path: str | Path | None = None, model_size: str = "small") -> dict:
    if srt_path:
        return parse_srt(Path(srt_path))

    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "未安装 faster-whisper。执行 `pip install faster-whisper`，"
            "或用 --srt 传入现成字幕。"
        ) from exc

    # WHISPER_MODEL 可以是模型尺寸，也可以是本地目录（离线环境推荐放本地）
    local = Path(__file__).resolve().parents[1] / "models" / "faster-whisper-small"
    model_ref = os.getenv("WHISPER_MODEL") or (str(local) if local.exists() else model_size)
    model = WhisperModel(
        model_ref,
        device=os.getenv("WHISPER_DEVICE", "cpu"),
        compute_type=os.getenv("WHISPER_COMPUTE", "int8"),
    )
    segments, info = model.transcribe(
        _decode(audio), language="zh", vad_filter=True, beam_size=5
    )
    items = [
        {"start": round(s.start, 3), "end": round(s.end, 3), "text": s.text.strip()}
        for s in segments
        if s.text.strip()
    ]
    return {
        "language": info.language,
        "segments": items,
        "text": "".join(i["text"] for i in items),
        "source": f"faster-whisper:{model_size}",
    }
