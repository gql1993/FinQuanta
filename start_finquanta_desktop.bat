@echo off
REM FinQuanta desktop launcher (ASCII only - avoids cmd codepage issues on CN Windows)
cd /d "%~dp0"
set "APP_ENTRY=%~dp0run_desktop.py"

where pythonw.exe >nul 2>nul
if %errorlevel% EQU 0 (
  start "" pythonw.exe "%APP_ENTRY%"
  exit /b 0
)

where pyw.exe >nul 2>nul
if %errorlevel% EQU 0 (
  start "" pyw.exe "%APP_ENTRY%"
  exit /b 0
)

echo [ERROR] pythonw.exe was not found. Please install Python with the py launcher or add Python to PATH.
pause
exit /b 1
