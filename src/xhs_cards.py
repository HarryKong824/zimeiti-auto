"""小红书图文卡生成。

小红书支持图文（多图轮播），这里把口播内容拆成 3-6 张卡片：
封面 + 关键观点 + 做法步骤 + 互动收尾。
风格与封面统一（深色 + 强调色），3:4 竖版。
"""

from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw

from .config import STYLE
from . import fonts
from .images import _font, _gradient, _wrap

CFG = STYLE
CW = 1080
CH = 1440  # 3:4
ACCENT = CFG.get("style", {}).get("accent", "#4F8CFF")
TEXT = CFG.get("style", {}).get("text", "#F2F5FA")
MUTED = CFG.get("style", {}).get("muted", "#8A94A6")
BOLD = fonts.resolve("bold", CFG.get("style", {}).get("font_bold", ""))
REGULAR = fonts.resolve("regular", CFG.get("style", {}).get("font_regular", ""))
BRAND = CFG.get("style", {}).get("brand", "")


def _extract_points(text: str, max_points: int = 4) -> list[str]:
    """从口播全文里提取关键句。优先含数字/步骤/结论的句子。"""
    sentences = [s.strip() for s in re.split(r"[。！？!?\n]", text) if s.strip()]
    if not sentences:
        return []
    scored = []
    for s in sentences:
        score = 0
        if re.search(r"[0-9一二三四五六七八九十第步]", s):
            score += 3
        if any(w in s for w in ["关键", "本质", "结论", "其实", "最重要", "核心", "说白了"]):
            score += 2
        if len(s) > 8:
            score += 1
        scored.append((score, s))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in scored[:max_points]]


def _make_card(title: str, body: str, out: Path, index: int, total: int) -> Path:
    img = _gradient("#0B0F17", CW, CH)
    draw = ImageDraw.Draw(img)

    # 装饰
    draw.rectangle([0, 0, CW, 10], fill=ACCENT)
    draw.text((72, 60), BRAND, font=_font(REGULAR, 32), fill=MUTED)

    # 页码
    draw.text((CW - 130, 56), f"{index}/{total}", font=_font(REGULAR, 32), fill=MUTED)

    # 标题
    title_font = _font(BOLD, 72)
    title_lines = _wrap(draw, title, title_font, CW - 160)[:2]
    y = 240
    for line in title_lines:
        draw.text((72, y), line, font=title_font, fill=TEXT)
        y += 82

    draw.line([(72, y + 20), (72 + 120, y + 20)], fill=ACCENT, width=6)
    y += 80

    # 正文（按换行分段，每段再自动换行）
    body_font = _font(REGULAR, 48)
    for para in body.split("\n"):
        for line in _wrap(draw, para, body_font, CW - 160)[:4]:
            draw.text((72, y), line, font=body_font, fill="#C8D2E0")
            y += 66

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out


def generate(text: str, shots: list[dict], job_dir: Path) -> list[Path]:
    """生成小红书图文卡，返回图片路径列表。"""
    points = _extract_points(text)
    headline = shots[0]["keyword"] if shots else (points[0][:12] if points else "干货")

    # 先算总数：封面 + 观点 + 收尾
    total = 1 + min(len(points), 4) + 1
    card_dir = job_dir / "xhs_cards"
    card_dir.mkdir(parents=True, exist_ok=True)

    cards: list[Path] = []
    idx = 1

    # 封面卡
    cards.append(_make_card(headline[:18], "看完你就知道怎么做了", card_dir / f"card_{idx:02d}.png", idx, total))
    idx += 1

    # 观点卡
    for i, point in enumerate(points[:4], start=1):
        cards.append(_make_card(f"第{i}点", point, card_dir / f"card_{idx:02d}.png", idx, total))
        idx += 1

    # 收尾卡
    cards.append(_make_card("你怎么看？", "评论区聊聊你的经历\n关注我，持续分享实操", card_dir / f"card_{idx:02d}.png", idx, total))

    return cards
