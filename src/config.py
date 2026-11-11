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
    # 素材库子目录
    (LIBRARY / "images").mkdir(parents=True, exist_ok=True)
    (LIBRARY / "videos").mkdir(parents=True, exist_ok=True)


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


def proxy() -> dict | None:
    """给 requests 用的代理字典。没配就返回 None（直连）。"""
    http = env("HTTP_PROXY") or env("http_proxy")
    https = env("HTTPS_PROXY") or env("https_proxy")
    if not http and not https:
        return None
    return {"http": http or https, "https": https or http}


# 需要走代理的海外域名（国内直连会超时）
OVERSEAS_HOSTS = ("reddit.com", "ycombinator.com", "firebaseio.com")


def proxy_for(url: str) -> dict | None:
    """按域名决定是否走代理：海外域名走，国内直连。"""
    if not any(host in url for host in OVERSEAS_HOSTS):
        return None
    return proxy()


def load_dotenv() -> None:
    """极简 .env 读取，避免额外依赖。

    覆盖系统环境变量：项目自己的 .env 优先。
    否则机器上存在同名变量时，改了 .env 却不生效，排查起来很费劲。
    """
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ[key.strip()] = value.strip()


STYLE = load_yaml("style.yaml")
PLATFORMS = load_yaml("platforms.yaml").get("platforms", {})
AUDIENCES = load_yaml("audiences.yaml").get("audiences", {})
