"""
In-memory metrics skeleton for observability.
"""

from __future__ import annotations

from collections import defaultdict
from threading import Lock
from typing import Any

_LOCK = Lock()
_COUNTERS: dict[str, float] = defaultdict(float)
_HIST_SUMMARY: dict[str, dict[str, float]] = {}


def inc_counter(name: str, value: float = 1.0, labels: dict[str, Any] | None = None) -> None:
    key = _metric_key(name, labels)
    with _LOCK:
        _COUNTERS[key] += float(value)


def observe_histogram(name: str, value: float, labels: dict[str, Any] | None = None) -> None:
    key = _metric_key(name, labels)
    with _LOCK:
        current = _HIST_SUMMARY.get(
            key,
            {"count": 0.0, "sum": 0.0, "min": float(value), "max": float(value)},
        )
        v = float(value)
        current["count"] += 1.0
        current["sum"] += v
        current["min"] = min(current["min"], v)
        current["max"] = max(current["max"], v)
        _HIST_SUMMARY[key] = current


def get_metrics_snapshot() -> dict[str, dict]:
    with _LOCK:
        counters = dict(_COUNTERS)
        hist = {
            k: {
                "count": int(v["count"]),
                "sum": v["sum"],
                "min": v["min"],
                "max": v["max"],
                "avg": (v["sum"] / v["count"]) if v["count"] else 0.0,
            }
            for k, v in _HIST_SUMMARY.items()
        }
    return {"counters": counters, "histograms": hist}


def reset_metrics() -> None:
    with _LOCK:
        _COUNTERS.clear()
        _HIST_SUMMARY.clear()


def _metric_key(name: str, labels: dict[str, Any] | None = None) -> str:
    if not labels:
        return name
    parts = [f"{k}={labels[k]}" for k in sorted(labels.keys())]
    return f"{name}|" + ",".join(parts)
