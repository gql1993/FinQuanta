"""CLI: python -m desktop.arena [run|leaderboard|snapshot]"""

from __future__ import annotations

import argparse
import logging
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(_PROJECT_ROOT)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def _parse_boards(raw: str | None) -> list[str]:
    if not raw:
        return ["人工智能"]
    return [b.strip() for b in raw.split(",") if b.strip()]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    parser = argparse.ArgumentParser(description="FinQuanta Agent Arena MVP")
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="Build snapshot, run all participants, print leaderboard")
    run_p.add_argument("--boards", default="人工智能", help="Comma-separated board names")
    run_p.add_argument("--force-snapshot", action="store_true", help="Force rescan even if today's snapshot exists")

    snap_p = sub.add_parser("snapshot", help="Build or show today's shared snapshot")
    snap_p.add_argument("--boards", default="人工智能")
    snap_p.add_argument("--force", action="store_true")

    sub.add_parser("leaderboard", help="Print current leaderboard from portfolio stats")

    loss_p = sub.add_parser("losses", help="Analyze top losing trades vs board on entry date")
    loss_p.add_argument("--limit", type=int, default=10)
    loss_p.add_argument("--save", action="store_true", help="Save markdown report under data_cache/arena/")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    if args.command == "snapshot":
        from desktop.arena.snapshot import build_shared_snapshot, get_shared_snapshot

        boards = _parse_boards(args.boards)
        snap = build_shared_snapshot(boards, force=args.force) if args.force else (
            get_shared_snapshot() or build_shared_snapshot(boards)
        )
        top3 = snap.get("top3") or []
        print(f"日期: {snap.get('date')}  候选: {snap.get('candidate_count')}  策略: {snap.get('scan_strategy')}")
        for i, row in enumerate(top3, 1):
            print(f"  {i}. {row.get('代码')} {row.get('名称')} 评分{row.get('评分')}")
        return

    if args.command == "leaderboard":
        from desktop.arena.leaderboard import format_leaderboard_text, get_leaderboard, save_leaderboard_csv

        lb = get_leaderboard()
        print(format_leaderboard_text(lb))
        path = save_leaderboard_csv(lb)
        print(f"\nCSV: {path}")
        return

    if args.command == "losses":
        import os

        from desktop.arena.loss_analysis import (
            format_loss_table,
            get_top_loss_analysis,
            summarize_diagnosis,
        )

        rows = get_top_loss_analysis(args.limit)
        text = format_loss_table(rows)
        summary = summarize_diagnosis(rows)
        print(text)
        print()
        print("诊断汇总:", summary)
        if args.save:
            os.makedirs("data_cache/arena", exist_ok=True)
            out = os.path.join("data_cache/arena", "loss_top10_report.md")
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(text + "\n\n## 诊断汇总\n\n")
                for k, v in summary.items():
                    fh.write(f"- {k}: {v}\n")
            print(f"\nReport: {out}")
        return

    if args.command == "run":
        from desktop.arena.runner import run_arena_cycle

        boards = _parse_boards(args.boards)
        result = run_arena_cycle(boards, force_snapshot=args.force_snapshot)
        print(result["leaderboard_text"])
        if result.get("leaderboard_csv"):
            print(f"\nCSV: {result['leaderboard_csv']}")
        print("\n--- 各参赛者执行摘要 ---")
        for pid, lines in result.get("run_log", {}).items():
            preview = "; ".join(lines[:2]) if lines else "无输出"
            print(f"{pid}: {preview[:200]}")


if __name__ == "__main__":
    main()
