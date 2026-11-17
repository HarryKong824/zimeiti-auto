"""发布前自动上传。

只做四件事：打开创作页、把视频塞进去、填好标题正文标签、传封面。
「发布」按钮永远留给人点。

登录态存在 work/browser/<平台>/<账号>/，第一次要扫码，之后复用。
Playwright 用系统已装的 Chrome（channel=chrome），不额外下载浏览器。
"""

from __future__ import annotations

from pathlib import Path

from .config import WORK, env, load_yaml

CFG = load_yaml("publish.yaml")


def platforms() -> list[str]:
    return list((CFG.get("platforms") or {}).keys())


def _parse_copy(text: str) -> dict:
    """解析 package.py 生成的 copy_*.md。"""
    result = {"title": "", "body": "", "tags": ""}
    section = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            section = stripped[3:].strip()
            continue
        if not stripped:
            continue
        if section == "标题":
            result["title"] = stripped
        elif section == "正文":
            result["body"] = (result["body"] + "\n" + stripped).strip()
        elif section == "标签":
            result["tags"] = stripped
    return result


def _read_copy(target: Path, platform: str) -> dict:
    """优先决策者版，没有就学习者版，都没有返回空。"""
    for audience in ("decision", "learner"):
        path = target / f"copy_{platform}_{audience}.md"
        if path.exists():
            return _parse_copy(path.read_text(encoding="utf-8"))
    return {}


def _find(page, selectors: list[str], timeout: int = 8000):
    """按候选顺序找第一个可见元素。"""
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            locator.wait_for(state="visible", timeout=timeout)
            return locator
        except Exception:
            continue
    return None


def _fill(locator, text: str) -> bool:
    if not locator or not text:
        return False
    try:
        locator.click(timeout=5000)
        locator.fill(text, timeout=5000)
        return True
    except Exception:
        try:
            locator.type(text, delay=20, timeout=8000)
            return True
        except Exception:
            return False


def _log_publish(
    platform: str,
    target: Path,
    status: str,
    account: str = "default",
    issues: list | None = None,
    url: str = "",
) -> None:
    """每次发布尝试落一条记录到 data/publish_log.jsonl。

    status: blocked（预校验没过）/ filled（填完待点）/ manual（选择器没找到，转手动）/ linked（已回填链接）
    有了这个日志，才能回答「这条到底发没发、卡在哪」。
    """
    import datetime as dt
    import json

    from .config import DATA

    DATA.mkdir(parents=True, exist_ok=True)
    record = {
        "time": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "platform": platform,
        "job": target.parent.name if target.name in ("short", "mid") else target.name,
        "version": target.name,
        "account": account,
        "status": status,
        "url": url,
        "issues": [i.as_dict() if hasattr(i, "as_dict") else i for i in (issues or [])],
    }
    with open(DATA / "publish_log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _auth_guide(name: str, platform: str, url: str, profile_dir: Path) -> None:
    """登录态失效时的结构化引导，而不是只丢一句报错。"""
    print(f"\n[{name}] 登录态失效，需要重新授权")
    print(f"  1. 浏览器窗口已停在登录页，直接扫码")
    print(f"  2. 登录态会存进 {profile_dir}，之后一直复用，不用重复扫")
    print(f"  3. 如果窗口被关了，重新跑：python run.py --publish <job目录> --to {platform}")
    print(f"  4. 创作页地址：{url}\n")


def upload(
    target: Path,
    platform: str,
    confirm: bool = True,
    account: str = "default",
) -> bool:
    """把 target 目录里的成品推进创作页。返回是否填表成功。

    account 用于多账号：登录态按 平台/账号 分开存，互不干扰。
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("没装 playwright。先跑：pip install playwright")

    spec = (CFG.get("platforms") or {}).get(platform)
    if not spec:
        raise SystemExit(f"没有配置这个平台：{platform}（可选：{', '.join(platforms())}）")

    video = target / "final.mp4"
    if not video.exists():
        raise SystemExit(f"找不到成品：{video}")

    cover = target / "cover.png"
    # 横版平台优先用 16:9 封面
    if platform in ("bilibili", "shipinhao") and (target / "cover_wide.png").exists():
        cover = target / "cover_wide.png"

    # 如果有备选封面，让用户选 A/B（为后续 A/B 测试积累数据）
    variant_picked = "A"
    alt = target / f"{cover.stem}_b{cover.suffix}"
    if alt.exists() and confirm:
        choice = input(f"  发现备选封面 B（{alt.name}），选 A 还是 B？[A/b]：").strip().lower()
        if choice == "b":
            cover = alt
            variant_picked = "B"

    name = spec.get("name", platform)

    print(f"[{name}] 使用封面：{cover.name}（方案 {variant_picked}）")
    copy = _read_copy(target, platform)
    browser_cfg = CFG.get("browser") or {}

    # 预校验：能在本地判断的问题，绝不等到打开浏览器、填完表才发现
    from . import preflight

    issues = preflight.check(target, platform, copy, cover)
    for issue in issues:
        mark = "❌" if issue.level == "error" else "⚠️"
        print(f"[{name}] {mark} {issue.field}：{issue.message}")
    if preflight.has_error(issues):
        print(f"[{name}] 预校验未通过，已中止（没打开浏览器，也没花钱）")
        _log_publish(platform, target, "blocked", account, issues)
        return False

    print(f"[{name}] 打开 {spec['url']}（账号：{account}）")
    profile_dir = WORK / "browser" / platform / account
    profile_dir.mkdir(parents=True, exist_ok=True)

    launch_opts: dict = {
        "user_data_dir": str(profile_dir),
        "channel": browser_cfg.get("channel", "chrome"),
        "headless": bool(browser_cfg.get("headless", False)),
        "slow_mo": int(browser_cfg.get("slow_mo", 120)),
        "viewport": {"width": 1440, "height": 900},
    }
    # 代理：环境变量 BROWSER_PROXY 优先，其次 HTTP_PROXY
    proxy_server = env("BROWSER_PROXY") or env("HTTP_PROXY")
    if proxy_server:
        launch_opts["proxy"] = {"server": proxy_server}
        print(f"[{name}] 走代理 {proxy_server}")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(**launch_opts)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(spec["url"], wait_until="domcontentloaded")

        # 登录失效检测：停在登录页时给结构化引导，就地等扫码，窗口不关
        login_urls = spec.get("login_url_patterns", [])
        if any(pat in page.url for pat in login_urls):
            _auth_guide(name, platform, spec["url"], profile_dir)
            if not confirm:
                _log_publish(
                    platform, target, "manual", account,
                    [{"field": "auth", "message": "登录态失效", "level": "error"}],
                )
                context.close()
                return False
            input("  扫码登录完成后按回车，我继续…")
            page.goto(spec["url"], wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

        selectors = spec.get("selectors", {})
        file_input = _find(page, selectors.get("file", []), timeout=12000)
        if file_input is None:
            print(f"[{name}] 看起来没登录。请在浏览器窗口里扫码登录。")
            if confirm:
                input("  登录完成后按回车，我继续上传…")
            page.goto(spec["url"], wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            file_input = _find(page, selectors.get("file", []), timeout=20000)
        auto_uploaded = file_input is not None
        if file_input is None:
            print(f"[{name}] 还是找不到上传入口。页面可能改版了，改 config/publish.yaml 里的 selectors。")
            if confirm:
                input("  你手动传完后按回车，我继续填标题…")
        else:
            print(f"[{name}] 上传视频 {video.name}")
            file_input.set_input_files(str(video))
            page.wait_for_timeout(5000)

        if cover.exists() and selectors.get("cover"):
            cover_input = _find(page, selectors["cover"], timeout=3000)
            if cover_input:
                cover_input.set_input_files(str(cover))
                print(f"[{name}] 上传封面")

        if copy.get("title") and _fill(_find(page, selectors.get("title", [])), copy["title"]):
            print(f"[{name}] 标题已填：{copy['title'][:20]}")
        if copy.get("body"):
            body = copy["body"] + ("\n" + copy["tags"] if copy.get("tags") else "")
            if _fill(_find(page, selectors.get("body", [])), body):
                print(f"[{name}] 正文已填")

        _log_publish(platform, target, "filled" if auto_uploaded else "manual", account, issues)
        print(f"[{name}] 填完了。请在浏览器里检查，然后自己点「发布」。")
        url = ""
        if confirm:
            url = input("  点完发布按回车；顺手粘贴作品链接（留空跳过）：").strip()
        if url:
            _record_link(target, platform, url, cover_variant=variant_picked)
            _log_publish(platform, target, "linked", account, issues, url=url)
            print(f"[{name}] 链接已记录到 links.md / data/links.csv")
        context.close()

    return True


def _record_link(target: Path, platform: str, url: str, cover_variant: str = "A") -> None:
    """把作品链接记到版本目录 links.md 和 data/links.csv，方便周报对应。"""
    import csv
    import datetime as dt

    from .config import DATA, PLATFORMS

    label = PLATFORMS.get(platform, {}).get("name", platform)
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    line = f"- {now}　{label}（封面 {cover_variant}）：{url}\n"

    links_md = target / "links.md"
    if not links_md.exists():
        links_md.write_text("# 作品链接\n\n", encoding="utf-8")
    with open(links_md, "a", encoding="utf-8") as f:
        f.write(line)

    DATA.mkdir(parents=True, exist_ok=True)
    csv_path = DATA / "links.csv"
    is_new = not csv_path.exists()
    with open(csv_path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["date", "platform", "version", "cover_variant", "url"])
        writer.writerow([now, platform, target.name, cover_variant, url])


def run(
    target: Path,
    names: list[str],
    confirm: bool = True,
    account: str = "default",
    accounts: dict[str, str] | None = None,
) -> list[str]:
    """accounts 可为每个平台单独指定账号，如 {"douyin": "小号"}。"""
    done = []
    for platform in names:
        acc = (accounts or {}).get(platform, account)
        if upload(target, platform, confirm, account=acc):
            done.append(platform)
    return done
