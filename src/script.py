"""口播稿生成。

输入一个选题，输出可以直接念的稿子。

两种模式：
- 配了 LLM 密钥：按段落结构生成完整口播稿
- 没配：输出结构骨架 + 每段写作提示，仍然能指导录制

稿子是"念出来"的，所以字数按时长换算，不按"看起来差不多"。
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import requests

from .config import DATA, env, load_yaml
from .topics import angles

CFG = load_yaml("script.yaml")


def _rate() -> int:
    return int(CFG.get("rate_per_minute", 240))


def _chars(seconds: float) -> int:
    return max(int(seconds / 60 * _rate()), 8)


def _sections(seconds: float) -> list[dict]:
    """按配置的权重把总时长拆成段落。权重是秒，按目标时长等比缩放。"""
    items = CFG.get("structure", [])
    weight = sum(float(item.get("seconds", 0)) for item in items) or 1
    sections = []
    for item in items:
        sec = round(seconds * float(item.get("seconds", 0)) / weight, 1)
        sections.append(
            {
                "heading": str(item.get("heading", "")),
                "hint": str(item.get("hint", "")),
                "seconds": sec,
                "chars": _chars(sec),
                "text": "",
            }
        )
    return sections


def _post(messages: list[dict], temperature: float = 0.8) -> dict:
    """统一调用，任何失败都返回空字典，由调用方决定降级。"""
    base_url = env("OPENAI_BASE_URL")
    api_key = env("OPENAI_API_KEY")
    if not base_url or not api_key:
        return {}

    payload = {
        "model": env("LLM_MODEL", "deepseek-chat"),
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "messages": messages,
    }
    try:
        resp = requests.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=180,
        )
        resp.raise_for_status()
        return json.loads(resp.json()["choices"][0]["message"]["content"])
    except Exception:
        return {}


def _llm(topic: dict, sections: list[dict]) -> dict:
    """逐段生成。

    整篇一次生成时，模型对每段字数几乎不敏感：要么整体缩水到三分之一，
    要么短段（钩子、收尾）严重超标。分段请求，每段单独盯字数，才控得住。
    """
    if not env("OPENAI_API_KEY"):
        return {}

    banned = "、".join(CFG.get("banned", []))
    head = _post(
        [
            {
                "role": "system",
                "content": (
                    "给短视频选题起标题和封面大字。只输出 JSON："
                    '{"title": str, "cover": str}。'
                    "title 不超过 24 字，必须带一个具体冲突或数字；cover 不超过 10 字，要有冲击力。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "选题": topic.get("title", ""),
                        "命中词": topic.get("hits", []),
                        "可切入": topic.get("angles", []),
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        temperature=0.9,
    )
    title = str(head.get("title", "")).strip() or topic.get("title", "")
    cover = str(head.get("cover", "")).strip()

    prev = ""
    for section in sections:
        section["text"] = _segment(topic, section, title, prev, banned)
        prev = section["text"][-80:]

    return {"title": title, "cover": cover}


def _segment(topic: dict, section: dict, title: str, prev_tail: str, banned: str) -> str:
    target = section["chars"]
    low, high = int(target * 0.9), int(target * 1.1)
    data = _post(
        [
            {
                "role": "system",
                "content": (
                    "你是短视频口播撰稿人。只写指定的这一段，不要写别的段。\n"
                    f"字数必须落在 {low} 到 {high} 字之间，写完自己数一遍："
                    "不够就补具体细节，超了就删铺垫。\n"
                    "硬要求：每句不超过 25 字；第一人称；本段至少两个具体数字（钱、时间、人数、比例）；"
                    "口语，不要书面语和排比；"
                    f"禁止出现这些词：{banned}。\n"
                    '只输出 JSON：{"text": str}'
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "选题": topic.get("title", ""),
                        "总标题": title,
                        "本段": section["heading"],
                        "本段写作要求": section["hint"],
                        "上一段结尾": prev_tail,
                        "目标字数": target,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        temperature=0.85,
    )
    return str(data.get("text", "")).strip()


def _fit(section: dict, topic_title: str, shrink: bool) -> str:
    """把某段字数控到目标附近。整篇生成容易整体缩水或注水，逐段校准更可控。"""
    action = "压缩" if shrink else "扩写"
    detail = "删掉重复、铺垫和总结句，保留数字和具体动作" if shrink else "补充新的细节和数字，不要复述已有句子"
    data = _post(
        [
            {
                "role": "system",
                "content": (
                    f"把给到的口播段落{action}到目标字数。保持第一人称、短句、口语。"
                    f"{detail}。不要写成书面语排比。\n"
                    '只输出 JSON：{"text": str}'
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "选题": topic_title,
                        "段落": section["heading"],
                        "写作要求": section["hint"],
                        "现有内容": section["text"],
                        "现有字数": len(section["text"]),
                        "目标字数": section["chars"],
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        temperature=0.7 if shrink else 0.9,
    )
    return str(data.get("text", "")).strip()


def _balance(sections: list[dict], topic_title: str) -> None:
    """不足目标 80% 的扩写，超过 130% 的压缩。各只做一次，避免来回震荡。"""
    for section in sections:
        if not section["text"]:
            continue
        target = section["chars"]
        size = len(section["text"])

        if size < target * 0.8:
            for _ in range(2):
                longer = _fit(section, topic_title, shrink=False)
                if len(longer) <= len(section["text"]):
                    break
                section["text"] = longer
                if len(section["text"]) >= target * 0.8:
                    break
        elif size > target * 1.3:
            fixed = _fit(section, topic_title, shrink=True)
            if fixed and abs(len(fixed) - target) < abs(size - target):
                section["text"] = fixed


def _pick(topic: str, index: int) -> dict:
    """选题来源：命令行直接给，或从今天的选题清单里取第 index 条。"""
    if topic.strip():
        return {"title": topic.strip(), "hits": [], "angles": [], "source": "手填"}

    path = DATA / "topics" / f"{dt.date.today().isoformat()}.json"
    if not path.exists():
        raise SystemExit(f"今天还没有选题清单，先跑 python run.py --topics，或用 --script \"主题\"")

    items = json.loads(path.read_text(encoding="utf-8"))
    if not items:
        raise SystemExit("选题清单是空的，换一个日期或调低 min_score")

    position = index or 1
    if not 1 <= position <= len(items):
        raise SystemExit(f"选题序号超范围，今天有 {len(items)} 条")

    item = items[position - 1]
    hits = item.get("hits", [])
    return {
        "title": item.get("title", ""),
        "hits": hits,
        "angles": angles(hits),
        "source": f"选题清单第 {position} 条（{item.get('score', 0)} 分）",
    }


def _banned_hits(text: str) -> list[str]:
    return [word for word in CFG.get("banned", []) if word and word in text]


def _short_title(text: str, limit: int = 24) -> str:
    """热榜标题常是一整句问句，做口播标题太长，截到第一个分句。"""
    text = text.strip()
    if len(text) <= limit:
        return text
    for sep in "，。？！；、,.?!;":
        cut = text.find(sep)
        if 6 <= cut <= limit:
            return text[:cut]
    return text[:limit]


def render(script: dict) -> str:
    seconds = script["seconds"]
    lines = [
        f"# 口播稿：{script['title']}",
        "",
        f"预计 {int(seconds // 60)} 分 {int(seconds % 60)} 秒"
        f"｜约 {script['chars']} 字｜语速 {_rate()} 字/分｜来源：{script['source']}",
        "",
    ]
    if script.get("cover"):
        lines += [f"封面大字：**{script['cover']}**", ""]
    if not script["generated"]:
        lines += [
            "> 没配 LLM 密钥，以下是结构骨架。每段按提示写，写满字数就是成稿。",
            "> 想让它一次写完整稿：在 `.env` 里填 `OPENAI_BASE_URL` 和 `OPENAI_API_KEY`。",
            "",
        ]

    lines += ["---", ""]
    for section in script["sections"]:
        actual = len(section["text"])
        head = f"## {section['heading']}（{section['seconds']:.0f} 秒 / 目标 {section['chars']} 字"
        head += f" / 实际 {actual} 字）" if actual else "）"
        lines.append(head)
        lines.append("")
        if section["text"]:
            lines.append(section["text"])
        else:
            lines.append(f"> 待填。{section['hint']}")
        lines.append("")

    actual_total = sum(len(section["text"]) for section in script["sections"])
    if actual_total:
        minutes = actual_total / _rate()
        target = script["seconds"] / 60
        lines += [
            "---",
            "",
            f"实际 {actual_total} 字，按 {_rate()} 字/分约 {minutes:.1f} 分钟"
            f"（目标 {target:.1f} 分钟）。",
            "",
        ]
    if script["generated"]:
        lines += [
            "> 稿子里的案例和数字是模型按常见情况编的，不是你的真实经历。",
            "> 录之前必须换成你自己见过的人和事，否则评论区一问就露馅。",
            "",
        ]
    hits = script.get("banned_hits") or []
    if hits:
        lines += ["---", "", f"⚠️ 出现 AI 味词汇：{'、'.join(hits)}。念之前顺手改掉。", ""]

    return "\n".join(lines)


def run(topic: str = "", index: int = 0, seconds: float = 0) -> Path:
    total = float(seconds or CFG.get("default_seconds", 290))
    data = _pick(topic, index)
    sections = _sections(total)
    picked = _llm(data, sections)
    if picked:
        _balance(sections, picked.get("title") or data["title"])

    script = {
        "title": picked.get("title") or _short_title(data["title"]),
        "cover": picked.get("cover", ""),
        "seconds": total,
        "chars": _chars(total),
        "source": data.get("source", ""),
        "generated": bool(picked),
        "sections": sections,
    }
    text = render(script)
    script["banned_hits"] = _banned_hits(text)

    out_dir = DATA / "scripts"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w\u4e00-\u9fff]+", "-", script["title"])[:16].strip("-") or "口播稿"
    path = out_dir / f"{dt.date.today().isoformat()}-{safe}.md"
    path.write_text(render(script), encoding="utf-8")
    return path