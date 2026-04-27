@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist logs mkdir logs
if not defined FINQUANTA_OPENCLAW_SERVICE_KEEPALIVE set FINQUANTA_OPENCLAW_SERVICE_KEEPALIVE=1
if not defined FINQUANTA_OPENCLAW_RESTART_DELAY_SECONDS set FINQUANTA_OPENCLAW_RESTART_DELAY_SECONDS=30
if not defined FINQUANTA_OPENCLAW_SERVICE_LOG set FINQUANTA_OPENCLAW_SERVICE_LOG=logs\openclaw_gateway_service.log

echo ========================================
echo   FinQuanta OpenClaw Gateway Wrapper
echo   keepalive=%FINQUANTA_OPENCLAW_SERVICE_KEEPALIVE%
echo   log=%FINQUANTA_OPENCLAW_SERVICE_LOG%
echo ========================================

:loop
call "%~dp0start_openclaw.bat" --health-only >> "%FINQUANTA_OPENCLAW_SERVICE_LOG%" 2>&1
if not errorlevel 1 (
  echo [%date% %time%] OpenClaw gateway already healthy; watching >> "%FINQUANTA_OPENCLAW_SERVICE_LOG%"
  python -c "import os,time; time.sleep(max(1, int(os.environ.get('FINQUANTA_OPENCLAW_RESTART_DELAY_SECONDS','30'))))" >nul 2>nul
  goto loop
)

echo [%date% %time%] starting OpenClaw gateway >> "%FINQUANTA_OPENCLAW_SERVICE_LOG%"
call "%~dp0start_openclaw.bat" >> "%FINQUANTA_OPENCLAW_SERVICE_LOG%" 2>&1
set EXIT_CODE=%ERRORLEVEL%
echo [%date% %time%] OpenClaw gateway start command exited with code %EXIT_CODE% >> "%FINQUANTA_OPENCLAW_SERVICE_LOG%"

if "%FINQUANTA_OPENCLAW_SERVICE_KEEPALIVE%"=="0" exit /b %EXIT_CODE%

echo Restarting gateway check in %FINQUANTA_OPENCLAW_RESTART_DELAY_SECONDS% seconds...
python -c "import os,time; time.sleep(max(1, int(os.environ.get('FINQUANTA_OPENCLAW_RESTART_DELAY_SECONDS','30'))))" >nul 2>nul
goto loop
