"""
Application-level trade approval execution service.
"""

from __future__ import annotations


def approve_trade(
    mode: str,
    action: str,
    code: str,
    name: str,
    price: float,
    shares: int,
    reason: str = "",
) -> dict:
    normalized_action = (action or "").upper()
    if normalized_action not in {"BUY", "SELL"}:
        raise ValueError("action must be BUY or SELL")

    if normalized_action == "BUY":
        from desktop.ai_portfolio import buy

        message = buy(
            mode,
            code,
            name or code,
            price,
            shares,
            round(price * 0.92, 2),
            f"[审批执行] {reason}",
        )
        return {"approved": True, "action": normalized_action, "message": message}

    from desktop.ai_portfolio import sell

    message = sell(mode, code, price, f"[审批执行] {reason}")
    return {"approved": True, "action": normalized_action, "message": message}
