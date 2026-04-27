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
SNAPSHOT_SCHEMA_VERSION = 2


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


def _load_latest_prices(codes: list[str]) -> dict[str, float]:
    prices: dict[str, float] = {}
    if not codes:
        return prices

    try:
        from desktop.realtime_data import get_realtime_quotes

        quotes = get_realtime_quotes(codes, force=True)
        for code, quote in quotes.items():
            px = quote.get("price", 0)
            if px and px > 0:
                prices[code] = float(px)
    except Exception:
        pass

    missing = [code for code in codes if code not in prices]
    if not missing:
        return prices

    try:
        from desktop.data_access import get_repo

        repo = get_repo()
        for code in missing:
            row = repo.fetchone(
                "SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 1",
                (code,),
            )
            if row and row[0] is not None:
                try:
                    px = float(row[0])
                    if px > 0:
                        prices[code] = px
                except (TypeError, ValueError):
                    pass
    except Exception:
        pass

    return prices


def _get_manual_sell_trades(manual_pf: dict) -> list[dict]:
    history = manual_pf.get("history", []) or []
    sell_history = [
        item for item in history
        if str(item.get("action", "")).upper() == "SELL"
    ]
    if sell_history:
        return sell_history
    return manual_pf.get("closed_trades", []) or []


def _get_manual_trade_count(manual_pf: dict) -> int:
    history = manual_pf.get("history", []) or []
    trade_history = [
        item for item in history
        if str(item.get("action", "")).upper() in {"BUY", "SELL"}
    ]
    if trade_history:
        return len(trade_history)

    positions = manual_pf.get("positions", []) or []
    closed_trades = manual_pf.get("closed_trades", []) or []
    return len(positions) + len(closed_trades) * 2


def _build_manual_portfolio_summary(manual_pf: dict) -> dict:
    positions = manual_pf.get("positions", []) or []
    cash = float(manual_pf.get("cash", 0) or 0)
    initial_capital = max(float(manual_pf.get("initial_capital", 1_000_000) or 1_000_000), 1)
    prices = _load_latest_prices([
        str(position.get("code", ""))
        for position in positions
        if position.get("code")
    ])

    position_value = 0.0
    total_cost = 0.0
    unrealized_pnl = 0.0
    for position in positions:
        entry_price = float(position.get("entry_price", 0) or 0)
        shares = int(position.get("shares", 0) or 0)
        price = prices.get(position.get("code", ""), entry_price)
        market_value = price * shares
        cost = entry_price * shares
        position_value += market_value
        total_cost += cost
        unrealized_pnl += market_value - cost

    sell_trades = _get_manual_sell_trades(manual_pf)
    realized_pnl = sum(float(item.get("pnl", 0) or 0) for item in sell_trades)
    total_equity = cash + position_value
    total_pnl = total_equity - initial_capital
    total_return = (total_pnl / initial_capital) * 100 if initial_capital > 0 else 0

    return {
        "equity": round(total_equity, 2),
        "return_pct": round(total_return, 2),
        "cash": round(cash, 2),
        "positions": len(positions),
        "position_value": round(position_value, 2),
        "total_cost": round(total_cost, 2),
        "unrealized_pnl": round(unrealized_pnl, 2),
        "realized_pnl": round(realized_pnl, 2),
        "total_pnl": round(total_pnl, 2),
        "total_trades": _get_manual_trade_count(manual_pf),
    }


def _snapshot_requires_refresh(snapshot: dict) -> bool:
    if snapshot.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        return True

    manual = snapshot.get("manual_portfolio", {}) or {}
    if not {"equity", "unrealized_pnl", "total_pnl", "total_trades"}.issubset(manual.keys()):
        return True

    ai = snapshot.get("ai_portfolios", {}) or {}
    for mode in ("full_auto", "auto", "custom", "quantum"):
        if mode in ai and "unrealized_pnl" not in (ai.get(mode) or {}):
            return True
    return False


def build_system_snapshot() -> dict:
    from desktop.ai_portfolio import get_comparison
    from desktop.market_state import get_market_state_snapshot
    from desktop.task_orchestrator import (
        get_recent_system_events,
        get_recent_task_runs,
    )

    manual_pf = snapshot_repo.get_manual_portfolio()
    manual_summary = _build_manual_portfolio_summary(manual_pf)

    comparison = get_comparison()
    ai_states = {
        mode: _safe_ai_state(mode)
        for mode in ["full_auto", "auto", "manual", "custom", "quantum"]
    }
    risk = snapshot_repo.get_portfolio_risk()
    market = get_market_state_snapshot()

    tracked_modes = ["full_auto", "auto", "custom", "quantum"]
    total_equity = manual_summary.get("equity", 0) + sum(
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
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "updated_at": datetime.now().isoformat(),
        "manual_portfolio_raw": manual_pf,
        "manual_portfolio": manual_summary,
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
    cached = get_system_snapshot_cached()
    if cached and not _snapshot_requires_refresh(cached):
        return cached
    return build_system_snapshot()
