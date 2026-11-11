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

# 把 SKILL.md 里的"项目根 = 当前打开的文件夹"替换为实际仓库路径
$SkillMd = Join-Path $SkillDst "SKILL.md"
$Content = Get-Content $SkillMd -Raw -Encoding UTF8

# 用单引号字符串避免反引号转义问题
$OldPattern = '**项目根 = 当前打开的文件夹**（即 `run.py` 所在目录）。所有命令都在项目根执行，**不要 cd 到别处**。Agent 执行命令时把 cwd 设为 run.py 所在目录即可。'
$NewText = "**项目根 = ``$RepoRoot``**（本仓库克隆位置）。所有命令都在这个目录执行——Agent 执行命令前必须先 ``cd $RepoRoot``，然后再跑 ``python run.py ...``。"

if ($Content.Contains($OldPattern)) {
    $Content = $Content.Replace($OldPattern, $NewText)
    Set-Content -Path $SkillMd -Value $Content -Encoding UTF8 -NoNewline
    Write-Host "[OK] 已在 SKILL.md 中写入仓库路径：$RepoRoot"
} else {
    Write-Warning "SKILL.md 里没找到预期占位文本，未做路径替换。请手动编辑 $SkillMd 把「项目根」改成 $RepoRoot"
}

Write-Host ""
Write-Host "[OK] 安装完成"
Write-Host "重启 Trae 后，在任何项目里说「剪视频」「选题」「跑 demo」即可触发本 skill。"
Write-Host ""
Write-Host "卸载：删除 $SkillDst 即可。"
