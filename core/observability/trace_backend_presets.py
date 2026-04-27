"""
Trace backend presets for Tempo/Jaeger compatible OTLP routes.
"""

from __future__ import annotations

from typing import Any


def normalize_trace_backend(backend: str) -> str:
    value = str(backend or "otlp").strip().lower()
    if value in {"tempo", "jaeger", "otlp"}:
        return value
    return "otlp"


def build_trace_backend_preset(
    *,
    backend: str = "otlp",
    base_url: str = "",
    tenant_id: str = "",
) -> dict[str, Any]:
    normalized = normalize_trace_backend(backend)
    clean_base = str(base_url or "").strip().rstrip("/")

    traces_endpoint = f"{clean_base}/v1/traces" if clean_base else ""
    metrics_endpoint = f"{clean_base}/v1/metrics" if clean_base else ""
    headers: dict[str, str] = {}
    if normalized == "tempo" and tenant_id.strip():
        headers["X-Scope-OrgID"] = tenant_id.strip()

    return {
        "backend": normalized,
        "base_url": clean_base,
        "signal_routes": {
            "traces": traces_endpoint,
            "metrics": metrics_endpoint,
        },
        "headers": headers,
        "payload_format": "otlp_json",
        "dashboard_template": "trace_default_v1",
    }


def resolve_trace_route(
    *,
    signal: str,
    endpoint: str = "",
    backend: str = "otlp",
    base_url: str = "",
    tenant_id: str = "",
) -> dict[str, Any]:
    preset = build_trace_backend_preset(
        backend=backend,
        base_url=base_url,
        tenant_id=tenant_id,
    )
    explicit_endpoint = str(endpoint or "").strip()
    signal_name = str(signal or "traces").strip().lower()
    selected_endpoint = explicit_endpoint or str(preset.get("signal_routes", {}).get(signal_name, ""))
    return {
        "backend": preset.get("backend", "otlp"),
        "signal": signal_name,
        "endpoint": selected_endpoint,
        "headers": dict(preset.get("headers", {})),
        "payload_format": preset.get("payload_format", "otlp_json"),
    }
