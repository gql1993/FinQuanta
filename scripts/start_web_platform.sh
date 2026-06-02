#!/usr/bin/env bash
# 方案一：启动 API (9000) + Streamlit Web (8501)，供 Windows 浏览器远程访问
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi

mkdir -p logs data_cache

if [[ ! -f .env.api ]]; then
  echo "[ERR] 缺少 .env.api，请从 .env.api.example 复制并编辑"
  exit 1
fi

# shellcheck disable=SC1091
set -a
source <(grep -v '^\s*#' .env.api | grep -v '^\s*$' | sed 's/^/export /')
set +a

API_PID_FILE="${ROOT}/logs/api.pid"
WEB_PID_FILE="${ROOT}/logs/web.pid"

_stop_pidfile() {
  local f="$1"
  local name="$2"
  if [[ -f "$f" ]]; then
    local pid
    pid="$(cat "$f")"
    if kill -0 "$pid" 2>/dev/null; then
      echo "[STOP] $name (pid $pid)"
      kill "$pid" 2>/dev/null || true
      sleep 1
      kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$f"
  fi
}

case "${1:-start}" in
  stop)
    _stop_pidfile "$API_PID_FILE" "API"
    _stop_pidfile "$WEB_PID_FILE" "Web"
    echo "已停止"
    exit 0
    ;;
  status)
    for pair in "API:$API_PID_FILE" "Web:$WEB_PID_FILE"; do
      name="${pair%%:*}"
      f="${pair##*:}"
      if [[ -f "$f" ]] && kill -0 "$(cat "$f")" 2>/dev/null; then
        echo "$name: running (pid $(cat "$f"))"
      else
        echo "$name: stopped"
      fi
    done
    if curl -sf "http://127.0.0.1:${FINQUANTA_API_PORT:-9000}/health" >/dev/null 2>&1; then
      echo "API health: ok"
    else
      echo "API health: unreachable"
    fi
    exit 0
    ;;
  start)
    _stop_pidfile "$API_PID_FILE" "API"
    _stop_pidfile "$WEB_PID_FILE" "Web"
    ;;
  *)
    echo "用法: $0 {start|stop|status}"
    exit 1
    ;;
esac

echo "[INIT] SQLite schema (kv_store / kline / …)"
"$PY" -c "import sys; sys.path.insert(0, '.'); from desktop.db import init_db; init_db()"

echo "[START] API on 0.0.0.0:${FINQUANTA_API_PORT:-9000} (daemon autostart=${FINQUANTA_API_AUTOSTART_DAEMON:-1})"
nohup "$PY" -m uvicorn api_server.main:app \
  --host "${FINQUANTA_API_HOST:-0.0.0.0}" \
  --port "${FINQUANTA_API_PORT:-9000}" \
  >> logs/api_service.log 2>&1 &
echo $! > "$API_PID_FILE"

for i in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:${FINQUANTA_API_PORT:-9000}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! curl -sf "http://127.0.0.1:${FINQUANTA_API_PORT:-9000}/health" >/dev/null 2>&1; then
  echo "[ERR] API 未在 30s 内就绪，查看 logs/api_service.log"
  exit 1
fi
echo "[OK] API health check passed"

WEB_PORT="${FINQUANTA_WEB_PORT:-8501}"
echo "[START] Web on 0.0.0.0:${WEB_PORT}"
nohup "$PY" -m streamlit run web_app.py \
  --server.port "$WEB_PORT" \
  --server.address 0.0.0.0 \
  --server.headless true \
  >> logs/web_service.log 2>&1 &
echo $! > "$WEB_PID_FILE"

sleep 2
_ips="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo ""
echo "=== 方案一已启动 ==="
echo "  本机 API:  http://127.0.0.1:${FINQUANTA_API_PORT:-9000}/health"
echo "  本机 Web:  http://127.0.0.1:${WEB_PORT}"
if [[ -n "$_ips" ]]; then
  echo "  远程 Web:  http://${_ips}:${WEB_PORT}  (Windows 浏览器打开)"
  echo "  远程 API:  http://${_ips}:${FINQUANTA_API_PORT:-9000}  (Web 侧边栏可保持 127.0.0.1:9000)"
fi
echo "  日志: logs/api_service.log  logs/web_service.log"
echo "  停止: $0 stop"
echo "  默认登录: admin / admin123  (公网暴露前请修改密码)"
echo ""
