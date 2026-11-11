#!/usr/bin/env bash
# 安装 zimeiti-auto skill 到 Trae 全局 skills 目录
# 用法：在仓库根目录执行  bash install.sh
# 可选：bash install.sh international   装到国际版 ~/.trae/skills/（默认 CN 版 ~/.trae-cn/skills/）

set -euo pipefail

EDITION="${1:-cn}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_SRC="$REPO_ROOT/.trae/skills/zimeiti-auto"

if [[ ! -d "$SKILL_SRC" ]]; then
    echo "找不到 skill 源目录：$SKILL_SRC" >&2
    exit 1
fi

if [[ "$EDITION" == "cn" ]]; then
    DATA_FOLDER=".trae-cn"
elif [[ "$EDITION" == "international" ]]; then
    DATA_FOLDER=".trae"
else
    echo "用法：bash install.sh [cn|international]" >&2
    exit 1
fi

GLOBAL_ROOT="$HOME/$DATA_FOLDER/skills"
SKILL_DST="$GLOBAL_ROOT/zimeiti-auto"

echo "源：$SKILL_SRC"
echo "目标：$SKILL_DST"
echo "仓库路径：$REPO_ROOT"

if [[ -d "$SKILL_DST" ]]; then
    BACKUP="$SKILL_DST.bak.$(date +%Y%m%d-%H%M%S)"
    echo "目标已存在，备份到：$BACKUP"
    mv "$SKILL_DST" "$BACKUP"
fi

mkdir -p "$GLOBAL_ROOT"
cp -r "$SKILL_SRC" "$SKILL_DST"

# 把 SKILL.md 里的占位文本替换为实际仓库路径
SKILL_MD="$SKILL_DST/SKILL.md"
OLD_PATTERN='**项目根 = 当前打开的文件夹**（即 `run.py` 所在目录）。所有命令都在项目根执行，**不要 cd 到别处**。Agent 执行命令时把 cwd 设为 run.py 所在目录即可。'
NEW_TEXT="**项目根 = \`$REPO_ROOT\`**（本仓库克隆位置）。所有命令都在这个目录执行——Agent 执行命令前必须先 \`cd $REPO_ROOT\`，然后再跑 \`python run.py ...\`。"

if grep -qF "$OLD_PATTERN" "$SKILL_MD"; then
    # 用 python 做替换，避免 sed 处理中文/特殊字符的坑
    python3 - "$SKILL_MD" "$OLD_PATTERN" "$NEW_TEXT" <<'PY'
import sys
path, old, new = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path, "r", encoding="utf-8") as f:
    content = f.read()
with open(path, "w", encoding="utf-8") as f:
    f.write(content.replace(old, new))
PY
    echo "[OK] 已在 SKILL.md 中写入仓库路径：$REPO_ROOT"
else
    echo "[warn] SKILL.md 里没找到预期占位文本，未做路径替换。请手动编辑 $SKILL_MD 把「项目根」改成 $REPO_ROOT" >&2
fi

echo ""
echo "[OK] 安装完成"
echo "重启 Trae 后，在任何项目里说「剪视频」「选题」「跑 demo」即可触发本 skill。"
echo ""
echo "卸载：rm -rf \"$SKILL_DST\""
