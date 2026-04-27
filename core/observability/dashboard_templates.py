"""
Dashboard templates for observability panels.
"""

from __future__ import annotations

from typing import Any


def build_trace_dashboard_template() -> dict[str, Any]:
    return {
        "template_name": "trace_default_v1",
        "description": "Trace dashboard fields for Tempo/Jaeger style observability.",
        "filters": [
            {"key": "trace_id", "label": "Trace ID", "type": "text"},
            {"key": "span_name", "label": "Span Name", "type": "text"},
            {"key": "status", "label": "Status", "type": "select", "options": ["ok", "error", "warning", "unknown"]},
            {"key": "time_range", "label": "Time Range", "type": "duration"},
        ],
        "panels": [
            {
                "panel_key": "trace_index_table",
                "title": "Trace Index",
                "kind": "table",
                "fields": ["trace_id_hex", "trace_id", "span_count", "status_counts", "root_span_names", "last_seen_at"],
            },
            {
                "panel_key": "trace_span_table",
                "title": "Trace Spans",
                "kind": "table",
                "fields": [
                    "span_id",
                    "parent_span_id",
                    "name",
                    "status",
                    "duration_ms",
                    "started_at",
                    "finished_at",
                    "metadata",
                ],
            },
            {
                "panel_key": "trace_graph",
                "title": "Trace Graph",
                "kind": "graph",
                "node_fields": ["id", "name", "status", "duration_ms"],
                "edge_fields": ["from", "to"],
            },
        ],
        "export_hints": {
            "otel_endpoint_param": "trace_id",
            "collector_push_params": ["signal=traces", "trace_id=<trace_id_hex>", "backend=tempo|jaeger"],
        },
    }
