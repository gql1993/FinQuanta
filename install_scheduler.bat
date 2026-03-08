@echo off
echo ============================================
echo  AI 量化交易平台 - 安装定时任务
echo  每天 10:00 和 14:00 自动运行
echo ============================================

set PYTHON_PATH=python
set SCRIPT_PATH=%~dp0desktop\auto_scheduler.py

echo.
echo 创建 10:00 定时任务...
schtasks /create /tn "AI量化_10点决策" /tr "%PYTHON_PATH% %SCRIPT_PATH%" /sc daily /st 10:00 /f
if %errorlevel% equ 0 (echo   成功!) else (echo   失败，请以管理员身份运行)

echo.
echo 创建 14:00 定时任务...
schtasks /create /tn "AI量化_14点决策" /tr "%PYTHON_PATH% %SCRIPT_PATH%" /sc daily /st 14:00 /f
if %errorlevel% equ 0 (echo   成功!) else (echo   失败，请以管理员身份运行)

echo.
echo ============================================
echo  安装完成！
echo  任务名: AI量化_10点决策 / AI量化_14点决策
echo  查看: 任务计划程序 或 schtasks /query /tn "AI量化*"
echo  卸载: 运行 uninstall_scheduler.bat
echo ============================================
pause
