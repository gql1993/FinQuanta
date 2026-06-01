@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist logs mkdir logs
if not defined FINQUANTA_DB_BACKEND set FINQUANTA_DB_BACKEND=sqlite
if not defined FINQUANTA_SQLITE_PATH set FINQUANTA_SQLITE_PATH=data_cache\quant.db

set BOARD=%~1
if "%BOARD%"=="" set BOARD=人工智能

echo [%date% %time%] Running FinQuanta AI scheduled decision for %BOARD%...
python desktop\auto_scheduler.py "%BOARD%" >> logs\ai_scheduler_once.log 2>&1
exit /b %ERRORLEVEL%
