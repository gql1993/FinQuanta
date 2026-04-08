"""
Shared AI decision memory storage helpers.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from core.repositories.decision_repo import DecisionRepository

decision_repo = DecisionRepository()


def ensure_decision_memory_table() -> None:
    decision_repo.ensure_table()


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
    decision_repo.save_memory(
        timestamp=result.get("timestamp"),
        mode=result.get("mode", ""),
        decisions=result.get("decisions", []),
        analysis=result.get("analysis", ""),
        intel_summary=intel_step.get("summary", ""),
        candidates_count=(
            int(analysis_step.get("summary", "0").split(" ")[1])
            if "评分" in analysis_step.get("summary", "")
            else 0
        ),
        market_regime=(
            analysis_step.get("summary", "").split("环境:")[1].strip()
            if "环境:" in analysis_step.get("summary", "")
            else ""
        ),
    )


def calibrate_decisions(days_after: int = 5) -> list[dict]:
    """Calibrate historical buy decisions with realized performance."""
    ensure_decision_memory_table()
    cutoff = (date.today() - timedelta(days=days_after)).isoformat()
    rows = decision_repo.get_uncalibrated_before(cutoff)

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
            from desktop.data_access import RepoCompatConnection

            conn = RepoCompatConnection()
            quote = conn.execute(
                "SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 1",
                (code,),
            ).fetchone()
            conn.close()
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

        decision_repo.mark_calibrated(row_id, actual)
        if actual:
            calibrations.append({"id": row_id, "date": ts[:10], "results": actual})

    return calibrations


def get_decision_accuracy(limit: int = 50) -> dict:
    """Aggregate recent calibrated decision accuracy."""
    ensure_decision_memory_table()
    rows = decision_repo.get_recent_calibrated_results(limit=limit)
    total = 0
    correct = 0
    total_pnl = 0.0

    for results_json in rows:
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

    return {
        "total_decisions": total,
        "correct": correct,
        "accuracy": round(correct / total * 100, 1) if total > 0 else 0,
        "avg_pnl": round(total_pnl / total, 2) if total > 0 else 0,
    }
