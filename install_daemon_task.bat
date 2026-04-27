@echo off
setlocal

set TASK_NAME=FinQuantaAutonomousDaemon
set SCRIPT_PATH=%~dp0start_daemon.bat

echo Registering Windows Task Scheduler job: %TASK_NAME%
echo Script: %SCRIPT_PATH%

schtasks /Create /F /TN "%TASK_NAME%" /TR "\"%SCRIPT_PATH%\"" /SC ONLOGON /RL LIMITED
if errorlevel 1 (
  echo Failed to create ONLOGON task.
  exit /b 1
)

schtasks /Create /F /TN "%TASK_NAME%-Daily" /TR "\"%SCRIPT_PATH%\"" /SC DAILY /ST 09:00 /RL LIMITED
if errorlevel 1 (
  echo Failed to create DAILY task.
  exit /b 1
)

echo Done. Tasks created:
echo   - %TASK_NAME% (on logon)
echo   - %TASK_NAME%-Daily (09:00 daily)
exit /b 0

