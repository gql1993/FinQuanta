@echo off
setlocal enabledelayedexpansion
title FinQuanta - OpenClaw Gateway

if not defined FINQUANTA_OPENCLAW_GATEWAY_ENABLED set FINQUANTA_OPENCLAW_GATEWAY_ENABLED=1
if not defined FINQUANTA_OPENCLAW_GATEWAY_HOST set FINQUANTA_OPENCLAW_GATEWAY_HOST=127.0.0.1
if not defined FINQUANTA_OPENCLAW_GATEWAY_PORT set FINQUANTA_OPENCLAW_GATEWAY_PORT=18789
if not defined FINQUANTA_OPENCLAW_GATEWAY_BASE set FINQUANTA_OPENCLAW_GATEWAY_BASE=http://%FINQUANTA_OPENCLAW_GATEWAY_HOST%:%FINQUANTA_OPENCLAW_GATEWAY_PORT%
if not defined FINQUANTA_OPENCLAW_GATEWAY_TIMEOUT_SECONDS set FINQUANTA_OPENCLAW_GATEWAY_TIMEOUT_SECONDS=8.0
if not defined FINQUANTA_OPENCLAW_GATEWAY_ENTRY set FINQUANTA_OPENCLAW_GATEWAY_ENTRY=C:\Program Files\nodejs\node_modules\openclaw\openclaw.mjs
if not defined FINQUANTA_OPENCLAW_GATEWAY_WINDOW set FINQUANTA_OPENCLAW_GATEWAY_WINDOW=normal
if not exist logs mkdir logs
if not defined FINQUANTA_OPENCLAW_GATEWAY_STDOUT set FINQUANTA_OPENCLAW_GATEWAY_STDOUT=%~dp0logs\openclaw_gateway_stdout.log
if not defined FINQUANTA_OPENCLAW_GATEWAY_STDERR set FINQUANTA_OPENCLAW_GATEWAY_STDERR=%~dp0logs\openclaw_gateway_stderr.log

if /I "%FINQUANTA_OPENCLAW_GATEWAY_HOST%"=="0.0.0.0" (
  set GATEWAY_PROBE_HOST=127.0.0.1
) else (
  set GATEWAY_PROBE_HOST=%FINQUANTA_OPENCLAW_GATEWAY_HOST%
)
if not defined FINQUANTA_OPENCLAW_GATEWAY_PORT set FINQUANTA_OPENCLAW_GATEWAY_PORT=18789

echo ================================================
echo   FinQuanta OpenClaw Gateway
echo ================================================
echo   ENABLED      = %FINQUANTA_OPENCLAW_GATEWAY_ENABLED%
echo   BASE URL     = %FINQUANTA_OPENCLAW_GATEWAY_BASE%
echo   PROBE HOST   = %GATEWAY_PROBE_HOST%
echo   PROBE PORT   = %FINQUANTA_OPENCLAW_GATEWAY_PORT%
echo   TIMEOUT SEC  = %FINQUANTA_OPENCLAW_GATEWAY_TIMEOUT_SECONDS%
echo   ENTRY        = %FINQUANTA_OPENCLAW_GATEWAY_ENTRY%
echo   WINDOW       = %FINQUANTA_OPENCLAW_GATEWAY_WINDOW%
echo ================================================
echo.

if /I "%FINQUANTA_OPENCLAW_GATEWAY_ENABLED%"=="0" (
  echo [WARN] FINQUANTA_OPENCLAW_GATEWAY_ENABLED=0, API will use local fallback.
  if /I not "%~1"=="--health-only" pause
  exit /b 0
)

call :probe_port
if %errorlevel% EQU 0 (
  echo [OK] Gateway port is reachable, reuse existing instance.
  goto :after_probe
)

if /I "%~1"=="--health-only" (
  echo [FAIL] Gateway is not running.
  exit /b 1
)

where node >nul 2>nul
if errorlevel 1 (
  echo [ERROR] node was not found. Please install Node.js first.
  pause
  exit /b 1
)

if not exist "%FINQUANTA_OPENCLAW_GATEWAY_ENTRY%" (
  echo [ERROR] OpenClaw gateway entry was not found:
  echo         "%FINQUANTA_OPENCLAW_GATEWAY_ENTRY%"
  echo         Set FINQUANTA_OPENCLAW_GATEWAY_ENTRY and retry.
  pause
  exit /b 1
)

if /I "%FINQUANTA_OPENCLAW_GATEWAY_WINDOW%"=="hidden" (
  echo [INFO] Starting OpenClaw gateway hidden in background...
  powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "Start-Process -WindowStyle Hidden -FilePath 'node' -ArgumentList @('%FINQUANTA_OPENCLAW_GATEWAY_ENTRY%','gateway','--port','%FINQUANTA_OPENCLAW_GATEWAY_PORT%') -RedirectStandardOutput '%FINQUANTA_OPENCLAW_GATEWAY_STDOUT%' -RedirectStandardError '%FINQUANTA_OPENCLAW_GATEWAY_STDERR%'"
) else (
  echo [INFO] Starting OpenClaw gateway in a new window...
  start "FinQuanta OpenClaw Gateway" cmd /k node "%FINQUANTA_OPENCLAW_GATEWAY_ENTRY%" gateway --port %FINQUANTA_OPENCLAW_GATEWAY_PORT%
)

set /a RETRIES=20
:wait_probe
timeout /t 1 /nobreak >nul
call :probe_port
if %errorlevel% EQU 0 goto :after_probe
set /a RETRIES-=1
if %RETRIES% GTR 0 goto :wait_probe

echo [WARN] Health probe timeout after startup. Check gateway logs.
echo        You can run: start_openclaw.bat --health-only
pause
exit /b 1

:after_probe
echo [OK] Gateway health probe passed: %GATEWAY_PROBE_HOST%:%FINQUANTA_OPENCLAW_GATEWAY_PORT%
if /I "%~1"=="--health-only" exit /b 0
echo.
echo [TIP] Keep API config aligned in .env.api:
echo       FINQUANTA_OPENCLAW_GATEWAY_ENABLED=1
echo       FINQUANTA_OPENCLAW_GATEWAY_BASE=%FINQUANTA_OPENCLAW_GATEWAY_BASE%
echo.
pause
exit /b 0

:probe_port
powershell -NoProfile -Command "$c=New-Object Net.Sockets.TcpClient; try { $ar=$c.BeginConnect('%GATEWAY_PROBE_HOST%',%FINQUANTA_OPENCLAW_GATEWAY_PORT%,$null,$null); if($ar.AsyncWaitHandle.WaitOne(700)){ $c.EndConnect($ar); exit 0 } else { exit 1 } } catch { exit 1 } finally { $c.Close() }" >nul 2>nul
exit /b %errorlevel%
