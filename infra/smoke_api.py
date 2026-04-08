from __future__ import annotations

import json
import os
import sys
import urllib.error
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


def api_call(method: str, path: str, payload: dict | None = None, token: str = ""):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"{API_BASE}{path}", method=method.upper(), headers=headers, data=data)
    parsed = urllib.parse.urlparse(API_BASE)
    host = (parsed.hostname or "").lower()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({})) if host in {"127.0.0.1", "localhost", "0.0.0.0"} else urllib.request.build_opener()
    with opener.open(req, timeout=20) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
        return json.loads(body) if body else {}


def check(name: str, fn):
    try:
        result = fn()
        print(f"[PASS] {name}: {result}")
        return True
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        print(f"[FAIL] {name}: HTTP {exc.code} {detail}")
        return False
    except Exception as exc:
        print(f"[FAIL] {name}: {exc}")
        return False


def main():
    print(f"API_BASE={API_BASE}")
    ok = True

    ok &= check("health", lambda: api_call("GET", "/health").get("service"))
    ok &= check("health_runtime_mode", lambda: api_call("GET", "/health").get("runtime_mode"))
    ok &= check("health_deps", lambda: api_call("GET", "/health/deps").get("dependencies", {}).get("database", {}))

    login_resp = {}

    def do_login():
        nonlocal login_resp
        login_resp = api_call("POST", "/api/auth/login", {"username": API_USER, "password": API_PASSWORD})
        if not login_resp.get("ok"):
            raise RuntimeError(login_resp.get("message", "login failed"))
        return login_resp.get("role", "")

    ok &= check("auth_login", do_login)
    token = login_resp.get("token", "")
    if not token:
        return 1

    ok &= check("auth_profile", lambda: api_call("GET", "/api/auth/profile", token=token).get("data", {}).get("username"))
    ok &= check(
        "snapshot_system",
        lambda: (
            api_call("GET", "/api/snapshot/system", token=token)
            .get("data", {})
            .get("totals", {})
        ),
    )
    ok &= check("scan_latest", lambda: api_call("GET", "/api/scan/latest", token=token).get("data", {}).get("count", 0))
    ok &= check("portfolio_summary", lambda: api_call("GET", "/api/portfolio/summary", token=token).get("data", {}).keys())
    ok &= check("portfolio_positions", lambda: api_call("GET", "/api/portfolio/positions", token=token).get("data", {}).keys())
    ok &= check(
        "portfolio_recommendations",
        lambda: api_call("GET", "/api/portfolio/recommendations", token=token).get("data", {}).keys(),
    )
    ok &= check("ops_tasks", lambda: len(api_call("GET", "/api/ops/tasks", token=token).get("data", [])))
    ok &= check("ops_events", lambda: len(api_call("GET", "/api/ops/events", token=token).get("data", [])))
    ok &= check("ops_center", lambda: api_call("GET", "/api/ops/center", token=token).get("data", {}).keys())
    ok &= check("messages", lambda: len(api_call("GET", "/api/messages", token=token).get("data", [])))
    ok &= check("openclaw_weights", lambda: api_call("GET", "/api/openclaw/weights", token=token).get("data", {}).keys())
    ok &= check("openclaw_sources", lambda: len(api_call("GET", "/api/openclaw/sources", token=token).get("data", [])))
    ok &= check("verify_summary", lambda: api_call("GET", "/api/verify/summary", token=token).get("data", {}).get("total", 0))
    ok &= check("settings_ai", lambda: api_call("GET", "/api/settings/ai", token=token).get("data", {}).keys())
    ok &= check(
        "assistant_context",
        lambda: sorted(
            key
            for key in api_call("GET", "/api/assistant/context", token=token)
            .get("data", {})
            .keys()
            if key
            in {
                "snapshot_context",
                "market_context",
                "scan_context",
                "verify_context",
                "strategy_weights_context",
                "ops_context",
                "context_text",
            }
        ),
    )
    ok &= check(
        "assistant_ask",
        lambda: api_call(
            "POST",
            "/api/assistant/ask",
            {"prompt": "请用一句话总结当前系统状态", "session_id": "smoke_test"},
            token=token,
        ).get("data", {}).get("session_id", ""),
    )
    ok &= check("assistant_sessions", lambda: len(api_call("GET", "/api/assistant/sessions", token=token).get("data", {}).get("items", [])))
    ok &= check("auth_logout", lambda: api_call("POST", "/api/auth/logout", token=token).get("data", {}).get("logout"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
