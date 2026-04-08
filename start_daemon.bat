@echo off
title FinQuanta Daemon Scheduler
echo ========================================
echo   FinQuanta 后台守护调度器
echo   7x24 自动化调度 + 预警 + 推送
echo ========================================
cd /d %~dp0
python -m desktop.daemon_scheduler 人工智能 芯片 量子科技 军工 新能源汽车 储能
pause
