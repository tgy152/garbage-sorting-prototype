# 一键启动原型
#
# 用法：powershell -ExecutionPolicy Bypass -File run.ps1
#       powershell -ExecutionPolicy Bypass -File run.ps1 -Mode direct

param(
    [ValidateSet("mock", "direct", "dify")]
    [string]$Mode = "",
    [int]$Port = 0,
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$VenvDir = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "==> 创建虚拟环境 .venv" -ForegroundColor Cyan
    $systemPython = (Get-Command python -ErrorAction SilentlyContinue)
    if (-not $systemPython) {
        $systemPython = "C:\Users\15040\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    } else {
        $systemPython = $systemPython.Source
    }
    & $systemPython -m venv $VenvDir
}

if (-not $SkipInstall) {
    Write-Host "==> 安装依赖" -ForegroundColor Cyan
    & $VenvPython -m pip install --upgrade pip --quiet
    & $VenvPython -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
}

if (-not (Test-Path (Join-Path $ProjectRoot ".env"))) {
    Write-Host "==> 未找到 .env，从 .env.example 复制" -ForegroundColor Yellow
    Copy-Item (Join-Path $ProjectRoot ".env.example") (Join-Path $ProjectRoot ".env")
}

if ($Mode) {
    $env:APP_MODE = $Mode
    Write-Host "==> 本次运行模式：$Mode" -ForegroundColor Green
}
if ($Port -gt 0) {
    $env:GRADIO_SERVER_PORT = "$Port"
}

Write-Host "==> 启动 Gradio，浏览器访问 http://127.0.0.1:$($env:GRADIO_SERVER_PORT)" -ForegroundColor Green
& $VenvPython (Join-Path $ProjectRoot "app.py")
