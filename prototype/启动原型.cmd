@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 智识固废：垃圾分类视觉识别与投放引导

echo ============================================================
echo   智识固废：垃圾分类视觉识别与投放引导 - 原型演示
echo ============================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [错误] 未找到虚拟环境 .venv
    echo.
    echo 请先在本目录执行下面两条命令，然后重新双击本文件：
    echo     python -m venv .venv
    echo     .venv\Scripts\python.exe -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

if not exist ".env" (
    echo [提示] 未找到 .env，已从 .env.example 复制一份
    copy /y ".env.example" ".env" >nul
)

echo 正在启动服务，稍后浏览器会自动打开。
echo 本机访问： http://127.0.0.1:7860
echo.
echo 关闭本窗口即可停止服务。
echo ------------------------------------------------------------
echo.

rem 打印手机访问地址（同一 WiFi 下的手机可用）
".venv\Scripts\python.exe" scripts\lan_access.py --no-qr

echo.
echo ------------------------------------------------------------
echo.

".venv\Scripts\python.exe" app.py

echo.
echo 服务已停止。
pause
