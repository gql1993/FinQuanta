@echo off
setlocal EnableExtensions
title FinQuanta Daemon Scheduler
cd /d "%~dp0"

if not exist logs mkdir logs
if not defined FINQUANTA_DB_BACKEND set FINQUANTA_DB_BACKEND=sqlite
if not defined FINQUANTA_SQLITE_PATH set FINQUANTA_SQLITE_PATH=data_cache\quant.db

echo ========================================
echo   FinQuanta 后台守护调度器
echo   交易日准点调度 + 预警 + 推送
echo ========================================
echo   cwd=%CD%
echo   DB_BACKEND=%FINQUANTA_DB_BACKEND%
echo   SQLITE_PATH=%FINQUANTA_SQLITE_PATH%

if "%~1"=="" (
  python -m desktop.daemon_scheduler 人工智能 芯片 量子科技 军工 新能源汽车 储能
) else (
  python -m desktop.daemon_scheduler %*
)
