@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 智识固废：垃圾分类视觉识别与投放引导 - 公网访问

echo ============================================================
echo   公网访问模式
echo   手机用 WiFi 或流量都能打开，不受局域网限制
echo ============================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [错误] 未找到虚拟环境 .venv
    echo 请先执行： python -m venv .venv
    echo            .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

if not exist ".env" (
    copy /y ".env.example" ".env" >nul
)

echo 首次运行会自动下载隧道工具（约 53 MB），请耐心等待。
echo 建立隧道通常需要 10~30 秒。
echo.

".venv\Scripts\python.exe" scripts\start_public.py

echo.
echo 服务已停止。
pause
