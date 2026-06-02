"""Arena (19-strategy horse race) application service for API / Web."""

from __future__ import annotations

from desktop.data_access import get_kv_json


def get_arena_leaderboard() -> dict:
    from desktop.arena.leaderboard import get_leaderboard

    return get_leaderboard()


def get_arena_latest_run() -> dict:
    latest = get_kv_json("arena_run_latest", {}) or {}
    if latest:
        return latest
    from datetime import date

    return get_kv_json(f"arena_run_{date.today().isoformat()}", {}) or {}


def get_arena_positions() -> dict:
    from desktop.arena.leaderboard import get_leaderboard
    from desktop.arena.participants import DEFAULT_PARTICIPANTS
    from desktop.ai_portfolio import get_modes_comparison, get_state

    modes = [p.mode for p in DEFAULT_PARTICIPANTS]
    comp = get_modes_comparison(modes)
    prices = comp.get("prices", {})
    rows = []
    for p in DEFAULT_PARTICIPANTS:
        state = get_state(p.mode)
        for pos in state.get("positions", []) or []:
            code = pos.get("code", "")
            entry = float(pos.get("entry_price", 0) or 0)
            price = float(prices.get(code, entry) or entry)
            pnl = (price / entry - 1) * 100 if entry > 0 else 0
            rows.append(
                {
                    "participant": p.display_name,
                    "mode": p.mode,
                    "strategy_id": p.strategy_id or "",
                    "code": code,
                    "name": pos.get("name", ""),
                    "entry_price": round(entry, 2),
                    "current_price": round(price, 2),
                    "pnl_pct": round(pnl, 2),
                    "shares": pos.get("shares", 0),
                    "entry_date": pos.get("entry_date", ""),
                }
            )
    return {"positions": rows, "leaderboard": get_leaderboard()}


def run_arena_cycle(boards: list[str] | None = None) -> dict:
    from desktop.arena.runner import run_arena_cycle as _run

    return _run(boards=boards)
