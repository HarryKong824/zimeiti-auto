from __future__ import annotations

import datetime as dt
import json
import re

import requests

from .config import DATA, load_yaml

CFG = load_yaml("topics.yaml")
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def _get(url: str, referer: str = "") -> dict:
    headers = {"User-Agent": UA}
    if referer:
        headers["Referer"] = referer
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _bilibili(limit: int) -> list[dict]:
    data = _get(
        "https://api.bilibili.com/x/web-interface/ranking/v2?rid=0&type=all",
        "https://www.bilibili.com",
    )
    items = data.get("data", {}).get("list", [])[:limit]
    return [
        {
            "title": item.get("title", ""),
            "desc": item.get("desc", "")[:80],
            "hot": int((item.get("stat") or {}).get("view", 0)),
            "url": f"https://www.bilibili.com/video/{item.get('bvid', '')}",
        }
        for item in items
    ]


def _zhihu(limit: int) -> list[dict]:
    data = _get("https://api.zhihu.com/topstory/hot-list")
    items = data.get("data", [])[:limit]
    out = []
    for item in items:
        target = item.get("target", {})
        out.append(
            {
                "title": target.get("title", ""),
                "desc": "",
                "hot": 0,
                "url": target.get("url", "").replace("api.zhihu.com/questions", "www.zhihu.com/question"),
            }
        )
    return out


def _baidu(limit: int) -> list[dict]:
    data = _get("https://top.baidu.com/api/board?platform=wise&tab=realtime")
    cards = data.get("data", {}).get("cards", [])
    rows: list[dict] = []
    for card in cards:
        for block in card.get("content") or []:
            if isinstance(block, dict) and isinstance(block.get("content"), list):
                rows.extend(block["content"])
    return [
        {
            "title": item.get("word", ""),
            "desc": (item.get("desc") or "")[:80],
            "hot": int(item.get("hotScore") or 0),
            "url": item.get("url", ""),
        }
        for item in rows[:limit]
        if item.get("word")
    ]


FETCHERS = {"bilibili": _bilibili, "zhihu": _zhihu, "baidu": _baidu}


def collect() -> tuple[list[dict], list[str]]:
    items: list[dict] = []
    notes: list[str] = []
    for key, conf in (CFG.get("sources") or {}).items():
        if not conf.get("enabled", True):
            continue
        fetcher = FETCHERS.get(key)
        if not fetcher:
            continue
        try:
            rows = fetcher(int(conf.get("limit", 50)))
        except Exception as exc:  # 单个源失败不影响整体
            notes.append(f"{conf.get('name', key)} 抓取失败：{type(exc).__name__}")
            continue
        for rank, row in enumerate(rows, start=1):
            if not row.get("title"):
                continue
            row.update({"source": conf.get("name", key), "source_key": key, "rank": rank})
            items.append(row)
        notes.append(f"{conf.get('name', key)} {len(rows)} 条")
    return items, notes


def _match(text: str, word: str) -> bool:
    word = word.lower()
    if re.fullmatch(r"[a-z0-9 .\-]+", word):
        return re.search(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", text) is not None
    return word in text


def _hits(text: str, keywords: dict) -> tuple[list[str], float]:
    text = text.lower()
    found = [word for word in keywords if _match(text, word)]
    return found, sum(float(keywords[word]) for word in found)


def _similar(a: str, b: str, threshold: float) -> bool:
    def grams(text: str) -> set[str]:
        clean = re.sub(r"\s+", "", text)
        return {clean[i : i + 2] for i in range(max(len(clean) - 1, 1))}

    ga, gb = grams(a), grams(b)
    if not ga or not gb:
        return False
    return len(ga & gb) / len(ga | gb) >= threshold


def rank_topics(items: list[dict]) -> list[dict]:
    domain = CFG.get("domain", {})
    keywords = domain.get("keywords", {})
    scoring = CFG.get("scoring", {})
    pos_weight = float(scoring.get("position_weight", 8))
    bonus = float(scoring.get("multi_source_bonus", 20))
    threshold = float(scoring.get("similarity", 0.35))

    for item in items:
        text = f"{item['title']} {item.get('desc', '')}"
        hits, keyword_score = _hits(text, keywords)
        position = max(0.0, pos_weight * (1 - (item["rank"] - 1) / 50))
        item["hits"] = hits
        item["score"] = round(keyword_score + (position if hits else 0), 2)

    ranked = sorted(items, key=lambda x: x["score"], reverse=True)

    # 合并同一件事的多平台来源
    merged: list[dict] = []
    for item in ranked:
        for exist in merged:
            if not (item["hits"] and exist["hits"]):
                continue
            if _similar(item["title"], exist["title"], threshold):
                exist["sources"].append(f"{item['source']} #{item['rank']}")
                exist["hits"] = list(dict.fromkeys(exist["hits"] + item["hits"]))
                exist["score"] += bonus
                break
        else:
            merged.append({**item, "sources": [f"{item['source']} #{item['rank']}"]})

    merged.sort(key=lambda x: x["score"], reverse=True)
    return merged


def angles(hits: list[str]) -> list[str]:
    angles_cfg = CFG.get("angles", {})
    for rule in angles_cfg.get("rules", []):
        if set(rule.get("keywords", [])) & set(hits):
            return rule.get("angles", [])
    return angles_cfg.get("default", [])


def render(topics: list[dict], notes: list[str], top_n: int) -> str:
    today = dt.date.today().isoformat()
    min_score = float(CFG.get("scoring", {}).get("min_score", 0))
    matched = [t for t in topics if t["score"] >= min_score][:top_n]
    lines = [
        f"# 选题清单 {today}",
        "",
        f"领域：{CFG.get('domain', {}).get('name', '')}",
        f"采集：{' / '.join(notes)}",
        f"命中：{len([t for t in topics if t['score'] >= min_score])} 条（门槛 {min_score:.0f} 分），取前 {len(matched)} 条",
        "",
    ]
    if not matched:
        lines.append("> 今天榜单没有过线的选题。调低 config/topics.yaml 里的 min_score，或往下看备选。")
        lines.append("")
        matched = topics[:top_n]

    for index, item in enumerate(matched, start=1):
        hot = f"热度 {item['hot']}" if item.get("hot") else ""
        lines += [
            f"## {index}. {item['title']}",
            f"- 分数：{item['score']:.1f}　来源：{'、'.join(item['sources'])}　{hot}".rstrip(),
            f"- 命中：{'、'.join(item['hits']) or '（未命中，备选）'}",
            f"- 可切入：{' / '.join(angles(item['hits']))}",
            "- 受众：决策者（看判断与成本）+ 学习者（看步骤与模板），同一条视频双版本即可",
        ]
        if item.get("url"):
            lines.append(f"- 链接：{item['url']}")
        lines.append("")

    lines += [
        "---",
        "",
        "## 怎么用",
        "1. 从上往下挑一条，确认你能讲出案例或实操",
        "2. 按「可切入」写口播稿（不需要 AI，写清楚三步就够了）",
        "3. 录完丢进 inbox，跑 `python run.py --input inbox/xxx.mp4`",
    ]
    return "\n".join(lines)


def run(top_n: int | None = None) -> str:
    cfg_out = CFG.get("output", {})
    limit = int(top_n or cfg_out.get("top_n", 20))
    items, notes = collect()
    topics = rank_topics(items)
    text = render(topics, notes, limit)

    out_dir = DATA / str(cfg_out.get("dir", "topics"))
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{dt.date.today().isoformat()}.md"
    path.write_text(text, encoding="utf-8")

    (out_dir / f"{dt.date.today().isoformat()}.json").write_text(
        json.dumps(topics[:limit], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return str(path)
