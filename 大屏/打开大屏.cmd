@echo off
chcp 65001 >nul
title 智识固废：垃圾分类视觉识别与投放引导 · 数据大屏

rem 优先打开单文件版：只有一份文件，不依赖同目录的 css/js，最不容易出问题
set "PAGE=%~dp0数据大屏-单文件版.html"
if not exist "%PAGE%" set "PAGE=%~dp0index.html"

echo ============================================================
echo   智识固废：垃圾分类视觉识别与投放引导 · 数据大屏
echo ============================================================
echo.
echo   正在用浏览器打开，请稍候……
echo.
echo   如果窗口一闪而过或者没有反应，直接手动双击这个文件也行：
echo   %PAGE%
echo.

set "EDGE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not exist "%EDGE%" set "EDGE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if exist "%EDGE%" (
  start "" "%EDGE%" "%PAGE%"
  exit /b
)

set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if exist "%CHROME%" (
  start "" "%CHROME%" "%PAGE%"
  exit /b
)

rem 前面的浏览器都没找到，交给系统默认程序
start "" "%PAGE%"
