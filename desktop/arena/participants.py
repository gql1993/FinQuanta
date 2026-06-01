"""Fixed arena participants: all strategy_profiles (19) racing 19×1."""

from __future__ import annotations

from dataclasses import dataclass

from strategy_profiles import STRATEGY_PROFILES


@dataclass(frozen=True)
class ArenaParticipant:
    id: str
    display_name: str
    mode: str
    pipeline: str
    description: str
    strategy_id: str = ""
    schedule: str = "daily"


def list_arena_strategy_ids() -> tuple[str, ...]:
    """All catalog strategies eligible for arena (same set as 选股雷达)."""
    return tuple(STRATEGY_PROFILES.keys())


def _strategy_participant(strategy_id: str) -> ArenaParticipant:
    profile = STRATEGY_PROFILES[strategy_id]
    display = f"[{profile.region}/{profile.camp}] {profile.name}"
    return ArenaParticipant(
        id=f"p_{strategy_id}",
        display_name=display,
        mode=f"arena_{strategy_id}",
        pipeline="fixed_strategy",
        description=profile.description,
        strategy_id=strategy_id,
    )


DEFAULT_PARTICIPANTS: tuple[ArenaParticipant, ...] = tuple(
    _strategy_participant(sid) for sid in list_arena_strategy_ids()
)

_MODE_TO_PARTICIPANT = {p.mode: p for p in DEFAULT_PARTICIPANTS}
_ID_TO_PARTICIPANT = {p.id: p for p in DEFAULT_PARTICIPANTS}


def get_participant_by_mode(mode: str) -> ArenaParticipant | None:
    return _MODE_TO_PARTICIPANT.get(mode)


def get_participant_by_id(participant_id: str) -> ArenaParticipant | None:
    return _ID_TO_PARTICIPANT.get(participant_id)


def list_active_participants() -> list[ArenaParticipant]:
    return list(DEFAULT_PARTICIPANTS)


def arena_modes() -> tuple[str, ...]:
    return tuple(p.mode for p in DEFAULT_PARTICIPANTS)


def ensure_participant_accounts(initial_capital: float = 1_000_000.0) -> None:
    from desktop.ai_portfolio import ensure_mode_account

    for participant in DEFAULT_PARTICIPANTS:
        ensure_mode_account(participant.mode, initial=initial_capital)
