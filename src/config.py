from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
WORK = ROOT / "work"
OUTBOX = ROOT / "outbox"
INBOX = ROOT / "inbox"
LIBRARY = ROOT / "library"
DATA = ROOT / "data"


def ensure_dirs() -> None:
    for d in (WORK, OUTBOX, INBOX, LIBRARY, DATA):
        d.mkdir(parents=True, exist_ok=True)


def load_yaml(name: str) -> dict:
    path = CONFIG_DIR / name
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def env(key: str, default: str = "") -> str:
    value = os.environ.get(key)
    if value is None:
        return default
    return value.strip()


def load_dotenv() -> None:
    """极简 .env 读取，避免额外依赖。"""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


STYLE = load_yaml("style.yaml")
PLATFORMS = load_yaml("platforms.yaml").get("platforms", {})
AUDIENCES = load_yaml("audiences.yaml").get("audiences", {})
