"""
Application-level trade approval execution service.
"""

from __future__ import annotations

from core.config.feature_flags import is_feature_enabled
from core.observability.metrics import inc_counter, observe_histogram
from core.observability.structured_logging import emit_structured_log
from core.observability.tracing import (
    create_decision_id,
    create_trace_id,
    finish_span,
    start_span,
)
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
    traceparent: str = "",
) -> dict:
    normalized_action_input = (action or "").upper()
    trace_id = create_trace_id("approval")
    decision_id = create_decision_id(mode, normalized_action_input, code)
    span = start_span(
        "trade.approval",
        trace_id=trace_id,
        decision_id=decision_id,
        traceparent=traceparent,
        metadata={"mode": mode, "action": normalized_action_input, "code": code},
    )
    if not is_feature_enabled("trade_approval"):
        inc_counter("trade_approval_disabled_total", labels={"mode": mode or "unknown"})
        _record_approval_span(span, "disabled")
        return {
            "approved": False,
            "disabled": True,
            "message": "trade_approval feature is disabled",
        }
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
        inc_counter(
            "trade_approval_rejected_total",
            labels={"mode": mode or "unknown", "action": normalized_action_input or "unknown"},
        )
        log_system_event(
            "approval",
            "trade",
            f"交易审批拒绝 {action} {code}",
            detail=evaluation["message"],
            level="warning",
            trace_id=trace_id,
            decision_id=decision_id,
            metadata={"mode": mode, "action": action, "code": code},
        )
        _record_approval_span(span, "rejected")
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
        inc_counter(
            "trade_approval_executed_total",
            labels={"mode": normalized["mode"], "action": normalized_action.lower()},
        )
        log_system_event(
            "approval",
            "trade",
            f"交易审批执行 {normalized_action} {normalized['code']}",
            detail=message,
            trace_id=trace_id,
            decision_id=decision_id,
            metadata={"mode": normalized["mode"], "action": normalized_action, "code": normalized["code"]},
        )
        _record_approval_span(span, "executed", action=normalized_action)
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
    inc_counter(
        "trade_approval_executed_total",
        labels={"mode": normalized["mode"], "action": normalized_action.lower()},
    )
    log_system_event(
        "approval",
        "trade",
        f"交易审批执行 {normalized_action} {normalized['code']}",
        detail=message,
        trace_id=trace_id,
        decision_id=decision_id,
        metadata={"mode": normalized["mode"], "action": normalized_action, "code": normalized["code"]},
    )
    _record_approval_span(span, "executed", action=normalized_action)
    return result


def _record_approval_span(span: dict, status: str, *, action: str = "") -> dict:
    result = finish_span(span, status=status)
    observe_histogram(
        "trade_approval_duration_ms",
        result["duration_ms"],
        labels={"status": status, "action": (action or "n/a").lower()},
    )
    emit_structured_log(
        "trade.approval.span",
        level="info",
        trace_id=result.get("trace_id", ""),
        decision_id=result.get("decision_id", ""),
        source="approval",
        category="trace",
        span_id=result.get("span_id", ""),
        span_name=result.get("name", ""),
        status=result.get("status", ""),
        duration_ms=result.get("duration_ms", 0.0),
        metadata=result.get("metadata", {}),
    )
    return result
