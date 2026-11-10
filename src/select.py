from __future__ import annotations

import re
import subprocess
from pathlib import Path


def score_segments(segments: list[dict], scoring: dict) -> list[dict]:
    weights = scoring.get("weights", {})
    patterns = {k: re.compile(v) for k, v in scoring.get("patterns", {}).items()}
    total = len(segments)
    result = []
    for index, seg in enumerate(segments):
        text = seg.get("text", "")
        value, hits = 0.0, []
        for key, regex in patterns.items():
            if regex.search(text):
                value += float(weights.get(key, 0))
                hits.append(key)
        value += float(weights.get("position", 0)) * (1 - index / max(total - 1, 1))
        result.append({"score": round(value, 3), "hits": hits})
    return result


def choose(segments: list[dict], scores: list[dict], target: float) -> list[int]:
    """按分数贪心选段，直到凑够目标时长。"""
    order = sorted(range(len(segments)), key=lambda i: scores[i]["score"], reverse=True)
    chosen: list[int] = []
    total = 0.0
    for index in order:
        duration = segments[index]["end"] - segments[index]["start"]
        if chosen and total + duration > target * 1.05:
            continue
        chosen.append(index)
        total += duration
        if total >= target:
            break
    if not chosen:
        chosen = list(range(min(2, len(segments))))
    return sorted(chosen)


def build_ranges(segments: list[dict], chosen: list[int], pad: float, duration: float) -> list[tuple[float, float]]:
    ranges: list[tuple[float, float]] = []
    for index in chosen:
        start = max(0.0, segments[index]["start"] - pad)
        end = min(duration, segments[index]["end"] + pad)
        if ranges and start <= ranges[-1][1] + 0.01:
            ranges[-1] = (ranges[-1][0], max(ranges[-1][1], end))
        else:
            ranges.append((start, end))
    return ranges


def apply_hook(
    ranges: list[tuple[float, float]], segments: list[dict], chosen: list[int], scores: list[dict]
) -> list[tuple[float, float]]:
    """把分数最高的一段提到最前面。"""
    if not chosen:
        return ranges
    top = max(chosen, key=lambda i: scores[i]["score"])
    start, end = segments[top]["start"], segments[top]["end"]
    index = next(
        (k for k, r in enumerate(ranges) if r[0] - 1e-6 <= start and end <= r[1] + 1e-6), None
    )
    if index is None or index == 0:
        return ranges
    item = ranges.pop(index)
    ranges.insert(0, item)
    return ranges


def cut_audio(source: Path, ranges: list[tuple[float, float]], out: Path) -> None:
    parts, labels = [], []
    for i, (start, end) in enumerate(ranges):
        parts.append(f"[0:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[a{i}]")
        labels.append(f"[a{i}]")
    graph = ";".join(parts) + f";{''.join(labels)}concat=n={len(ranges)}:v=0:a=1[out]"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(source), "-filter_complex", graph, "-map", "[out]", str(out)],
        capture_output=True,
        check=True,
    )


def rebuild(segments: list[dict], ranges: list[tuple[float, float]]) -> dict:
    """把原时间轴映射到剪切后的新时间轴。"""
    out: list[dict] = []
    cursor = 0.0
    for range_start, range_end in ranges:
        for seg in segments:
            if seg["end"] <= range_start + 1e-6 or seg["start"] >= range_end - 1e-6:
                continue
            start = max(seg["start"], range_start)
            end = min(seg["end"], range_end)
            if end - start < 0.15:
                continue
            out.append(
                {
                    "start": round(cursor + start - range_start, 3),
                    "end": round(cursor + end - range_start, 3),
                    "text": seg["text"],
                }
            )
        cursor += range_end - range_start
    return {
        "language": "zh",
        "segments": out,
        "text": "".join(s["text"] for s in out),
        "duration": round(cursor, 3),
        "source": "cut",
    }


def plan_selected(
    transcript: dict,
    chosen: list[int],
    duration: float,
    scoring: dict,
    pad: float,
    hook: bool,
) -> dict:
    """按人工确认过的句子重新组时间轴。"""
    segments = transcript.get("segments", [])
    picked = sorted({i for i in chosen if 0 <= i < len(segments)})
    if not picked:
        return {"ranges": [(0.0, duration)], "transcript": transcript}
    ranges = build_ranges(segments, picked, pad, duration)
    if hook:
        scores = score_segments(segments, scoring)
        ranges = apply_hook(ranges, segments, picked, scores)
    return {"ranges": ranges, "transcript": rebuild(segments, ranges)}


def plan(
    transcript: dict,
    duration: float,
    target: float,
    scoring: dict,
    pad: float,
    hook: bool,
) -> dict:
    segments = transcript.get("segments", [])
    if not segments:
        return {"ranges": [], "transcript": transcript, "candidates": []}

    full = sum(s["end"] - s["start"] for s in segments)
    if target <= 0 or target >= full * 0.95:
        return {"ranges": [(0.0, duration)], "transcript": transcript, "candidates": []}

    scores = score_segments(segments, scoring)
    chosen = choose(segments, scores, target)
    ranges = build_ranges(segments, chosen, pad, duration)
    if hook:
        ranges = apply_hook(ranges, segments, chosen, scores)

    candidates = [
        {
            "index": i,
            "score": scores[i]["score"],
            "hits": scores[i]["hits"],
            "text": segments[i]["text"],
            "chosen": i in chosen,
        }
        for i in sorted(range(len(segments)), key=lambda i: scores[i]["score"], reverse=True)
    ]
    return {
        "ranges": ranges,
        "transcript": rebuild(segments, ranges),
        "candidates": candidates,
    }
