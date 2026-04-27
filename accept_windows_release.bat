@echo off
setlocal
cd /d "%~dp0"

python infra\accept_windows_release.py %*
exit /b %errorlevel%
