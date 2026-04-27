@echo off
setlocal

set TASK_NAME=FinQuantaApiService

echo Stopping Windows Task Scheduler job: %TASK_NAME%
schtasks /End /TN "%TASK_NAME%" 2>nul

echo Deleting Windows Task Scheduler job: %TASK_NAME%
schtasks /Delete /TN "%TASK_NAME%" /F 2>nul
if errorlevel 1 (
  echo Task may not exist or could not be deleted.
  exit /b 1
)

echo Done.
exit /b 0
