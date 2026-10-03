# 一键拉起自托管 Dify（需要 Docker Desktop 或已配置的 WSL2）
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File scripts/setup_dify.ps1
#
# 说明：本脚本把官方仓库克隆到 vendor/dify，再启动其中 docker 目录下的 compose。
#       不修改官方文件，便于后续 git pull 升级。

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VendorDir = Join-Path $ProjectRoot "vendor\dify"

Write-Host "==> 检查 Docker" -ForegroundColor Cyan
$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) {
    Write-Host "未找到 docker 命令。" -ForegroundColor Red
    Write-Host "请先安装 Docker Desktop 并启用 WSL2 后端：" -ForegroundColor Yellow
    Write-Host "  https://docs.docker.com/desktop/setup/install/windows-install/"
    Write-Host "若本机无法安装 Docker，可改用 Dify 云端版或云主机，直接在 .env 里配置 DIFY_API_BASE 即可。"
    exit 1
}
docker --version

if (-not (Test-Path $VendorDir)) {
    Write-Host "==> 克隆 Dify 仓库到 $VendorDir" -ForegroundColor Cyan
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $VendorDir) | Out-Null
    git clone --depth 1 https://github.com/langgenius/dify.git $VendorDir
} else {
    Write-Host "==> vendor/dify 已存在，跳过克隆（如需升级请手动 git pull）" -ForegroundColor Yellow
}

$DockerDir = Join-Path $VendorDir "docker"
Push-Location $DockerDir
if (-not (Test-Path ".env")) {
    Write-Host "==> 生成 docker/.env" -ForegroundColor Cyan
    Copy-Item ".env.example" ".env"
}

Write-Host "==> 启动 Dify 容器（首次拉取镜像约需 5-15 分钟）" -ForegroundColor Cyan
docker compose up -d
Pop-Location

Write-Host ""
Write-Host "==> 启动完成" -ForegroundColor Green
Write-Host "1. 打开 http://localhost/install 创建管理员账号"
Write-Host "2. 新建「知识库」，上传文档，记录 Dataset ID"
Write-Host "3. 新建「聊天助手」应用，关联上一步的知识库"
Write-Host "4. 在应用「访问 API」中生成 API Key"
Write-Host "5. 回到本项目，把 .env 改成："
Write-Host "     APP_MODE=dify"
Write-Host "     DIFY_API_BASE=http://localhost/v1"
Write-Host "     DIFY_API_KEY=<应用 API Key>"
Write-Host "     DIFY_DATASET_ID=<知识库 Dataset ID>"
Write-Host "6. 重新运行 .\run.ps1"
