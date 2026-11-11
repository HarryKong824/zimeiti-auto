from __future__ import annotations

import json
import re

from .config import STYLE, env
from .providers import chat as llm_chat, is_available as provider_available
from .templates import TEMPLATES, pick_template

# 两套风格后缀：占位图用扁平矢量；真实生图 API 用摄影风格
_PLACEHOLDER_STYLE = (
    "flat vector illustration, muted dark palette, deep blue accent, "
    "high contrast, clean composition, no text, no watermark, vertical 9:16"
)
_AI_STYLE = (
    "cinematic, realistic photography, natural lighting, "
    "high detail, 8k, shallow depth of field, no text, no watermark"
)


def _style_suffix(uses_ai: bool = True) -> str:
    return _AI_STYLE if uses_ai else _PLACEHOLDER_STYLE


def _merge_short(shots: list[dict], lo: float, hi: float) -> list[dict]:
    merged: list[dict] = []
    for shot in shots:
        if merged:
            span = shot["end"] - merged[-1]["start"]
            before = merged[-1]["end"] - merged[-1]["start"]
            if span <= hi and before < lo:
                merged[-1]["end"] = shot["end"]
                merged[-1]["text"] += shot["text"]
                continue
        merged.append(dict(shot))
    return merged


def _keyword(text: str) -> str:
    clean = re.sub(r"[，。！？、；：“”‘’（）《》\s,.!?;:\"'()]+", " ", text).strip()
    first = clean.split(" ")[0] if clean else ""
    return first[:12] or text[:12]


def build(
    transcript: dict, duration: float, lo: float | None = None, hi: float | None = None,
    image_provider: str = "placeholder",
) -> list[dict]:
    """规则模式：按时间切镜头，按关键词选模板。无 LLM 也能跑通。"""
    global STYLE_SUFFIX
    uses_ai = image_provider not in ("placeholder", "comfyui", "")
    STYLE_SUFFIX = _style_suffix(uses_ai)

    video_cfg = STYLE.get("video", {})
    lo = float(lo if lo is not None else video_cfg.get("shot_min", 3.0))
    hi = float(hi if hi is not None else video_cfg.get("shot_max", 9.0))

    raw = []
    for seg in transcript.get("segments", []):
        raw.append(
            {"start": float(seg["start"]), "end": float(seg["end"]), "text": seg["text"]}
        )
    if not raw:
        return []

    shots = _merge_short(raw, lo, hi)
    if shots:
        shots[-1]["end"] = max(shots[-1]["end"], duration)

    result = []
    for index, shot in enumerate(shots):
        template = pick_template(shot["text"], index)
        keyword = _keyword(shot["text"])
        result.append(
            {
                "index": index,
                "start": round(shot["start"], 3),
                "end": round(shot["end"], 3),
                "template": template,
                "template_name": TEMPLATES[template]["name"],
                "motion": TEMPLATES[template]["motion"],
                "keyword": keyword,
                "text": shot["text"],
                "prompt": f"{TEMPLATES[template]['prompt']}, {STYLE_SUFFIX}",
            }
        )
    return result


def refine_with_llm(shots: list[dict], topic: str = "") -> list[dict]:
    """可选：让 LLM 只改关键词和画面描述，模板仍限定在 8 个内。"""
    if not provider_available("llm", ""):
        return shots

    allowed = ", ".join(TEMPLATES.keys())
    messages = [
        {
            "role": "system",
            "content": (
                "你是短视频分镜师。只输出 JSON，不要解释。"
                f"template 只能取以下之一：{allowed}。"
                "keyword 是不超过 10 个汉字的画面主题词。"
                "scene 是一句英文画面描述，不含文字元素。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {"topic": topic, "shots": [{"i": s["index"], "t": s["text"]} for s in shots]},
                ensure_ascii=False,
            ),
        },
    ]
    data = llm_chat(messages, temperature=0.4, response_format={"type": "json_object"}, timeout=90)
    if not data:
        return shots
    items = {int(item["i"]): item for item in data.get("shots", [])}

    for shot in shots:
        item = items.get(shot["index"])
        if not item:
            continue
        template = item.get("template")
        if template in TEMPLATES:
            shot["template"] = template
            shot["template_name"] = TEMPLATES[template]["name"]
            shot["motion"] = TEMPLATES[template]["motion"]
        if item.get("keyword"):
            shot["keyword"] = str(item["keyword"])[:12]
        if item.get("scene"):
            shot["prompt"] = f"{item['scene']}, {STYLE_SUFFIX}"
    return shots
