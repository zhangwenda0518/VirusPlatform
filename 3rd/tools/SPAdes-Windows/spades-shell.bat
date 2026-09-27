@echo off
set "PATH=%~dp0bin;%~dp0python;%PATH%"
title SPAdes for Windows
echo ============================================================
echo   SPAdes for Windows (4.3.0-dev) is ready.
echo.
echo   Try:   spades --help
echo          spades --test
echo          spades --isolate -1 reads_1.fq -2 reads_2.fq -o out_dir
echo          metaspades / plasmidspades / rnaspades / coronaspades ...
echo.
echo   (The classic 'spades.py ...' also works.)
echo ============================================================
echo.
cd /d "%USERPROFILE%"
cmd /k
