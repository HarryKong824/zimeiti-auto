"""发布前预校验：在打开浏览器之前，把能本地判断的问题一次列完。

思路参考 AiToEarn 的 get_channel_platform + issues[].path：
限制不写在发布代码里，也不靠人肉记忆，而是配置驱动、逐项校验、返回结构化问题。
好处是平台改规则只改 config，报错能精确指到字段，而不是填完表才失败。

error 级阻断（不打开浏览器、不花任何钱），warn 级只提示。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .config import PLATFORMS, load_yaml

PUB = load_yaml("publish.yaml")
VIDEO_EXT = {".mp4", ".mov", ".m4v"}
DEFAULT_MAX_MB = 4096


@dataclass
class Issue:
    field: str
    message: str
    level: str = "error"

    def as_dict(self) -> dict:
        return {"field": self.field, "message": self.message, "level": self.level}


def _count(text: str) -> int:
    return len((text or "").strip())


def _tag_list(tags: str) -> list[str]:
    return [t for t in re.split(r"[\s,#，]+", tags or "") if t.strip()]


def check(
    target: Path,
    platform: str,
    copy: dict,
    cover: Path | None,
    max_file_mb: int | None = None,
) -> list[Issue]:
    """返回问题清单。空列表表示可以进浏览器。"""
    issues: list[Issue] = []

    spec = (PUB.get("platforms") or {}).get(platform)
    if not spec:
        return [Issue("platform", f"publish.yaml 里没有配置 {platform}")]

    limits = PLATFORMS.get(platform) or {}
    if not limits:
        issues.append(Issue("platform", f"platforms.yaml 里没有 {platform} 的限制配置", "warn"))

    # 视频
    video = target / "final.mp4"
    if not video.exists():
        issues.append(Issue("video", f"找不到成品：{video}"))
    else:
        if video.suffix.lower() not in VIDEO_EXT:
            issues.append(Issue("video", f"格式可能不被接受：{video.suffix}，建议 mp4"))
        size_mb = video.stat().st_size / 1048576
        cap = int(max_file_mb or (PUB.get("preflight") or {}).get("max_file_mb") or DEFAULT_MAX_MB)
        if size_mb > cap:
            issues.append(Issue("video", f"文件 {size_mb:.0f} MB，超过上限 {cap} MB"))
        elif size_mb < 0.05:
            issues.append(Issue("video", f"文件只有 {size_mb * 1024:.0f} KB，可能是空文件", "warn"))

    # 封面
    if limits.get("cover_required"):
        if not cover or not cover.exists():
            issues.append(Issue("cover", f"{limits.get('name', platform)} 需要封面，但没找到 cover.png"))
    elif cover and not cover.exists():
        issues.append(Issue("cover", f"封面不存在：{cover.name}", "warn"))

    # 标题
    title_limit = int(limits.get("title_limit") or 0)
    title = copy.get("title", "")
    if title_limit:
        if not _count(title):
            issues.append(Issue("copy.title", "标题为空", "warn"))
        elif _count(title) > title_limit:
            issues.append(
                Issue("copy.title", f"标题 {_count(title)} 字，超过 {platform} 上限 {title_limit}")
            )

    # 正文（含标签的总长度，很多平台按整体算）
    body = copy.get("body", "")
    tags = copy.get("tags", "")
    full_body = f"{body}\n{tags}".strip() if tags else body
    body_limit = int(limits.get("body_limit") or 0)
    if body_limit and _count(full_body) > body_limit:
        issues.append(
            Issue("copy.body", f"正文含标签共 {_count(full_body)} 字，超过上限 {body_limit}")
        )
    elif not _count(full_body):
        issues.append(Issue("copy.body", "正文为空", "warn"))

    # 标签数量
    tag_max = int(limits.get("tags") or 0)
    tag_n = len(_tag_list(tags))
    if tag_max and tag_n > tag_max:
        issues.append(Issue("copy.tags", f"标签 {tag_n} 个，超过 {platform} 建议上限 {tag_max}", "warn"))

    return issues


def has_error(issues: list[Issue]) -> bool:
    return any(i.level == "error" for i in issues)
