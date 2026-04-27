@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set TASK_NAME=FinQuantaOpenClawGateway
set SCRIPT_PATH=%~dp0start_openclaw_service.bat
set TASK_COMMAND=%ComSpec% /c ""%SCRIPT_PATH%""
set MODE=user
set START_NOW=0

if /I "%~1"=="--system" set MODE=system
if /I "%~2"=="--start" set START_NOW=1
if /I "%~1"=="--start" set START_NOW=1

echo Registering Windows Task Scheduler job: %TASK_NAME%
echo Script: %SCRIPT_PATH%
echo Command: %TASK_COMMAND%
echo Mode: %MODE%

if /I "%MODE%"=="system" (
  echo Creating ONSTART task as SYSTEM. Run this script as Administrator.
  schtasks /Create /F /TN "%TASK_NAME%" /TR "%TASK_COMMAND%" /SC ONSTART /RU SYSTEM /RL HIGHEST
) else (
  echo Creating ONLOGON task for current user.
  schtasks /Create /F /TN "%TASK_NAME%" /TR "%TASK_COMMAND%" /SC ONLOGON /RL LIMITED
)

if errorlevel 1 (
  echo Failed to create task. If using --system, please run as Administrator.
  exit /b 1
)

if "%START_NOW%"=="1" (
  echo Starting task now...
  schtasks /Run /TN "%TASK_NAME%"
  if errorlevel 1 (
    echo Task was created but failed to start. Check Task Scheduler for details.
    exit /b 1
  )
)

echo Done.
echo   Task: %TASK_NAME%
echo   Query: schtasks /Query /TN "%TASK_NAME%" /V /FO LIST
echo   Stop:  schtasks /End /TN "%TASK_NAME%"
echo   Logs:  logs\openclaw_gateway_service.log
exit /b 0
