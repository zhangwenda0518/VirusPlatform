@echo off
chcp 65001 >nul
title 植物病毒分析平台（网页模式）
cd /d "%~dp0"
echo.
echo   ╔══════════════════════════════════════════╗
echo   ║   植物病毒分析平台 · 网页模式（浏览器）     ║
echo   ╚══════════════════════════════════════════╝
echo.
echo   服务启动后自动在默认浏览器打开；地址也会打印在下方，
echo   可复制到其它浏览器/设备调试。关闭本窗口即退出平台。
echo.
rem 优先使用项目内置的绿色版 Python（3rd\python），不存在时回退系统 Python
set "PYTHONNOUSERSITE=1"
set "PYTHON=python"
if exist "%~dp03rd\python\python.exe" set "PYTHON=%~dp03rd\python\python.exe"
"%PYTHON%" app.py --web
pause
