@echo off
chcp 65001 >nul
title 环境自检（模块 / 工具 / 数据库 / 磁盘）
cd /d "%~dp0"
rem 优先使用项目内置的绿色版 Python（3rd\python），不存在时回退系统 Python
set "PYTHONNOUSERSITE=1"
set "PYTHON=python"
if exist "%~dp03rd\python\python.exe" set "PYTHON=%~dp03rd\python\python.exe"
"%PYTHON%" main.py selfcheck
echo.
"%PYTHON%" Virus_Platform_Core\mem_check.py
pause
