@echo off
setlocal

if not defined FINQUANTA_ENV set FINQUANTA_ENV=dev
if not defined FINQUANTA_API_HOST set FINQUANTA_API_HOST=0.0.0.0
if not defined FINQUANTA_API_PORT set FINQUANTA_API_PORT=9000
if not defined FINQUANTA_DB_BACKEND set FINQUANTA_DB_BACKEND=sqlite
if not defined FINQUANTA_SQLITE_PATH set FINQUANTA_SQLITE_PATH=data_cache\quant.db
if not defined FINQUANTA_CORS_ORIGINS set FINQUANTA_CORS_ORIGINS=*
if not defined FINQUANTA_SNAPSHOT_CACHE_TTL set FINQUANTA_SNAPSHOT_CACHE_TTL=120

echo Starting FinQuanta API...
python -m uvicorn api_server.main:app --host %FINQUANTA_API_HOST% --port %FINQUANTA_API_PORT%
