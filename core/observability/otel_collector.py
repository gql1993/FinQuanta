"""
OTEL collector connector with batching, retry and circuit breaker.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from core.observability.exporters import export_otel_metrics
from core.observability.trace_backend_presets import resolve_trace_route
from core.observability.tracing import export_otel_traces

_LOCK = Lock()
_STATE = {
    "consecutive_failures": 0,
    "circuit_open_until_ts": 0.0,
    "last_error": "",
    "last_attempt_at": "",
    "last_success_at": "",
}


def push_otel_collector(
    *,
    endpoint: str,
    metrics_snapshot: dict[str, Any] | None = None,
    trace_limit: int = 500,
    batch_size: int = 100,
    timeout_seconds: float = 5.0,
    retries: int = 2,
    backoff_seconds: float = 0.2,
    breaker_fail_threshold: int = 3,
    breaker_cooldown_seconds: int = 30,
    signals: tuple[str, ...] = ("metrics", "traces"),
    trace_id: str = "",
    trace_backend: str = "otlp",
    trace_backend_base_url: str = "",
    trace_tenant_id: str = "",
    dry_run: bool = True,
    sender=None,
) -> dict[str, Any]:
    selected = [item for item in signals if item in {"metrics", "traces"}]
    if not selected:
        selected = ["metrics", "traces"]
    sender_fn = sender or _default_sender
    now = time.time()

    if not endpoint and not dry_run:
        return {
            "status": "skipped",
            "reason": "collector endpoint is empty",
            "signals": selected,
            "state": get_collector_state(),
        }
    if _is_circuit_open(now) and not dry_run:
        return {
            "status": "blocked",
            "reason": "circuit breaker open",
            "signals": selected,
            "state": get_collector_state(),
        }

    signal_results: dict[str, Any] = {}
    signal_routes: dict[str, Any] = {}
    total_batches = 0
    total_failed = 0
    for signal in selected:
        route = resolve_trace_route(
            signal=signal,
            endpoint=endpoint,
            backend=trace_backend,
            base_url=trace_backend_base_url,
            tenant_id=trace_tenant_id,
        )
        signal_routes[signal] = route
        if signal == "metrics":
            batches = build_metrics_batches(metrics_snapshot or {}, batch_size=batch_size)
        else:
            batches = build_traces_batches(limit=trace_limit, batch_size=batch_size, trace_id=trace_id)
        result = _push_batches(
            endpoint=str(route.get("endpoint", "")),
            route_headers=dict(route.get("headers", {})),
            signal=signal,
            batches=batches,
            timeout_seconds=timeout_seconds,
            retries=retries,
            backoff_seconds=backoff_seconds,
            breaker_fail_threshold=breaker_fail_threshold,
            breaker_cooldown_seconds=breaker_cooldown_seconds,
            dry_run=dry_run,
            sender=sender_fn,
        )
        signal_results[signal] = result
        total_batches += int(result.get("batch_count", 0))
        total_failed += int(result.get("failed_batches", 0))

    status = "ok" if total_failed == 0 else "partial_failed"
    return {
        "status": status,
        "signals": selected,
        "trace_id": trace_id or "",
        "trace_backend": str(resolve_trace_route(signal="traces", backend=trace_backend).get("backend", "otlp")),
        "signal_routes": signal_routes,
        "total_batches": total_batches,
        "failed_batches": total_failed,
        "dry_run": bool(dry_run),
        "signal_results": signal_results,
        "state": get_collector_state(),
    }


def build_metrics_batches(metrics_snapshot: dict[str, Any], *, batch_size: int = 100) -> list[dict[str, Any]]:
    payload = export_otel_metrics(metrics_snapshot)
    metrics = _extract_otel_metrics(payload)
    if not metrics:
        return [payload]
    chunks = _chunk(metrics, max(1, int(batch_size)))
    return [_build_metrics_payload(chunk) for chunk in chunks]


def build_traces_batches(*, limit: int = 500, batch_size: int = 100, trace_id: str = "") -> list[dict[str, Any]]:
    payload = export_otel_traces(limit=limit, trace_id=trace_id)
    spans = _extract_otel_spans(payload)
    if not spans:
        return [payload]
    chunks = _chunk(spans, max(1, int(batch_size)))
    return [_build_traces_payload(chunk) for chunk in chunks]


def get_collector_state() -> dict[str, Any]:
    now = time.time()
    with _LOCK:
        state = dict(_STATE)
    open_until = float(state.get("circuit_open_until_ts", 0.0) or 0.0)
    return {
        "consecutive_failures": int(state.get("consecutive_failures", 0)),
        "circuit_open": now < open_until,
        "circuit_open_until_ts": open_until,
        "last_error": str(state.get("last_error", "")),
        "last_attempt_at": str(state.get("last_attempt_at", "")),
        "last_success_at": str(state.get("last_success_at", "")),
    }


def reset_collector_state() -> None:
    with _LOCK:
        _STATE["consecutive_failures"] = 0
        _STATE["circuit_open_until_ts"] = 0.0
        _STATE["last_error"] = ""
        _STATE["last_attempt_at"] = ""
        _STATE["last_success_at"] = ""


def _push_batches(
    *,
    endpoint: str,
    route_headers: dict[str, str],
    signal: str,
    batches: list[dict[str, Any]],
    timeout_seconds: float,
    retries: int,
    backoff_seconds: float,
    breaker_fail_threshold: int,
    breaker_cooldown_seconds: int,
    dry_run: bool,
    sender,
) -> dict[str, Any]:
    sent = 0
    failed = 0
    errors: list[str] = []
    for payload in batches:
        ok = False
        last_error = ""
        _mark_attempt()
        for attempt in range(max(0, int(retries)) + 1):
            if dry_run:
                ok = True
                break
            try:
                ok, message = sender(endpoint, payload, float(timeout_seconds), dict(route_headers or {}))
            except TypeError:
                ok, message = sender(endpoint, payload, float(timeout_seconds))
            if ok:
                break
            last_error = message
            if attempt < int(retries):
                time.sleep(max(0.0, float(backoff_seconds)) * (2**attempt))
        if ok:
            sent += 1
            _mark_success()
        else:
            failed += 1
            errors.append(last_error or "send failed")
            _mark_failure(
                last_error or "send failed",
                fail_threshold=max(1, int(breaker_fail_threshold)),
                cooldown_seconds=max(1, int(breaker_cooldown_seconds)),
            )
    return {
        "signal": signal,
        "batch_count": len(batches),
        "sent_batches": sent,
        "failed_batches": failed,
        "errors": errors,
    }


def _default_sender(
    endpoint: str,
    payload: dict[str, Any],
    timeout_seconds: float,
    extra_headers: dict[str, str] | None = None,
) -> tuple[bool, str]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if isinstance(extra_headers, dict):
        headers.update(extra_headers)
    req = urllib.request.Request(endpoint, method="POST", headers=headers, data=body)
    parsed = urllib.parse.urlparse(endpoint)
    host = (parsed.hostname or "").lower()
    opener = (
        urllib.request.build_opener(urllib.request.ProxyHandler({}))
        if host in {"127.0.0.1", "localhost", "0.0.0.0"}
        else urllib.request.build_opener()
    )
    try:
        with opener.open(req, timeout=max(0.1, timeout_seconds)) as resp:
            status = int(getattr(resp, "status", 200))
            if 200 <= status < 300:
                return True, f"http {status}"
            return False, f"http {status}"
    except urllib.error.HTTPError as exc:
        return False, f"http {exc.code}"
    except Exception as exc:
        return False, str(exc)


def _extract_otel_metrics(payload: dict[str, Any]) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    for resource in payload.get("resource_metrics", []) or []:
        for scope in resource.get("scope_metrics", []) or []:
            metrics.extend(scope.get("metrics", []) or [])
    return metrics


def _extract_otel_spans(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    for resource in payload.get("resource_spans", []) or []:
        for scope in resource.get("scope_spans", []) or []:
            spans.extend(scope.get("spans", []) or [])
    return spans


def _build_metrics_payload(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "resource_metrics": [
            {
                "resource": {"service.name": "finquanta-api"},
                "scope_metrics": [{"scope": {"name": "finquanta.observability"}, "metrics": metrics}],
            }
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _build_traces_payload(spans: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "resource_spans": [
            {
                "resource": {"service.name": "finquanta-api"},
                "scope_spans": [{"scope": {"name": "finquanta.observability.tracing"}, "spans": spans}],
            }
        ],
        "count": len(spans),
    }


def _chunk(items: list[dict[str, Any]], chunk_size: int) -> list[list[dict[str, Any]]]:
    return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]


def _is_circuit_open(now_ts: float) -> bool:
    with _LOCK:
        return now_ts < float(_STATE.get("circuit_open_until_ts", 0.0) or 0.0)


def _mark_attempt() -> None:
    with _LOCK:
        _STATE["last_attempt_at"] = datetime.now(timezone.utc).isoformat()


def _mark_success() -> None:
    with _LOCK:
        _STATE["consecutive_failures"] = 0
        _STATE["circuit_open_until_ts"] = 0.0
        _STATE["last_success_at"] = datetime.now(timezone.utc).isoformat()
        _STATE["last_error"] = ""


def _mark_failure(message: str, *, fail_threshold: int, cooldown_seconds: int) -> None:
    with _LOCK:
        count = int(_STATE.get("consecutive_failures", 0)) + 1
        _STATE["consecutive_failures"] = count
        _STATE["last_error"] = str(message)
        if count >= fail_threshold:
            _STATE["circuit_open_until_ts"] = time.time() + cooldown_seconds
