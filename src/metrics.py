"""数据回填与周报。

数据入库三条路，按可靠程度排：
1. CSV 导入（从各平台后台导出，最稳）
2. 手动补一条（--stats-add）
3. 自动抓取（playwright，需要登录态，页面改版会失效）

先保证前两条能跑通，抓取是有账号之后的事。
"""

from __future__ import annotations

import csv
import datetime as dt
import sqlite3
from pathlib import Path
from statistics import median

from .config import DATA, PLATFORMS

DB = DATA / "metrics.db"
COLUMNS = [
    "platform", "title", "url", "published_at",
    "views", "likes", "comments", "shares", "followers", "note",
]
NUMERIC = ("views", "likes", "comments", "shares", "followers")


def _conn() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT DEFAULT '',
            published_at TEXT DEFAULT '',
            views INTEGER DEFAULT 0,
            likes INTEGER DEFAULT 0,
            comments INTEGER DEFAULT 0,
            shares INTEGER DEFAULT 0,
            followers INTEGER DEFAULT 0,
            note TEXT DEFAULT '',
            recorded_at TEXT NOT NULL,
            UNIQUE(platform, title, published_at)
        )
        """
    )
    return conn


def add(row: dict) -> bool:
    """写一条。同平台同标题同发布日期视为同一条，重复写会覆盖数字。"""
    data = {key: row.get(key, "") for key in COLUMNS}
    if not data["platform"] or not data["title"]:
        raise ValueError("platform 和 title 不能为空")
    for key in NUMERIC:
        try:
            data[key] = int(float(data[key] or 0))
        except (TypeError, ValueError):
            data[key] = 0

    conn = _conn()
    with conn:
        conn.execute(
            f"""
            INSERT INTO videos ({", ".join(COLUMNS)}, recorded_at)
            VALUES ({", ".join("?" * len(COLUMNS))}, ?)
            ON CONFLICT(platform, title, published_at) DO UPDATE SET
                views=excluded.views, likes=excluded.likes,
                comments=excluded.comments, shares=excluded.shares,
                followers=excluded.followers, note=excluded.note,
                url=excluded.url, recorded_at=excluded.recorded_at
            """,
            [data[key] for key in COLUMNS] + [dt.date.today().isoformat()],
        )
    conn.close()
    return True


def import_csv(path: Path) -> int:
    if not path.exists():
        raise SystemExit(f"找不到 {path}")
    count = 0
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if add(row):
                count += 1
    return count


def rows(since: str | None = None) -> list[dict]:
    conn = _conn()
    sql = "SELECT * FROM videos"
    args: list = []
    if since:
        sql += " WHERE recorded_at >= ?"
        args.append(since)
    sql += " ORDER BY views DESC"
    items = [dict(row) for row in conn.execute(sql, args)]
    conn.close()
    return items


def _label(key: str) -> str:
    return (PLATFORMS.get(key) or {}).get("name", key)


def _advice(items: list[dict], mid: float) -> list[str]:
    tips = []
    if not items:
        return ["本周没有数据。先把 CSV 从后台导出来，或者用 --stats-add 手动补几条。"]

    top = items[0]
    if mid > 0 and top["views"] >= mid * 2:
        ratio = top["views"] / mid
        tips.append(
            f"「{top['title'][:20]}」在{_label(top['platform'])}跑出中位数的 {ratio:.1f} 倍，"
            "同一个角度可以拆成第二条，换成更具体的案例。"
        )

    weak = [item for item in items if mid > 0 and item["views"] < mid * 0.5]
    if len(weak) >= 2:
        titles = "、".join(f"「{item['title'][:12]}」" for item in weak[:3])
        tips.append(f"{titles} 都没到中位数一半。先看开头 3 秒，再怀疑选题。")

    platforms_hit = {item["platform"] for item in items}
    missing = [key for key in PLATFORMS if key not in platforms_hit]
    if missing:
        tips.append(f"{'、'.join(_label(key) for key in missing)} 本周是空的，要么没发，要么没回填。")

    engaged = [item for item in items if item["views"] > 0]
    if engaged:
        best = max(engaged, key=lambda x: (x["likes"] + x["comments"]) / max(x["views"], 1))
        rate = (best["likes"] + best["comments"]) / max(best["views"], 1) * 100
        if rate >= 3:
            tips.append(
                f"「{best['title'][:20]}」互动率 {rate:.1f}%，评论值得一条条看，"
                "里面问得最多的问题就是下一条选题。"
            )
    return tips


def weekly(days: int = 7) -> Path:
    since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    items = rows(since)
    views = [item["views"] for item in items if item["views"]]
    mid = median(views) if views else 0

    by_platform: dict[str, list[dict]] = {}
    for item in items:
        by_platform.setdefault(item["platform"], []).append(item)

    week = dt.date.today().isocalendar()
    lines = [
        f"# 数据周报 {week.year}-W{week.week:02d}",
        "",
        f"统计区间：{since} ~ {dt.date.today().isoformat()}（近 {days} 天，按回填日计）",
        "",
        "## 总览",
        "",
    ]
    if items:
        lines += [
            f"- 收录 {len(items)} 条，覆盖 {len(by_platform)} 个平台",
            f"- 播放合计 {sum(views):,}，中位数 {mid:,.0f}",
            f"- 涨粉合计 {sum(item['followers'] for item in items):,}",
        ]
    else:
        lines.append("- 本周没有回填任何数据")

    lines += ["", "## 分平台", "", "| 平台 | 条数 | 播放合计 | 中位数 | 最高 |", "|---|---|---|---|---|"]
    if by_platform:
        for key, group in sorted(by_platform.items(), key=lambda x: -sum(i["views"] for i in x[1])):
            numbers = [item["views"] for item in group]
            lines.append(
                f"| {_label(key)} | {len(group)} | {sum(numbers):,} | "
                f"{median(numbers):,.0f} | {max(numbers):,} |"
            )
    else:
        lines.append("| — | 0 | 0 | 0 | 0 |")

    if items:
        lines += ["", "## 明细", "", "| 平台 | 标题 | 播放 | 赞 | 评 | 粉 |", "|---|---|---|---|---|---|"]
        for item in items[:20]:
            lines.append(
                f"| {_label(item['platform'])} | {item['title'][:24]} | {item['views']:,} | "
                f"{item['likes']:,} | {item['comments']:,} | {item['followers']:,} |"
            )

    lines += ["", "## 下周建议", ""]
    lines += [f"- {tip}" for tip in _advice(items, mid)]
    lines.append("")

    out_dir = DATA / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{dt.date.today().isoformat()}-周报.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


CSV_TEMPLATE = ",".join(COLUMNS) + "\n"


def template() -> Path:
    path = DATA / "metrics-template.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(CSV_TEMPLATE, encoding="utf-8-sig")
    return path
