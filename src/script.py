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


def _llm(topic: dict, sections: list[dict]) -> dict:
    base_url = env("OPENAI_BASE_URL")
    api_key = env("OPENAI_API_KEY")
    if not base_url or not api_key:
        return {}

    banned = "、".join(CFG.get("banned", []))
    outline = [
        {"heading": s["heading"], "seconds": s["seconds"], "chars": s["chars"], "hint": s["hint"]}
        for s in sections
    ]
    payload = {
        "model": env("LLM_MODEL", "deepseek-chat"),
        "temperature": 0.8,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是短视频口播撰稿人。写的是要念出来的稿子，不是文章。\n"
                    "硬规则：\n"
                    "1. 每句不超过 25 字，能断就断；\n"
                    "2. 全篇第一人称，讲你亲眼见过的事，不引用报告和专家；\n"
                    "3. 每段至少出现一个具体数字（钱、时间、人力、比例）；\n"
                    "4. 同时服务两类听众：老板要听判断和代价，学习者要听能照做的步骤；\n"
                    f"5. 禁止出现这些词：{banned}；\n"
                    '6. 不要写「大家好」「今天我们来聊聊」这类开场；\n'
                    "7. 不要用排比句和四字成语堆砌。\n"
                    '只输出 JSON：{"title": str, "sections": [{"text": str}], "cover": str}。'
                    "sections 的数量和顺序必须与大纲完全一致，"
                    "每段字数控制在给定值的 ±20% 以内。cover 是不超过 10 个字的封面大字。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "选题": topic.get("title", ""),
                        "命中词": topic.get("hits", []),
                        "可切入": topic.get("angles", []),
                        "大纲": outline,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
    }
    try:
        resp = requests.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        data = json.loads(resp.json()["choices"][0]["message"]["content"])
    except Exception:
        return {}

    for section, item in zip(sections, data.get("sections") or []):
        section["text"] = str(item.get("text", "")).strip()
    return {"title": str(data.get("title", "")).strip(), "cover": str(data.get("cover", "")).strip()}


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
        lines.append(f"## {section['heading']}（{section['seconds']:.0f} 秒 / 约 {section['chars']} 字）")
        lines.append("")
        if section["text"]:
            lines.append(section["text"])
        else:
            lines.append(f"> 待填。{section['hint']}")
        lines.append("")

    hits = script.get("banned_hits") or []
    if hits:
        lines += ["---", "", f"⚠️ 出现 AI 味词汇：{'、'.join(hits)}。念之前顺手改掉。", ""]

    return "\n".join(lines)


def run(topic: str = "", index: int = 0, seconds: float = 0) -> Path:
    total = float(seconds or CFG.get("default_seconds", 290))
    data = _pick(topic, index)
    sections = _sections(total)
    picked = _llm(data, sections)

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