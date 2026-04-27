@echo off
setlocal EnableExtensions
cd /d "%~dp0"

python infra\replay_openclaw_history.py %*
exit /b %errorlevel%
