@echo off
setlocal
cd /d "%~dp0"

python infra\replay_openclaw_guard.py %*
exit /b %errorlevel%
