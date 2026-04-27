@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set SERVICE_NAME=FinQuantaApiService
set USAGE_EXIT=2

:parse_args
if "%~1"=="" goto after_args
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

echo Removing Windows Service: %SERVICE_NAME%
echo This script should be run as Administrator.

where "%NSSM_EXE%" >nul 2>nul
if errorlevel 1 (
  if exist "%NSSM_EXE%" goto nssm_remove
  echo [WARN] nssm.exe was not found. Falling back to sc.exe delete.
  sc stop "%SERVICE_NAME%" >nul 2>nul
  sc delete "%SERVICE_NAME%"
  exit /b %errorlevel%
)

:nssm_remove
"%NSSM_EXE%" stop "%SERVICE_NAME%" >nul 2>nul
"%NSSM_EXE%" remove "%SERVICE_NAME%" confirm
exit /b %errorlevel%

:usage
echo Usage: uninstall_api_windows_service.bat [--name SERVICE_NAME] [--nssm PATH_TO_NSSM_EXE]
echo.
echo Removes the FinQuanta API Windows Service.
exit /b %USAGE_EXIT%
