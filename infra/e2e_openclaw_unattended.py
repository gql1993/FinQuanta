from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api_server.env_loader import load_env_files

load_env_files()

API_BASE = os.environ.get("FINQUANTA_API_BASE", "http://127.0.0.1:9000").rstrip("/")
API_USER = os.environ.get("FINQUANTA_SMOKE_USER", "admin")
API_PASSWORD = os.environ.get("FINQUANTA_SMOKE_PASSWORD", "admin123")


def _opener():
    parsed = urllib.parse.urlparse(API_BASE)
    host = (parsed.hostname or "").lower()
    return (
        urllib.request.build_opener(urllib.request.ProxyHandler({}))
        if host in {"127.0.0.1", "localhost", "0.0.0.0"}
        else urllib.request.build_opener()
    )


def api_call(method: str, path: str, payload: dict | None = None, token: str = "") -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload or {}).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(f"{API_BASE}{path}", method=method.upper(), headers=headers, data=data)
    with _opener().open(req, timeout=30) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    return json.loads(body) if body else {}


def _run_local_step(name: str, cmd: list[str]) -> dict:
    started = time.time()
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        shell=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return {
        "name": name,
        "command": cmd,
        "status": "pass" if proc.returncode == 0 else "fail",
        "exit_code": proc.returncode,
        "elapsed_seconds": round(time.time() - started, 3),
        "stdout": (proc.stdout or "")[-8000:],
        "stderr": (proc.stderr or "")[-8000:],
    }


def _check(name: str, fn, steps: list[dict]) -> bool:
    started = time.time()
    try:
        value = fn()
        steps.append(
            {
                "name": name,
                "status": "pass",
                "elapsed_seconds": round(time.time() - started, 3),
                "value": value,
            }
        )
        print(f"[PASS] {name}: {value}")
        return True
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        steps.append(
            {
                "name": name,
                "status": "fail",
                "elapsed_seconds": round(time.time() - started, 3),
                "error": f"HTTP {exc.code} {detail}",
            }
        )
        print(f"[FAIL] {name}: HTTP {exc.code} {detail}")
        return False
    except Exception as exc:
        steps.append(
            {
                "name": name,
                "status": "fail",
                "elapsed_seconds": round(time.time() - started, 3),
                "error": str(exc),
            }
        )
        print(f"[FAIL] {name}: {exc}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="End-to-end read-only acceptance for unattended OpenClaw.")
    parser.add_argument("--output", default="logs/openclaw_unattended_e2e_report.json", help="Output report path.")
    parser.add_argument("--require-security-ready", action="store_true", help="Fail if admin security check is not ready.")
    parser.add_argument("--require-buy-disabled", action="store_true", help="Fail if unattended buy is enabled.")
    parser.add_argument("--require-simulation-pass", action="store_true", help="Fail if simulation gate is not passed.")
    parser.add_argument("--skip-local-scripts", action="store_true", help="Skip local .py safety/replay script checks.")
    args = parser.parse_args()

    print(f"API_BASE={API_BASE}")
    ok = True
    steps: list[dict] = []
    context: dict = {"api_base": API_BASE}
    token = ""

    def health():
        payload = api_call("GET", "/health")
        if not payload.get("ok"):
            raise RuntimeError(payload)
        return {"service": payload.get("service"), "daemon_started": payload.get("daemon_started")}

    ok &= _check("api_health", health, steps)

    def login():
        nonlocal token
        payload = api_call("POST", "/api/auth/login", {"username": API_USER, "password": API_PASSWORD})
        if not payload.get("ok") or not payload.get("token"):
            raise RuntimeError(payload.get("message", "login failed"))
        token = str(payload["token"])
        return {"role": payload.get("role", "")}

    ok &= _check("auth_login", login, steps)
    if not token:
        return 1

    def daemon_status():
        data = api_call("GET", "/api/openclaw/daemon/status", token=token).get("data", {})
        daemon = data.get("daemon", {}) or {}
        openclaw = data.get("openclaw", {}) or {}
        guard = data.get("trade_guard", {}) or {}
        readiness = openclaw.get("readiness", {}) or {}
        last_run = openclaw.get("last_run", {}) or {}
        simulation = (guard.get("simulation", {}) or {})
        cfg = guard.get("config", {}) or {}
        if not daemon.get("active"):
            raise RuntimeError("daemon inactive")
        if readiness.get("status") != "ready":
            raise RuntimeError(f"readiness={readiness.get('status')}: {readiness.get('summary', '')}")
        if args.require_buy_disabled and cfg.get("unattended_buy_enabled"):
            raise RuntimeError("unattended buy is enabled")
        if args.require_simulation_pass and not simulation.get("passed"):
            raise RuntimeError("simulation gate not passed")
        context["daemon"] = {
            "readiness": readiness,
            "history_count": len(openclaw.get("history", []) or []),
            "last_run_status": last_run.get("status", "-"),
            "guard_buy_enabled": cfg.get("unattended_buy_enabled", False),
            "simulation": simulation,
            "decision_sample": last_run.get("decision_sample", []) if isinstance(last_run.get("decision_sample", []), list) else [],
        }
        return context["daemon"]

    ok &= _check("openclaw_daemon_status", daemon_status, steps)

    def security_check():
        data = api_call("GET", "/api/admin/security-check", token=token).get("data", {})
        if args.require_security_ready and data.get("status") != "ready":
            raise RuntimeError(f"security status={data.get('status')}")
        context["security"] = {
            "status": data.get("status", "-"),
            "default_admin_password": data.get("default_admin_password", None),
            "tokens": data.get("tokens", {}),
            "finding_count": len(data.get("findings", []) or []),
        }
        return context["security"]

    ok &= _check("admin_security_check", security_check, steps)

    def history_replay_api():
        data = api_call(
            "POST",
            "/api/openclaw/replay/history",
            {
                "limit": 30,
                "include_guard_replay": True,
                "replay_limit": 10,
                "shares": 100,
                "mode": "auto",
                "use_real_price": False,
            },
            token=token,
        ).get("data", {})
        if data.get("verdict") == "error":
            raise RuntimeError(data.get("summary", "history replay error"))
        context["history_replay"] = {
            "verdict": data.get("verdict"),
            "success_rate": (data.get("daemon", {}) or {}).get("success_rate"),
            "history_count": (data.get("window", {}) or {}).get("history_count"),
            "finding_count": len(data.get("findings", []) or []),
        }
        return context["history_replay"]

    ok &= _check("openclaw_history_replay_api", history_replay_api, steps)

    def guard_replay_api():
        items = (context.get("daemon", {}) or {}).get("decision_sample", []) or []
        data = api_call(
            "POST",
            "/api/openclaw/unattended-trade-guard/replay",
            {"items": items, "limit": 10, "shares": 100, "mode": "auto", "use_real_price": False},
            token=token,
        ).get("data", {})
        if data.get("ok") is False:
            raise RuntimeError(data.get("message", "guard replay failed"))
        return {
            "input_count": data.get("input_count", 0),
            "approved_count": data.get("approved_count", 0),
            "rejected_count": data.get("rejected_count", 0),
            "skipped_count": data.get("skipped_count", 0),
        }

    ok &= _check("unattended_guard_replay_api", guard_replay_api, steps)

    if not args.skip_local_scripts:
        local_steps = [
            _run_local_step(
                "local_trade_channel_safety",
                [
                    sys.executable,
                    "infra/check_trade_channel_safety.py",
                    "--require-last-run-success",
                    "--output-json",
                    "logs/trade_channel_safety_report.json",
                    *(["--require-buy-disabled"] if args.require_buy_disabled else []),
                    *(["--require-simulation-pass"] if args.require_simulation_pass else []),
                ],
            ),
            _run_local_step(
                "local_history_replay",
                [
                    sys.executable,
                    "infra/replay_openclaw_history.py",
                    "--output",
                    "logs/openclaw_history_replay_report.json",
                ],
            ),
        ]
        for step in local_steps:
            steps.append(step)
            ok &= step["status"] == "pass"
            print(f"[{step['status'].upper()}] {step['name']}: exit_code={step['exit_code']}")

    _check("auth_logout", lambda: api_call("POST", "/api/auth/logout", token=token).get("data", {}).get("logout"), steps)

    report = {
        "status": "pass" if ok else "fail",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "context": context,
        "steps": steps,
    }
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"[REPORT] {output}")
    print("[RESULT] PASS" if ok else "[RESULT] FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
