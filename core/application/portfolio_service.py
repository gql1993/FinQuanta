"""
Application-level portfolio service.

The first iteration intentionally exposes read-oriented use cases so API and
clients can stop rebuilding portfolio response shapes in multiple places.
"""

from __future__ import annotations

from core.application.snapshot_service import get_system_snapshot
from core.repositories.portfolio_repo import PortfolioRepository

portfolio_repo = PortfolioRepository()


def get_portfolio_summary(refresh: bool = False) -> dict:
    snapshot = get_system_snapshot(refresh=refresh)
    return {
        "manual": snapshot.get("manual_portfolio", {}),
        "ai": snapshot.get("ai_portfolios", {}),
        "totals": snapshot.get("totals", {}),
    }


def get_portfolio_positions(refresh: bool = False) -> dict:
    snapshot = get_system_snapshot(refresh=refresh)
    return {
        "manual_positions": snapshot.get("manual_portfolio_raw", {}).get(
            "positions", []
        ),
        "ai_states": snapshot.get("ai_states", {}),
    }


def get_portfolio_recommendations(limit: int = 20) -> dict:
    latest = portfolio_repo.get_latest_auto_decision_memory()
    if not latest:
        return {
            "timestamp": "",
            "analysis": "",
            "items": [],
            "raw_items": [],
            "verification_summary": {},
            "guardrail_summary": {},
            "execution_plan": {},
        }
    return {
        "timestamp": latest.get("timestamp", ""),
        "analysis": latest.get("analysis", ""),
        "items": (latest.get("items") or [])[:limit],
        "raw_items": (latest.get("raw_items") or [])[:limit],
        "verification_summary": latest.get("verification_summary", {}) or {},
        "guardrail_summary": latest.get("guardrail_summary", {}) or {},
        "execution_plan": latest.get("execution_plan", {}) or {},
    }
