"""
Lightweight alert evaluation for observability metrics.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.observability.alert_policy import build_alert_policy


def evaluate_metrics_alerts(
    metrics_snapshot: dict[str, Any],
    *,
    rejected_threshold: int = 5,
    duration_ms_threshold: float = 3000.0,
) -> dict[str, Any]:
    counters = metrics_snapshot.get("counters", {}) or {}
    histograms = metrics_snapshot.get("histograms", {}) or {}

    rejected_total = _sum_counter(counters, "trade_approval_rejected_total")
    disabled_total = _sum_counter(counters, "trade_approval_disabled_total")
    executed_total = _sum_counter(counters, "trade_approval_executed_total")
    max_duration_ms = _max_histogram_value(histograms, "trade_approval_duration_ms", field="max")
    avg_duration_ms = _max_histogram_value(histograms, "trade_approval_duration_ms", field="avg")

    alerts: list[dict[str, Any]] = []
    if rejected_total >= int(rejected_threshold):
        alerts.append(
            {
                "code": "approval.rejected.spike",
                "severity": "warning",
                "message": (
                    f"trade approval rejected count reached {rejected_total}, "
                    f"threshold={int(rejected_threshold)}"
                ),
                "value": rejected_total,
                "threshold": int(rejected_threshold),
            }
        )
    if max_duration_ms >= float(duration_ms_threshold):
        alerts.append(
            {
                "code": "approval.duration.high",
                "severity": "warning",
                "message": (
                    f"trade approval max duration reached {max_duration_ms:.2f}ms, "
                    f"threshold={float(duration_ms_threshold):.2f}ms"
                ),
                "value": max_duration_ms,
                "threshold": float(duration_ms_threshold),
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "alerting" if alerts else "ok",
        "alerts": alerts,
        "summary": {
            "approval_rejected_total": rejected_total,
            "approval_disabled_total": disabled_total,
            "approval_executed_total": executed_total,
            "approval_duration_max_ms": max_duration_ms,
            "approval_duration_avg_ms": avg_duration_ms,
        },
        "thresholds": {
            "approval_rejected_total": int(rejected_threshold),
            "approval_duration_ms_max": float(duration_ms_threshold),
        },
    }


def evaluate_observability_alerts(
    metrics_snapshot: dict[str, Any],
    trend_report: dict[str, Any],
    *,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy_data = dict(policy or build_alert_policy())
    thresholds = policy_data.get("thresholds", {}) or {}
    metrics_result = evaluate_metrics_alerts(
        metrics_snapshot,
        rejected_threshold=int(thresholds.get("approval_rejected_total", 5)),
        duration_ms_threshold=float(thresholds.get("approval_duration_ms_max", 3000.0)),
    )
    alerts = list(metrics_result.get("alerts", []))
    trend_totals = trend_report.get("totals", {}) or {}
    daily = trend_report.get("daily", []) or []
    max_daily_rejected = max((int(item.get("approval_rejected", 0) or 0) for item in daily), default=0)
    error_total = int(trend_totals.get("error_total", 0) or 0)

    error_threshold = int(thresholds.get("event_error_total", 10))
    rejected_daily_threshold = int(thresholds.get("approval_rejected_daily", 5))

    if error_total >= error_threshold:
        alerts.append(
            {
                "code": "events.error.spike",
                "severity": "warning",
                "message": f"event error total reached {error_total}, threshold={error_threshold}",
                "value": error_total,
                "threshold": error_threshold,
            }
        )
    if max_daily_rejected >= rejected_daily_threshold:
        alerts.append(
            {
                "code": "approval.rejected.daily.spike",
                "severity": "warning",
                "message": (
                    f"max daily approval rejected reached {max_daily_rejected}, "
                    f"threshold={rejected_daily_threshold}"
                ),
                "value": max_daily_rejected,
                "threshold": rejected_daily_threshold,
            }
        )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "alerting" if alerts else "ok",
        "alerts": alerts,
        "summary": {
            **(metrics_result.get("summary", {}) or {}),
            "event_error_total": error_total,
            "approval_rejected_daily_max": max_daily_rejected,
        },
        "policy": policy_data,
    }


def _sum_counter(counters: dict[str, Any], metric_name: str) -> float:
    total = 0.0
    for key, value in counters.items():
        if key == metric_name or str(key).startswith(f"{metric_name}|"):
            try:
                total += float(value)
            except (TypeError, ValueError):
                continue
    return total


def _max_histogram_value(histograms: dict[str, Any], metric_name: str, *, field: str) -> float:
    max_value = 0.0
    for key, value in histograms.items():
        if key == metric_name or str(key).startswith(f"{metric_name}|"):
            item = value or {}
            try:
                max_value = max(max_value, float(item.get(field, 0.0)))
            except (TypeError, ValueError):
                continue
    return max_value
