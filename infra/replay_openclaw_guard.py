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


def _load_json_file(path: str) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        if isinstance(data.get("decisions"), list):
            return data["decisions"]
        if isinstance(data.get("items"), list):
            return data["items"]
        return [data]
    if isinstance(data, list):
        return data
    return []


def _load_last_scan_results() -> list[dict]:
    from desktop.data_access import get_kv_json

    rows = get_kv_json("last_scan_results", []) or []
    return rows if isinstance(rows, list) else []


def build_replay_decisions(rows: list[dict], *, default_shares: int, limit: int) -> list[dict]:
    from core.application.openclaw_service import build_unattended_trade_guard_replay_decisions

    return build_unattended_trade_guard_replay_decisions(rows, default_shares=default_shares, limit=limit)


def run_replay(decisions: list[dict], *, mode: str, use_input_price: bool = True) -> dict:
    from core.application.openclaw_service import run_unattended_trade_guard_replay_decisions

    return run_unattended_trade_guard_replay_decisions(decisions, mode=mode, use_input_price=use_input_price)


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay OpenClaw unattended trade guard without placing orders.")
    parser.add_argument("--input", help="JSON file containing decisions/items. Defaults to kv_store.last_scan_results.")
    parser.add_argument("--output", help="Write replay report to JSON file.")
    parser.add_argument("--limit", type=int, default=10, help="Max decisions to replay; <=0 means no limit.")
    parser.add_argument("--shares", type=int, default=100, help="Default shares when input does not include shares.")
    parser.add_argument("--mode", default="auto", choices=["auto", "full_auto", "manual"], help="Approval mode.")
    parser.add_argument("--use-real-price", action="store_true", help="Allow replay to fetch real prices.")
    args = parser.parse_args()

    rows = _load_json_file(args.input) if args.input else _load_last_scan_results()
    decisions = build_replay_decisions(rows, default_shares=max(1, args.shares), limit=args.limit)
    if not decisions:
        print("[FAIL] no replay decisions found")
        print("[HINT] Run OpenClaw/scan first, or pass --input replay_items.json")
        return 1

    result = run_replay(decisions, mode=args.mode, use_input_price=not args.use_real_price)
    text = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"[PASS] replay report written: {args.output}")
    print(
        "[RESULT] "
        f"input={result['input_count']} approved={result['approved_count']} "
        f"rejected={result['rejected_count']} skipped={result['skipped_count']}"
    )
    if result["rejected_count"]:
        for item in result["report"].get("rejected_decisions", [])[:5]:
            print(f"[REJECT] {item.get('code', '')} {item.get('name', '')}: {item.get('message', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
