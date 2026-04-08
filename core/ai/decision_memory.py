"""
Shared AI decision memory storage helpers.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from api_server.config import settings
from desktop.data_access import RepoCompatConnection, get_repo

_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS ai_decision_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    mode TEXT,
    decisions TEXT,
    analysis TEXT,
    intel_summary TEXT,
    candidates_count INTEGER,
    market_regime TEXT,
    actual_results TEXT,
    calibrated INTEGER DEFAULT 0
)
"""


def ensure_decision_memory_table() -> None:
    if settings.db_backend != "postgres":
        repo = get_repo()
        repo.executescript(_DDL_SQLITE)


def save_decision_memory(result: dict) -> None:
    """Persist decision context for later calibration."""
    ensure_decision_memory_table()
    intel_step = next(
        (step for step in result.get("steps", []) if "情报" in step.get("agent", "")),
        {},
    )
    analysis_step = next(
        (step for step in result.get("steps", []) if "分析" in step.get("agent", "")),
        {},
    )
    try:
        conn = RepoCompatConnection()
        conn.execute(
            "INSERT INTO ai_decision_memory "
            "(timestamp,mode,decisions,analysis,intel_summary,candidates_count,market_regime) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                result.get("timestamp", datetime.now().isoformat()),
                result.get("mode", ""),
                json.dumps(result.get("decisions", []), ensure_ascii=False),
                result.get("analysis", ""),
                intel_step.get("summary", ""),
                int(analysis_step.get("summary", "0").split(" ")[1])
                if "评分" in analysis_step.get("summary", "")
                else 0,
                analysis_step.get("summary", "").split("环境:")[1].strip()
                if "环境:" in analysis_step.get("summary", "")
                else "",
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def calibrate_decisions(days_after: int = 5) -> list[dict]:
    """Calibrate historical buy decisions with realized performance."""
    ensure_decision_memory_table()
    conn = RepoCompatConnection()
    cutoff = (date.today() - timedelta(days=days_after)).isoformat()
    rows = conn.execute(
        "SELECT id, timestamp, decisions FROM ai_decision_memory "
        "WHERE calibrated=0 AND timestamp<? ORDER BY id",
        (cutoff,),
    ).fetchall()

    calibrations = []
    for row_id, ts, decisions_json in rows:
        try:
            decisions = json.loads(decisions_json)
        except Exception:
            continue

        actual = []
        for decision in decisions:
            if decision.get("action") != "buy":
                continue
            code = decision.get("code", "")
            buy_price = float(decision.get("price", 0))
            if not code or buy_price <= 0:
                continue
            quote = conn.execute(
                "SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 1",
                (code,),
            ).fetchone()
            if quote:
                current = quote[0]
                pnl = (current / buy_price - 1) * 100
                actual.append(
                    {
                        "code": code,
                        "buy_price": buy_price,
                        "current": round(current, 2),
                        "pnl_pct": round(pnl, 2),
                        "correct": pnl > 0,
                    }
                )

        conn.execute(
            "UPDATE ai_decision_memory SET actual_results=?, calibrated=1 WHERE id=?",
            (json.dumps(actual, ensure_ascii=False), row_id),
        )
        if actual:
            calibrations.append({"id": row_id, "date": ts[:10], "results": actual})

    conn.commit()
    conn.close()
    return calibrations


def get_decision_accuracy(limit: int = 50) -> dict:
    """Aggregate recent calibrated decision accuracy."""
    ensure_decision_memory_table()
    conn = RepoCompatConnection()
    rows = conn.execute(
        "SELECT actual_results FROM ai_decision_memory WHERE calibrated=1 ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    total = 0
    correct = 0
    total_pnl = 0.0

    for (results_json,) in rows:
        try:
            results = json.loads(results_json)
        except Exception:
            continue
        for item in results:
            total += 1
            if item.get("correct"):
                correct += 1
            pnl = item.get("pnl_pct", 0) or 0
            try:
                total_pnl += float(pnl)
            except (TypeError, ValueError):
                pass

    conn.close()
    return {
        "total_decisions": total,
        "correct": correct,
        "accuracy": round(correct / total * 100, 1) if total > 0 else 0,
        "avg_pnl": round(total_pnl / total, 2) if total > 0 else 0,
    }
