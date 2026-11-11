from __future__ import annotations

import json
import re

from .config import AUDIENCES, PLATFORMS, env
from .providers import chat as llm_chat, is_available as provider_available

AUDIENCE_KEYS = list(AUDIENCES.keys()) or ["decision", "learner"]


def _hooks(text: str) -> tuple[str, list[str]]:
    sentences = [s.strip() for s in re.split(r"[。！？!?]", text) if s.strip()]
    hook = sentences[0] if sentences else text[:30]
    return hook, sentences[1:]


def _fallback(text: str, shots: list[dict], cfg: dict, audience: str) -> dict:
    keywords = []
    for shot in shots:
        word = shot.get("keyword", "").strip()
        if word and word not in keywords:
            keywords.append(word)

    hook, rest = _hooks(text)
    limit = int(cfg.get("title_limit") or 30)
    tag_count = int(cfg.get("tags", 5))

    if audience == "decision":
        title = f"{hook[:limit]}｜到底值不值得做"[:limit] if limit else hook
        body = [
            f"痛点：{rest[0] if rest else hook}",
            f"结论：{hook}",
            "代价：先算清人力和时间成本，再谈工具",
            "三步落地：",
        ]
        body += [f"{i + 1}. {word}" for i, word in enumerate(keywords[:3])] or ["1. 列出重复动作", "2. 能写规则的不靠人记", "3. 把不确定性关进模板"]
        body.append("你们公司现在的瓶颈，是没人做还是不会做？")
    else:
        title = f"我 {hook[:max(limit - 3, 6)]}"[:limit] if limit else hook
        body = [
            f"先说个反常识的：{hook}",
            f"我一开始也踩坑——{rest[0] if rest else '以为要靠工具，其实要靠流程'}",
            "照着做就行：",
        ]
        body += [f"{i + 1}. {word}" for i, word in enumerate(keywords[:3])] or ["1. 列重复动作", "2. 写规则", "3. 做模板"]
        body.append("模板我放在评论区了，需要的话自取。")

    return {"title": title, "body": "\n".join(body), "tags": keywords[:tag_count]}


def _llm(text: str, shots: list[dict], platforms: list[str]) -> dict:
    if not provider_available("llm", ""):
        return {}

    platform_spec = {
        name: {
            "title_limit": PLATFORMS[name].get("title_limit", 30),
            "tag_count": PLATFORMS[name].get("tags", 5),
            "style": PLATFORMS[name].get("body_style", ""),
        }
        for name in platforms
        if name in PLATFORMS
    }
    audience_spec = {
        key: {
            "goal": value.get("goal", ""),
            "tone": value.get("tone", ""),
            "structure": value.get("structure", []),
        }
        for key, value in AUDIENCES.items()
    }

    messages = [
        {
            "role": "system",
            "content": (
                "你是短视频运营。同一条口播要出两种受众版本：决策者和学习者，"
                "两版必须真的不同——决策者要判断依据和成本收益，学习者要可复制的步骤。"
                "只输出 JSON：{\"平台key\": {\"决策者key|学习者key\": {\"title\": str, \"body\": str, \"tags\": [str]}}}。"
                "严格遵守平台字数与风格，不要写\"大家好\"这类空话。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "口播全文": text,
                    "画面关键词": [s.get("keyword") for s in shots],
                    "平台要求": platform_spec,
                    "受众要求": audience_spec,
                },
                ensure_ascii=False,
            ),
        },
    ]
    return llm_chat(messages, temperature=0.7, response_format={"type": "json_object"}, timeout=120)


def _trim(text: str, limit: int) -> str:
    """按字数截断，尽量断在标点/换行处，不硬切半个词。"""
    if limit <= 0 or len(text) <= limit:
        return text
    cut = text[:limit]
    for sep in ("\n", "。", "！", "？", "!", "?", "，", ",", " ", "、"):
        pos = cut.rfind(sep)
        if pos >= int(limit * 0.6):
            keep = pos + 1 if sep in "。！？!?" else pos
            return cut[:keep].rstrip()
    return cut.rstrip()


def _enforce(item: dict, cfg: dict) -> dict:
    """按平台硬限制裁剪标题和正文，标签也计入正文字数（X 等平台）。"""
    title_limit = int(cfg.get("title_limit") or 0)
    body_limit = int(cfg.get("body_limit") or 0)

    if title_limit:
        item["title"] = _trim(str(item.get("title", "")), title_limit)

    if body_limit:
        tags = item.get("tags") or []
        reserve = sum(len(str(tag)) + 2 for tag in tags)
        item["body"] = _trim(str(item.get("body", "")), max(body_limit - reserve, 40))
    return item


def generate(text: str, shots: list[dict], platforms: list[str]) -> dict[str, dict[str, dict]]:
    """返回 {platform: {audience: {title, body, tags}}}"""
    llm_result = _llm(text, shots, platforms)
    result: dict[str, dict[str, dict]] = {}
    for name in platforms:
        cfg = PLATFORMS.get(name, {})
        result[name] = {}
        for audience in AUDIENCE_KEYS:
            item = (llm_result.get(name) or {}).get(audience) or _fallback(text, shots, cfg, audience)
            item.setdefault("title", "")
            item.setdefault("body", "")
            item.setdefault("tags", [])
            result[name][audience] = _enforce(item, cfg)
    return result
