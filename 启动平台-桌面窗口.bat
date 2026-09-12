@echo off
chcp 65001 >nul
title 植物病毒分析平台（桌面窗口）
cd /d "%~dp0"
echo.
echo   ╔══════════════════════════════════════════╗
echo   ║   植物病毒分析平台 · 独立桌面窗口模式      ║
echo   ╚══════════════════════════════════════════╝
echo.
echo   弹出独立窗口（无地址栏）；若本机缺 pywebview / WebView2，
echo   会自动回退为系统浏览器，不会启动失败。
echo.
rem 优先使用项目内置的绿色版 Python（3rd\python），不存在时回退系统 Python
set "PYTHONNOUSERSITE=1"
set "PYTHON=python"
if exist "%~dp03rd\python\python.exe" set "PYTHON=%~dp03rd\python\python.exe"
"%PYTHON%" app.py --gui
pause
