"""Bidirectional merge for ai_positions (open + recent closed)."""

from __future__ import annotations

from datetime import date, timedelta


def export_positions_bundle(repo, *, closed_days: int = 14) -> list[dict]:
    cutoff = (date.today() - timedelta(days=closed_days)).isoformat()
    rows = repo.fetchall(
        "SELECT mode, code, name, entry_date, entry_price, shares, stop_loss, status, "
        "exit_date, exit_price, exit_reason, pnl "
        "FROM ai_positions WHERE status='open' OR (status='closed' AND exit_date >= ?) "
        "ORDER BY mode, code",
        (cutoff,),
    )
    items = []
    for r in rows or []:
        items.append(
            {
                "mode": r[0],
                "code": r[1],
                "name": r[2] or "",
                "entry_date": r[3] or "",
                "entry_price": float(r[4] or 0),
                "shares": int(r[5] or 0),
                "stop_loss": float(r[6] or 0),
                "status": r[7] or "open",
                "exit_date": r[8] or "",
                "exit_price": float(r[9] or 0) if r[9] is not None else 0.0,
                "exit_reason": r[10] or "",
                "pnl": float(r[11] or 0) if r[11] is not None else 0.0,
            }
        )
    return items


def _position_key(row: dict) -> tuple:
    return (str(row.get("mode", "")), str(row.get("code", "")), str(row.get("status", "")))


def merge_position_rows(local_rows: list[dict], remote_rows: list[dict]) -> list[dict]:
    """Last-write-wins by entry_date for open; closed wins over open when exit_date newer."""
    merged: dict[tuple, dict] = {}
    for row in list(local_rows) + list(remote_rows):
        mode = str(row.get("mode", ""))
        code = str(row.get("code", ""))
        if not mode or not code:
            continue
        open_key = (mode, code, "open")
        existing = merged.get(open_key)
        if row.get("status") == "open":
            if existing is None or str(row.get("entry_date", "")) >= str(existing.get("entry_date", "")):
                merged[open_key] = dict(row)
            continue
        # closed row
        closed_key = (mode, code, "closed")
        prev = merged.get(closed_key)
        if prev is None or str(row.get("exit_date", "")) >= str(prev.get("exit_date", "")):
            merged[closed_key] = dict(row)
        # if closed is newer than open, drop open
        open_row = merged.get(open_key)
        if open_row and str(row.get("exit_date", "")) >= str(open_row.get("entry_date", "")):
            merged.pop(open_key, None)
    return list(merged.values())


def apply_positions_bundle(repo, rows: list[dict]) -> dict:
    """Replace open positions per (mode,code) and upsert recent closed."""
    applied_open = 0
    applied_closed = 0
    for row in rows:
        mode = str(row.get("mode", ""))
        code = str(row.get("code", ""))
        if not mode or not code:
            continue
        if row.get("status") == "open":
            repo.execute(
                "DELETE FROM ai_positions WHERE mode=? AND code=? AND status='open'",
                (mode, code),
            )
            repo.execute(
                "INSERT INTO ai_positions "
                "(mode,code,name,entry_date,entry_price,shares,stop_loss,status) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    mode,
                    code,
                    row.get("name", ""),
                    row.get("entry_date", ""),
                    float(row.get("entry_price", 0) or 0),
                    int(row.get("shares", 0) or 0),
                    float(row.get("stop_loss", 0) or 0),
                    "open",
                ),
            )
            applied_open += 1
        elif row.get("status") == "closed":
            repo.execute(
                "UPDATE ai_positions SET status='closed', exit_date=?, exit_price=?, "
                "exit_reason=?, pnl=? WHERE mode=? AND code=? AND status='open'",
                (
                    row.get("exit_date", ""),
                    float(row.get("exit_price", 0) or 0),
                    row.get("exit_reason", ""),
                    float(row.get("pnl", 0) or 0),
                    mode,
                    code,
                ),
            )
            applied_closed += 1
    return {"applied_open": applied_open, "applied_closed": applied_closed, "total": len(rows)}
