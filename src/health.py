from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from . import fonts, providers
from .config import (
    DATA,
    INBOX,
    LIBRARY,
    OUTBOX,
    ROOT,
    WORK,
    env,
    load_dotenv,
    load_yaml,
    proxy,
    proxy_for,
)
from .ffmpeg import ffmpeg_exe, ffprobe_exe, has_ffmpeg

OK, WARN, BAD = "✓", "!", "✗"
LEVEL = {OK: "ok", WARN: "warn", BAD: "error"}

ITEMS: list[dict] = []


def _line(mark: str, name: str, detail: str, fix: str = "") -> None:
    print(f" {mark} {name:<22} {detail}")
    ITEMS.append({"name": name, "level": LEVEL[mark], "detail": detail, "fix": fix})


def check(network: bool = False, as_json: bool = False) -> int:
    """环境自检。as_json=True 时输出机器可读结果，供 agent 直接补齐依赖。"""
    ITEMS.clear()
    critical = 0

    def emit(mark: str, name: str, detail: str, fix: str = "") -> None:
        nonlocal critical
        if mark == BAD:
            critical += 1
        if not as_json:
            _line(mark, name, detail, fix)
        else:
            ITEMS.append({"name": name, "level": LEVEL[mark], "detail": detail, "fix": fix})

    if not as_json:
        print("\n环境自检\n" + "-" * 46)

    version = sys.version_info
    if version >= (3, 10):
        emit(OK, "Python", f"{version.major}.{version.minor}.{version.micro}", "")
    else:
        emit(BAD, "Python", f"{version.major}.{version.minor}，需要 3.10+", "安装 Python 3.10 或以上")

    if has_ffmpeg():
        emit(OK, "ffmpeg", ffmpeg_exe(), "")
    else:
        emit(BAD, "ffmpeg", "未找到", "pip install imageio-ffmpeg")

    if ffprobe_exe():
        emit(OK, "ffprobe", ffprobe_exe(), "")
    else:
        emit(WARN, "ffprobe", "未找到：时长改用 ffmpeg 兜底解析", "可选，不影响出片")

    for module, label, needed, fix in (
        ("PIL", "Pillow", True, "pip install Pillow"),
        ("requests", "requests", True, "pip install requests"),
        ("yaml", "PyYAML", True, "pip install PyYAML"),
        ("numpy", "numpy", True, "pip install numpy"),
        ("faster_whisper", "faster-whisper", False, "pip install faster-whisper"),
    ):
        found = importlib.util.find_spec(module) is not None
        if found:
            emit(OK, label, "已安装")
        elif needed:
            emit(BAD, label, "未安装", fix)
        else:
            emit(WARN, label, "未安装：没有字幕文件时无法转写", fix)

    model_dir = ROOT / "models" / "faster-whisper-small"
    model_bin = model_dir / "model.bin"
    if model_bin.exists() and model_bin.stat().st_size > 100 * 1024 * 1024:
        emit(OK, "whisper 模型", f"{model_bin.stat().st_size / 1024 / 1024:.0f} MB")
    else:
        emit(WARN, "whisper 模型", "本地没有，首次转写会联网下载（国内极慢）", "")

    for kind in ("bold", "regular"):
        path = fonts.resolve(kind)
        if path:
            emit(OK, f"字体 {kind}", path)
        else:
            emit(BAD, f"字体 {kind}", "没找到中文字体，字幕会变方块", "安装任一中文系统字体")
    emit(OK, "ASS 字体族", fonts.ass_family())

    for label, directory in (
        ("inbox", INBOX), ("work", WORK), ("outbox", OUTBOX),
        ("library", LIBRARY), ("data", DATA),
    ):
        try:
            directory.mkdir(parents=True, exist_ok=True)
            probe_file = directory / ".write_test"
            probe_file.write_text("ok", encoding="utf-8")
            probe_file.unlink()
            emit(OK, f"目录 {label}", str(directory))
        except Exception as exc:
            emit(BAD, f"目录 {label}", f"不可写：{exc}", f"检查目录权限：{directory}")

    if network:
        import requests

        for name, url in (
            ("B站榜", "https://api.bilibili.com/x/web-interface/ranking/v2?rid=0&type=all"),
            ("知乎热榜", "https://api.zhihu.com/topstory/hot-list"),
            ("Reddit", "https://www.reddit.com/r/artificial/hot.json?limit=1"),
        ):
            try:
                resp = requests.get(
                    url, timeout=8, headers={"User-Agent": "Mozilla/5.0"}, proxies=proxy_for(url)
                )
                emit(OK if resp.ok else WARN, f"热榜 {name}", f"HTTP {resp.status_code}")
            except Exception:
                hint = "（Reddit 建议在 .env 配 HTTP_PROXY）" if "reddit" in url else ""
                emit(WARN, f"热榜 {name}", "连不上，选题功能会缺数据源" + hint, "")

    if proxy():
        emit(OK, "代理", "已配置 HTTP_PROXY，海外源自动走代理")

    load_dotenv()
    llm_ok = providers.is_available("llm", "")
    emit(OK if llm_ok else WARN, "LLM 密钥", "已配置" if llm_ok else "未配置：口播稿/文案/分镜降级为规则模式",
         "在 .env 配置 LLM_API_KEY")

    configured = env("IMAGE_PROVIDER") or load_yaml("profile.yaml").get("image_provider", "placeholder")
    img_provider = providers.image_provider_name(str(configured))
    if img_provider in ("placeholder", "comfyui"):
        emit(OK, f"出图 {img_provider}", "本地生成，无需密钥")
    else:
        img_ok = providers.is_available("image", img_provider)
        emit(OK if img_ok else WARN, f"出图 {img_provider}",
             "已配置密钥" if img_ok else "未配置：会自动降级为占位图",
             "在 .env 配置 IMAGE_API_KEY，或改 IMAGE_PROVIDER=placeholder")

    if as_json:
        payload = {
            "ok": critical == 0,
            "blocking": critical,
            "ffmpeg": ffmpeg_exe(),
            "items": ITEMS,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if critical == 0 else 1

    print("-" * 46)
    if critical:
        print(f"{critical} 项阻塞，其余可用。\n")
        return 1
    print("检查完成，可以运行：python run.py --input inbox/你的口播.mp4\n")
    return 0
