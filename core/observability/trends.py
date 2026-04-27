"""
Trend report helpers for approvals and system events.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def build_event_trend_report(
    events: list[dict[str, Any]],
    *,
    window_days: int = 7,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=max(1, int(window_days)) - 1)).date()
    buckets: dict[str, dict[str, int]] = {}
    for idx in range(max(1, int(window_days))):
        d = start + timedelta(days=idx)
        buckets[d.isoformat()] = {
            "event_total": 0,
            "approval_total": 0,
            "approval_executed": 0,
            "approval_rejected": 0,
            "warning": 0,
            "error": 0,
        }

    by_category: dict[str, int] = {}
    by_level: dict[str, int] = {}
    totals = {
        "events_total": 0,
        "approval_total": 0,
        "approval_executed": 0,
        "approval_rejected": 0,
        "warning_total": 0,
        "error_total": 0,
    }

    for event in events or []:
        ts = _parse_dt(event.get("timestamp") or event.get("time") or "")
        if not ts:
            continue
        day = ts.date().isoformat()
        if day not in buckets:
            continue

        level = str(event.get("level", "info") or "info").lower()
        source = str(event.get("source", "") or "").lower()
        title = str(event.get("title", "") or "")
        category = str(event.get("category", "unknown") or "unknown")

        row = buckets[day]
        row["event_total"] += 1
        totals["events_total"] += 1
        by_category[category] = by_category.get(category, 0) + 1
        by_level[level] = by_level.get(level, 0) + 1

        if level in {"warning", "error", "critical"}:
            row["warning"] += 1
            totals["warning_total"] += 1
        if level in {"error", "critical"}:
            row["error"] += 1
            totals["error_total"] += 1

        if source == "approval":
            row["approval_total"] += 1
            totals["approval_total"] += 1
            if "拒绝" in title or level in {"warning", "error", "critical"}:
                row["approval_rejected"] += 1
                totals["approval_rejected"] += 1
            else:
                row["approval_executed"] += 1
                totals["approval_executed"] += 1

    return {
        "generated_at": now.isoformat(),
        "window_days": max(1, int(window_days)),
        "totals": totals,
        "daily": [{"date": d, **v} for d, v in sorted(buckets.items())],
        "by_category": by_category,
        "by_level": by_level,
    }


def _parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
