"""
Portfolio repository.

This repository is the first extraction target for portfolio-related persisted
reads so application services stop reaching directly into SQL details.
"""

from __future__ import annotations

from core.repositories.decision_repo import DecisionRepository
from desktop.platform_store import get_kv_json

decision_repo = DecisionRepository()


class PortfolioRepository:
    def get_manual_portfolio(self) -> dict:
        value = get_kv_json(
            "manual_portfolio",
            {"positions": [], "cash": 1_000_000, "initial_capital": 1_000_000},
        )
        return value if isinstance(value, dict) else {}

    def get_latest_auto_decision_memory(self) -> dict | None:
        return decision_repo.get_latest_auto_memory()
