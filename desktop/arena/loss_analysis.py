"""Analyze worst losing trades vs board performance on entry date."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from desktop.data_access import get_repo


def _board_for_code(repo, code: str) -> str:
    row = repo.fetchone("SELECT board FROM board_stocks WHERE code=? LIMIT 1", (code,))
    return str(row[0]) if row and row[0] else ""


def _board_codes(repo, board: str, limit: int = 30) -> list[str]:
    if not board:
        return []
    rows = repo.fetchall(
        "SELECT code FROM board_stocks WHERE board=? LIMIT ?",
        (board, limit),
    )
    return [r[0] for r in rows]


def _pct_on_date(repo, code: str, day: str) -> float | None:
    row = repo.fetchone(
        "SELECT pct_change FROM daily_kline WHERE code=? AND date=?",
        (code, day),
    )
    if row and row[0] is not None:
        return float(row[0])
    rows = repo.fetchall(
        "SELECT date, close FROM daily_kline WHERE code=? AND date<=? ORDER BY date DESC LIMIT 2",
        (code, day),
    )
    if len(rows) < 2:
        return None
    cur, prev = float(rows[0][1]), float(rows[1][1])
    if prev <= 0:
        return None
    return (cur / prev - 1) * 100


def _board_avg_pct(repo, board: str, day: str) -> float | None:
    codes = _board_codes(repo, board)
    vals = [_pct_on_date(repo, c, day) for c in codes]
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 2) if vals else None


def _board_avg_window(repo, board: str, end_day: str, days: int) -> float | None:
    """Average N-day return of board constituents ending on end_day."""
    codes = _board_codes(repo, board)
    if not codes:
        return None
    rets: list[float] = []
    for code in codes:
        rows = repo.fetchall(
            "SELECT close FROM daily_kline WHERE code=? AND date<=? ORDER BY date DESC LIMIT ?",
            (code, end_day, days + 1),
        )
        if len(rows) < days + 1:
            continue
        start = float(rows[-1][0])
        end = float(rows[0][0])
        if start > 0:
            rets.append((end / start - 1) * 100)
    return round(sum(rets) / len(rets), 2) if rets else None


def get_board_return_window(board: str, end_day: str | None = None, days: int = 5) -> float | None:
    """Public helper: average N-day return for a board ending on end_day (default today)."""
    if not board:
        return None
    day = end_day or date.today().isoformat()
    return _board_avg_window(get_repo(), board, day, days)


def _stop_distance_pct(entry: float, stop: float | None) -> float | None:
    if not entry or entry <= 0 or not stop or stop <= 0:
        return None
    return round((entry - stop) / entry * 100, 2)


def _classify_exit(exit_reason: str) -> str:
    text = str(exit_reason or "")
    if "止损触发" in text or "ATR" in text:
        return "止损"
    if "VCP失败" in text:
        return "VCP失败"
    if "AI决策" in text:
        return "AI卖出"
    if "时间止损" in text:
        return "时间止损"
    return "其他"


def _diagnose(row: dict[str, Any]) -> str:
    tags: list[str] = []
    board5 = row.get("board_5d_before_buy")
    stock5 = row.get("stock_5d_before_buy")
    board_day = row.get("board_day_pct")
    stock_day = row.get("stock_day_pct")
    hold = row.get("hold_days")
    exit_type = row.get("exit_type")
    stop_dist = row.get("stop_distance_pct")

    if board5 is not None and board5 < 0:
        tags.append("时机:板块5日弱")
    elif stock5 is not None and board5 is not None and stock5 > board5 + 5:
        tags.append("时机:追高")

    if board_day is not None and stock_day is not None and stock_day < board_day - 2:
        tags.append("选股:弱于板块")

    if exit_type in {"止损", "VCP失败"} and hold is not None and hold <= 5:
        tags.append("止损:过快触发")
    if stop_dist is not None and stop_dist <= 8:
        tags.append("止损:距离偏紧")

    if not tags:
        tags.append("综合")
    return " | ".join(tags)


def get_top_loss_analysis(limit: int = 10) -> list[dict[str, Any]]:
    repo = get_repo()
    rows = repo.fetchall(
        """
        SELECT mode, code, name, entry_date, entry_price, exit_date, exit_price,
               shares, pnl, stop_loss, exit_reason
        FROM ai_positions
        WHERE status='closed' AND pnl IS NOT NULL
        ORDER BY pnl ASC
        LIMIT ?
        """,
        (limit,),
    )

    results: list[dict[str, Any]] = []
    for mode, code, name, entry_date, entry_price, exit_date, exit_price, shares, pnl, stop_loss, exit_reason in rows:
        board = _board_for_code(repo, code)
        entry_day = str(entry_date or "")[:10]
        exit_day = str(exit_date or "")[:10]

        try:
            hold_days = (date.fromisoformat(exit_day) - date.fromisoformat(entry_day)).days
        except Exception:
            hold_days = None

        stock_day_pct = _pct_on_date(repo, code, entry_day) if entry_day else None
        board_day_pct = _board_avg_pct(repo, board, entry_day) if entry_day and board else None
        board_5d = _board_avg_window(repo, board, entry_day, 5) if entry_day and board else None
        stock_5d = None
        if entry_day:
            srows = repo.fetchall(
                "SELECT close FROM daily_kline WHERE code=? AND date<=? ORDER BY date DESC LIMIT 6",
                (code, entry_day),
            )
            if len(srows) >= 6 and float(srows[-1][0]) > 0:
                stock_5d = round((float(srows[0][0]) / float(srows[-1][0]) - 1) * 100, 2)

        trade_ret = None
        if entry_price and exit_price and entry_price > 0:
            trade_ret = round((float(exit_price) / float(entry_price) - 1) * 100, 2)

        exit_type = _classify_exit(exit_reason or "")
        stop_dist = _stop_distance_pct(float(entry_price or 0), float(stop_loss) if stop_loss else None)

        item = {
            "mode": mode,
            "code": code,
            "name": name or "",
            "board": board,
            "entry_date": entry_day,
            "exit_date": exit_day,
            "hold_days": hold_days,
            "entry_price": round(float(entry_price or 0), 2),
            "exit_price": round(float(exit_price or 0), 2),
            "trade_return_pct": trade_ret,
            "pnl": round(float(pnl or 0), 2),
            "shares": int(shares or 0),
            "stop_loss": round(float(stop_loss), 2) if stop_loss else None,
            "stop_distance_pct": stop_dist,
            "stock_day_pct": round(stock_day_pct, 2) if stock_day_pct is not None else None,
            "board_day_pct": board_day_pct,
            "stock_5d_before_buy": stock_5d,
            "board_5d_before_buy": board_5d,
            "exit_type": exit_type,
            "exit_reason": str(exit_reason or "")[:80],
        }
        item["diagnosis"] = _diagnose(item)
        results.append(item)
    return results


def summarize_diagnosis(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        for part in str(row.get("diagnosis", "")).split(" | "):
            counts[part] = counts.get(part, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: -x[1]))


def format_loss_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "亏损 Top10 对照表（买入日 vs 板块）",
        "",
        "| # | 仓 | 代码 | 板块 | 买入日 | 持有 | 盈亏 | 个股买日% | 板块买日% | 个股5日% | 板块5日% | 止损距% | 退出 | 诊断 |",
        "|---|-----|------|------|--------|------|------|-----------|-----------|----------|----------|---------|------|------|",
    ]
    for i, r in enumerate(rows, 1):
        lines.append(
            f"| {i} | {r['mode']} | {r['code']} | {r['board'] or '-'} | {r['entry_date']} | "
            f"{r['hold_days']}d | {r['pnl']:+.0f} | "
            f"{_fmt(r.get('stock_day_pct'))} | {_fmt(r.get('board_day_pct'))} | "
            f"{_fmt(r.get('stock_5d_before_buy'))} | {_fmt(r.get('board_5d_before_buy'))} | "
            f"{_fmt(r.get('stop_distance_pct'))} | {r['exit_type']} | {r['diagnosis']} |"
        )
    return "\n".join(lines)


def _fmt(v: Any) -> str:
    if v is None:
        return "-"
    return f"{float(v):+.1f}%" if isinstance(v, (int, float)) else str(v)
