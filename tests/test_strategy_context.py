"""Richer arena strategy context."""

from __future__ import annotations

import json
import sys
import types
from datetime import date, timedelta
from pathlib import Path

import pytest

_ARENA_PKG = "desktop.arena"


@pytest.fixture(autouse=True)
def _stub_arena_package():
    import desktop

    if _ARENA_PKG not in sys.modules:
        pkg = types.ModuleType(_ARENA_PKG)
        pkg.__path__ = [str(Path(__file__).resolve().parents[1] / "desktop" / "arena")]
        sys.modules[_ARENA_PKG] = pkg
        desktop.arena = pkg
    yield


class FakeRepo:
    def fetchall(self, sql, params=()):
        if "PRAGMA table_info(financial)" in sql:
            return [
                (0, "code"),
                (1, "name"),
                (2, "pe_dynamic"),
                (3, "pb"),
                (4, "total_mv"),
                (5, "circ_mv"),
                (6, "updated_at"),
            ]
        if "SELECT board FROM board_stocks" in sql:
            return [("人工智能",), ("算力",)]
        if "FROM events" in sql:
            return [
                (
                    date.today().isoformat(),
                    "AI算力政策利好",
                    "手动",
                    json.dumps(["人工智能", "算力"], ensure_ascii=False),
                    date.today().isoformat(),
                )
            ]
        return []

    def fetchone(self, sql, params=()):
        if "FROM financial" in sql:
            return ("600000", "测试", 18.0, 2.0, 100_000_000_000, 80_000_000_000, "2026-06-01")
        if "FROM fund_holdings" in sql:
            return (
                "2025-Q4",
                120,
                2_000_000_000,
                "🔺 增持",
                "人工智能",
                (date.today() - timedelta(days=5)).isoformat(),
            )
        return None


def test_build_strategy_context_combines_real_sources(monkeypatch):
    monkeypatch.setattr(
        "desktop.arena.strategy_context.get_kv_json",
        lambda key: {
            "rankings": [
                {"board": "人工智能", "avg_5d": 4.0, "avg_20d": 10.0, "composite": 6.4},
                {"board": "煤炭", "avg_5d": -3.0, "avg_20d": -8.0, "composite": -5.0},
            ],
            "top3": ["人工智能"],
            "bottom3": ["煤炭"],
        }
        if key == "sector_rotation"
        else {},
    )
    monkeypatch.setattr(
        "desktop.market_state.get_market_state_snapshot",
        lambda: {"state": "strong_trend", "reason": "测试"},
    )

    from desktop.arena.strategy_context import build_strategy_context

    ctx = build_strategy_context("600000", FakeRepo())
    assert ctx["pe_dynamic"] == 18.0
    assert ctx["holding_funds"] == 120
    assert ctx["fund_is_accumulating"] is True
    assert ctx["sector_is_top3"] is True
    assert ctx["sector_composite"] == 6.4
    assert ctx["matched_events"]
    assert ctx["latest_event_days"] == 0
    assert ctx["market_state_label"] == "strong_trend"
