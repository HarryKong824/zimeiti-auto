from __future__ import annotations

import re
from pathlib import Path


def _clock(seconds: float) -> str:
    return f"{int(seconds // 60):02d}:{int(seconds % 60):02d}"


def write(
    path: Path,
    segments: list[dict],
    scores: list[dict],
    chosen: list[int],
    prof: dict,
    duration: float,
) -> Path:
    chosen_set = set(chosen)
    total = sum(segments[i]["end"] - segments[i]["start"] for i in sorted(chosen_set))
    lines = [
        f"# {prof.get('name', path.stem)} 选段确认",
        "",
        f"目标 {prof.get('duration', {}).get('target', 0)} 秒，当前勾选 {len(chosen_set)} 句，"
        f"合计 {total:.1f} 秒。",
        "",
        "**怎么用**：把不想留的那行开头的 `[x]` 改成 `[ ]`，保存后运行：",
        "",
        f"    python run.py --resume {path.parents[2].name} --profiles {prof['key']}",
        "",
        "---",
        "",
    ]
    for index, seg in enumerate(segments):
        mark = "x" if index in chosen_set else " "
        text = seg.get("text", "").replace("\n", " ").strip()
        lines.append(
            f"- [{mark}] {index:03d}  {scores[index]['score']:5.1f}分  "
            f"{_clock(seg['start'])}-{_clock(seg['end'])}  {text}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def read(path: Path) -> list[int]:
    chosen: list[int] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^- \[(x|X|✓)\] (\d{3})\b", line.strip())
        if match:
            chosen.append(int(match.group(2)))
    return chosen
