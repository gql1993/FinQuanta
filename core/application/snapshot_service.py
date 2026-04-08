"""
Application-level snapshot service.

This module is the first extraction from the desktop monolith. The initial
implementation intentionally reuses existing desktop/domain functions so API,
desktop, and web can start converging on a shared service entry point without
breaking the runnable baseline.
"""

from __future__ import annotations

from datetime import datetime

from core.repositories.snapshot_repo import SnapshotRepository


snapshot_repo = SnapshotRepository()


def _safe_ai_state(mode: str) -> dict:
    from desktop.ai_portfolio import get_state

    try:
        return get_state(mode)
    except Exception:
        return {
            "cash": 0,
            "initial_capital": 1_000_000,
            "positions": [],
            "closed_trades": [],
        }


def build_system_snapshot() -> dict:
    from desktop.ai_portfolio import get_comparison
    from desktop.market_state import get_market_state_snapshot
    from desktop.task_orchestrator import (
        get_recent_system_events,
        get_recent_task_runs,
    )

    manual_pf = snapshot_repo.get_manual_portfolio()
    manual_cost = sum(
        (position.get("entry_price", 0) or 0)
        * (position.get("shares", 0) or 0)
        for position in manual_pf.get("positions", [])
    )
    manual_eq = manual_pf.get("cash", 0) + manual_cost
    initial_capital = max(manual_pf.get("initial_capital", 1_000_000), 1)
    manual_ret = (manual_eq - initial_capital) / initial_capital * 100

    comparison = get_comparison()
    ai_states = {
        mode: _safe_ai_state(mode)
        for mode in ["full_auto", "auto", "manual", "custom", "quantum"]
    }
    risk = snapshot_repo.get_portfolio_risk()
    market = get_market_state_snapshot()

    tracked_modes = ["full_auto", "auto", "custom", "quantum"]
    total_equity = manual_eq + sum(
        comparison.get(mode, {}).get("equity", 0) for mode in tracked_modes
    )
    total_cash = manual_pf.get("cash", 0) + sum(
        comparison.get(mode, {}).get("cash", 0) for mode in tracked_modes
    )
    total_positions = len(manual_pf.get("positions", [])) + sum(
        comparison.get(mode, {}).get("positions", 0) for mode in tracked_modes
    )

    trading_engine: dict = {}
    try:
        from desktop.engine.main_engine import get_default_main_engine

        trading_engine = get_default_main_engine().snapshot()
    except Exception:
        trading_engine = {}

    return {
        "updated_at": datetime.now().isoformat(),
        "manual_portfolio_raw": manual_pf,
        "manual_portfolio": {
            "equity": round(manual_eq, 2),
            "return_pct": round(manual_ret, 2),
            "cash": round(manual_pf.get("cash", 0), 2),
            "positions": len(manual_pf.get("positions", [])),
            "total_pnl": round(manual_eq - initial_capital, 2),
        },
        "ai_portfolios": comparison,
        "ai_states": ai_states,
        "risk": risk,
        "market_state": market,
        "task_runs": get_recent_task_runs(20),
        "system_events": get_recent_system_events(20),
        "totals": {
            "equity": round(total_equity, 2),
            "cash": round(total_cash, 2),
            "positions": total_positions,
        },
        "trading_engine": trading_engine,
    }


def save_system_snapshot() -> dict:
    snapshot = build_system_snapshot()
    snapshot_repo.save_snapshot(snapshot)
    return snapshot


def get_system_snapshot_cached() -> dict | None:
    return snapshot_repo.get_cached_snapshot()


def get_system_snapshot(refresh: bool = False) -> dict:
    if refresh:
        return build_system_snapshot()
    return get_system_snapshot_cached() or build_system_snapshot()
