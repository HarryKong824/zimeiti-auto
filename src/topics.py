from __future__ import annotations

import datetime as dt
import json
import re

import requests

from .config import DATA, OVERSEAS_HOSTS, load_yaml, proxy_for

CFG = load_yaml("topics.yaml")
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def _active_direction() -> str:
    """当前选题方向。优先读 profile.yaml，否则用 topics.yaml 的 active_direction。"""
    profile = load_yaml("profile.yaml")
    if profile.get("direction"):
        return str(profile["direction"])
    return str(CFG.get("active_direction", "ai"))


def _keywords_for(region: str) -> dict:
    """根据数据源区域返回对应语言的关键词权重。"""
    direction = _active_direction()
    directions = CFG.get("directions", {})
    dir_cfg = directions.get(direction, {})
    if not dir_cfg:
        # 方向不存在时回退到第一个可用方向
        first = next(iter(directions.values()), {})
        dir_cfg = first
    key = "keywords_en" if region == "overseas" else "keywords_zh"
    return dict(dir_cfg.get(key, {}))


def _direction_name() -> str:
    direction = _active_direction()
    return CFG.get("directions", {}).get(direction, {}).get("name", direction)


def _get(url: str, referer: str = "") -> dict:
    headers = {"User-Agent": UA}
    if referer:
        headers["Referer"] = referer
    # 海外源自动走代理；没配代理时缩短超时，避免白等
    proxies = proxy_for(url)
    overseas = any(host in url for host in OVERSEAS_HOSTS)
    if proxies:
        timeout = 20
    elif overseas:
        timeout = 8
    else:
        timeout = 15
    resp = requests.get(url, headers=headers, timeout=timeout, proxies=proxies)
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


def _subreddits() -> list[str]:
    """当前选题方向对应的 Reddit 子版块，没有则用默认科技/AI 版。"""
    direction = _active_direction()
    dir_cfg = CFG.get("directions", {}).get(direction, {})
    subs = dir_cfg.get("subreddits")
    if subs:
        return list(subs)
    return ["artificial", "MachineLearning", "OpenAI", "singularity", "automation"]


def _hackernews(limit: int) -> list[dict]:
    """HackerNews Top Stories，免登录公开 API。条目详情并发拉取。"""
    from concurrent.futures import ThreadPoolExecutor

    ids = _get("https://hacker-news.firebaseio.com/v0/topstories.json")[:limit]

    def _item(sid: int) -> dict | None:
        try:
            item = _get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json")
        except Exception:
            return None
        if not item or not item.get("title"):
            return None
        return {
            "title": item["title"],
            "desc": "",
            "hot": int(item.get("score") or 0),
            "url": item.get("url") or f"https://news.ycombinator.com/item?id={sid}",
        }

    if not ids:
        return []
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(_item, ids))
    return [r for r in results if r]


def _reddit(limit: int) -> list[dict]:
    """Reddit 热帖，公开 JSON 接口，只需 UA。多子版块合并抓取。"""
    subs = _subreddits()
    combined = "+".join(subs)
    url = f"https://www.reddit.com/r/{combined}/hot.json?limit={limit}"
    data = _get(url, "https://www.reddit.com")
    children = (data.get("data") or {}).get("children", [])
    out = []
    for child in children:
        post = child.get("data", {})
        if not post.get("title") or post.get("stickied"):
            continue
        out.append(
            {
                "title": post["title"],
                "desc": (post.get("selftext") or "")[:80],
                "hot": int(post.get("score") or 0),
                "url": f"https://www.reddit.com{post.get('permalink', '')}",
            }
        )
    return out


FETCHERS = {
    "bilibili": _bilibili,
    "zhihu": _zhihu,
    "baidu": _baidu,
    "hackernews": _hackernews,
    "reddit": _reddit,
}


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
            row.update({
                "source": conf.get("name", key),
                "source_key": key,
                "region": conf.get("region", "domestic"),
                "rank": rank,
            })
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
    scoring = CFG.get("scoring", {})
    pos_weight = float(scoring.get("position_weight", 8))
    bonus = float(scoring.get("multi_source_bonus", 20))
    threshold = float(scoring.get("similarity", 0.35))

    for item in items:
        # 国内源用中文关键词，国外源用英文关键词
        keywords = _keywords_for(item.get("region", "domestic"))
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
        f"领域：{_direction_name()}",
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
