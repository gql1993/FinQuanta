@echo off
setlocal
if not defined FINQUANTA_API_BASE set FINQUANTA_API_BASE=http://127.0.0.1:9000
set SMOKE_MODE=%~1
if "%SMOKE_MODE%"=="" set SMOKE_MODE=%FINQUANTA_SMOKE_GATEWAY_MODE%
if "%SMOKE_MODE%"=="" set SMOKE_MODE=strict

if /I not "%SMOKE_MODE%"=="strict" if /I not "%SMOKE_MODE%"=="relaxed" (
  echo [smoke] invalid mode: %SMOKE_MODE%
  echo [smoke] usage: smoke_api.bat [strict^|relaxed]
  exit /b 2
)

echo [smoke] API_BASE=%FINQUANTA_API_BASE%
echo [smoke] GATEWAY_MODE=%SMOKE_MODE%

if /I "%SMOKE_MODE%"=="strict" (
  python infra\check_openclaw_gateway.py --strict
  if errorlevel 1 exit /b %errorlevel%
) else (
  python infra\check_openclaw_gateway.py
)

python infra\smoke_api.py
exit /b %errorlevel%
