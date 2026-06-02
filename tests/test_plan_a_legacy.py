"""Plan A: legacy AI warehouses off by default; arena auto-sell enabled."""

from __future__ import annotations

import pytest


@pytest.fixture
def legacy_env(monkeypatch):
    def _set(val: str | None):
        if val is None:
            monkeypatch.delenv("FINQUANTA_LEGACY_AI_WAREHOUSES", raising=False)
        else:
            monkeypatch.setenv("FINQUANTA_LEGACY_AI_WAREHOUSES", val)

    return _set


def test_legacy_ai_default_off(legacy_env):
    legacy_env(None)
    from core.config.legacy_ai import get_legacy_ai_warehouse_settings

    assert get_legacy_ai_warehouse_settings().enabled is False


def test_sell_execution_modes_excludes_legacy_when_off(legacy_env):
    legacy_env("0")
    from desktop.auto_sell import sell_execution_modes

    modes = sell_execution_modes()
    for legacy_mode in ("full_auto", "auto", "custom", "quantum"):
        assert legacy_mode not in modes


def test_sell_execution_modes_includes_legacy_when_on(legacy_env):
    legacy_env("1")
    from desktop.auto_sell import sell_execution_modes

    modes = sell_execution_modes()
    assert "full_auto" in modes
    assert "custom" in modes


def test_auto_scheduler_skips_when_legacy_off(legacy_env):
    legacy_env("0")
    from desktop.auto_scheduler import run_scheduled_task

    result = run_scheduled_task()
    assert result.get("skipped") is True


def test_sum_modes_aggregate_math():
    """Pure math check matching desktop.arena.portfolio_summary._sum_modes."""
    comp = {
        "arena_a": {
            "equity": 1_010_000,
            "cash": 500_000,
            "positions": 2,
            "total_trades": 3,
            "total_pnl": 10_000,
            "unrealized_pnl": 8_000,
            "closed_trade_count": 1,
            "win_rate": 100.0,
        },
        "arena_b": {
            "equity": 990_000,
            "cash": 600_000,
            "positions": 1,
            "total_trades": 1,
            "total_pnl": -5_000,
            "unrealized_pnl": -3_000,
            "closed_trade_count": 0,
            "win_rate": 0.0,
        },
    }
    equity = sum(float(comp[m]["equity"]) for m in comp)
    positions = sum(int(comp[m]["positions"]) for m in comp)
    initial = 1_000_000 * len(comp)
    ret = round((equity - initial) / initial * 100, 2)
    assert equity == 2_000_000
    assert positions == 3
    assert ret == 0.0
