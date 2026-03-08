@echo off
echo 卸载定时任务...
schtasks /delete /tn "AI量化_10点决策" /f 2>nul
schtasks /delete /tn "AI量化_14点决策" /f 2>nul
echo 已卸载。
pause
