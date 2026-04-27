@echo off
setlocal
cd /d "%~dp0"

python infra\build_windows_release.py %*
exit /b %errorlevel%
