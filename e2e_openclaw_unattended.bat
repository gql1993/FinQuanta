@echo off
setlocal EnableExtensions
cd /d "%~dp0"

python infra\e2e_openclaw_unattended.py %*
exit /b %errorlevel%
