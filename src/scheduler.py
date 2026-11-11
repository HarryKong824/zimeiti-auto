"""定时任务：用 Windows 任务计划程序跑选题/周报。

不引入额外依赖，直接调 schtasks。任务名前缀固定，方便批量管理。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .config import ROOT, load_yaml

PREFIX = "ZiMeiTiAuto_"
RUN = ROOT / "run.py"


def _tasks() -> dict:
    return load_yaml("schedule.yaml").get("tasks", {}) or {}


def _task_name(key: str) -> str:
    return f"{PREFIX}{key}"


def _tr_command(args: list[str]) -> str:
    """拼出 schtasks /TR 需要的完整命令行。"""
    python = sys.executable
    parts = [f'"{python}"', f'"{RUN}"', *args]
    return " ".join(parts)


def _run_schtasks(args: list[str]) -> tuple[int, str]:
    result = subprocess.run(
        ["schtasks", *args], capture_output=True, text=True, encoding="gbk", errors="replace"
    )
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def install() -> int:
    """按 config/schedule.yaml 注册任务（已存在则覆盖）。"""
    ok = 0
    total = 0
    for key, spec in _tasks().items():
        if not spec.get("enabled", True):
            continue
        total += 1
        schedule = spec.get("schedule", "DAILY")
        args = [
            "/Create", "/F",
            "/TN", _task_name(key),
            "/TR", _tr_command(spec.get("command", [])),
            "/SC", schedule,
            "/ST", spec.get("time", "08:00"),
        ]
        if schedule.upper() == "WEEKLY":
            args += ["/D", spec.get("day", "MON")]

        code, out = _run_schtasks(args)
        if code == 0:
            ok += 1
            print(f"✓ {spec.get('name', key)}：{schedule} {spec.get('day', '')} {spec.get('time', '')}")
        else:
            print(f"✗ {spec.get('name', key)}：{out.strip()[:200]}")
    print(f"\n注册 {ok}/{total} 个任务。")
    return 0 if ok == total else 1


def remove() -> int:
    ok = 0
    for key in _tasks():
        code, out = _run_schtasks(["/Delete", "/F", "/TN", _task_name(key)])
        if code == 0:
            ok += 1
            print(f"✓ 已删除 {key}")
        else:
            print(f"! {key}：{out.strip()[:120]}")
    print(f"\n删除 {ok} 个任务。")
    return 0


def status() -> int:
    # 用 CSV 输出，避免中文系统下 LIST 字段名被本地化
    code, out = _run_schtasks(["/Query", "/FO", "CSV", "/NH"])
    if code != 0:
        print("查询失败：", out.strip()[:200])
        return 1
    rows = [line for line in out.splitlines() if PREFIX in line]
    if not rows:
        print("还没有注册任何定时任务。跑 python run.py --schedule-install")
        return 0
    for line in rows:
        cells = [c.strip('"') for c in line.split('","')]
        name = cells[0].strip('"')
        nxt = cells[1] if len(cells) > 1 else ""
        print(f"- {name}  下次：{nxt}")
    return 0
