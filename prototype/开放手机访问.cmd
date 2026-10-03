@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 开放手机访问 - 防火墙设置

echo ============================================================
echo   让手机访问本机原型（Windows 防火墙放行）
echo ============================================================
echo.

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [需要管理员权限]
    echo.
    echo 请右键本文件，选择「以管理员身份运行」。
    echo.
    pause
    exit /b 1
)

echo 正在为 TCP 7860 端口添加入站放行规则...
netsh advfirewall firewall delete rule name="Codex原型演示" >nul 2>&1
netsh advfirewall firewall add rule name="Codex原型演示" dir=in action=allow protocol=TCP localport=7860

if %errorlevel%==0 (
    echo.
    echo [成功] 已放行 TCP 7860。
    echo.
    echo 接下来：
    echo   1. 双击「启动原型.cmd」启动服务（窗口不要关闭）
    echo   2. 手机连上同一个 WiFi
    echo   3. 手机浏览器访问控制台提示的地址，或扫描二维码
    echo.
    echo 提示：如果你的 WiFi 被识别为「公用网络」，Windows 默认还会拦截入站连接。
    echo      若仍打不开，可在「设置 - 网络和 Internet - WLAN」把网络改为「专用网络」。
) else (
    echo.
    echo [失败] 添加规则未成功，请检查权限。
)

echo.
pause
