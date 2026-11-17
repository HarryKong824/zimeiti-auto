# 安装 zimeiti-auto skill 到 Trae 全局 skills 目录（CN 版）
# 用法：在仓库根目录执行  .\install.ps1
# 可选：.\install.ps1 -Edition international   装到国际版 ~/.trae/skills/

param(
    [ValidateSet("cn", "international")]
    [string]$Edition = "cn"
)

$ErrorActionPreference = "Stop"

# 本仓库根 = 脚本所在目录
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$SkillSrc = Join-Path $RepoRoot ".trae\skills\zimeiti-auto"

if (-not (Test-Path $SkillSrc)) {
    Write-Error "找不到 skill 源目录：$SkillSrc"
    exit 1
}

# 目标全局 skills 目录
$DataFolder = if ($Edition -eq "cn") { ".trae-cn" } else { ".trae" }
$GlobalRoot = Join-Path $env:USERPROFILE "$DataFolder\skills"
$SkillDst = Join-Path $GlobalRoot "zimeiti-auto"

Write-Host "源：$SkillSrc"
Write-Host "目标：$SkillDst"
Write-Host "仓库路径：$RepoRoot"

# 如果目标已存在，先备份
if (Test-Path $SkillDst) {
    $Backup = "$SkillDst.bak.$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    Write-Host "目标已存在，备份到：$Backup"
    Move-Item $SkillDst $Backup
}

New-Item -ItemType Directory -Force -Path $GlobalRoot | Out-Null
Copy-Item -Recurse -Force $SkillSrc $SkillDst

# SKILL.md 用相对路径定位项目根（本文件往上两级），无需写入绝对路径，
# 因此换盘符、换机器、多份克隆都不会失效。

$SkillMd = Join-Path $SkillDst "SKILL.md"
if (-not (Test-Path $SkillMd)) {
    Write-Warning "没有找到 $SkillMd，请检查仓库结构是否完整"
}

Write-Host ""
Write-Host "[OK] 安装完成"
Write-Host "重启 Trae 后，在任何项目里说「剪视频」「选题」「跑 demo」即可触发本 skill。"
Write-Host ""
Write-Host "卸载：删除 $SkillDst 即可。"
