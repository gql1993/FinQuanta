"""
Build panel-ready observability payloads.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_observability_panel_input(
    *,
    active_trace_id: str,
    trace_index: list[dict[str, Any]],
    trace_items: list[dict[str, Any]],
    trace_summary: dict[str, Any],
    trace_graph: dict[str, Any],
    trace_otel_export: dict[str, Any],
    alerts_payload: dict[str, Any],
    routing_state: dict[str, Any],
    dispatch_receipts: list[dict[str, Any]],
    collector_state: dict[str, Any],
    backend_presets: dict[str, Any],
    dashboard_template: dict[str, Any],
) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "trace": {
            "active_trace_id": str(active_trace_id or ""),
            "index": list(trace_index or []),
            "detail": {
                "items": list(trace_items or []),
                "summary": dict(trace_summary or {}),
                "graph": dict(trace_graph or {}),
                "otel_export": dict(trace_otel_export or {}),
            },
        },
        "alerts": {
            "current": dict(alerts_payload or {}),
            "routing_state": dict(routing_state or {}),
            "dispatch_receipts": list(dispatch_receipts or []),
        },
        "collector": {
            "state": dict(collector_state or {}),
            "presets": dict(backend_presets or {}),
        },
        "template": dict(dashboard_template or {}),
    }
