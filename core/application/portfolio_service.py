"""
Application-level portfolio service.

The first iteration intentionally exposes read-oriented use cases so API and
clients can stop rebuilding portfolio response shapes in multiple places.
"""

from __future__ import annotations

from core.application.snapshot_service import get_system_snapshot


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
