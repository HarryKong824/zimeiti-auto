from __future__ import annotations

import json
import re

from .config import STYLE, env
from .providers import chat as llm_chat, is_available as provider_available
from .templates import TEMPLATES, pick_template

# 两套风格后缀：占位图用扁平矢量；真实生图 API 用摄影风格
# no text 约束：中英文双重否定，AI 模型（尤其是中文模型）只看英文 no text 不够强
_PLACEHOLDER_STYLE = (
    "flat vector illustration, muted dark palette, deep blue accent, "
    "high contrast, clean composition, 严禁任何文字、字幕、标题、水印,"
    "no text, no letters, no words, no captions, no title cards anywhere in image, "
    "vertical 9:16"
)
_AI_STYLE = (
    "cinematic, realistic photography, natural lighting, "
    "high detail, 8k, shallow depth of field, "
    "严禁任何文字、字幕、标题、水印、字母、单词, "
    "absolutely no text overlay, no captions, no title, no letters, no words, no subtitles anywhere in image"
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


def _build_prompt(shot: dict, suffix: str) -> str:
    """统一 prompt 拼接：keyword + text_anchor + 模板视觉隐喻 + 风格后缀。

    保证：
    1. 每个 shot 的 prompt 不同（text_anchor 不同 → 去重）
    2. chart/title/quote 模板的视觉隐喻不会被覆盖（模板 prompt 写死在 templates.py）
    3. template/keyword 被改后 prompt 同步重建
    """
    text_anchor = re.sub(r"[，。！？、；,.!?;:]+", " ", shot.get("text", "")).strip()[:24]
    tpl = shot.get("template", "title")
    return f"{shot.get('keyword', '')}, {text_anchor}, {TEMPLATES[tpl]['prompt']}, {suffix}"


def build(
    transcript: dict, duration: float, lo: float | None = None, hi: float | None = None,
    image_provider: str = "placeholder",
) -> list[dict]:
    """规则模式：按时间切镜头，按关键词选模板。无 LLM 也能跑通。"""
    uses_ai = image_provider not in ("placeholder", "comfyui", "")
    suffix = _style_suffix(uses_ai)

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
        shot_dict = {
            "index": index,
            "start": round(shot["start"], 3),
            "end": round(shot["end"], 3),
            "template": template,
            "template_name": TEMPLATES[template]["name"],
            "motion": TEMPLATES[template]["motion"],
            "keyword": keyword,
            "text": shot["text"],
        }
        shot_dict["prompt"] = _build_prompt(shot_dict, suffix)
        result.append(shot_dict)
    return result


def refine_with_llm(shots: list[dict], topic: str = "", image_provider: str = "placeholder") -> list[dict]:
    """可选：让 LLM 只改 **keyword** 和 **template**，然后同步重建 prompt。

    绝对不让 LLM 生成 scene/prompt——因为 chart/title/quote 模板会被 LLM 改成
    "白板流程图"等让 AI 瞎写字的描述。prompt 永远由规则函数 _build_prompt() 生成。
    """
    if not provider_available("llm", ""):
        return shots

    uses_ai = image_provider not in ("placeholder", "comfyui", "")
    suffix = _style_suffix(uses_ai)

    allowed = ", ".join(TEMPLATES.keys())
    messages = [
        {
            "role": "system",
            "content": (
                "你是短视频分镜师。只输出 JSON，不要解释。"
                f"template 只能取以下之一：{allowed}。"
                "keyword 是不超过 10 个汉字的画面主题词（中文）。"
                "只输出 template 和 keyword 字段，不要生成 scene 或 prompt。"
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
    items = {}
    for item in data.get("shots", []):
        try:
            items[int(item["i"])] = item
        except (KeyError, TypeError, ValueError):
            continue

    for shot in shots:
        item = items.get(shot["index"])
        if not item:
            continue
        changed = False
        template = item.get("template")
        if template in TEMPLATES and template != shot.get("template"):
            shot["template"] = template
            shot["template_name"] = TEMPLATES[template]["name"]
            shot["motion"] = TEMPLATES[template]["motion"]
            changed = True
        new_kw = str(item.get("keyword", ""))[:12]
        if new_kw and new_kw != shot.get("keyword"):
            shot["keyword"] = new_kw
            changed = True
        # template 或 keyword 变了 → 同步重建 prompt（保证去重 + 视觉隐喻不丢）
        if changed:
            shot["prompt"] = _build_prompt(shot, suffix)
    return shots
