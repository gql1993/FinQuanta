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


def check(name: str, fn) -> bool:
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


def _print_api_startup_hint(exc: Exception) -> None:
    parsed = urllib.parse.urlparse(API_BASE)
    port = parsed.port or 9000
    print(f"[ERROR] API unreachable at {API_BASE}: {exc}")
    print("[HINT] Start API server then rerun e2e:")
    print(f"       python -m uvicorn api_server.main:app --host 0.0.0.0 --port {port}")


def main() -> int:
    print(f"API_BASE={API_BASE}")
    try:
        api_call("GET", "/health")
    except Exception as exc:
        _print_api_startup_hint(exc)
        return 1

    ok = True
    login_resp: dict = {}

    def do_login():
        nonlocal login_resp
        login_resp = api_call("POST", "/api/auth/login", {"username": API_USER, "password": API_PASSWORD})
        if not login_resp.get("ok"):
            raise RuntimeError(login_resp.get("message", "login failed"))
        return login_resp.get("role", "")

    ok &= check("e2e_login", do_login)
    token = str(login_resp.get("token", "") or "")
    if not token:
        return 1

    def check_ops_center():
        data = api_call("GET", "/api/ops/center", token=token).get("data", {})
        required_keys = {"snapshot", "tasks", "events", "operations", "registry", "registry_sync"}
        missing = required_keys - set(data.keys())
        if missing:
            raise RuntimeError(f"ops center missing keys: {sorted(missing)}")
        return sorted(required_keys)

    ok &= check("e2e_ops_center", check_ops_center)

    # Use an intentionally invalid BUY lot to validate approval chain while avoiding real execution side effects.
    def check_approval_chain():
        payload = {
            "mode": "auto",
            "action": "BUY",
            "code": "600519",
            "name": "贵州茅台",
            "price": 123.45,
            "shares": 250,
            "reason": "e2e minimal approval chain",
        }
        result = api_call("POST", "/api/approval/trade", payload, token=token)
        if not result.get("ok", False):
            raise RuntimeError(f"api response not ok: {result}")
        data = result.get("data", {}) or {}
        if data.get("approved") is not False:
            raise RuntimeError(f"expected rejected approval, got: {data}")
        message = str(data.get("message", "") or "")
        if "multiple of 100" not in message:
            raise RuntimeError(f"unexpected rejection reason: {message}")
        return {"approved": data.get("approved"), "message": message}

    ok &= check("e2e_approval_chain", check_approval_chain)
    ok &= check("e2e_logout", lambda: api_call("POST", "/api/auth/logout", token=token).get("data", {}).get("logout"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
