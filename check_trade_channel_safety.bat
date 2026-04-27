@echo off
setlocal EnableExtensions
cd /d "%~dp0"

python infra\check_trade_channel_safety.py %*
exit /b %errorlevel%
