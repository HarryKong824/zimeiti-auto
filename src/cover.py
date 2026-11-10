from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from .config import STYLE
from . import fonts
from .images import _font, _gradient, _wrap

COVER = STYLE.get("cover", {})
CW = int(COVER.get("width", 1080))
CH = int(COVER.get("height", 1440))
TITLE_SIZE = int(COVER.get("title_size", 92))
MAX_LINES = int(COVER.get("max_lines", 3))

ACCENT = STYLE.get("style", {}).get("accent", "#4F8CFF")
TEXT = STYLE.get("style", {}).get("text", "#F2F5FA")
BOLD = fonts.resolve("bold", STYLE.get("style", {}).get("font_bold", ""))
REGULAR = fonts.resolve("regular", STYLE.get("style", {}).get("font_regular", ""))
BRAND = STYLE.get("style", {}).get("brand", "")


def make_cover(title: str, subtitle: str, out: Path) -> Path:
    img = _gradient("#0B0F17", CW, CH)
    draw = ImageDraw.Draw(img)

    # 装饰：右下半透明圆 + 底部色块，避免大面积留白
    draw.ellipse([CW - 520, CH - 620, CW + 260, CH + 160], fill="#141C28")
    draw.rectangle([0, CH - 16, CW, CH], fill=ACCENT)

    draw.rectangle([0, 0, CW, 10], fill=ACCENT)
    draw.text((72, 110), BRAND, font=_font(REGULAR, 36), fill="#8A94A6")

    font = _font(BOLD, TITLE_SIZE)
    lines = _wrap(draw, title, font, CW - 160)[:MAX_LINES]
    y = 320
    for line in lines:
        draw.text((72, y), line, font=font, fill=TEXT)
        y += TITLE_SIZE + 26

    draw.line([(72, y + 30), (72 + 140, y + 30)], fill=ACCENT, width=6)
    y += 80

    sub_font = _font(REGULAR, 46)
    for line in _wrap(draw, subtitle, sub_font, CW - 160)[:4]:
        draw.text((72, y), line, font=sub_font, fill="#A8B3C4")
        y += 70

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out
