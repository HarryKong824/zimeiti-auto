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

# SKILL.md 用相对路径定位项目根（本文件往上两级），无需写入绝对路径，
# 因此换盘符、换机器、多份克隆都不会失效。
SKILL_MD="$SKILL_DST/SKILL.md"
if [ ! -f "$SKILL_MD" ]; then
    echo "[warn] 没有找到 $SKILL_MD，请检查仓库结构是否完整" >&2
fi

echo ""
echo "[OK] 安装完成"
echo "重启 Trae 后，在任何项目里说「剪视频」「选题」「跑 demo」即可触发本 skill。"
echo ""
echo "卸载：rm -rf \"$SKILL_DST\""
