@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist logs mkdir logs
if not defined FINQUANTA_API_KEEPALIVE set FINQUANTA_API_KEEPALIVE=1
if not defined FINQUANTA_API_RESTART_DELAY_SECONDS set FINQUANTA_API_RESTART_DELAY_SECONDS=15
if not defined FINQUANTA_API_SERVICE_LOG set FINQUANTA_API_SERVICE_LOG=logs\api_service.log
if not defined FINQUANTA_API_BASE set FINQUANTA_API_BASE=http://127.0.0.1:9000

echo ========================================
echo   FinQuanta API Service Wrapper
echo   keepalive=%FINQUANTA_API_KEEPALIVE%
echo   log=%FINQUANTA_API_SERVICE_LOG%
echo ========================================

:loop
python -c "import os,sys,urllib.request; base=os.environ.get('FINQUANTA_API_BASE','http://127.0.0.1:9000').rstrip('/'); req=urllib.request.Request(base + '/health', method='GET'); opener=urllib.request.build_opener(urllib.request.ProxyHandler({})); resp=opener.open(req, timeout=5); sys.exit(0 if resp.status < 500 else 1)" >nul 2>nul
if not errorlevel 1 (
  echo [%date% %time%] API already healthy at %FINQUANTA_API_BASE%; watching >> "%FINQUANTA_API_SERVICE_LOG%"
  python -c "import os,time; time.sleep(max(1, int(os.environ.get('FINQUANTA_API_RESTART_DELAY_SECONDS','15'))))" >nul 2>nul
  goto loop
)

echo [%date% %time%] starting FinQuanta API >> "%FINQUANTA_API_SERVICE_LOG%"
call "%~dp0start_api.bat" >> "%FINQUANTA_API_SERVICE_LOG%" 2>&1
set EXIT_CODE=%ERRORLEVEL%
echo [%date% %time%] FinQuanta API exited with code %EXIT_CODE% >> "%FINQUANTA_API_SERVICE_LOG%"

if "%FINQUANTA_API_KEEPALIVE%"=="0" exit /b %EXIT_CODE%

echo Restarting in %FINQUANTA_API_RESTART_DELAY_SECONDS% seconds...
python -c "import os,time; time.sleep(max(1, int(os.environ.get('FINQUANTA_API_RESTART_DELAY_SECONDS','15'))))" >nul 2>nul
goto loop
