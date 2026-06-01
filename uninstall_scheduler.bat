@echo off
echo Uninstalling FinQuanta AI scheduler tasks...
schtasks /delete /tn "FinQuantaAiDecisionMorning" /f 2>nul
schtasks /delete /tn "FinQuantaAiDecisionAfternoon" /f 2>nul
echo Done.
exit /b 0
