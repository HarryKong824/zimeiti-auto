"""一键补齐运行环境：agent 可以直接执行本脚本，不需要用户懂 Python。

用法：
    python bootstrap.py              # 装缺失依赖 + 自检
    python bootstrap.py --json       # 输出机器可读结果
    python bootstrap.py --with-model # 额外下载 whisper 小模型（约 480MB）
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

REQUIRED = [
    ("PIL", "Pillow"),
    ("requests", "requests"),
    ("yaml", "PyYAML"),
    ("numpy", "numpy"),
]
OPTIONAL = [
    ("faster_whisper", "faster-whisper"),
    ("imageio_ffmpeg", "imageio-ffmpeg"),
]


def _installed(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def _pip_install(packages: list[str]) -> bool:
    if not packages:
        return True
    mirror = os.environ.get("PIP_INDEX_URL", "https://pypi.tuna.tsinghua.edu.cn/simple")
    cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-q"]
    if mirror:
        cmd += ["-i", mirror]
    cmd += packages
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout[-1500:])
        print(result.stderr[-1500:])
    return result.returncode == 0


def _ensure_model() -> str:
    model_dir = ROOT / "models" / "faster-whisper-small"
    if (model_dir / "model.bin").exists():
        return "已存在"
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    try:
        from huggingface_hub import snapshot_download

        snapshot_download(
            repo_id="Systran/faster-whisper-small",
            local_dir=str(model_dir),
        )
        return "已下载"
    except Exception as exc:
        return f"下载失败（首次转写会再试）：{exc}"


def main() -> int:
    parser = argparse.ArgumentParser(description="补齐 zimeiti-auto 运行环境")
    parser.add_argument("--json", action="store_true", help="输出机器可读结果")
    parser.add_argument("--with-model", action="store_true", help="下载 whisper 转写模型")
    args = parser.parse_args()

    steps: list[dict] = []

    def record(name: str, ok: bool, detail: str) -> None:
        steps.append({"step": name, "ok": ok, "detail": detail})
        if not args.json:
            print(f" {'✓' if ok else '✗'} {name:<18} {detail}")

    ok = sys.version_info >= (3, 10)
    record("Python", ok, f"{sys.version_info.major}.{sys.version_info.minor}")
    if not ok:
        _finish(steps, args.json)
        return 1

    missing = [pkg for module, pkg in REQUIRED if not _installed(module)]
    missing += [pkg for module, pkg in OPTIONAL if not _installed(module)]
    if missing:
        record("安装依赖", _pip_install(missing), ", ".join(missing))
    else:
        record("安装依赖", True, "已齐全")

    from src.ffmpeg import ffmpeg_exe, has_ffmpeg

    _pip_install([pkg for module, pkg in OPTIONAL if module == "imageio_ffmpeg" and not _installed(module)])
    record("ffmpeg", has_ffmpeg(), ffmpeg_exe())

    if args.with_model:
        model_state = _ensure_model()
        record("whisper 模型", "失败" not in model_state, model_state)

    from src.health import check

    code = check(as_json=False)
    record("环境自检", code == 0, "全部通过" if code == 0 else "有阻塞项")

    _finish(steps, args.json)
    return 0 if all(step["ok"] for step in steps) else 1


def _finish(steps: list[dict], as_json: bool) -> None:
    if as_json:
        print(json.dumps({"ok": all(s["ok"] for s in steps), "steps": steps}, ensure_ascii=False, indent=2))
    elif all(s["ok"] for s in steps):
        print("\n环境就绪，下一步：python run.py --demo\n")
    else:
        print("\n有未完成的步骤，按上面提示处理后重跑本脚本。\n")


if __name__ == "__main__":
    raise SystemExit(main())
