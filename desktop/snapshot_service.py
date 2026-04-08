"""
统一快照服务

为 Dashboard / AI仓 / OpenClaw / Web 端提供统一的只读快照，
避免每个模块各自重复聚合计算。
"""
from __future__ import annotations

from datetime import datetime
from desktop.platform_store import get_kv_json, set_kv_json


def build_system_snapshot() -> dict:
    from desktop.ai_portfolio import get_comparison, get_state
    from desktop.market_state import get_market_state_snapshot
    from desktop.task_orchestrator import get_recent_system_events, get_recent_task_runs

    manual_pf = get_kv_json("manual_portfolio", {"positions": [], "cash": 1_000_000, "initial_capital": 1_000_000})

    manual_cost = sum((p.get("entry_price", 0) or 0) * (p.get("shares", 0) or 0) for p in manual_pf.get("positions", []))
    manual_eq = manual_pf.get("cash", 0) + manual_cost
    manual_ret = (manual_eq - manual_pf.get("initial_capital", 1_000_000)) / max(manual_pf.get("initial_capital", 1_000_000), 1) * 100

    comp = get_comparison()
    ai_states = {}
    for mode in ["full_auto", "auto", "manual", "custom", "quantum"]:
        try:
            ai_states[mode] = get_state(mode)
        except Exception:
            ai_states[mode] = {"cash": 0, "initial_capital": 1_000_000, "positions": [], "closed_trades": []}
    risk = get_kv_json("portfolio_risk", {})
    market = get_market_state_snapshot()

    total_equity = manual_eq + sum(comp.get(m, {}).get("equity", 0) for m in ["full_auto", "auto", "custom", "quantum"])
    total_cash = manual_pf.get("cash", 0) + sum(comp.get(m, {}).get("cash", 0) for m in ["full_auto", "auto", "custom", "quantum"])
    total_positions = len(manual_pf.get("positions", [])) + sum(comp.get(m, {}).get("positions", 0) for m in ["full_auto", "auto", "custom", "quantum"])

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
            "total_pnl": round(manual_eq - manual_pf.get("initial_capital", 1_000_000), 2),
        },
        "ai_portfolios": comp,
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
    snap = build_system_snapshot()
    set_kv_json("system_snapshot", snap)
    return snap


def get_system_snapshot() -> dict:
    snap = get_kv_json("system_snapshot", None)
    return snap if isinstance(snap, dict) else build_system_snapshot()
