"""Arena leaderboard — rank fixed participants by return, win rate, and sample size."""

from __future__ import annotations

import csv
import os
from datetime import date, datetime

from desktop.arena.participants import DEFAULT_PARTICIPANTS, ArenaParticipant
from desktop.data_access import set_kv_json


def _composite_score(row: dict) -> float:
    """Personal-use ranking: return first, win rate when enough closed trades."""
    ret = float(row.get("return_pct", 0) or 0)
    win_rate = float(row.get("win_rate", 0) or 0)
    closed = int(row.get("closed_trade_count", 0) or 0)
    sample_factor = min(closed, 15) / 15.0
    win_component = win_rate * sample_factor if closed >= 3 else win_rate * 0.25
    return round(ret * 0.65 + win_component * 0.25 + sample_factor * 10 * 0.10, 2)


def get_leaderboard(participants: tuple[ArenaParticipant, ...] | None = None) -> dict:
    from desktop.ai_portfolio import get_modes_comparison

    participants = participants or DEFAULT_PARTICIPANTS
    modes = [p.mode for p in participants]
    comp = get_modes_comparison(modes)
    rows: list[dict] = []

    for p in participants:
        stats = comp.get(p.mode, {})
        row = {
            "participant_id": p.id,
            "display_name": p.display_name,
            "mode": p.mode,
            "pipeline": p.pipeline,
            "description": p.description,
            "strategy_id": p.strategy_id or "",
            "return_pct": round(float(stats.get("return_pct", 0) or 0), 2),
            "win_rate": round(float(stats.get("win_rate", 0) or 0), 1),
            "open_win_rate": round(float(stats.get("open_win_rate", 0) or 0), 1),
            "total_trades": int(stats.get("total_trades", 0) or 0),
            "closed_trade_count": int(stats.get("closed_trade_count", 0) or 0),
            "positions": int(stats.get("positions", 0) or 0),
            "equity": round(float(stats.get("equity", 0) or 0), 2),
            "total_pnl": round(float(stats.get("total_pnl", 0) or 0), 2),
        }
        row["composite_score"] = _composite_score(row)
        rows.append(row)

    rows.sort(
        key=lambda r: (r["composite_score"], r["return_pct"], r["win_rate"]),
        reverse=True,
    )
    for idx, row in enumerate(rows, start=1):
        row["rank"] = idx

    payload = {
        "date": date.today().isoformat(),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "leader": rows[0]["participant_id"] if rows else None,
        "rows": rows,
    }
    set_kv_json("arena_leaderboard_latest", payload)
    return payload


def format_leaderboard_text(leaderboard: dict | None = None) -> str:
    leaderboard = leaderboard or get_leaderboard()
    lines = [
        f"[Agent Arena] 排行榜 ({leaderboard.get('date', '')})",
        "",
    ]
    for row in leaderboard.get("rows", []):
        sample_note = ""
        closed = row.get("closed_trade_count", 0)
        if closed < 5:
            sample_note = f" ⚠样本{closed}笔"
        lines.append(
            f"{row['rank']}. {row['display_name']}"
            f"  综合{row['composite_score']:.1f}"
            f"  收益{row['return_pct']:+.2f}%"
            f"  胜率{row['win_rate']:.0f}%"
            f"  持仓{row['positions']}  交易{row['total_trades']}笔{sample_note}"
        )
    if leaderboard.get("leader"):
        leader_name = next(
            (r["display_name"] for r in leaderboard["rows"] if r["participant_id"] == leaderboard["leader"]),
            leaderboard["leader"],
        )
        lines.extend(["", f"当前领先: {leader_name}"])
    return "\n".join(lines)


def save_leaderboard_csv(
    leaderboard: dict | None = None,
    *,
    output_dir: str = "data_cache/arena",
) -> str:
    leaderboard = leaderboard or get_leaderboard()
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"leaderboard_{leaderboard.get('date', date.today().isoformat())}.csv")
    fieldnames = [
        "rank",
        "participant_id",
        "display_name",
        "mode",
        "pipeline",
        "composite_score",
        "return_pct",
        "win_rate",
        "closed_trade_count",
        "total_trades",
        "positions",
        "equity",
        "total_pnl",
    ]
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(leaderboard.get("rows", []))
    return path
