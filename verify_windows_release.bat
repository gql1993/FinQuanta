@echo off
setlocal
cd /d "%~dp0"

python infra\verify_windows_release.py %*
exit /b %errorlevel%
