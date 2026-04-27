@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set SERVICE_NAME=FinQuantaApiService
set SCRIPT_PATH=%~dp0start_api_service.bat
set START_NOW=0
set USAGE_EXIT=2

:parse_args
if "%~1"=="" goto after_args
if /I "%~1"=="--start" (
  set START_NOW=1
  shift
  goto parse_args
)
if /I "%~1"=="--name" (
  set SERVICE_NAME=%~2
  shift
  shift
  goto parse_args
)
if /I "%~1"=="--nssm" (
  set NSSM_EXE=%~2
  shift
  shift
  goto parse_args
)
if /I "%~1"=="--help" (
  set USAGE_EXIT=0
  goto usage
)
echo Unknown argument: %~1
goto usage

:after_args
if not defined NSSM_EXE set NSSM_EXE=nssm

where "%NSSM_EXE%" >nul 2>nul
if errorlevel 1 (
  if not exist "%NSSM_EXE%" (
    echo [ERROR] nssm.exe was not found.
    echo [HINT] Download NSSM and place nssm.exe on PATH, or pass --nssm C:\path\to\nssm.exe
    echo [HINT] This script must be run as Administrator.
    exit /b 1
  )
)

if not exist "%SCRIPT_PATH%" (
  echo [ERROR] Missing service wrapper: %SCRIPT_PATH%
  exit /b 1
)

if not exist logs mkdir logs

echo Installing Windows Service: %SERVICE_NAME%
echo Script: %SCRIPT_PATH%
echo NSSM: %NSSM_EXE%
echo This script must be run as Administrator.

"%NSSM_EXE%" install "%SERVICE_NAME%" "%ComSpec%"
if errorlevel 1 exit /b 1

"%NSSM_EXE%" set "%SERVICE_NAME%" AppParameters /c ""%SCRIPT_PATH%""
"%NSSM_EXE%" set "%SERVICE_NAME%" AppDirectory "%~dp0"
"%NSSM_EXE%" set "%SERVICE_NAME%" AppStdout "%~dp0logs\api_service_stdout.log"
"%NSSM_EXE%" set "%SERVICE_NAME%" AppStderr "%~dp0logs\api_service_stderr.log"
"%NSSM_EXE%" set "%SERVICE_NAME%" AppRotateFiles 1
"%NSSM_EXE%" set "%SERVICE_NAME%" AppRotateBytes 10485760
"%NSSM_EXE%" set "%SERVICE_NAME%" Start SERVICE_AUTO_START
"%NSSM_EXE%" set "%SERVICE_NAME%" Description "FinQuanta API service wrapper with OpenClaw daemon autostart."

if "%START_NOW%"=="1" (
  echo Starting service...
  "%NSSM_EXE%" start "%SERVICE_NAME%"
  if errorlevel 1 exit /b 1
)

echo Done.
echo   Service: %SERVICE_NAME%
echo   Query:   sc query "%SERVICE_NAME%"
echo   Stop:    net stop "%SERVICE_NAME%"
echo   Logs:    logs\api_service.log
exit /b 0

:usage
echo Usage: install_api_windows_service.bat [--start] [--name SERVICE_NAME] [--nssm PATH_TO_NSSM_EXE]
echo.
echo Installs FinQuanta API as a real Windows Service through NSSM.
echo Run from an Administrator terminal.
exit /b %USAGE_EXIT%
