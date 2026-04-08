"""
Execution policy helpers for AI and approval flows.
"""

from __future__ import annotations


def get_execution_stage(action: str) -> str:
    normalized = (action or "").upper()
    if normalized in {"BUY", "SELL"}:
        return "execute"
    return "recommend"


def get_risk_level(action: str, mode: str = "auto") -> str:
    normalized = (action or "").upper()
    if normalized == "BUY":
        return "high"
    if normalized == "SELL":
        return "medium"
    return "low"


def build_trade_policy(action: str, mode: str = "auto") -> dict:
    return {
        "mode": mode,
        "action": (action or "").upper(),
        "stage": get_execution_stage(action),
        "risk_level": get_risk_level(action, mode=mode),
        "requires_confirmation": True,
    }
