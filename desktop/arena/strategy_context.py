"""Build richer per-stock context for arena strategy rules."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from desktop.data_access import get_kv_json, get_repo


def _parse_json_list(raw: Any) -> list:
    if isinstance(raw, list):
        return raw
    if not raw:
        return []
    try:
        value = json.loads(raw)
        return value if isinstance(value, list) else []
    except Exception:
        return []


def _days_since(value: Any) -> int | None:
    if not value:
        return None
    try:
        d = date.fromisoformat(str(value)[:10])
        return (date.today() - d).days
    except Exception:
        return None


def _table_columns(repo, table: str) -> list[str]:
    try:
        rows = repo.fetchall(f"PRAGMA table_info({table})", ())
        return [str(r[1]) for r in rows]
    except Exception:
        return []


def _latest_financial_context(code: str, repo) -> dict:
    cols = _table_columns(repo, "financial")
    if not cols:
        return {}
    wanted = [
        c
        for c in (
            "code",
            "name",
            "pe_dynamic",
            "pb",
            "total_mv",
            "circ_mv",
            "roe",
            "revenue_growth",
            "net_profit_growth",
            "gross_margin",
            "debt_ratio",
            "report_date",
            "updated_at",
        )
        if c in cols
    ]
    if not wanted:
        return {}
    order_col = "report_date" if "report_date" in cols else "updated_at" if "updated_at" in cols else "code"
    try:
        row = repo.fetchone(
            f"SELECT {', '.join(wanted)} FROM financial WHERE code=? ORDER BY {order_col} DESC LIMIT 1",
            (code,),
        )
    except Exception:
        return {}
    if not row:
        return {}
    data = dict(zip(wanted, row))
    data["financial_data_quality"] = "db"
    return data


def _board_context(code: str, repo) -> dict:
    boards: list[str] = []
    try:
        boards = [str(r[0]) for r in repo.fetchall("SELECT board FROM board_stocks WHERE code=?", (code,))]
    except Exception:
        boards = []

    rotation = get_kv_json("sector_rotation") or {}
    rankings = rotation.get("rankings", []) if isinstance(rotation, dict) else []
    top3 = rotation.get("top3", []) if isinstance(rotation, dict) else []
    bottom3 = rotation.get("bottom3", []) if isinstance(rotation, dict) else []
    by_board = {str(x.get("board")): x for x in rankings if isinstance(x, dict)}

    matched = [by_board[b] for b in boards if b in by_board]
    best = max(matched, key=lambda x: float(x.get("composite", 0) or 0), default={})
    return {
        "boards": boards,
        "sector_rotation": rotation if isinstance(rotation, dict) else {},
        "sector_best": best,
        "sector_composite": float(best.get("composite", 0) or 0) if best else 0.0,
        "sector_avg_5d": float(best.get("avg_5d", 0) or 0) if best else 0.0,
        "sector_avg_20d": float(best.get("avg_20d", 0) or 0) if best else 0.0,
        "sector_is_top3": any(b in top3 for b in boards),
        "sector_is_bottom3": any(b in bottom3 for b in boards),
    }


def _fund_context(code: str, repo) -> dict:
    try:
        row = repo.fetchone(
            "SELECT report_period, holding_funds, holding_value, change_type, sector, updated_at "
            "FROM fund_holdings WHERE code=? ORDER BY report_period DESC, updated_at DESC LIMIT 1",
            (code,),
        )
    except Exception:
        row = None
    if not row:
        return {}
    report_period, holding_funds, holding_value, change_type, sector, updated_at = row
    change = str(change_type or "")
    return {
        "fund_report_period": report_period,
        "holding_funds": holding_funds,
        "holding_value": holding_value,
        "fund_change_type": change,
        "fund_sector": sector,
        "fund_updated_at": updated_at,
        "fund_context_age_days": _days_since(updated_at),
        "fund_is_accumulating": ("增持" in change) or ("新进" in change),
        "fund_is_reducing": ("减持" in change) or ("退出" in change),
    }


def _event_context(boards: list[str], repo) -> dict:
    if not boards:
        return {"matched_events": [], "latest_event_days": None, "event_boards": []}
    try:
        rows = repo.fetchall(
            "SELECT event_date, event_text, source, matched_boards, created_at "
            "FROM events ORDER BY event_date DESC, id DESC LIMIT 50",
            (),
        )
    except Exception:
        rows = []

    matched = []
    for event_date, text, source, matched_boards, created_at in rows:
        event_boards = _parse_json_list(matched_boards)
        if any(b in event_boards for b in boards):
            matched.append(
                {
                    "date": event_date,
                    "text": text,
                    "source": source,
                    "boards": event_boards,
                    "created_at": created_at,
                    "days_since": _days_since(event_date),
                }
            )
    latest_days = min(
        (x["days_since"] for x in matched if x.get("days_since") is not None),
        default=None,
    )
    event_boards = sorted({b for e in matched for b in e.get("boards", [])})
    return {
        "matched_events": matched,
        "latest_event_days": latest_days,
        "event_boards": event_boards,
    }


def build_strategy_context(code: str, repo=None) -> dict:
    """Return a single context dict consumed by strategy profiles."""
    repo = repo or get_repo()
    context: dict[str, Any] = {"code": code}
    context.update(_latest_financial_context(code, repo))
    board_ctx = _board_context(code, repo)
    context.update(board_ctx)
    context.update(_fund_context(code, repo))
    context.update(_event_context(board_ctx.get("boards", []), repo))
    try:
        from desktop.market_state import get_market_state_snapshot

        market_state = get_market_state_snapshot() or {}
    except Exception:
        market_state = {}
    context["market_state"] = market_state
    context["market_state_label"] = str(market_state.get("state", "") or "")
    context["context_updated_at"] = datetime.now().isoformat()
    return context
