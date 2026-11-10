from __future__ import annotations

import copy

from .config import load_yaml

_CFG = load_yaml("profiles.yaml")
DEFAULTS = _CFG.get("defaults", {})
SCORING = _CFG.get("scoring", {})
PROFILES = _CFG.get("profiles", {})


def _merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def names() -> list[str]:
    return list(PROFILES.keys())


def resolve(name: str) -> dict:
    if name not in PROFILES:
        raise KeyError(f"未知版本：{name}，可选：{', '.join(PROFILES)}")
    cfg = _merge(DEFAULTS, PROFILES[name])
    cfg["key"] = name
    cfg.setdefault("name", name)
    if "duration" not in cfg:
        cfg["duration"] = {"target": 0}
    return cfg


def box(aspect: str) -> tuple[int, int]:
    """返回该画幅下的渲染尺寸（短边固定 1080）。"""
    return {
        "9:16": (1080, 1920),
        "16:9": (1920, 1080),
        "1:1": (1080, 1080),
    }.get(aspect, (1080, 1920))
