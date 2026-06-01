@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set TASK_NAME=FinQuantaAutonomousDaemon
set SCRIPT_PATH=%~dp0start_daemon.bat
set LAUNCHER_PATH=%~dp0hidden_task_launcher.vbs
set TASK_COMMAND=%SystemRoot%\System32\wscript.exe //B "%LAUNCHER_PATH%" "%SCRIPT_PATH%"

echo Registering Windows Task Scheduler job: %TASK_NAME%
echo Script: %SCRIPT_PATH%
echo Command: %TASK_COMMAND%

schtasks /Delete /TN "%TASK_NAME%-Daily" /F >nul 2>nul

schtasks /Create /F /TN "%TASK_NAME%" /TR "%TASK_COMMAND%" /SC ONLOGON /RL LIMITED
if errorlevel 1 (
  echo Failed to create ONLOGON task.
  exit /b 1
)

schtasks /Create /F /TN "%TASK_NAME%-Morning" /TR "%TASK_COMMAND%" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 09:35 /RL LIMITED
if errorlevel 1 (
  echo Failed to create morning weekday task.
  exit /b 1
)

schtasks /Create /F /TN "%TASK_NAME%-Afternoon" /TR "%TASK_COMMAND%" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 12:55 /RL LIMITED
if errorlevel 1 (
  echo Failed to create afternoon weekday task.
  exit /b 1
)

echo Done. Tasks created:
echo   - %TASK_NAME% (on logon)
echo   - %TASK_NAME%-Morning (09:35 Mon-Fri)
echo   - %TASK_NAME%-Afternoon (12:55 Mon-Fri)
exit /b 0

