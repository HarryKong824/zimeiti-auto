"""评论草稿生成。

只出草稿，由用户手动复制发布。不自动发评论（硬边界）。
LLM 生成失败时用规则降级：从正文里摘几句改写。
"""

from __future__ import annotations

import json
import random

from .config import PLATFORMS, load_yaml
from .providers import chat as llm_chat, is_available as provider_available

CFG = load_yaml("comments.yaml")


def _fallback(text: str, count: int) -> list[str]:
    """没 LLM 时从正文摘句子改写。"""
    import re

    sentences = [s.strip() for s in re.split(r"[。！？!?]", text) if s.strip()]
    if not sentences:
        return [f"学到了，请问{random.choice(['具体怎么操作', '有没有模板', '成本多少'])}？"]
    picked = random.sample(sentences, min(count, len(sentences)))
    templates = [
        "这个点我也踩过，{s}",
        "想问下{s}后面怎么处理？",
        "收藏了，{s}这步太关键",
        "{s}——说到我心坎里了",
        "有没有更详细的？{s}",
    ]
    out = []
    for s in picked:
        out.append(random.choice(templates).format(s=s[:30]))
    while len(out) < count:
        out.append("学到了，感谢分享！")
    return out[:count]


def generate(text: str, shots: list[dict], platforms: list[str]) -> dict[str, list[str]]:
    """返回 {platform: [comment, ...]}"""
    plat_cfg = CFG.get("platforms", {})
    defaults = CFG.get("defaults", {})
    result: dict[str, list[str]] = {}

    for name in platforms:
        pc = plat_cfg.get(name, {})
        count = int(pc.get("count") or defaults.get("count", 3))
        style = pc.get("style", "")
        label = PLATFORMS.get(name, {}).get("name", name)

        comments = _llm(text, shots, label, style, count) or _fallback(text, count)
        result[name] = comments

    return result


def _llm(text: str, shots: list[dict], platform: str, style: str, count: int) -> list[str] | None:
    if not provider_available("llm", ""):
        return None

    keywords = [s.get("keyword", "") for s in shots if s.get("keyword")][:5]
    messages = [
        {
            "role": "system",
            "content": (
                f"你是{platform}的真实观众。看完视频写{count}条评论草稿。"
                f"风格：{style}"
                "只输出 JSON：{\"comments\": [str, ...]}。"
                "每条不超过80字，不要雷同，像真人留言不是营销号。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {"视频内容": text[:500], "画面关键词": keywords},
                ensure_ascii=False,
            ),
        },
    ]
    data = llm_chat(messages, temperature=0.9, response_format={"type": "json_object"}, timeout=60)
    if not data:
        return None
    comments = data.get("comments", [])
    if isinstance(comments, list) and comments:
        return [str(c)[:100] for c in comments[:count]]
    return None
