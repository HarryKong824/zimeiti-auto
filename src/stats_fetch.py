"""数据自动回填（尽力而为）。

用 Playwright 打开各平台创作中心，跑配置里的 JS 抓作品数据，写入 metrics 库。
页面改版会失效，所以：
1. 抓不到就明确报告，不静默失败
2. 优先推荐 CSV 导入
"""

from __future__ import annotations

from . import metrics
from .config import WORK, env, load_yaml

CFG = load_yaml("stats.yaml")


def _launch_opts(platform: str, account: str) -> dict:
    profile_dir = WORK / "browser" / platform / account
    profile_dir.mkdir(parents=True, exist_ok=True)
    opts: dict = {
        "user_data_dir": str(profile_dir),
        "channel": "chrome",
        "headless": False,
        "slow_mo": 100,
        "viewport": {"width": 1440, "height": 900},
    }
    proxy_server = env("BROWSER_PROXY") or env("HTTP_PROXY")
    if proxy_server:
        opts["proxy"] = {"server": proxy_server}
    return opts


def fetch_one(platform: str, account: str = "default") -> int:
    spec = (CFG.get("platforms") or {}).get(platform)
    if not spec or not spec.get("enabled"):
        return 0

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("没装 playwright。先跑：pip install playwright")

    print(f"[{platform}] 打开 {spec['url']}（账号：{account}）")
    count = 0
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(**_launch_opts(platform, account))
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(spec["url"], wait_until="domcontentloaded")
        page.wait_for_timeout(int(spec.get("wait", 5000)))

        # 登录失效检测
        login_patterns = spec.get("login_url_patterns", [])
        if any(pat in page.url for pat in login_patterns):
            print(f"[{platform}] ⚠️ 登录态已失效（在 {page.url}），请先扫码登录再跑。")
            context.close()
            return 0  # 返回 int，保持类型一致

        try:
            rows = page.evaluate(spec.get("js", "() => []"))
        except Exception as exc:
            print(f"[{platform}] 提取脚本报错：{exc}")
            rows = []

        if not rows:
            print(f"[{platform}] 没抓到数据。可能没登录，或页面结构变了。可在浏览器里核对，必要时改 config/stats.yaml 的 js。")
        for row in rows or []:
            title = str(row.get("title", "")).strip()
            if not title:
                continue
            try:
                metrics.add({
                    "platform": platform,
                    "title": title,
                    "published_at": "",
                    "views": row.get("views", 0),
                    "likes": row.get("likes", 0),
                    "comments": row.get("comments", 0),
                    "shares": row.get("shares", 0),
                    "followers": row.get("followers", 0),
                    "url": row.get("url", ""),
                    "note": "自动抓取",
                })
                count += 1
            except Exception as exc:
                print(f"[{platform}] 入库失败 {title[:20]}：{exc}")
        context.close()
    return count


def fetch(names: list[str] | None = None, account: str = "default") -> int:
    targets = names or [k for k, v in (CFG.get("platforms") or {}).items() if v.get("enabled")]
    total = 0
    for platform in targets:
        total += fetch_one(platform, account)
    print(f"\n共回填 {total} 条。建议再跑 python run.py --stats 出周报。")
    return total
