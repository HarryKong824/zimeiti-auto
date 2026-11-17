"""ffmpeg 路径解析：系统 PATH 优先，其次 imageio-ffmpeg 自带的二进制。

用户不需要手动装 ffmpeg —— `pip install imageio-ffmpeg` 会带一个可执行文件，
不需要管理员权限，也不需要改 PATH。
"""
from __future__ import annotations

import os
import shutil

_cached: str | None = None


def ffmpeg_exe() -> str:
    """返回可用的 ffmpeg 路径，找不到时退回字符串 "ffmpeg"（由调用处报错）。"""
    global _cached
    if _cached:
        return _cached

    override = os.environ.get("FFMPEG_BIN", "").strip()
    if override and (os.path.isfile(override) or shutil.which(override)):
        _cached = override
        return _cached

    found = shutil.which("ffmpeg")
    if found:
        _cached = found
        return _cached

    try:
        import imageio_ffmpeg

        path = imageio_ffmpeg.get_ffmpeg_exe()
        if path and os.path.isfile(path):
            _cached = path
            return _cached
    except Exception:
        pass

    _cached = "ffmpeg"
    return _cached


def has_ffmpeg() -> bool:
    return ffmpeg_exe() != "ffmpeg" or shutil.which("ffmpeg") is not None


def ffprobe_exe() -> str | None:
    override = os.environ.get("FFPROBE_BIN", "").strip()
    if override and (os.path.isfile(override) or shutil.which(override)):
        return override
    return shutil.which("ffprobe")


def media_duration(path) -> float:
    """取媒体时长（秒）。没有 ffprobe 时用 ffmpeg 的 stderr 兜底解析。"""
    import re
    import subprocess
    from pathlib import Path

    target = str(Path(path))
    probe = ffprobe_exe()
    if probe:
        result = subprocess.run(
            [probe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", target],
            capture_output=True, text=True,
        )
        try:
            return float(result.stdout.strip())
        except ValueError:
            pass

    result = subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-i", target],
        capture_output=True, text=True,
    )
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", result.stderr or "")
    if not match:
        raise RuntimeError(f"无法读取时长：{target}")
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
