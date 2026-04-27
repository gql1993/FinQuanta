from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

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
    with opener.open(req, timeout=30) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
        return json.loads(body) if body else {}


def _login() -> str:
    user = os.environ.get("FINQUANTA_SMOKE_USER", "admin")
    password = os.environ.get("FINQUANTA_SMOKE_PASSWORD", "admin123")
    resp = _api_call("POST", "/api/auth/login", {"username": user, "password": password})
    if not resp.get("ok") or not resp.get("token"):
        raise RuntimeError(resp.get("message", "login failed"))
    return str(resp["token"])


def _build_report(payload: dict) -> dict:
    from core.application.openclaw_service import build_openclaw_historical_replay_report

    try:
        return build_openclaw_historical_replay_report(payload)
    except Exception as exc:
        token = ""
        try:
            token = _login()
            resp = _api_call("POST", "/api/openclaw/replay/history", payload, token=token)
            if resp.get("ok") and isinstance(resp.get("data"), dict):
                report = resp["data"]
                report.setdefault("notes", [])
                if isinstance(report["notes"], list):
                    report["notes"].append(f"local replay fell back to API: {exc}")
                return report
        finally:
            if token:
                try:
                    _api_call("POST", "/api/auth/logout", token=token)
                except Exception:
                    pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a no-order OpenClaw historical replay report.")
    parser.add_argument("--output", default="logs/openclaw_history_replay_report.json", help="Output JSON report path.")
    parser.add_argument("--limit", type=int, default=30, help="Daemon history records to summarize.")
    parser.add_argument("--skip-guard-replay", action="store_true", help="Do not run the no-order trade guard replay.")
    parser.add_argument("--replay-limit", type=int, default=10, help="Trade guard replay decision limit.")
    parser.add_argument("--shares", type=int, default=100, help="Default shares for guard replay decisions.")
    parser.add_argument("--mode", default="auto", choices=["auto", "full_auto", "manual"], help="Approval mode for guard replay.")
    parser.add_argument("--use-real-price", action="store_true", help="Allow guard replay to fetch real prices.")
    args = parser.parse_args()

    report = _build_report(
        {
            "limit": args.limit,
            "include_guard_replay": not args.skip_guard_replay,
            "replay_limit": args.replay_limit,
            "shares": args.shares,
            "mode": args.mode,
            "use_real_price": args.use_real_price,
        }
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    daemon = report.get("daemon", {}) or {}
    guard = report.get("trade_guard", {}) or {}
    simulation = guard.get("simulation", {}) or {}
    print(f"[REPORT] {output}")
    print(
        "[RESULT] "
        f"verdict={report.get('verdict')} "
        f"history={report.get('window', {}).get('history_count', 0)} "
        f"success_rate={daemon.get('success_rate', 0)}% "
        f"simulation={simulation.get('consecutive_success_runs', 0)}/{simulation.get('required_success_runs', 0)}"
    )
    for item in report.get("findings", [])[:10]:
        print(f"[{str(item.get('level', '')).upper()}] {item.get('code')}: {item.get('message')}")
    return 0 if report.get("verdict") != "error" else 1


if __name__ == "__main__":
    raise SystemExit(main())
