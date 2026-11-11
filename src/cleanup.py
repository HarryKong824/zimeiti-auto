"""清理 work 目录，避免长期运行堆积几十 G。

保留项：浏览器登录态、demo 素材。其余超过 N 天的 job 目录删除。
"""

from __future__ import annotations

import shutil
import time

from .config import WORK

PROTECT = {"browser", "_demo", "_batch"}


def clean(days: int = 7, dry_run: bool = False) -> int:
    """删除 work 下超过 days 天没动的目录，返回删除数量。"""
    if not WORK.exists():
        return 0
    cutoff = time.time() - days * 86400
    removed = 0
    freed = 0
    for path in sorted(WORK.iterdir()):
        if not path.is_dir() or path.name in PROTECT:
            continue
        if path.stat().st_mtime >= cutoff:
            continue
        size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        freed += size
        if dry_run:
            print(f"[预览] 将删除 {path.name}（{size / 1024 / 1024:.1f} MB）")
        else:
            shutil.rmtree(path, ignore_errors=True)
            print(f"已删除 {path.name}（{size / 1024 / 1024:.1f} MB）")
        removed += 1
    action = "可清理" if dry_run else "已清理"
    print(f"\n{action} {removed} 个目录，{'预计' if dry_run else ''}释放 {freed / 1024 / 1024:.1f} MB")
    return removed
