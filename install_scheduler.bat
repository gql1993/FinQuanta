@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo ============================================
echo  FinQuanta AI Scheduler - Install Tasks
if not defined FINQUANTA_AI_SCHEDULER_MORNING_TIME set FINQUANTA_AI_SCHEDULER_MORNING_TIME=10:15
if not defined FINQUANTA_AI_SCHEDULER_AFTERNOON_TIME set FINQUANTA_AI_SCHEDULER_AFTERNOON_TIME=14:00
echo  Weekdays %FINQUANTA_AI_SCHEDULER_MORNING_TIME% and %FINQUANTA_AI_SCHEDULER_AFTERNOON_TIME%
echo ============================================

set TASK_SCRIPT=%~dp0run_ai_scheduler_once.bat
set LAUNCHER_SCRIPT=%~dp0hidden_task_launcher.vbs
set TASK_COMMAND=%SystemRoot%\System32\wscript.exe //B "%LAUNCHER_SCRIPT%" "%TASK_SCRIPT%"

echo.
echo Creating %FINQUANTA_AI_SCHEDULER_MORNING_TIME% task...
schtasks /create /tn "FinQuantaAiDecisionMorning" /tr "%TASK_COMMAND%" /sc weekly /d MON,TUE,WED,THU,FRI /st %FINQUANTA_AI_SCHEDULER_MORNING_TIME% /f
if %errorlevel% equ 0 (echo   OK) else (echo   FAILED)

echo.
echo Creating %FINQUANTA_AI_SCHEDULER_AFTERNOON_TIME% task...
schtasks /create /tn "FinQuantaAiDecisionAfternoon" /tr "%TASK_COMMAND%" /sc weekly /d MON,TUE,WED,THU,FRI /st %FINQUANTA_AI_SCHEDULER_AFTERNOON_TIME% /f
if %errorlevel% equ 0 (echo   OK) else (echo   FAILED)

echo.
echo ============================================
echo  Done.
echo  Tasks: FinQuantaAiDecisionMorning / FinQuantaAiDecisionAfternoon
echo  Logs:  logs\ai_scheduler_once.log
echo  Query: schtasks /query /tn "FinQuantaAiDecisionMorning" /v /fo list
echo  Uninstall: uninstall_scheduler.bat
echo ============================================
exit /b 0
