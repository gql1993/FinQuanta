"""
Approval and risk-check skeleton for high-risk actions.
"""

from __future__ import annotations

from core.risk.policies import build_trade_policy
from desktop.engine.risk_manager import RiskManager


def evaluate_trade_request(
    *,
    mode: str,
    action: str,
    code: str,
    name: str,
    price: float,
    shares: int,
    reason: str = "",
) -> dict:
    normalized_action = (action or "").upper()
    policy = build_trade_policy(normalized_action, mode=mode)
    errors: list[str] = []

    if normalized_action not in {"BUY", "SELL"}:
        errors.append("action must be BUY or SELL")
    if not code or len(code.strip()) != 6:
        errors.append("invalid stock code")
    if price <= 0:
        errors.append("price must be positive")
    if normalized_action == "BUY":
        if shares <= 0:
            errors.append("shares must be positive for BUY")
        elif shares % 100 != 0:
            errors.append("shares must be a multiple of 100 for BUY")

    risk_manager = RiskManager()
    risk_check = risk_manager.check_new_order(
        normalized_action,
        code.strip(),
        max(shares, 0),
        price,
    )
    risk_checks = [
        {
            "ok": risk_check.ok,
            "reason": risk_check.reason,
        }
    ]
    if not risk_check.ok:
        errors.append(risk_check.reason or "risk check failed")

    approved = not errors
    return {
        "approved": approved,
        "policy": policy,
        "normalized": {
            "mode": mode,
            "action": normalized_action,
            "code": code.strip(),
            "name": name or code.strip(),
            "price": price,
            "shares": shares,
            "reason": reason,
        },
        "risk_checks": risk_checks,
        "message": "approved" if approved else "; ".join(errors),
    }
