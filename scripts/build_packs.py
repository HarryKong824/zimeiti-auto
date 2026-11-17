"""把同一份 skill 打包成不同客户端能直接放的安装包。

一套源（.trae/skills/zimeiti-auto），多端产物：
  trae    -> .trae/skills/zimeiti-auto/
  claude  -> .claude/skills/zimeiti-auto/
  zip     -> 通用压缩包，手动丢进任意客户端

用法：
    python scripts/build_packs.py            # 全打
    python scripts/build_packs.py --target trae
"""

from __future__ import annotations

import argparse
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / ".trae" / "skills" / "zimeiti-auto"
OUT = ROOT / "dist" / "packs"
NAME = "zimeiti-auto"

TARGETS = {
    "trae": Path(".trae") / "skills",
    "claude": Path(".claude") / "skills",
}

INSTALL = """# 安装 {name}

1. 把本压缩包解到目标项目根目录，保持路径 `{dest}/{name}/SKILL.md`
2. 确认 Python 3.10+ 与 ffmpeg 已装
3. 在项目里执行 `pip install -r requirements.txt`
4. 重启客户端，新开会话，说「跑个 demo」

skill 里的命令都以仓库根为工作目录，`run.py` 必须在这个目录下。
"""


def build(target: str) -> Path:
    dest = TARGETS[target] / NAME
    pack_dir = OUT / target
    if pack_dir.exists():
        shutil.rmtree(pack_dir)
    shutil.copytree(SRC, pack_dir / dest)

    (pack_dir / "INSTALL.md").write_text(
        INSTALL.format(name=NAME, dest=str(dest).replace("\\", "/")),
        encoding="utf-8",
    )

    zip_path = OUT / f"{NAME}-{target}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in pack_dir.rglob("*"):
            if file.is_file():
                zf.write(file, file.relative_to(pack_dir))
    return zip_path


def main() -> None:
    parser = argparse.ArgumentParser(description="打包 skill 安装包")
    parser.add_argument("--target", choices=list(TARGETS) + ["all"], default="all")
    args = parser.parse_args()

    if not SRC.exists():
        raise SystemExit(f"找不到源 skill：{SRC}")

    wanted = list(TARGETS) if args.target == "all" else [args.target]
    for target in wanted:
        path = build(target)
        print(f"[{target}] {path.relative_to(ROOT)}  {path.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
