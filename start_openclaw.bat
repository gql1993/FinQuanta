@echo off
title FinQuanta - OpenClaw Gateway
echo ================================================
echo   FinQuanta OpenClaw Gateway
echo   7x24 AI Agent + Cron + Webhook + Push
echo ================================================
echo.
node "C:\Program Files\nodejs\node_modules\openclaw\openclaw.mjs" gateway --port 18789
pause
