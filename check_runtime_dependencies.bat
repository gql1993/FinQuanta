@echo off
setlocal
cd /d "%~dp0"

python infra\check_runtime_dependencies.py %*
exit /b %errorlevel%
