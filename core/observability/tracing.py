"""
Lightweight tracing skeleton.
"""

from __future__ import annotations

import os
import random
import re
import time
import uuid
from datetime import datetime, timezone
from threading import Lock
from typing import Any

_TRACE_SPANS_LOCK = Lock()
_TRACE_SPANS: list[dict[str, Any]] = []
_TRACEPARENT_RE = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$")


def create_trace_id(prefix: str = "trace") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16]}"


def create_decision_id(mode: str, action: str, code: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"{mode}:{action}:{code}:{stamp}"


def start_span(
    name: str,
    *,
    trace_id: str = "",
    decision_id: str = "",
    traceparent: str = "",
    sampled: bool | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = parse_traceparent(traceparent) if traceparent else {}
    trace_id_hex = str(context.get("trace_id_hex") or uuid.uuid4().hex)
    parent_span_id = str(context.get("span_id") or "")
    sampled_flag = bool(context.get("sampled", False)) if sampled is None else bool(sampled)
    if sampled is None and not context:
        sampled_flag = should_sample_trace()
    span_id = uuid.uuid4().hex[:16]
    return {
        "name": name,
        "trace_id": trace_id,
        "trace_id_hex": trace_id_hex,
        "decision_id": decision_id,
        "span_id": span_id,
        "parent_span_id": parent_span_id,
        "traceparent": build_traceparent(trace_id_hex, span_id, sampled=sampled_flag),
        "sampled": sampled_flag,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "started_at_ns": time.perf_counter_ns(),
        "metadata": dict(metadata or {}),
    }


def finish_span(span: dict[str, Any], *, status: str = "ok") -> dict[str, Any]:
    end_ns = time.perf_counter_ns()
    started_ns = int(span.get("started_at_ns", end_ns))
    duration_ms = max(0.0, (end_ns - started_ns) / 1_000_000.0)
    result = dict(span)
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    result["duration_ms"] = duration_ms
    result["status"] = status
    _record_trace_span(result)
    return result


def should_sample_trace(sample_ratio: float | None = None) -> bool:
    ratio = _normalize_sample_ratio(sample_ratio)
    if ratio >= 1.0:
        return True
    if ratio <= 0.0:
        return False
    return random.random() < ratio


def build_traceparent(trace_id_hex: str, span_id_hex: str, *, sampled: bool = True) -> str:
    trace_hex = str(trace_id_hex or "").lower().replace("-", "")
    span_hex = str(span_id_hex or "").lower().replace("-", "")
    trace_hex = (trace_hex + ("0" * 32))[:32]
    span_hex = (span_hex + ("0" * 16))[:16]
    flags = "01" if sampled else "00"
    return f"00-{trace_hex}-{span_hex}-{flags}"


def parse_traceparent(traceparent: str) -> dict[str, Any]:
    text = str(traceparent or "").strip().lower()
    match = _TRACEPARENT_RE.match(text)
    if not match:
        return {}
    trace_id_hex, span_id_hex, flags_hex = match.groups()
    flags = int(flags_hex, 16)
    return {
        "version": "00",
        "trace_id_hex": trace_id_hex,
        "span_id": span_id_hex,
        "sampled": bool(flags & 0x1),
        "trace_flags": flags_hex,
    }


def extract_trace_context(headers: dict[str, str] | None = None) -> dict[str, Any]:
    incoming = dict(headers or {})
    traceparent = (
        incoming.get("traceparent")
        or incoming.get("Traceparent")
        or incoming.get("TRACEPARENT")
        or ""
    )
    context = parse_traceparent(str(traceparent))
    if not context:
        return {
            "incoming_traceparent": "",
            "trace_id_hex": "",
            "parent_span_id": "",
            "sampled": False,
        }
    return {
        "incoming_traceparent": str(traceparent),
        "trace_id_hex": context.get("trace_id_hex", ""),
        "parent_span_id": context.get("span_id", ""),
        "sampled": bool(context.get("sampled", False)),
    }


def inject_trace_context(headers: dict[str, str] | None, span: dict[str, Any]) -> dict[str, str]:
    out = dict(headers or {})
    out["traceparent"] = str(span.get("traceparent", ""))
    return out


def get_recent_trace_spans(limit: int = 100) -> list[dict[str, Any]]:
    with _TRACE_SPANS_LOCK:
        items = list(_TRACE_SPANS[-max(1, int(limit)):])
    return [dict(item) for item in reversed(items)]


def get_trace_spans(trace_id: str, *, limit: int = 500) -> list[dict[str, Any]]:
    needle = str(trace_id or "").strip().lower()
    if not needle:
        return []
    recent = get_recent_trace_spans(limit=max(100, int(limit)))
    matched: list[dict[str, Any]] = []
    for item in recent:
        trace_id_hex = str(item.get("trace_id_hex", "")).lower()
        trace_plain = str(item.get("trace_id", "")).lower()
        if needle == trace_id_hex or needle == trace_plain:
            matched.append(dict(item))
    return matched[: max(1, int(limit))]


def get_trace_index(limit: int = 500) -> list[dict[str, Any]]:
    spans = get_recent_trace_spans(limit=max(100, int(limit)))
    grouped: dict[str, dict[str, Any]] = {}
    for span in spans:
        trace_id_hex = str(span.get("trace_id_hex", "") or "")
        if not trace_id_hex:
            continue
        item = grouped.get(trace_id_hex)
        if not item:
            item = {
                "trace_id_hex": trace_id_hex,
                "trace_id": str(span.get("trace_id", "") or ""),
                "span_count": 0,
                "last_seen_at": str(span.get("finished_at", "") or span.get("started_at", "")),
                "root_span_names": set(),
                "status_counts": {},
            }
            grouped[trace_id_hex] = item
        item["span_count"] = int(item.get("span_count", 0)) + 1
        finished_at = str(span.get("finished_at", "") or span.get("started_at", ""))
        if finished_at > str(item.get("last_seen_at", "")):
            item["last_seen_at"] = finished_at
        if not str(span.get("parent_span_id", "") or ""):
            item["root_span_names"].add(str(span.get("name", "") or "unknown"))
        status = str(span.get("status", "unknown") or "unknown")
        counts = item["status_counts"]
        counts[status] = int(counts.get(status, 0)) + 1

    result = []
    for trace in grouped.values():
        trace["root_span_names"] = sorted(trace.get("root_span_names", set()))
        result.append(trace)
    result.sort(key=lambda x: str(x.get("last_seen_at", "")), reverse=True)
    return result[: max(1, int(limit))]


def summarize_trace(spans: list[dict[str, Any]]) -> dict[str, Any]:
    items = list(spans or [])
    if not items:
        return {"span_count": 0, "status_counts": {}, "root_span_names": [], "max_duration_ms": 0.0}

    status_counts: dict[str, int] = {}
    roots: set[str] = set()
    max_duration_ms = 0.0
    for span in items:
        status = str(span.get("status", "unknown") or "unknown")
        status_counts[status] = int(status_counts.get(status, 0)) + 1
        if not str(span.get("parent_span_id", "") or ""):
            roots.add(str(span.get("name", "") or "unknown"))
        try:
            max_duration_ms = max(max_duration_ms, float(span.get("duration_ms", 0.0) or 0.0))
        except (TypeError, ValueError):
            pass
    return {
        "span_count": len(items),
        "status_counts": status_counts,
        "root_span_names": sorted(roots),
        "max_duration_ms": round(max_duration_ms, 3),
    }


def build_trace_graph(spans: list[dict[str, Any]]) -> dict[str, Any]:
    items = list(spans or [])
    node_ids = set()
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for span in items:
        span_id = str(span.get("span_id", "") or "")
        parent_span_id = str(span.get("parent_span_id", "") or "")
        if span_id and span_id not in node_ids:
            node_ids.add(span_id)
            nodes.append(
                {
                    "id": span_id,
                    "name": str(span.get("name", "") or "unknown"),
                    "status": str(span.get("status", "") or "unknown"),
                    "duration_ms": float(span.get("duration_ms", 0.0) or 0.0),
                }
            )
        if parent_span_id and span_id:
            edges.append({"from": parent_span_id, "to": span_id})
    return {"nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges)}


def export_otel_traces(limit: int = 100, *, trace_id: str = "") -> dict[str, Any]:
    spans = get_trace_spans(trace_id=trace_id, limit=limit) if trace_id else get_recent_trace_spans(limit=limit)
    transformed = []
    for item in spans:
        transformed.append(
            {
                "trace_id": item.get("trace_id_hex", ""),
                "span_id": item.get("span_id", ""),
                "parent_span_id": item.get("parent_span_id", ""),
                "name": item.get("name", ""),
                "start_time_unix_nano": int(item.get("started_at_ns", 0)),
                "end_time_unix_nano": int(item.get("started_at_ns", 0) + (item.get("duration_ms", 0.0) * 1_000_000)),
                "attributes": {
                    "status": item.get("status", ""),
                    "decision_id": item.get("decision_id", ""),
                    "trace_id": item.get("trace_id", ""),
                    **(item.get("metadata", {}) or {}),
                },
            }
        )
    graph = build_trace_graph(spans)
    return {
        "resource_spans": [
            {
                "resource": {"service.name": "finquanta-api"},
                "scope_spans": [{"scope": {"name": "finquanta.observability.tracing"}, "spans": transformed}],
            }
        ],
        "trace_id": trace_id or "",
        "summary": summarize_trace(spans),
        "graph": graph,
        "count": len(transformed),
    }


def _record_trace_span(span: dict[str, Any]) -> None:
    if not bool(span.get("sampled", False)):
        return
    max_spans = _trace_buffer_size()
    item = dict(span)
    item.pop("started_at_ns", None)
    item["started_at_ns"] = int(span.get("started_at_ns", 0))
    with _TRACE_SPANS_LOCK:
        _TRACE_SPANS.append(item)
        if len(_TRACE_SPANS) > max_spans:
            del _TRACE_SPANS[: len(_TRACE_SPANS) - max_spans]


def _normalize_sample_ratio(sample_ratio: float | None) -> float:
    if sample_ratio is None:
        raw = os.environ.get("FINQUANTA_TRACE_SAMPLE_RATIO", "1.0")
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return 1.0
    else:
        value = float(sample_ratio)
    return max(0.0, min(1.0, value))


def _trace_buffer_size() -> int:
    raw = os.environ.get("FINQUANTA_TRACE_SPAN_BUFFER_SIZE", "2000")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 2000
    return max(100, value)
