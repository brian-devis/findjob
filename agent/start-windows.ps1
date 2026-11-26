# AIJob Windows Local Agent 一键初始化与启动脚本
$ErrorActionPreference = "Stop"

Set-Location -Path $PSScriptRoot

$pyCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pyCmd) {
    Write-Error "未检测到 python，请先安装 Python 3.11+ 并勾选 Add to PATH。"
    exit 1
}

$venvDir = Join-Path $PSScriptRoot ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$venvPip = Join-Path $venvDir "Scripts\pip.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "[AIJob Agent] 正在创建虚拟环境 .venv..."
    & python -m venv $venvDir
}

Write-Host "[AIJob Agent] 正在校验并安装 Python 依赖..."
& $venvPip install -q -r (Join-Path $PSScriptRoot "requirements.txt")

$envFile = Join-Path $PSScriptRoot ".env"
$envExample = Join-Path $PSScriptRoot ".env.example"
if (-not (Test-Path $envFile)) {
    Copy-Item $envExample $envFile
    Write-Host ""
    Write-Host "[AIJob Agent] 已从 .env.example 创建 .env 文件：" -ForegroundColor Yellow
    Write-Host "  请先在管理后台（Agents 页）注册 Agent，并将 AIJOB_AGENT_ID 与 AIJOB_AGENT_SECRET 填入：" -ForegroundColor Yellow
    Write-Host "  $envFile"
    Write-Host "  填好后重新运行 .\start-windows.ps1 即可启动。"
    exit 0
}

# 若 .env 未显式配置 AIJOB_BROWSER_PROFILE_DIR，默认放到 %LOCALAPPDATA%\AIJob\browser-profile 避免污染仓库目录
$hasCustomProfile = Select-String -Path $envFile -Pattern "^\s*AIJOB_BROWSER_PROFILE_DIR\s*=" -Quiet
if (-not $hasCustomProfile -and -not $env:AIJOB_BROWSER_PROFILE_DIR) {
    $env:AIJOB_BROWSER_PROFILE_DIR = Join-Path $env:LOCALAPPDATA "AIJob\browser-profile"
}

Write-Host "[AIJob Agent] 正在启动 Local Agent..."
& $venvPython -m agent.main
