from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api_server.env_loader import load_env_files

load_env_files()


def _api_base() -> str:
    return os.environ.get("FINQUANTA_API_BASE", "http://127.0.0.1:9000").rstrip("/")


def _api_call(method: str, path: str, payload: dict | None = None, token: str = "") -> dict:
    data = json.dumps(payload or {}).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{_api_base()}{path}", method=method.upper(), headers=headers, data=data)
    parsed = urllib.parse.urlparse(_api_base())
    opener = (
        urllib.request.build_opener(urllib.request.ProxyHandler({}))
        if (parsed.hostname or "").lower() in {"127.0.0.1", "localhost", "0.0.0.0"}
        else urllib.request.build_opener()
    )
    with opener.open(req, timeout=20) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    return json.loads(body) if body else {}


def _login() -> str:
    username = os.environ.get("FINQUANTA_SMOKE_USER", "admin")
    password = os.environ.get("FINQUANTA_SMOKE_PASSWORD", "admin123")
    resp = _api_call("POST", "/api/auth/login", {"username": username, "password": password})
    if not resp.get("ok") or not resp.get("token"):
        raise RuntimeError(resp.get("message") or "login failed")
    return str(resp["token"])


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        text = raw.replace("\x00", "").strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        values[key.strip().lstrip("\ufeff")] = value.strip().strip('"').strip("'")
    return values


def _env_snapshot() -> dict:
    file_values = _read_env_file(ROOT / ".env.api")
    env = {**file_values, **{k: v for k, v in os.environ.items() if k.startswith("FINQUANTA_")}}
    gateway_enabled = str(env.get("FINQUANTA_OPENCLAW_GATEWAY_ENABLED", "1")).strip().lower() not in {
        "0",
        "false",
        "off",
        "no",
    }
    return {
        "env": env.get("FINQUANTA_ENV", "dev"),
        "api_base": env.get("FINQUANTA_API_BASE", _api_base()),
        "gateway_enabled": gateway_enabled,
        "gateway_base": env.get("FINQUANTA_OPENCLAW_GATEWAY_BASE", "http://127.0.0.1:18789"),
        "gateway_token_set": bool(str(env.get("FINQUANTA_OPENCLAW_GATEWAY_TOKEN", "")).strip()),
    }


def _add(condition: bool, level: str, code: str, message: str, findings: list[dict]) -> None:
    if condition:
        findings.append({"level": level, "code": code, "message": message})


def _status_from_findings(findings: list[dict], *, strict: bool) -> str:
    if any(item["level"] == "error" for item in findings):
        return "fail"
    if strict and any(item["level"] == "warning" for item in findings):
        return "fail"
    return "pass"


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only safety check for the real trading channel.")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures.")
    parser.add_argument("--require-security-ready", action="store_true", help="Fail unless admin security status is ready.")
    parser.add_argument("--require-daemon-ready", action="store_true", help="Fail unless OpenClaw daemon readiness is ready.")
    parser.add_argument("--require-last-run-success", action="store_true", help="Fail unless the latest daemon run succeeded.")
    parser.add_argument("--require-simulation-pass", action="store_true", help="Fail unless unattended buy simulation gate passed.")
    parser.add_argument("--require-buy-disabled", action="store_true", help="Fail unless unattended buy is disabled.")
    parser.add_argument("--output-json", default="", help="Optional path to write the full report JSON.")
    args = parser.parse_args()

    findings: list[dict] = []
    checks: dict[str, object] = {"api_base": _api_base()}

    try:
        health = _api_call("GET", "/health")
        checks["health"] = health
        _add(not bool(health.get("ok")), "error", "api_health_not_ok", "API /health did not return ok=true.", findings)
    except Exception as exc:
        findings.append({"level": "error", "code": "api_unreachable", "message": f"API is unreachable: {exc}"})
        health = {}

    token = ""
    if not any(item["level"] == "error" and item["code"] == "api_unreachable" for item in findings):
        try:
            token = _login()
            checks["auth_login"] = {"ok": True}
        except Exception as exc:
            findings.append({"level": "error", "code": "auth_login_failed", "message": f"Smoke login failed: {exc}"})
            checks["auth_login"] = {"ok": False, "error": str(exc)}

    if token:
        security = _api_call("GET", "/api/admin/security-check", token=token).get("data", {})
        checks["security"] = security
        _add(
            args.require_security_ready and security.get("status") != "ready",
            "error",
            "security_not_ready",
            f"Admin security status is {security.get('status', '-')}.",
            findings,
        )
        _add(
            bool(security.get("default_admin_password")),
            "warning",
            "default_admin_password",
            "Default admin password is still usable; change it before production.",
            findings,
        )

        daemon_status = _api_call("GET", "/api/openclaw/daemon/status", token=token).get("data", {})
        trade_guard = _api_call("GET", "/api/openclaw/unattended-trade-guard", token=token).get("data", {})
        checks["daemon_status"] = daemon_status
        checks["trade_guard"] = trade_guard

        daemon = daemon_status.get("daemon", {}) or {}
        openclaw = daemon_status.get("openclaw", {}) or {}
        readiness = openclaw.get("readiness", {}) or {}
        last_run = openclaw.get("last_run", {}) or {}
        cfg = (trade_guard.get("config", {}) or {})
        simulation = (trade_guard.get("simulation", {}) or {})
        replay = (trade_guard.get("replay", {}) or {})

        _add(not bool(daemon.get("active")), "error", "daemon_inactive", "Daemon heartbeat is inactive.", findings)
        _add(
            args.require_daemon_ready and readiness.get("status") != "ready",
            "error",
            "daemon_not_ready",
            f"OpenClaw readiness is {readiness.get('status', '-')}: {readiness.get('summary', '')}",
            findings,
        )
        _add(not bool(cfg.get("enabled", True)), "error", "trade_guard_disabled", "Unattended trade guard is disabled.", findings)
        _add(
            args.require_buy_disabled and bool(cfg.get("unattended_buy_enabled", False)),
            "error",
            "unattended_buy_enabled",
            "Unattended buy is enabled while this check requires it to remain disabled.",
            findings,
        )
        _add(
            bool(cfg.get("unattended_buy_enabled", False))
            and bool(cfg.get("require_simulation_pass", True))
            and not bool(simulation.get("passed", False)),
            "error",
            "buy_enabled_without_simulation",
            "Unattended buy is enabled but simulation gate has not passed.",
            findings,
        )
        _add(
            args.require_simulation_pass and not bool(simulation.get("passed", False)),
            "error",
            "simulation_not_passed",
            "Simulation gate has not passed.",
            findings,
        )
        _add(
            bool(cfg.get("unattended_buy_enabled", False)) and not replay.get("last"),
            "warning",
            "buy_enabled_without_replay",
            "Unattended buy is enabled but no guard replay record is available.",
            findings,
        )
        _add(
            not bool(cfg.get("unattended_buy_enabled", False)),
            "info",
            "unattended_buy_disabled",
            "Unattended buy is disabled; sell-only risk reduction remains the safer default.",
            findings,
        )
        _add(
            not bool(cfg.get("allow_sell_when_buy_disabled", True)),
            "warning",
            "sell_disabled_when_buy_disabled",
            "Sell is disabled while unattended buy is disabled; risk-reducing exits may be blocked.",
            findings,
        )
        _add(
            args.require_last_run_success and last_run.get("status") != "success",
            "error",
            "last_run_not_success",
            f"Latest OpenClaw daemon run status is {last_run.get('status', '-')}.",
            findings,
        )

    env = _env_snapshot()
    checks["env"] = env
    _add(
        env["gateway_enabled"] and not env["gateway_token_set"],
        "warning",
        "gateway_token_missing",
        "OpenClaw gateway is enabled but FINQUANTA_OPENCLAW_GATEWAY_TOKEN is not set in the local environment.",
        findings,
    )

    status = _status_from_findings(findings, strict=args.strict)
    report = {
        "status": status,
        "strict": bool(args.strict),
        "summary": "真实交易通道安全检查通过" if status == "pass" else "真实交易通道安全检查未通过",
        "findings": findings,
        "checks": checks,
    }

    print(f"API_BASE={_api_base()}")
    for item in findings:
        print(f"[{item['level'].upper()}] {item['code']}: {item['message']}")
    print("[RESULT] PASS" if status == "pass" else "[RESULT] FAIL")

    if args.output_json:
        Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
