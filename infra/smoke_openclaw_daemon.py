from __future__ import annotations

import argparse
import json
import locale
import os
import subprocess
import sys
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api_server.env_loader import load_env_files

load_env_files()


def _api_base() -> str:
    return os.environ.get("FINQUANTA_API_BASE", "http://127.0.0.1:9000").rstrip("/")


def _api_call(method: str, path: str, payload: dict | None = None, token: str = "") -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{_api_base()}{path}", method=method.upper(), headers=headers, data=data)
    parsed = urllib.parse.urlparse(_api_base())
    host = (parsed.hostname or "").lower()
    opener = (
        urllib.request.build_opener(urllib.request.ProxyHandler({}))
        if host in {"127.0.0.1", "localhost", "0.0.0.0"}
        else urllib.request.build_opener()
    )
    with opener.open(req, timeout=20) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
        return json.loads(body) if body else {}


def _login() -> str:
    user = os.environ.get("FINQUANTA_SMOKE_USER", "admin")
    password = os.environ.get("FINQUANTA_SMOKE_PASSWORD", "admin123")
    resp = _api_call("POST", "/api/auth/login", {"username": user, "password": password})
    if not resp.get("ok") or not resp.get("token"):
        raise RuntimeError(resp.get("message", "login failed"))
    return str(resp.get("token", ""))


def _query_task(task_name: str) -> dict:
    if os.name != "nt":
        return {"checked": False, "ok": True, "message": "skipped on non-Windows"}
    proc = subprocess.run(
        ["schtasks", "/Query", "/TN", task_name, "/FO", "LIST"],
        capture_output=True,
        text=True,
        encoding=locale.getpreferredencoding(False),
        errors="replace",
        shell=False,
    )
    return {
        "checked": True,
        "ok": proc.returncode == 0,
        "message": (proc.stdout or proc.stderr or "").strip()[:500],
    }


def _check(name: str, fn):
    try:
        value = fn()
        print(f"[PASS] {name}: {value}")
        return True, value
    except Exception as exc:
        print(f"[FAIL] {name}: {exc}")
        return False, None


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test headless OpenClaw daemon setup.")
    parser.add_argument("--require-task", action="store_true", help="Fail if FinQuantaApiService task is not installed.")
    parser.add_argument("--require-daemon-active", action="store_true", help="Fail if daemon heartbeat is not active.")
    parser.add_argument("--require-last-run", action="store_true", help="Fail if no OpenClaw daemon last_run is recorded.")
    parser.add_argument("--require-ready", action="store_true", help="Fail unless OpenClaw daemon readiness is ready.")
    parser.add_argument("--require-security-ready", action="store_true", help="Fail unless admin security check is ready.")
    parser.add_argument("--task-name", default="FinQuantaApiService", help="Windows scheduled task name.")
    args = parser.parse_args()

    print(f"API_BASE={_api_base()}")
    ok = True

    task_ok, task = _check("windows_task", lambda: _query_task(args.task_name))
    ok &= task_ok and (not args.require_task or bool(task.get("ok")))

    ok &= _check("health", lambda: _api_call("GET", "/health").get("service"))[0]
    ok &= _check("health_deps", lambda: _api_call("GET", "/health/deps").get("dependencies", {}).get("database", {}))[0]

    token_ok, token = _check("auth_login", _login)
    ok &= token_ok
    if not token:
        return 1

    try:
        def read_status():
            data = _api_call("GET", "/api/openclaw/daemon/status", token=token).get("data", {})
            daemon = data.get("daemon", {})
            openclaw = data.get("openclaw", {})
            guard = data.get("trade_guard", {})
            readiness = openclaw.get("readiness", {}) or {}
            if args.require_daemon_active and not daemon.get("active"):
                raise RuntimeError("daemon is not active")
            if args.require_last_run and not openclaw.get("last_run"):
                raise RuntimeError("openclaw last_run is empty")
            if args.require_ready and readiness.get("status") != "ready":
                raise RuntimeError(
                    "readiness is not ready: "
                    f"{readiness.get('status', '-')}; {readiness.get('summary', '')}"
                )
            return {
                "daemon_active": daemon.get("active"),
                "readiness": readiness,
                "next_task": daemon.get("next_task", {}),
                "openclaw_config": openclaw.get("config", {}),
                "last_run_status": (openclaw.get("last_run", {}) or {}).get("status", "-"),
                "history_count": len(openclaw.get("history", []) or []),
                "guard_buy_enabled": (guard.get("config", {}) or {}).get("unattended_buy_enabled", False),
                "simulation": guard.get("simulation", {}),
            }

        ok &= _check("openclaw_daemon_status", read_status)[0]

        def read_security_status():
            data = _api_call("GET", "/api/admin/security-check", token=token).get("data", {})
            if args.require_security_ready and data.get("status") != "ready":
                findings = data.get("findings", []) or []
                detail = "; ".join(str(item.get("message", "")) for item in findings[:3] if isinstance(item, dict))
                raise RuntimeError(f"security status is not ready: {data.get('status', '-')}; {detail}")
            return {
                "status": data.get("status", "-"),
                "default_admin_password": data.get("default_admin_password", None),
                "role_counts": data.get("role_counts", {}),
                "tokens": data.get("tokens", {}),
                "finding_count": len(data.get("findings", []) or []),
            }

        if args.require_security_ready:
            ok &= _check("admin_security_check", read_security_status)[0]
    finally:
        try:
            _api_call("POST", "/api/auth/logout", token=token)
        except Exception:
            pass

    print("[RESULT] PASS" if ok else "[RESULT] FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
