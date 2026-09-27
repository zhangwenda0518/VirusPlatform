@echo off
rem SPAdes launcher - runs coronaspades.py with the bundled Python.
"%~dp0..\python\python.exe" "%~dp0coronaspades.py" %*
