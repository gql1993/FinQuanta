"""
Application-level trade approval execution service.
"""

from __future__ import annotations

from core.application.ops_service import log_system_event
from core.risk.approval_service import evaluate_trade_request


def approve_trade(
    mode: str,
    action: str,
    code: str,
    name: str,
    price: float,
    shares: int,
    reason: str = "",
) -> dict:
    evaluation = evaluate_trade_request(
        mode=mode,
        action=action,
        code=code,
        name=name,
        price=price,
        shares=shares,
        reason=reason,
    )
    if not evaluation["approved"]:
        log_system_event(
            "approval",
            "trade",
            f"交易审批拒绝 {action} {code}",
            detail=evaluation["message"],
            level="warning",
        )
        return evaluation

    normalized = evaluation["normalized"]
    normalized_action = normalized["action"]

    if normalized_action == "BUY":
        from desktop.ai_portfolio import buy

        message = buy(
            normalized["mode"],
            normalized["code"],
            normalized["name"],
            normalized["price"],
            normalized["shares"],
            round(normalized["price"] * 0.92, 2),
            f"[审批执行] {reason}",
        )
        result = {
            **evaluation,
            "approved": True,
            "action": normalized_action,
            "message": message,
        }
        log_system_event(
            "approval",
            "trade",
            f"交易审批执行 {normalized_action} {normalized['code']}",
            detail=message,
        )
        return result

    from desktop.ai_portfolio import sell

    message = sell(
        normalized["mode"],
        normalized["code"],
        normalized["price"],
        f"[审批执行] {reason}",
    )
    result = {
        **evaluation,
        "approved": True,
        "action": normalized_action,
        "message": message,
    }
    log_system_event(
        "approval",
        "trade",
        f"交易审批执行 {normalized_action} {normalized['code']}",
        detail=message,
    )
    return result
