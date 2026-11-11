from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from . import asr, comments, compose, copywrite, cover, images, ingest, package, review, select, storyboard, xhs_cards
from .config import STYLE, WORK, env, ensure_dirs
from .profiles import SCORING, box, names as profile_names, resolve


def _normalize_loudness(src: Path, target_lufs: float = -16.0) -> Path:
    """响度标准化到 LUFS -16（YouTube/抖音推荐值）。失败返回原文件不中断。"""
    dst = src.with_name(src.stem + "_norm.wav")
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-filter_complex", f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11",
        "-ar", "48000", "-ac", "1", str(dst),
    ]
    try:
        subprocess.run(cmd, capture_output=True, check=True, timeout=120)
        return dst
    except Exception:
        return src


def _log(step: str, message: str) -> None:
    print(f"[{step}] {message}", flush=True)


def _apply_plan(plan: dict, full_audio: Path, sub: Path, duration: float, key: str) -> tuple[dict, float]:
    ranges = plan["ranges"]
    if len(ranges) == 1 and abs(ranges[0][1] - duration) < 0.02:
        shutil.copy2(full_audio, sub / "audio.wav")
        detail = "全片"
    else:
        select.cut_audio(full_audio, ranges, sub / "audio.wav")
        detail = f"{len(ranges)} 段"
    tr = plan["transcript"]
    out_duration = float(tr.get("duration") or duration)
    _log("3/5 选段", f"{key}：{detail} → {out_duration:.0f}s")
    return tr, out_duration


def run_pipeline(
    source: str | Path | None = None,
    profiles: list[str] | None = None,
    platforms: list[str] | None = None,
    provider: str = "placeholder",
    srt: str | Path | None = None,
    title: str = "",
    job_id: str | None = None,
    resume: str | None = None,
    force_review: bool = False,
) -> list[Path]:
    ensure_dirs()
    started = time.time()

    if resume:
        job_dir = WORK / resume
        meta = json.loads((job_dir / "meta.json").read_text(encoding="utf-8"))
        transcript = json.loads((job_dir / "transcript.json").read_text(encoding="utf-8"))
        _log("0/5 续跑", f"{resume}  时长 {meta['duration']:.1f}s  转写已复用")
    else:
        job_dir, meta = ingest.prepare(source, job_id)
        (job_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        _log("1/5 素材", f"{meta['job_id']}  时长 {meta['duration']:.1f}s")
        transcript = asr.transcribe(Path(meta["audio"]), srt_path=srt)
        (job_dir / "transcript.json").write_text(
            json.dumps(transcript, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _log("2/5 转写", f"{len(transcript['segments'])} 段（{transcript.get('source')}）")

    if not transcript.get("segments"):
        raise RuntimeError(
            "没有识别到语音内容。请确认视频/音频里有说话声，"
            "或用 --srt 直接提供字幕文件。"
        )

    full_audio = _normalize_loudness(Path(meta["audio"]))
    duration_all = float(meta["duration"])
    pending: list[Path] = []
    results: list[Path] = []

    for key in profiles or profile_names():
        prof = resolve(key)
        sub = job_dir / "profiles" / key
        sub.mkdir(parents=True, exist_ok=True)

        sel = prof.get("selection", {})
        pad = float(sel.get("pad", 0.08))
        hook = bool(prof.get("hook", {}).get("enabled", False))
        target = float(prof.get("duration", {}).get("target", 0) or 0)
        mode = "review" if force_review else sel.get("mode", "auto")
        review_file = sub / "选段.md"

        if review_file.exists():
            chosen = review.read(review_file)
            if not chosen:
                _log("跳过", f"{key}：{review_file} 里一句都没勾选")
                continue
            plan = select.plan_selected(transcript, chosen, duration_all, SCORING, pad, hook)
        elif mode == "review":
            scores = select.score_segments(transcript.get("segments", []), SCORING)
            chosen = select.choose(transcript.get("segments", []), scores, target or duration_all)
            review.write(
                review_file, transcript.get("segments", []), scores, chosen, prof, duration_all
            )
            pending.append(review_file)
            _log("⏸ 待确认", f"{key}：{review_file}")
            continue
        else:
            plan = select.plan(transcript, duration_all, target, SCORING, pad, hook)

        tr, duration = _apply_plan(plan, full_audio, sub, duration_all, key)
        (sub / "transcript.json").write_text(
            json.dumps(tr, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        pacing = prof.get("pacing", {})
        shots = storyboard.build(
            tr, duration, pacing.get("shot_min"), pacing.get("shot_max"),
            image_provider=env("IMAGE_PROVIDER", "placeholder"),
        )
        shots = storyboard.refine_with_llm(shots, topic=title)
        (sub / "storyboard.json").write_text(
            json.dumps(shots, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        width, height = box(prof.get("aspect", "9:16"))
        image_paths = images.render_all(shots, sub, provider=provider, video_size=(width, height))
        final = compose.compose(shots, image_paths, tr, sub, width, height, prof.get("subtitle"))

        headline = title or (shots[0]["keyword"] if shots else meta["job_id"])
        subline = "  ·  ".join(dict.fromkeys(s["keyword"] for s in shots[:3])) if shots else ""
        cover_count = int(STYLE.get("cover", {}).get("variants", 2))
        covers = cover.make_covers(headline[:18], subline[:30], sub, cover_count)
        cover_path = covers[0]

        plats = platforms or prof.get("platforms", [])
        copies = copywrite.generate(tr.get("text", ""), shots, plats)
        cms = comments.generate(tr.get("text", ""), shots, plats)
        cards = xhs_cards.generate(tr.get("text", ""), shots, sub) if "xhs" in plats else []
        target_dir = package.package(
            sub, final, cover_path, copies, shots,
            name=f"{job_dir.name}/{key}", comments=cms, xhs_cards=cards,
        )
        results.append(target_dir)
        _log(
            "4/5 出片",
            f"{key}（{prof.get('name')}）{duration:.0f}s / {len(shots)} 镜 / "
            f"{width}x{height} / {len(plats)} 平台 → {target_dir}",
        )

    if pending:
        _log("5/5 等待", "以下版本需要你确认后再跑：")
        for path in pending:
            _log("   ", str(path))
        _log(
            "    ",
            f"改完运行：python run.py --resume {job_dir.name} --profiles "
            + ",".join(p.parent.name for p in pending),
        )
    else:
        _log("5/5 完成", f"用时 {time.time() - started:.0f}s，共 {len(results)} 个版本")
    return results
