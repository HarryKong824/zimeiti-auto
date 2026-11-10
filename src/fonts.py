from __future__ import annotations

import os
import sys
from pathlib import Path

# 逻辑字体名 → 各平台候选文件，按顺序取第一个存在的
_CANDIDATES = {
    "bold": [
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    ],
    "regular": [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    ],
}

# ASS 字幕用的字体族名，libass 按名字找系统字体
_ASS_FAMILY = {
    "win32": ["Microsoft YaHei", "SimHei", "SimSun"],
    "darwin": ["PingFang SC", "Heiti SC", "Songti SC"],
    "linux": ["Noto Sans CJK SC", "WenQuanYi Zen Hei", "DejaVu Sans"],
}


def resolve(kind: str = "regular", preferred: str = "") -> str:
    """返回一个真实存在的字体文件路径；找不到返回空字符串。"""
    env_key = "FONT_BOLD" if kind == "bold" else "FONT_REGULAR"
    for candidate in (os.getenv(env_key, ""), preferred, *_CANDIDATES[kind]):
        if candidate and Path(candidate).exists():
            return candidate
    return ""


def ass_family(preferred: str = "") -> str:
    """返回 ASS 样式里可用的字体族名。"""
    if preferred:
        return preferred
    ordered = _ASS_FAMILY.get(sys.platform, _ASS_FAMILY["linux"])
    return ordered[0]
