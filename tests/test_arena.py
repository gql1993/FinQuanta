"""Tests for Agent Arena (19 strategy profiles)."""

from strategy_profiles import STRATEGY_PROFILES

from desktop.arena.participants import (
    DEFAULT_PARTICIPANTS,
    arena_modes,
    list_active_participants,
    list_arena_strategy_ids,
)
from desktop.arena.leaderboard import _composite_score


def test_composite_score_prefers_return_with_enough_samples():
    high_return = _composite_score(
        {"return_pct": 12.0, "win_rate": 55.0, "closed_trade_count": 10}
    )
    low_return = _composite_score(
        {"return_pct": 2.0, "win_rate": 80.0, "closed_trade_count": 10}
    )
    assert high_return > low_return


def test_default_participants_count():
    assert len(DEFAULT_PARTICIPANTS) == len(STRATEGY_PROFILES) == 19


def test_strategy_participants_cover_all_profiles():
    strategy_ids = {p.strategy_id for p in DEFAULT_PARTICIPANTS if p.pipeline == "fixed_strategy"}
    assert strategy_ids == set(STRATEGY_PROFILES.keys())
    assert strategy_ids == set(list_arena_strategy_ids())


def test_all_participants_use_fixed_strategy_pipeline():
    assert all(p.pipeline == "fixed_strategy" for p in DEFAULT_PARTICIPANTS)


def test_arena_modes_count():
    assert len(arena_modes()) == 19


def test_list_active_participants_returns_all():
    assert len(list_active_participants()) == 19


def test_participant_modes_are_unique():
    modes = [p.mode for p in DEFAULT_PARTICIPANTS]
    assert len(modes) == len(set(modes))
    assert all(m.startswith("arena_") for m in modes)
