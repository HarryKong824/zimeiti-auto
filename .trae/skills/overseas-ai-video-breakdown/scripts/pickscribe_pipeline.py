#!/usr/bin/env python3
"""抓取 pickscribe 频道视频 ID、下载转写页并解析为可核验文本。仅使用 Python 标准库。"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote

BASE_URL = "https://pickscribe.com"
VIDEO_ID_RE = re.compile(r"[A-Za-z0-9_-]{5,}")
NAV_WORDS = (
    "Sign in",
    "Get Chrome",
    "Browse Popular",
    "All Channels",
    "Video Transcript",
    "Video Chapters",
    "Video Word",
    "Video Title",
    "Video Analytics",
    "Creator Video",
    "Chat with Video",
    "Pricing",
    "Sitemap",
    "Copyright",
    "Terms Privacy",
)
TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{5,}")


def fetch_html(url: str, timeout: int) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="ignore")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def extract_video_ids(page_html: str) -> list[str]:
    """页面使用相对 /v/ 链接，不能用只匹配完整域名的正则。"""
    return unique(re.findall(r"/v/([A-Za-z0-9_-]{5,})", page_html))


def command_channel(args: argparse.Namespace) -> int:
    output = Path(args.out)
    all_ids: list[str] = []
    manifest = []
    for page in args.pages:
        url = (
            f"{BASE_URL}/channel/{quote(args.channel_id, safe='')}"
            f"?sort={quote(args.sort, safe='')}&page={page}"
        )
        try:
            page_html = fetch_html(url, args.timeout)
        except Exception as exc:
            print(f"FAIL page={page}: {exc}", file=sys.stderr)
            manifest.append({"page": page, "url": url, "error": str(exc)})
            continue
        write_text(output / f"page-{page}.html", page_html)
        ids = extract_video_ids(page_html)
        all_ids.extend(ids)
        manifest.append({"page": page, "url": url, "count": len(ids), "ids": ids})
        print(f"page={page}: {len(ids)} ids")
    all_ids = unique(all_ids)
    write_text(output / "ids.txt", "\n".join(all_ids) + ("\n" if all_ids else ""))
    write_text(output / "channel-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"unique_ids={len(all_ids)} output={output / 'ids.txt'}")
    return 0 if all_ids else 2


def read_ids(args: argparse.Namespace) -> list[str]:
    raw_ids = list(args.ids or [])
    if args.ids_file:
        for line in Path(args.ids_file).read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                raw_ids.append(line)
    ids = unique(raw_ids)
    invalid = [video_id for video_id in ids if not VIDEO_ID_RE.fullmatch(video_id)]
    if invalid:
        raise ValueError(f"非法视频 ID: {', '.join(invalid)}")
    return ids


def download_one(video_id: str, output: Path, timeout: int, retries: int) -> dict:
    url = f"{BASE_URL}/v/{video_id}"
    last_error = ""
    for attempt in range(1, retries + 1):
        try:
            page_html = fetch_html(url, timeout)
            write_text(output / f"{video_id}.html", page_html)
            return {"id": video_id, "ok": True, "bytes": len(page_html.encode("utf-8")), "attempts": attempt}
        except Exception as exc:
            last_error = str(exc)
            if attempt < retries:
                time.sleep(min(1.5 * attempt, 3.0))
    return {"id": video_id, "ok": False, "error": last_error, "attempts": retries}


def command_fetch(args: argparse.Namespace) -> int:
    ids = read_ids(args)
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)
    pending = [video_id for video_id in ids if not (output / f"{video_id}.html").exists()]
    skipped = [video_id for video_id in ids if video_id not in pending]
    print(f"total={len(ids)} existing={len(skipped)} pending={len(pending)}")
    results = []
    if pending:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(download_one, video_id, output, args.timeout, args.retries): video_id
                for video_id in pending
            }
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                if result["ok"]:
                    print(f"OK {result['id']} attempts={result['attempts']}")
                else:
                    print(f"FAIL {result['id']}: {result['error']}", file=sys.stderr)
    report = {
        "ok": [item["id"] for item in results if item["ok"]],
        "failed": [item for item in results if not item["ok"]],
        "skipped": skipped,
        "results": results,
    }
    write_text(output / "fetch-report.json", json.dumps(report, ensure_ascii=False, indent=2))
    print(f"downloaded={len(report['ok'])} failed={len(report['failed'])} skipped={len(skipped)}")
    return 1 if report["failed"] else 0


def clean_page(page_html: str) -> tuple[str, str, str, str]:
    title_match = re.search(r"<title>(.*?)</title>", page_html, re.S | re.I)
    title = html_lib.unescape(title_match.group(1).strip()) if title_match else "UNKNOWN"
    title = re.sub(r"\s*\|\s*.*$", "", title).strip()

    view_match = re.search(r"(\d[\d.,]*)\s*[kKmM]?\s*(?:views?|plays?)", page_html, re.I)
    views = view_match.group(0).strip() if view_match else "未核实"
    duration_match = re.search(r"(?<!\d)(\d{1,2}:\d{2}(?::\d{2})?)(?!\d)", page_html)
    duration = duration_match.group(1) if duration_match else "未核实"

    # 侧栏相关视频不是转写正文，必须在拆分文本前移除。
    related = re.search(r"<[^>]+>\s*Related Videos\s*</[^>]+>(?=\s*<a\b)", page_html, flags=re.I)
    if related:
        page_html = page_html[:related.start()]

    body = re.sub(r"<script[^>]*>.*?</script>", " ", page_html, flags=re.S | re.I)
    body = re.sub(r"<style[^>]*>.*?</style>", " ", body, flags=re.S | re.I)
    body = re.sub(r"<svg[^>]*>.*?</svg>", " ", body, flags=re.S | re.I)
    body = re.sub(r"<img[^>]*>", " ", body, flags=re.I)

    parts = []
    for segment in re.split(r"<[^>]+>", body):
        segment = html_lib.unescape(segment.strip())
        if len(segment) <= 30 or segment.count(" ") <= 3:
            continue
        # 只在短文本上过滤导航，避免误删含 pricing 等词的长段正文。
        if len(segment) < 300 and any(word.lower() in segment.lower() for word in NAV_WORDS):
            continue
        if "| Transcript" in segment and len(segment) < 100:
            continue
        parts.append(segment)
    combined = re.sub(r"\s+", " ", " ".join(parts)).strip()
    combined = re.sub(r"^Like it\? Make Scribe even better by .*?😊\s*", "", combined, count=1, flags=re.S)

    # pickscribe 常把“标题 | 频道 Transcripts 标题”放在正文前，第二次标题后才是转写。
    if title != "UNKNOWN":
        occurrences = list(re.finditer(re.escape(title), combined, flags=re.I))
        if len(occurrences) >= 2:
            second = occurrences[1]
            combined = combined[second.end():].strip()
    return title, views, duration, combined


def command_parse(args: argparse.Namespace) -> int:
    raw = Path(args.raw)
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)
    files = sorted(raw.glob("*.html"))
    if not files:
        print(f"没有找到 HTML: {raw}", file=sys.stderr)
        return 2
    metadata = []
    for path in files:
        video_id = path.stem
        try:
            title, views, duration, text = clean_page(path.read_text(encoding="utf-8", errors="ignore"))
            word_count = len(text.split())
            status = "ok" if word_count >= args.min_words else "needs_review"
            clean_text = (
                f"VIDEO_ID: {video_id}\nTITLE: {title}\nPLAY_COUNT: {views}\n"
                f"DURATION: {duration}\nWORD_COUNT: {word_count}\nSTATUS: {status}\n"
                f"SOURCE: {BASE_URL}/v/{video_id}\n{'=' * 60}\n\n{text}\n"
            )
            write_text(output / f"{video_id}.txt", clean_text)
            metadata.append(
                {
                    "id": video_id,
                    "title": title,
                    "views": views,
                    "duration": duration,
                    "word_count": word_count,
                    "status": status,
                    "source": f"{BASE_URL}/v/{video_id}",
                }
            )
            print(f"{status:12} wc={word_count:6} {video_id} | {title[:70]}")
        except Exception as exc:
            metadata.append({"id": video_id, "status": "error", "error": str(exc)})
            print(f"ERROR {video_id}: {exc}", file=sys.stderr)
    write_text(output / "metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))
    review = sum(item["status"] != "ok" for item in metadata)
    print(f"parsed={len(metadata)} needs_review={review} metadata={output / 'metadata.json'}")
    print("注意：解析状态不等于证据 A，仍需人工抽查转写完整性。")
    return 0


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("必须是正整数")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    channel = subparsers.add_parser("channel", help="按频道分页提取视频 ID")
    channel.add_argument("--channel-id", required=True)
    channel.add_argument("--pages", type=positive_int, nargs="+", default=[1])
    channel.add_argument("--sort", default="views")
    channel.add_argument("--timeout", type=positive_int, default=60)
    channel.add_argument("--out", required=True)
    channel.set_defaults(func=command_channel)

    fetch = subparsers.add_parser("fetch", help="并行下载转写页，已有文件自动跳过")
    fetch.add_argument("--ids", nargs="*")
    fetch.add_argument("--ids-file")
    fetch.add_argument("--out", required=True)
    fetch.add_argument("--workers", type=positive_int, default=6)
    fetch.add_argument("--timeout", type=positive_int, default=60)
    fetch.add_argument("--retries", type=positive_int, default=3)
    fetch.set_defaults(func=command_fetch)

    parse = subparsers.add_parser("parse", help="清洗本地 HTML 并生成文本与 metadata.json")
    parse.add_argument("--raw", required=True)
    parse.add_argument("--out", required=True)
    parse.add_argument("--min-words", type=positive_int, default=100)
    parse.set_defaults(func=command_parse)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "fetch" and not args.ids and not args.ids_file:
        parser.error("fetch 需要 --ids 或 --ids-file")
    try:
        return args.func(args)
    except ValueError as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
