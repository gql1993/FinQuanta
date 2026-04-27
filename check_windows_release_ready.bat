@echo off
setlocal
cd /d "%~dp0"

python infra\check_windows_release_ready.py %*
exit /b %errorlevel%
