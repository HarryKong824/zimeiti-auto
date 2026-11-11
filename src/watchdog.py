"""监听 inbox/ 目录，发现新文件自动跑流水线。

设计：
- 每 30 秒扫一次 inbox/ 下的音视频文件
- 新文件（不在 seen set 里）→ 触发 pipeline
- 跑之前把路径 append 到 work/_inbox_seen.json，防止下次重复
- 默认后台运行，Ctrl+C 退出
- 发布按钮仍然是人点——监听只到出片+填表，不碰 publish

用法：
    python run.py --watch                # 前台监听（Ctrl+C 退出）
    python run.py --watch --once         # 扫一次就走（适合 cron 调用）
    python run.py --watch --interval 60  # 改轮询间隔
"""

from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

from .config import INBOX, WORK


MEDIA_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".wav", ".mp3", ".m4a"}
SEEN_FILE = WORK / "_inbox_seen.json"


def _load_seen() -> set[str]:
    if not SEEN_FILE.exists():
        return set()
    try:
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    except Exception:
        return set()


def _save_seen(seen: set[str]) -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=2), encoding="utf-8")


def scan() -> list[Path]:
    """返回 inbox/ 下所有没处理过的音视频文件。"""
    if not INBOX.exists():
        return []
    seen = _load_seen()
    new = []
    for p in INBOX.iterdir():
        if not p.is_file() or p.suffix.lower() not in MEDIA_EXTS:
            continue
        key = str(p.resolve())
        if key not in seen:
            new.append(p)
    return new


def mark_seen(paths: list[Path]) -> None:
    seen = _load_seen()
    for p in paths:
        seen.add(str(p.resolve()))
    _save_seen(seen)


def loop(interval: int = 30, once: bool = False) -> None:
    """轮询主循环。once=True 扫一次就退出。"""
    print(f"[inbox] 开始监听 {INBOX}，每 {interval}s 扫一次", flush=True)
    while True:
        try:
            new_files = scan()
            if new_files:
                for f in new_files:
                    print(f"\n[inbox] 发现新文件：{f.name}", flush=True)
                    try:
                        from . import pipeline
                        pipeline.run_pipeline(source=str(f))
                        mark_seen([f])
                    except Exception as exc:
                        print(f"[inbox] 处理失败 {f.name}: {exc}", flush=True)
            elif once:
                print("[inbox] 无新文件，--once 模式退出", flush=True)
                return
            else:
                print(f"[inbox] {dt.datetime.now():%H:%M:%S} 扫描无新文件", flush=True)
        except KeyboardInterrupt:
            print("\n[inbox] 退出监听", flush=True)
            return
        except Exception as exc:
            print(f"[inbox] 扫描异常：{exc}", flush=True)
        time.sleep(interval)
