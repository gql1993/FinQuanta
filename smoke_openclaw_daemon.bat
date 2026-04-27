@echo off
setlocal
cd /d "%~dp0"

if not defined FINQUANTA_API_BASE set FINQUANTA_API_BASE=http://127.0.0.1:9000

echo [smoke-openclaw-daemon] API_BASE=%FINQUANTA_API_BASE%
python infra\smoke_openclaw_daemon.py %*
exit /b %errorlevel%
