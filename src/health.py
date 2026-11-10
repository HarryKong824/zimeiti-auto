from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

from . import fonts
from .config import DATA, INBOX, LIBRARY, OUTBOX, ROOT, WORK

OK, WARN, BAD = "✓", "!", "✗"


def _line(mark: str, name: str, detail: str) -> None:
    print(f" {mark} {name:<22} {detail}")


def check(network: bool = False) -> int:
    critical = 0
    print("\n环境自检\n" + "-" * 46)

    version = sys.version_info
    if version >= (3, 10):
        _line(OK, "Python", f"{version.major}.{version.minor}.{version.micro}")
    else:
        critical += 1
        _line(BAD, "Python", f"{version.major}.{version.minor}，需要 3.10+")

    for tool in ("ffmpeg", "ffprobe"):
        path = shutil.which(tool)
        if path:
            _line(OK, tool, path)
        else:
            critical += 1
            _line(BAD, tool, "不在 PATH，请先安装并加入环境变量")

    for module, label, needed in (
        ("PIL", "Pillow", True),
        ("requests", "requests", True),
        ("yaml", "PyYAML", True),
        ("numpy", "numpy", True),
        ("faster_whisper", "faster-whisper", False),
    ):
        found = importlib.util.find_spec(module) is not None
        if found:
            _line(OK, label, "已安装")
        elif needed:
            critical += 1
            _line(BAD, label, "未安装，pip install -r requirements.txt")
        else:
            _line(WARN, label, "未安装：没有字幕文件时无法转写")

    model_dir = ROOT / "models" / "faster-whisper-small"
    model_bin = model_dir / "model.bin"
    if model_bin.exists() and model_bin.stat().st_size > 100 * 1024 * 1024:
        _line(OK, "whisper 模型", f"{model_bin.stat().st_size / 1024 / 1024:.0f} MB")
    else:
        _line(WARN, "whisper 模型", "本地没有，首次转写会联网下载（国内极慢）")

    for kind in ("bold", "regular"):
        path = fonts.resolve(kind)
        if path:
            _line(OK, f"字体 {kind}", path)
        else:
            critical += 1
            _line(BAD, f"字体 {kind}", "没找到中文字体，字幕会变方块")
    _line(OK, "ASS 字体族", fonts.ass_family())

    for label, directory in (
        ("inbox", INBOX), ("work", WORK), ("outbox", OUTBOX),
        ("library", LIBRARY), ("data", DATA),
    ):
        try:
            directory.mkdir(parents=True, exist_ok=True)
            probe = directory / ".write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            _line(OK, f"目录 {label}", str(directory))
        except Exception as exc:
            critical += 1
            _line(BAD, f"目录 {label}", f"不可写：{exc}")

    if network:
        import requests

        for name, url in (
            ("B站榜", "https://api.bilibili.com/x/web-interface/ranking/v2?rid=0&type=all"),
            ("知乎热榜", "https://api.zhihu.com/topstory/hot-list"),
        ):
            try:
                resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
                _line(OK if resp.ok else WARN, f"热榜 {name}", f"HTTP {resp.status_code}")
            except Exception:
                _line(WARN, f"热榜 {name}", "连不上，选题功能会缺数据源")

    print("-" * 46)
    if critical:
        print(f"{critical} 项阻塞，其余可用。\n")
        return 1
    print("全部通过，可以运行：python run.py --input inbox/你的口播.mp4\n")
    return 0
