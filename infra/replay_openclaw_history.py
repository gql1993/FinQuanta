from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api_server.env_loader import load_env_files

load_env_files()


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

    from core.application.openclaw_service import build_openclaw_historical_replay_report

    report = build_openclaw_historical_replay_report(
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
