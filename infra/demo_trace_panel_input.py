from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api_server.env_loader import load_env_files

load_env_files()

API_BASE = os.environ.get("FINQUANTA_API_BASE", "http://127.0.0.1:9000").rstrip("/")
API_USER = os.environ.get("FINQUANTA_SMOKE_USER", "admin")
API_PASSWORD = os.environ.get("FINQUANTA_SMOKE_PASSWORD", "admin123")


def api_call(method: str, path: str, payload: dict | None = None, token: str = "") -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"{API_BASE}{path}", method=method.upper(), headers=headers, data=data)
    parsed = urllib.parse.urlparse(API_BASE)
    host = (parsed.hostname or "").lower()
    opener = (
        urllib.request.build_opener(urllib.request.ProxyHandler({}))
        if host in {"127.0.0.1", "localhost", "0.0.0.0"}
        else urllib.request.build_opener()
    )
    with opener.open(req, timeout=20) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
        return json.loads(body) if body else {}


def main() -> int:
    login = api_call("POST", "/api/auth/login", {"username": API_USER, "password": API_PASSWORD})
    if not login.get("ok"):
        print(f"[FAIL] login: {login}")
        return 1
    token = str(login.get("token", "") or "")
    if not token:
        print("[FAIL] missing token")
        return 1

    context = api_call("GET", "/api/observability/trace/context", token=token).get("data", {})
    traceparent = str(context.get("outgoing", {}).get("traceparent", "") or "")
    trace_id = traceparent.split("-")[1] if "-" in traceparent else ""

    panel_input = api_call(
        "GET",
        f"/api/observability/dashboard/panel-input?trace_id={trace_id}&index_limit=20&trace_limit=50",
        token=token,
    ).get("data", {})

    collector_preview = api_call(
        "POST",
        (
            "/api/observability/collector/push"
            f"?signal=traces&dry_run=true&trace_id={trace_id}"
            "&trace_backend=tempo&trace_backend_base_url=http://127.0.0.1:4318"
        ),
        token=token,
    ).get("data", {})

    print("=== Trace Demo Summary ===")
    print(f"api_base={API_BASE}")
    print(f"trace_id={trace_id}")
    print(f"panel_trace_index_count={len(panel_input.get('trace', {}).get('index', []))}")
    print(f"panel_active_trace_id={panel_input.get('trace', {}).get('active_trace_id', '')}")
    print(
        "collector_signal_route_traces=",
        collector_preview.get("signal_routes", {}).get("traces", {}).get("endpoint", ""),
    )
    print("collector_backend=", collector_preview.get("trace_backend", ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
