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


def _evaluate_buy_decisions(decisions: list[dict]) -> list[dict]:
    actual = []
    for decision in decisions:
        if decision.get("action") != "buy":
            continue
        code = decision.get("code", "")
        buy_price = float(decision.get("price", 0) or 0)
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
    return actual


def _extract_actual_items(results) -> list[dict]:
    if isinstance(results, list):
        return results
    if isinstance(results, dict):
        items = []
        items.extend(results.get("executed_buys", []) or [])
        return items
    return []


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
    verification = result.get("verification", {}) or {}
    guardrails = result.get("decision_guardrails", {}) or {}
    execution_plan = result.get("execution_plan", {}) or {}
    decision_repo.save_memory(
        timestamp=result.get("timestamp"),
        mode=result.get("mode", ""),
        decisions=result.get("executed_decisions", result.get("decisions", [])),
        raw_decisions=result.get("raw_decisions", []),
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
        verification_summary={
            "verified_count": len(verification.get("verified_candidates", []) or []),
            "questionable_count": len(verification.get("questionable_candidates", []) or []),
            "rejected_count": len(verification.get("rejected_candidates", []) or []),
            "top_failure_roots": verification.get("top_failure_roots", []),
            "accuracy": verification.get("accuracy", 0),
        },
        guardrail_summary={
            "blocked_buy_count": len(guardrails.get("blocked_buys", []) or []),
            "annotated_buy_count": len(guardrails.get("annotated_buys", []) or []),
            "summary": guardrails.get("summary", ""),
        },
        execution_plan={
            "mode": execution_plan.get("mode", "normal") if isinstance(execution_plan, dict) else "normal",
            "policy": execution_plan.get("policy", {}) if isinstance(execution_plan, dict) else {},
            "blocked_count": len(execution_plan.get("blocked", []) or []) if isinstance(execution_plan, dict) else 0,
            "blocked": execution_plan.get("blocked", []) if isinstance(execution_plan, dict) else [],
        },
    )


def calibrate_decisions(days_after: int = 5) -> list[dict]:
    """Calibrate historical buy decisions with realized performance."""
    ensure_decision_memory_table()
    cutoff = (date.today() - timedelta(days=days_after)).isoformat()
    rows = decision_repo.get_uncalibrated_before(cutoff)

    calibrations = []
    for row in rows:
        row_id, ts, decisions_json, raw_decisions_json = row[:4]
        execution_plan_json = row[4] if len(row) > 4 else ""
        try:
            decisions = json.loads(decisions_json)
        except Exception:
            continue
        try:
            raw_decisions = json.loads(raw_decisions_json) if raw_decisions_json else []
        except Exception:
            raw_decisions = []
        try:
            execution_plan = json.loads(execution_plan_json) if execution_plan_json else {}
        except Exception:
            execution_plan = {}

        actual_executed = _evaluate_buy_decisions(decisions if isinstance(decisions, list) else [])
        executed_buy_codes = {
            str(item.get("code", "") or "")
            for item in (decisions if isinstance(decisions, list) else [])
            if str(item.get("action", "")).lower() == "buy"
        }
        routed_blocked_codes = {
            str(item.get("code", "") or "")
            for item in (execution_plan.get("blocked", []) if isinstance(execution_plan, dict) else [])
            if str(item.get("action", "")).lower() == "buy"
        }
        raw_buy_decisions = [
            item for item in (raw_decisions if isinstance(raw_decisions, list) else [])
            if str(item.get("action", "")).lower() == "buy"
        ]
        routed_blocked_candidates = [
            item for item in raw_buy_decisions
            if str(item.get("code", "") or "") in routed_blocked_codes
        ]
        blocked_candidates = [
            item for item in raw_buy_decisions
            if str(item.get("code", "") or "") not in executed_buy_codes
            and str(item.get("code", "") or "") not in routed_blocked_codes
        ]
        actual_blocked = _evaluate_buy_decisions(blocked_candidates)
        actual_routed_blocked = _evaluate_buy_decisions(routed_blocked_candidates)

        summary = {
            "executed_count": len(actual_executed),
            "executed_correct": sum(1 for item in actual_executed if item.get("correct")),
            "blocked_count": len(actual_blocked),
            "blocked_avoided_losses": sum(1 for item in actual_blocked if not item.get("correct")),
            "blocked_missed_gains": sum(1 for item in actual_blocked if item.get("correct")),
            "routed_blocked_count": len(actual_routed_blocked),
            "routed_avoided_losses": sum(1 for item in actual_routed_blocked if not item.get("correct")),
            "routed_missed_gains": sum(1 for item in actual_routed_blocked if item.get("correct")),
        }
        actual_payload = {
            "executed_buys": actual_executed,
            "blocked_buys": actual_blocked,
            "routed_blocked_buys": actual_routed_blocked,
            "summary": summary,
        }

        decision_repo.mark_calibrated(row_id, actual_payload)
        if actual_executed or actual_blocked or actual_routed_blocked:
            calibrations.append({"id": row_id, "date": ts[:10], "results": actual_payload})

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
        for item in _extract_actual_items(results):
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
