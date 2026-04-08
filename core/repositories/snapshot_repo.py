"""
Snapshot repository.

This repository focuses on persisted snapshot-related reads/writes and keeps
cache-oriented storage access out of application services.
"""

from __future__ import annotations

from desktop.platform_store import get_kv_json, set_kv_json


DEFAULT_MANUAL_PORTFOLIO = {
    "positions": [],
    "cash": 1_000_000,
    "initial_capital": 1_000_000,
}


class SnapshotRepository:
    def get_manual_portfolio(self) -> dict:
        manual = get_kv_json("manual_portfolio", DEFAULT_MANUAL_PORTFOLIO)
        return manual if isinstance(manual, dict) else dict(DEFAULT_MANUAL_PORTFOLIO)

    def get_portfolio_risk(self) -> dict:
        risk = get_kv_json("portfolio_risk", {})
        return risk if isinstance(risk, dict) else {}

    def get_cached_snapshot(self) -> dict | None:
        snapshot = get_kv_json("system_snapshot", None)
        return snapshot if isinstance(snapshot, dict) else None

    def save_snapshot(self, snapshot: dict) -> None:
        set_kv_json("system_snapshot", snapshot)
