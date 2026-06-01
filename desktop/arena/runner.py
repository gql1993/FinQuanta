"""Run all arena participants against one shared snapshot."""

from __future__ import annotations

import logging
from datetime import datetime

from desktop.arena.leaderboard import format_leaderboard_text, get_leaderboard, save_leaderboard_csv
from desktop.arena.participants import ArenaParticipant, ensure_participant_accounts, list_active_participants
from desktop.arena.snapshot import build_shared_snapshot, get_strategy_candidates
from desktop.arena.strategy_runner import buy_strategy_top
from desktop.data_access import set_kv_json

_log = logging.getLogger("arena.runner")


def run_participant(
    participant: ArenaParticipant,
    boards: list[str],
    snapshot: dict | None,
) -> list[str]:
    if participant.pipeline == "fixed_strategy":
        candidates = get_strategy_candidates(snapshot, participant.strategy_id)
        return buy_strategy_top(
            participant.mode,
            candidates,
            top_n=1,
            reason_prefix=participant.display_name,
        )
    return [f"未知 pipeline: {participant.pipeline}"]


def run_arena_cycle(
    boards: list[str] | None = None,
    *,
    force_snapshot: bool = False,
    save_csv: bool = True,
) -> dict:
    """One arena round: shared per-strategy snapshot → run all profile strategies → leaderboard."""
    from datetime import date

    boards = boards or ["人工智能"]
    ts = datetime.now().isoformat(timespec="seconds")

    ensure_participant_accounts()
    snapshot = build_shared_snapshot(boards, force=force_snapshot)
    participants = list_active_participants()
    run_log: dict[str, list[str]] = {}

    for participant in participants:
        _log.info("arena run: %s (%s)", participant.display_name, participant.pipeline)
        try:
            run_log[participant.id] = run_participant(participant, boards, snapshot)
        except Exception as exc:
            _log.exception("arena participant failed: %s", participant.id)
            run_log[participant.id] = [f"失败: {exc}"]

    leaderboard = get_leaderboard()
    csv_path = save_leaderboard_csv(leaderboard) if save_csv else ""

    result = {
        "time": ts,
        "boards": boards,
        "snapshot": {
            "date": snapshot.get("date"),
            "strategy_count": snapshot.get("strategy_count"),
            "sector_top3": snapshot.get("sector_top3"),
            "candidate_count": snapshot.get("candidate_count"),
        },
        "participants_run": [p.id for p in participants],
        "run_log": run_log,
        "leaderboard": leaderboard,
        "leaderboard_text": format_leaderboard_text(leaderboard),
        "leaderboard_csv": csv_path,
    }
    set_kv_json(f"arena_run_{date.today().isoformat()}", result)
    set_kv_json("arena_run_latest", result)
    return result
