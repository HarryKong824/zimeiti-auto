from __future__ import annotations

import json
import shutil
from pathlib import Path

from .config import AUDIENCES, OUTBOX, PLATFORMS


def package(
    job_dir: Path,
    final: Path,
    cover: Path,
    copies: dict[str, dict[str, dict]],
    shots: list[dict],
    name: str | None = None,
    comments: dict[str, list[str]] | None = None,
    xhs_cards: list[Path] | None = None,
) -> Path:
    target = OUTBOX / (name or job_dir.name)
    target.mkdir(parents=True, exist_ok=True)

    shutil.copy2(final, target / "final.mp4")
    shutil.copy2(cover, target / "cover.png")

    # 备选封面（cover_a.png / cover_b.png ...）
    variants = sorted(cover.parent.glob("cover_*.png"))
    for path in variants:
        shutil.copy2(path, target / path.name)

    checklist = ["# 发布检查清单\n", f"素材：`{job_dir.name}`\n"]
    if variants:
        checklist.append(
            f"- [ ] 封面 {len(variants) + 1} 张（主封面 + 备选；竖版 3:4 给抖音/小红书，横版 16:9 给 B站/视频号）\n"
        )
    for name, aud_map in copies.items():
        label = PLATFORMS.get(name, {}).get("name", name)
        for audience, item in aud_map.items():
            aud_label = AUDIENCES.get(audience, {}).get("name", audience)
            tags = " ".join(f"#{tag}" for tag in item.get("tags", []) if tag)
            content = (
                f"# {label} · {aud_label}\n\n"
                f"## 标题\n{item.get('title', '')}\n\n"
                f"## 正文\n{item.get('body', '')}\n\n"
                f"## 标签\n{tags}\n"
            )
            filename = f"copy_{name}_{audience}.md"
            (target / filename).write_text(content, encoding="utf-8")
            checklist.append(f"- [ ] {label}／{aud_label}：`{filename}`")

    # 评论草稿
    if comments:
        for plat, items in comments.items():
            label = PLATFORMS.get(plat, {}).get("name", plat)
            lines = [f"# {label} 评论草稿\n", "> 手动复制发布，不要用脚本自动发。\n"]
            for i, c in enumerate(items, 1):
                lines.append(f"{i}. {c}")
            (target / f"comments_{plat}.md").write_text("\n".join(lines), encoding="utf-8")
            checklist.append(f"- [ ] {label}评论：`comments_{plat}.md`")

    # 小红书图文卡
    if xhs_cards:
        card_dir = target / "xhs_cards"
        card_dir.mkdir(exist_ok=True)
        for card in xhs_cards:
            shutil.copy2(card, card_dir / card.name)
        checklist.append(f"- [ ] 小红书图文卡：`xhs_cards/`（{len(xhs_cards)} 张）")

    (target / "storyboard.json").write_text(
        json.dumps(shots, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    checklist += [
        "",
        "## 发布前自查",
        "- [ ] 决策者版：标题能在 3 秒内说清价值，正文没有术语堆砌",
        "- [ ] 学习者版：步骤可直接照做，不空喊",
        "- [ ] 两版说的是同一件事，不是两条不同的视频",
        "- [ ] 封面在手机尺寸下标题可读",
        "- [ ] 字幕无错别字、无遮挡人脸",
        "",
        "## 发布后",
        "- [ ] 把链接回填到 data/links.csv",
    ]
    (target / "checklist.md").write_text("\n".join(checklist), encoding="utf-8")

    return target
