from __future__ import annotations

from pathlib import Path

from PIL import ImageDraw

from .config import STYLE
from . import fonts
from .images import _font, _gradient, _wrap

COVER = STYLE.get("cover", {})
BASE_W = int(COVER.get("width", 1080))
BASE_H = int(COVER.get("height", 1440))
TITLE_SIZE = int(COVER.get("title_size", 92))
MAX_LINES = int(COVER.get("max_lines", 3))

# 各平台封面比例：竖版给抖音/小红书，横版给 B站/视频号
SIZES = COVER.get("sizes") or [
    {"key": "vertical", "width": BASE_W, "height": BASE_H},
    {"key": "wide", "width": 1920, "height": 1080},
]

ACCENT = STYLE.get("style", {}).get("accent", "#4F8CFF")
TEXT = STYLE.get("style", {}).get("text", "#F2F5FA")
BOLD = fonts.resolve("bold", STYLE.get("style", {}).get("font_bold", ""))
REGULAR = fonts.resolve("regular", STYLE.get("style", {}).get("font_regular", ""))
BRAND = STYLE.get("style", {}).get("brand", "")

# 备选封面配色（A/B 测试用）
VARIANTS = [
    {"accent": ACCENT, "bg": "#0B0F17", "title_y": 320, "align": "left"},
    {"accent": "#FF5C5C", "bg": "#12080A", "title_y": 420, "align": "left"},
    {"accent": "#22C55E", "bg": "#07120D", "title_y": 260, "align": "center"},
]


def _layout(width: int, height: int) -> dict:
    """按尺寸等比换算边距、字号、坐标。以 1080×1440 为基准。"""
    scale = height / BASE_H
    return {
        "margin": max(int(width * 0.067), 48),
        "title_size": max(int(TITLE_SIZE * scale), 56),
        "gap": int(26 * scale),
        "brand_size": max(int(36 * scale), 22),
        "brand_y": int(110 * scale),
        "rule_w": int(140 * scale),
        "rule_gap": int(30 * scale),
        "sub_size": max(int(46 * scale), 30),
        "sub_gap": int(70 * scale),
        "bar": max(int(16 * scale), 8),
        "title_y": int(VARIANTS[0]["title_y"] * scale),
    }


def make_cover(
    title: str,
    subtitle: str,
    out: Path,
    variant: int = 0,
    width: int = BASE_W,
    height: int = BASE_H,
) -> Path:
    spec = VARIANTS[variant % len(VARIANTS)]
    accent = spec["accent"]
    lay = _layout(width, height)
    margin = lay["margin"]

    img = _gradient(spec["bg"], width, height)
    draw = ImageDraw.Draw(img)

    # 装饰：右下半透明圆 + 底部色块，避免大面积留白
    draw.ellipse(
        [width - int(width * 0.48), height - int(height * 0.43), width + 60, height + 40],
        fill="#141C28",
    )
    draw.rectangle([0, height - lay["bar"], width, height], fill=accent)
    draw.rectangle([0, 0, width, max(int(10 * height / BASE_H), 6)], fill=accent)

    draw.text((margin, lay["brand_y"]), BRAND, font=_font(REGULAR, lay["brand_size"]), fill="#8A94A6")

    # 标题
    font = _font(BOLD, lay["title_size"])
    lines = _wrap(draw, title, font, width - 2 * margin)[:MAX_LINES]
    y = lay["title_y"]
    for line in lines:
        x = margin
        if spec["align"] == "center":
            width_px = draw.textlength(line, font=font)
            x = max(int((width - width_px) / 2), margin)
        draw.text((x, y), line, font=font, fill=TEXT)
        y += lay["title_size"] + lay["gap"]

    # 分隔线
    line_x = margin
    if spec["align"] == "center":
        line_x = int(width / 2 - lay["rule_w"] / 2)
    y += lay["rule_gap"]
    draw.line(
        [(line_x, y), (line_x + lay["rule_w"], y)], fill=accent, width=max(int(6 * height / BASE_H), 3)
    )
    y += int(50 * height / BASE_H)

    # 副标题
    sub_font = _font(REGULAR, lay["sub_size"])
    for line in _wrap(draw, subtitle, sub_font, width - 2 * margin)[:4]:
        x = margin
        if spec["align"] == "center":
            width_px = draw.textlength(line, font=sub_font)
            x = max(int((width - width_px) / 2), margin)
        draw.text((x, y), line, font=sub_font, fill="#A8B3C4")
        y += lay["sub_gap"]

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out


def make_covers(title: str, subtitle: str, out_dir: Path, count: int = 2) -> list[Path]:
    """按配置的每个尺寸生成 count 张风格不同的封面。

    命名：竖版 cover.png / cover_b.png，横版 cover_wide.png / cover_wide_b.png。
    返回列表第一张是主封面（竖版）。
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for size_idx, size in enumerate(SIZES):
        width = int(size.get("width", BASE_W))
        height = int(size.get("height", BASE_H))
        size_sfx = "" if size_idx == 0 else f"_{size.get('key', size_idx)}"
        for i in range(max(count, 1)):
            var_sfx = "" if i == 0 else f"_{chr(ord('a') + i)}"
            name = f"cover{size_sfx}{var_sfx}.png"
            paths.append(make_cover(title, subtitle, out_dir / name, variant=i, width=width, height=height))
    return paths
