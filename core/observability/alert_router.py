"""
Policy-based alert routing skeleton (notify/suppress/escalate).
"""

from __future__ import annotations

import time
from threading import Lock
from typing import Any

_LOCK = Lock()
_ALERT_SEEN_COUNT: dict[str, int] = {}
_ALERT_SUPPRESS_UNTIL: dict[str, float] = {}


def build_alert_routing_policy(
    *,
    policy_name: str = "route-baseline-v1",
    suppress_seconds: int = 300,
    escalate_after: int = 3,
    default_channels: list[str] | None = None,
    escalation_channels: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "name": policy_name,
        "suppress_seconds": max(0, int(suppress_seconds)),
        "escalate_after": max(1, int(escalate_after)),
        "default_channels": list(default_channels or ["in_app_feed"]),
        "escalation_channels": list(escalation_channels or ["wechat_personal"]),
    }


def route_alerts(
    alerts: list[dict[str, Any]],
    *,
    routing_policy: dict[str, Any],
    notifiers: list[dict[str, Any]] | None = None,
    dry_run: bool = True,
    now_ts: float | None = None,
) -> dict[str, Any]:
    timestamp = float(now_ts if now_ts is not None else time.time())
    policy = dict(routing_policy or {})
    suppress_seconds = int(policy.get("suppress_seconds", 300))
    escalate_after = int(policy.get("escalate_after", 3))
    default_channels = list(policy.get("default_channels", ["in_app_feed"]))
    escalation_channels = list(policy.get("escalation_channels", ["wechat_personal"]))
    available_channels = _collect_channels(notifiers or [])

    decisions: list[dict[str, Any]] = []
    for alert in alerts or []:
        code = str(alert.get("code", "unknown") or "unknown")
        severity = str(alert.get("severity", "warning") or "warning").lower()

        with _LOCK:
            count = int(_ALERT_SEEN_COUNT.get(code, 0)) + 1
            _ALERT_SEEN_COUNT[code] = count
            suppress_until = float(_ALERT_SUPPRESS_UNTIL.get(code, 0.0) or 0.0)
            suppressed = timestamp < suppress_until
            escalated = (count >= escalate_after) or (severity in {"error", "critical"})
            if (not dry_run) and (not suppressed):
                _ALERT_SUPPRESS_UNTIL[code] = timestamp + suppress_seconds

        selected_channels = _select_channels(
            available_channels=available_channels,
            default_channels=default_channels,
            escalation_channels=escalation_channels,
            escalated=escalated,
        )
        decisions.append(
            {
                "code": code,
                "suppressed": suppressed,
                "escalated": escalated,
                "severity": severity,
                "seen_count": count,
                "channels": selected_channels,
                "action": "skip" if suppressed else ("escalate_notify" if escalated else "notify"),
            }
        )

    return {
        "policy": policy,
        "dry_run": bool(dry_run),
        "decision_count": len(decisions),
        "decisions": decisions,
    }


def get_alert_routing_state() -> dict[str, Any]:
    with _LOCK:
        return {
            "seen_count": dict(_ALERT_SEEN_COUNT),
            "suppress_until": dict(_ALERT_SUPPRESS_UNTIL),
        }


def _collect_channels(notifiers: list[dict[str, Any]]) -> set[str]:
    channels: set[str] = set()
    for item in notifiers:
        for channel in item.get("channels", []) or []:
            channels.add(str(channel))
    return channels


def _select_channels(
    *,
    available_channels: set[str],
    default_channels: list[str],
    escalation_channels: list[str],
    escalated: bool,
) -> list[str]:
    preferred = escalation_channels if escalated else default_channels
    selected = [c for c in preferred if c in available_channels]
    if selected:
        return selected
    return sorted(available_channels)[:1]
