"""Agent Arena — 19 strategy profiles racing 19×1 (same rules as 选股雷达)."""

from desktop.arena.leaderboard import format_leaderboard_text, get_leaderboard, save_leaderboard_csv
from desktop.arena.participants import (
    DEFAULT_PARTICIPANTS,
    ArenaParticipant,
    arena_modes,
    ensure_participant_accounts,
    get_participant_by_id,
    get_participant_by_mode,
    list_active_participants,
)
from desktop.arena.runner import run_arena_cycle
from desktop.arena.snapshot import build_shared_snapshot, get_shared_snapshot, get_strategy_candidates
from desktop.arena.strategy_runner import buy_strategy_top, scan_with_strategy

__all__ = [
    "ArenaParticipant",
    "DEFAULT_PARTICIPANTS",
    "arena_modes",
    "build_shared_snapshot",
    "buy_strategy_top",
    "ensure_participant_accounts",
    "format_leaderboard_text",
    "get_leaderboard",
    "get_participant_by_id",
    "get_participant_by_mode",
    "get_shared_snapshot",
    "get_strategy_candidates",
    "list_active_participants",
    "run_arena_cycle",
    "save_leaderboard_csv",
    "scan_with_strategy",
]
