"""
Alert policy model and resolver.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_alert_policy(
    *,
    policy_name: str = "baseline-v1",
    rejected_threshold: int = 5,
    duration_ms_threshold: float = 3000.0,
    event_error_threshold: int = 10,
    approval_rejected_daily_threshold: int = 5,
) -> dict[str, Any]:
    return {
        "name": policy_name,
        "version": "2026.04",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "thresholds": {
            "approval_rejected_total": int(rejected_threshold),
            "approval_duration_ms_max": float(duration_ms_threshold),
            "event_error_total": int(event_error_threshold),
            "approval_rejected_daily": int(approval_rejected_daily_threshold),
        },
        "rules": [
            "approval.rejected.spike",
            "approval.duration.high",
            "events.error.spike",
            "approval.rejected.daily.spike",
        ],
    }
