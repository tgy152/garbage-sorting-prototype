@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 作品介绍页预览

echo ============================================================
echo   作品介绍页
echo   与原型共用同一个服务，地址是 /landing/
echo ============================================================
echo.

if not exist "..\landing\index.html" (
    echo [错误] 未找到 ..\landing\index.html
    echo.
    pause
    exit /b 1
)

echo 作品页由原型服务一并提供，不需要单独启动。
echo 正在确认服务状态...
echo.

powershell -NoProfile -Command "try { $r = Invoke-WebRequest 'http://127.0.0.1:7860/landing/' -UseBasicParsing -TimeoutSec 5; exit 0 } catch { exit 1 }"

if %errorlevel% neq 0 (
    echo 服务尚未启动，正在启动...
    start "" "%~dp0启动原型.cmd"
    timeout /t 20 /nobreak >nul
)

echo 正在打开作品页： http://127.0.0.1:7860/landing/
start "" http://127.0.0.1:7860/landing/

echo.
echo 提示：内网穿透开启时，对外地址就是「公网地址 + /landing/」。
echo.
pause
