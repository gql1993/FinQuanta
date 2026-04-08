from __future__ import annotations

from typing import Any


ACTION_POLICIES: dict[str, dict[str, Any]] = {
    "query.system_snapshot": {"allowed": True, "requires_confirmation": False, "risk_level": "low"},
    "query.trend_verify_summary": {"allowed": True, "requires_confirmation": False, "risk_level": "low"},
    "query.task_runs": {"allowed": True, "requires_confirmation": False, "risk_level": "low"},
    "query.system_events": {"allowed": True, "requires_confirmation": False, "risk_level": "low"},
    "explain.trend_verify_empty": {"allowed": True, "requires_confirmation": False, "risk_level": "low"},
    "run.refresh_snapshot": {"allowed": True, "requires_confirmation": True, "risk_level": "medium"},
    "run.refresh_latest_kline": {"allowed": True, "requires_confirmation": True, "risk_level": "medium"},
    "run.calibrate_trend_verify": {"allowed": True, "requires_confirmation": True, "risk_level": "medium"},
    "update.scheduler_time": {"allowed": True, "requires_confirmation": True, "risk_level": "medium"},
    "update.manual_portfolio_cash": {"allowed": True, "requires_confirmation": True, "risk_level": "high"},
    "update.manual_portfolio_position_add": {"allowed": True, "requires_confirmation": True, "risk_level": "high"},
    "update.manual_portfolio_position_remove": {"allowed": True, "requires_confirmation": True, "risk_level": "high"},
    "update.manual_portfolio_position_edit": {"allowed": True, "requires_confirmation": True, "risk_level": "high"},
}


def build_action_key(intent: dict[str, Any]) -> str:
    if intent.get("action_key"):
        return str(intent["action_key"])
    prefix = str(intent.get("intent", "")).strip()
    action = str(intent.get("action", "")).strip()
    if prefix and action:
        return f"{prefix}.{action}"
    return prefix


def get_policy(intent: dict[str, Any]) -> dict[str, Any]:
    action_key = build_action_key(intent)
    policy = dict(ACTION_POLICIES.get(action_key, {}))
    if not policy:
        return {
            "allowed": False,
            "requires_confirmation": True,
            "risk_level": "high",
            "action_key": action_key,
        }
    policy["action_key"] = action_key
    return policy


def apply_policy(intent: dict[str, Any]) -> dict[str, Any]:
    merged = dict(intent)
    policy = get_policy(intent)
    merged["action_key"] = policy["action_key"]
    merged["allowed"] = policy["allowed"]
    merged["requires_confirmation"] = bool(policy["requires_confirmation"])
    merged["risk_level"] = policy["risk_level"]
    return merged


def validate_intent(intent: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    policy = get_policy(intent)
    if not policy["allowed"]:
        errors.append(f"未开放的动作: {policy['action_key']}")
    if not intent.get("intent"):
        errors.append("缺少 intent")
    if not intent.get("action"):
        errors.append("缺少 action")
    return errors
