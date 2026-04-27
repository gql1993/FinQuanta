"""
Metric export helpers for Prometheus and OTEL-style payloads.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any


def export_prometheus_text(metrics_snapshot: dict[str, Any]) -> str:
    lines: list[str] = []
    counters = metrics_snapshot.get("counters", {}) or {}
    histograms = metrics_snapshot.get("histograms", {}) or {}

    lines.append("# finquanta observability metrics")
    for key in sorted(counters.keys()):
        name, labels = _split_metric_key(str(key))
        metric_name = _sanitize_prom_name(name)
        value = _safe_float(counters.get(key))
        lines.append(_render_prom_sample(metric_name, labels, value))

    for key in sorted(histograms.keys()):
        name, labels = _split_metric_key(str(key))
        base = _sanitize_prom_name(name)
        item = histograms.get(key) or {}
        lines.append(_render_prom_sample(f"{base}_count", labels, _safe_float(item.get("count"))))
        lines.append(_render_prom_sample(f"{base}_sum", labels, _safe_float(item.get("sum"))))
        lines.append(_render_prom_sample(f"{base}_min", labels, _safe_float(item.get("min"))))
        lines.append(_render_prom_sample(f"{base}_max", labels, _safe_float(item.get("max"))))
        lines.append(_render_prom_sample(f"{base}_avg", labels, _safe_float(item.get("avg"))))

    return "\n".join(lines) + "\n"


def export_otel_metrics(metrics_snapshot: dict[str, Any]) -> dict[str, Any]:
    counters = metrics_snapshot.get("counters", {}) or {}
    histograms = metrics_snapshot.get("histograms", {}) or {}
    metrics: list[dict[str, Any]] = []

    for key in sorted(counters.keys()):
        name, labels = _split_metric_key(str(key))
        metrics.append(
            {
                "name": name,
                "unit": "1",
                "type": "sum",
                "is_monotonic": True,
                "temporality": "cumulative",
                "data_points": [
                    {
                        "attributes": labels,
                        "value": _safe_float(counters.get(key)),
                    }
                ],
            }
        )

    for key in sorted(histograms.keys()):
        name, labels = _split_metric_key(str(key))
        item = histograms.get(key) or {}
        metrics.append(
            {
                "name": name,
                "unit": "ms",
                "type": "histogram_summary",
                "data_points": [
                    {
                        "attributes": labels,
                        "count": int(_safe_float(item.get("count"))),
                        "sum": _safe_float(item.get("sum")),
                        "min": _safe_float(item.get("min")),
                        "max": _safe_float(item.get("max")),
                        "avg": _safe_float(item.get("avg")),
                    }
                ],
            }
        )

    return {
        "resource_metrics": [
            {
                "resource": {"service.name": "finquanta-api"},
                "scope_metrics": [{"scope": {"name": "finquanta.observability"}, "metrics": metrics}],
            }
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _split_metric_key(metric_key: str) -> tuple[str, dict[str, str]]:
    if "|" not in metric_key:
        return metric_key, {}
    name, raw_labels = metric_key.split("|", 1)
    labels: dict[str, str] = {}
    for part in raw_labels.split(","):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        labels[k.strip()] = v.strip()
    return name, labels


def _sanitize_prom_name(name: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_:]", "_", name or "metric")
    if not re.match(r"^[a-zA-Z_:]", normalized):
        normalized = f"finquanta_{normalized}"
    return normalized


def _render_prom_sample(name: str, labels: dict[str, str], value: float) -> str:
    if not labels:
        return f"{name} {value}"
    body = ",".join(f'{k}="{_escape_label(v)}"' for k, v in sorted(labels.items()))
    return f"{name}{{{body}}} {value}"


def _escape_label(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
