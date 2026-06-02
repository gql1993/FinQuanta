"""Aggregate arena portfolio stats for dashboard / reports."""

from __future__ import annotations

from desktop.arena.leaderboard import get_leaderboard
from desktop.arena.participants import DEFAULT_PARTICIPANTS, arena_modes
from desktop.ai_portfolio import get_modes_comparison

_ARENA_INITIAL_PER_MODE = 1_000_000.0


def _sum_modes(comp: dict, modes: list[str]) -> dict:
    totals = {
        "equity": 0.0,
        "cash": 0.0,
        "positions": 0,
        "total_trades": 0,
        "total_pnl": 0.0,
        "unrealized_pnl": 0.0,
        "closed_trade_count": 0,
        "win_weight": 0.0,
        "open_win_weight": 0.0,
    }
    for mode in modes:
        c = comp.get(mode, {})
        totals["equity"] += float(c.get("equity", 0) or 0)
        totals["cash"] += float(c.get("cash", 0) or 0)
        totals["positions"] += int(c.get("positions", 0) or 0)
        totals["total_trades"] += int(c.get("total_trades", 0) or 0)
        totals["total_pnl"] += float(c.get("total_pnl", 0) or 0)
        totals["unrealized_pnl"] += float(c.get("unrealized_pnl", 0) or 0)
        closed = int(c.get("closed_trade_count", 0) or 0)
        totals["closed_trade_count"] += closed
        totals["win_weight"] += float(c.get("win_rate", 0) or 0) * closed
        open_n = int(c.get("positions", 0) or 0)
        totals["open_win_weight"] += float(c.get("open_win_rate", 0) or 0) * open_n

    initial = _ARENA_INITIAL_PER_MODE * max(len(modes), 1)
    totals["return_pct"] = round((totals["equity"] - initial) / initial * 100, 2) if initial else 0.0
    closed_all = totals["closed_trade_count"]
    open_all = totals["positions"]
    totals["win_rate"] = round(totals["win_weight"] / closed_all, 1) if closed_all else 0.0
    totals["open_win_rate"] = round(totals["open_win_weight"] / open_all, 1) if open_all else 0.0
    totals["equity"] = round(totals["equity"], 2)
    totals["cash"] = round(totals["cash"], 2)
    totals["total_pnl"] = round(totals["total_pnl"], 2)
    totals["unrealized_pnl"] = round(totals["unrealized_pnl"], 2)
    return totals


def get_arena_dashboard_data(*, top_n: int = 4) -> tuple[dict, list[dict], dict]:
    """Return (aggregate, top-N strategy stats, full modes comparison)."""
    modes = list(arena_modes())
    comp = get_modes_comparison(modes)
    aggregate = _sum_modes(comp, modes)

    leaderboard = get_leaderboard()
    top_rows: list[dict] = []
    for row in leaderboard.get("rows", [])[:top_n]:
        mode = str(row.get("mode") or "")
        stats = dict(comp.get(mode, {}))
        stats["display_name"] = row.get("display_name", mode)
        stats["rank"] = row.get("rank", 0)
        stats["strategy_id"] = row.get("strategy_id", "")
        top_rows.append(stats)

    while len(top_rows) < top_n:
        top_rows.append(
            {
                "display_name": "-",
                "equity": 0,
                "return_pct": 0,
                "total_pnl": 0,
                "positions": 0,
                "cash": 0,
                "win_rate": 0,
                "open_win_rate": 0,
                "total_trades": 0,
            }
        )

    return aggregate, top_rows, comp


def get_arena_all_states(comp: dict | None = None) -> dict[str, dict]:
    """States keyed by arena mode for position tables."""
    from desktop.ai_portfolio import get_state

    comp = comp or get_modes_comparison(list(arena_modes()))
    states: dict[str, dict] = {}
    for participant in DEFAULT_PARTICIPANTS:
        states[participant.mode] = get_state(participant.mode)
    states["_prices"] = comp.get("prices", {})
    return states
