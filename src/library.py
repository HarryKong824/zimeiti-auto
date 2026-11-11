"""素材库复用。

用户把可复用的 B-roll 图片/视频片段放到 library/ 下，
脚本出图时优先从库里挑匹配关键词的素材，没有再调 API 或画占位图。

素材打标签两种方式：
1. 文件名包含关键词：如「企业_办公室.png」「数据_图表.jpg」
2. 同名 .yaml 侧车文件：tags: [企业, 办公室]
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import yaml

from .config import LIBRARY, WORK

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".m4v", ".webm"}


def _tags_from_name(path: Path) -> list[str]:
    """从文件名提取标签：下划线/空格/短横线分隔，去掉纯数字。"""
    stem = path.stem
    parts = re.split(r"[_\-\s]+", stem)
    return [p for p in parts if p and not p.isdigit()]


def _tags_from_sidecar(path: Path) -> list[str] | None:
    """读同名 .yaml 侧车的 tags 字段。"""
    sidecar = path.with_suffix(".yaml")
    if not sidecar.exists():
        return None
    try:
        data = yaml.safe_load(sidecar.read_text(encoding="utf-8")) or {}
        tags = data.get("tags")
        if isinstance(tags, list):
            return [str(t) for t in tags]
    except Exception:
        pass
    return None


def _asset_tags(path: Path) -> list[str]:
    sidecar = _tags_from_sidecar(path)
    if sidecar is not None:
        return sidecar
    return _tags_from_name(path)


def _scan(exts: set[str]) -> list[dict]:
    """扫描 library/images/ 和 library/videos/，返回指定后缀的素材及标签。"""
    assets = []
    for sub in ("images", "videos"):
        img_dir = LIBRARY / sub
        if not img_dir.exists():
            continue
        for path in sorted(img_dir.iterdir()):
            if path.suffix.lower() not in exts:
                continue
            assets.append({"path": path, "tags": _asset_tags(path)})
    return assets


def list_images() -> list[dict]:
    return _scan(IMAGE_EXTS)


def list_videos() -> list[dict]:
    return _scan(VIDEO_EXTS)


def pick_asset(keywords: list[str]) -> Path | None:
    """图片和视频一起匹配，返回最佳命中。视频优先（动态画面更有吸引力）。"""
    if not keywords:
        return None
    kw_lower = [k.lower() for k in keywords]

    best_path, best_score, best_is_video = None, 0, False
    for asset in list_videos() + list_images():
        tags_lower = [t.lower() for t in asset["tags"]]
        score = sum(1 for kw in kw_lower if any(kw in t or t in kw for t in tags_lower))
        if not score:
            continue
        is_video = asset["path"].suffix.lower() in VIDEO_EXTS
        # 同分时视频优先
        if score > best_score or (score == best_score and is_video and not best_is_video):
            best_path, best_score, best_is_video = asset["path"], score, is_video
    return best_path


def pick_image(keywords: list[str]) -> Path | None:
    """只匹配图片（保留兼容）。"""
    if not keywords:
        return None
    kw_lower = [k.lower() for k in keywords]
    best_path, best_score = None, 0
    for asset in list_images():
        tags_lower = [t.lower() for t in asset["tags"]]
        score = sum(1 for kw in kw_lower if any(kw in t or t in kw for t in tags_lower))
        if score > best_score:
            best_score, best_path = score, asset["path"]
    return best_path


def collect_from(job_dir: Path) -> int:
    """把一个版本目录里生成的图收进素材库，带关键词侧车。返回收录数量。

    传 outbox/<job>/<版本> 也行：没有 images/ 时自动去 work/<job>/<版本> 找。
    """
    img_dir = job_dir / "images"
    if not img_dir.exists():
        # outbox/<job>/<版本> → 映射回 work/<job>/profiles/<版本> 或 work/<job>/<版本>
        job, ver = job_dir.parent.name, job_dir.name
        for alt in (WORK / job / "profiles" / ver, WORK / job / ver):
            if (alt / "images").exists():
                job_dir = alt
                img_dir = alt / "images"
                break
    if not img_dir.exists():
        raise SystemExit(f"没找到图片目录：{img_dir}")

    board_path = job_dir / "storyboard.json"
    keyword_map: dict[int, list[str]] = {}
    if board_path.exists():
        try:
            shots = json.loads(board_path.read_text(encoding="utf-8"))
            for shot in shots:
                tags = [str(shot.get("keyword", "")).strip(), str(shot.get("template", "")).strip()]
                keyword_map[int(shot.get("index", -1))] = [t for t in tags if t]
        except Exception:
            keyword_map = {}

    dest = LIBRARY / "images"
    dest.mkdir(parents=True, exist_ok=True)
    # 目录可能是 work/<job>/profiles/<版本>，取真正的 job 名
    parent = job_dir.parent
    job_id = parent.parent.name if parent.name == "profiles" else parent.name
    prefix = f"{job_id}_{job_dir.name}"
    count = 0
    for png in sorted(img_dir.glob("*.png")):
        try:
            idx = int(png.stem.split("_")[-1])
        except ValueError:
            idx = -1
        tags = keyword_map.get(idx) or []
        if not tags:
            continue
        stem = re.sub(r'[\\/:*?"<>|]', "", f"{prefix}_{png.stem}_{tags[0]}")
        shutil.copy2(png, dest / f"{stem}.png")
        (dest / f"{stem}.yaml").write_text(
            yaml.safe_dump({"tags": tags}, allow_unicode=True), encoding="utf-8"
        )
        count += 1
    return count
