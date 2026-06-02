"""Short-term event / fund holdings views for API / Web."""

from __future__ import annotations

import json

from desktop.data_access import get_kv_json
from api_server.storage import repo


def list_recent_events(limit: int = 50) -> list[dict]:
    rows = repo.fetchall(
        "SELECT id, event_date, event_text, source, matched_boards, created_at "
        "FROM events ORDER BY id DESC LIMIT ?",
        (max(1, min(limit, 200)),),
    )
    items = []
    for row in rows or []:
        boards_raw = row[4] if len(row) > 4 else "[]"
        try:
            boards = json.loads(boards_raw) if isinstance(boards_raw, str) else boards_raw
        except Exception:
            boards = []
        items.append(
            {
                "id": row[0],
                "event_date": row[1],
                "event_text": row[2],
                "source": row[3],
                "matched_boards": boards if isinstance(boards, list) else [],
                "created_at": row[5] if len(row) > 5 else "",
            }
        )
    return items


def list_fund_holdings(report_period: str | None = None, limit: int = 100) -> dict:
    period = report_period
    if not period:
        row = repo.fetchone(
            "SELECT report_period FROM fund_holdings ORDER BY report_period DESC LIMIT 1"
        )
        period = row[0] if row else ""
    if not period:
        return {"report_period": "", "items": []}

    rows = repo.fetchall(
        "SELECT code, name, holding_funds, total_shares, market_value, change_type, report_period "
        "FROM fund_holdings WHERE report_period=? "
        "ORDER BY holding_funds DESC LIMIT ?",
        (period, max(1, min(limit, 500))),
    )
    items = [
        {
            "code": r[0],
            "name": r[1],
            "holding_funds": r[2],
            "total_shares": r[3],
            "market_value": r[4],
            "change_type": r[5],
            "report_period": r[6],
        }
        for r in (rows or [])
    ]
    return {"report_period": period, "items": items}


def get_news_sentiment_snapshot() -> dict:
    snap = get_kv_json("news_sentiment_snapshot", {}) or {}
    if isinstance(snap, dict):
        return snap
    return {}
