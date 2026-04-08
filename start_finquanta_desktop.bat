@echo off
REM FinQuanta desktop launcher (ASCII only - avoids cmd codepage issues on CN Windows)
cd /d "%~dp0"
pythonw run_desktop.py 2>nul
if errorlevel 1 python run_desktop.py
