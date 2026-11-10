from __future__ import annotations

# 句末标点：遇到就收尾，不再往下拼
SENTENCE_END = "。！？!?…"
# 可以断行的软标点，切长句时优先在这些位置切
SOFT_BREAK = "，。！？；、：,.;:!?"


def _meaningful(text: str) -> bool:
    return any(char.isalnum() or "\u4e00" <= char <= "\u9fff" for char in text)


def _cut(text: str, limit: int) -> list[str]:
    """按上限切长句，优先切在标点上，且不切断英文单词或数字。"""
    if len(text) <= limit:
        return [text]
    parts, rest = [], text
    while len(rest) > limit:
        window = rest[:limit]
        pos = -1
        for index in range(len(window) - 1, max(int(limit * 0.5), 1) - 1, -1):
            if window[index] in SOFT_BREAK:
                pos = index
                break
        if pos < 0:
            pos = limit - 1
            # 向右补全整词：AI / GPT-4 / 2026
            while pos + 1 < len(rest) and rest[pos].isascii() and rest[pos].isalnum() \
                    and rest[pos + 1].isascii() and rest[pos + 1].isalnum():
                pos += 1
        parts.append(rest[: pos + 1].strip())
        rest = rest[pos + 1 :].lstrip()
    if rest:
        parts.append(rest)
    return [part for part in parts if part]


def build(segments: list[dict], cfg: dict | None = None) -> list[dict]:
    """把转写的碎句合成字幕条：合并短句、按时长均分、保证最短停留。"""
    cfg = cfg or {}
    chars_per_line = int(cfg.get("chars_per_line", 14))
    max_chars = chars_per_line * int(cfg.get("lines", 2))
    min_cue = float(cfg.get("min_cue", 1.2))
    max_cue = float(cfg.get("max_cue", 5.0))
    gap = float(cfg.get("merge_gap", 0.8))

    merged: list[dict] = []
    current: dict | None = None
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text or not _meaningful(text):
            continue
        start, end = float(seg["start"]), float(seg["end"])
        if current and (
            start - current["end"] > gap
            or len(current["text"]) + len(text) > max_chars
            or end - current["start"] > max_cue
            or current["text"].endswith(tuple(SENTENCE_END))
        ):
            merged.append(current)
            current = None
        if current is None:
            current = {"start": start, "end": end, "text": text}
        else:
            current["text"] += text
            current["end"] = end
    if current:
        merged.append(current)

    cues: list[dict] = []
    for block in merged:
        pieces = _cut(block["text"], max_chars)
        total = sum(len(piece) for piece in pieces) or 1
        cursor = block["start"]
        for piece in pieces:
            span = (block["end"] - block["start"]) * len(piece) / total
            cues.append({"start": cursor, "end": cursor + span, "text": piece})
            cursor += span

    for index, cue in enumerate(cues):
        ceiling = cues[index + 1]["start"] if index + 1 < len(cues) else 1e9
        if cue["end"] - cue["start"] < min_cue:
            cue["end"] = min(cue["start"] + min_cue, ceiling)
    return cues
