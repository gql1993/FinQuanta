from __future__ import annotations

import os
from dataclasses import dataclass

from api_server.env_loader import load_env_files
from core.config.settings_center import settings_center
from core.runtime.mode import resolve_runtime_mode_context

load_env_files()

_runtime_context = resolve_runtime_mode_context()


@dataclass
class ApiSettings:
    app_env: str = settings_center.get_str("FINQUANTA_ENV", "dev")
    runtime_mode: str = _runtime_context.runtime_mode
    api_base: str = _runtime_context.api_base
    api_host: str = settings_center.get_str("FINQUANTA_API_HOST", "0.0.0.0")
    api_port: int = settings_center.get_int("FINQUANTA_API_PORT", 9000)
    db_backend: str = _runtime_context.db_backend  # sqlite / postgres
    sqlite_path: str = settings_center.get_str(
        "FINQUANTA_SQLITE_PATH", os.path.join("data_cache", "quant.db")
    )
    postgres_dsn: str = settings_center.get_str("FINQUANTA_POSTGRES_DSN", "")
    redis_url: str = settings_center.get_str("FINQUANTA_REDIS_URL", "")
    cors_origins: str = settings_center.get_str("FINQUANTA_CORS_ORIGINS", "*")
    snapshot_cache_ttl: int = settings_center.get_int(
        "FINQUANTA_SNAPSHOT_CACHE_TTL", 120
    )
    web_ops_center_cache_ttl: int = settings_center.get_int(
        "FINQUANTA_WEB_OPS_CENTER_CACHE_TTL", 5
    )
    alert_approval_rejected_threshold: int = settings_center.get_int(
        "FINQUANTA_ALERT_APPROVAL_REJECTED_THRESHOLD", 5
    )
    alert_approval_duration_ms_threshold: int = settings_center.get_int(
        "FINQUANTA_ALERT_APPROVAL_DURATION_MS_THRESHOLD", 3000
    )
    alert_event_error_threshold: int = settings_center.get_int(
        "FINQUANTA_ALERT_EVENT_ERROR_THRESHOLD", 10
    )
    alert_approval_rejected_daily_threshold: int = settings_center.get_int(
        "FINQUANTA_ALERT_APPROVAL_REJECTED_DAILY_THRESHOLD", 5
    )
    alert_policy_name: str = settings_center.get_str("FINQUANTA_ALERT_POLICY_NAME", "baseline-v1")
    observability_trend_window_days: int = settings_center.get_int(
        "FINQUANTA_OBSERVABILITY_TREND_WINDOW_DAYS", 7
    )
    observability_trend_event_limit: int = settings_center.get_int(
        "FINQUANTA_OBSERVABILITY_TREND_EVENT_LIMIT", 500
    )
    trace_sample_ratio: str = settings_center.get_str("FINQUANTA_TRACE_SAMPLE_RATIO", "1.0")
    trace_span_buffer_size: int = settings_center.get_int("FINQUANTA_TRACE_SPAN_BUFFER_SIZE", 2000)
    otel_collector_endpoint: str = settings_center.get_str("FINQUANTA_OTEL_COLLECTOR_ENDPOINT", "")
    alert_route_suppress_seconds: int = settings_center.get_int("FINQUANTA_ALERT_ROUTE_SUPPRESS_SECONDS", 300)
    alert_route_escalate_after: int = settings_center.get_int("FINQUANTA_ALERT_ROUTE_ESCALATE_AFTER", 3)
    alert_route_default_channels: str = settings_center.get_str(
        "FINQUANTA_ALERT_ROUTE_DEFAULT_CHANNELS", "in_app_feed"
    )
    alert_route_escalation_channels: str = settings_center.get_str(
        "FINQUANTA_ALERT_ROUTE_ESCALATION_CHANNELS", "wechat_personal"
    )
    alert_dispatch_receipt_limit: int = settings_center.get_int("FINQUANTA_ALERT_DISPATCH_RECEIPT_LIMIT", 1000)
    otel_export_timeout_seconds: float = settings_center.get_float(
        "FINQUANTA_OTEL_EXPORT_TIMEOUT_SECONDS", 5.0
    )
    otel_export_retries: int = settings_center.get_int("FINQUANTA_OTEL_EXPORT_RETRIES", 2)
    otel_export_backoff_seconds: float = settings_center.get_float(
        "FINQUANTA_OTEL_EXPORT_BACKOFF_SECONDS", 0.2
    )
    otel_breaker_fail_threshold: int = settings_center.get_int(
        "FINQUANTA_OTEL_BREAKER_FAIL_THRESHOLD", 3
    )
    otel_breaker_cooldown_seconds: int = settings_center.get_int(
        "FINQUANTA_OTEL_BREAKER_COOLDOWN_SECONDS", 30
    )
    otel_batch_size: int = settings_center.get_int("FINQUANTA_OTEL_BATCH_SIZE", 100)
    trace_visual_backend: str = settings_center.get_str("FINQUANTA_TRACE_VISUAL_BACKEND", "otlp")
    trace_visual_backend_base_url: str = settings_center.get_str("FINQUANTA_TRACE_VISUAL_BACKEND_BASE_URL", "")
    trace_visual_tenant_id: str = settings_center.get_str("FINQUANTA_TRACE_VISUAL_TENANT_ID", "")
    observability_read_token: str = settings_center.get_str("FINQUANTA_OBSERVABILITY_READ_TOKEN", "")
    openclaw_gateway_enabled: str = settings_center.get_str("FINQUANTA_OPENCLAW_GATEWAY_ENABLED", "1")
    openclaw_gateway_base: str = settings_center.get_str("FINQUANTA_OPENCLAW_GATEWAY_BASE", "http://127.0.0.1:18789")
    openclaw_gateway_timeout_seconds: float = settings_center.get_float(
        "FINQUANTA_OPENCLAW_GATEWAY_TIMEOUT_SECONDS", 8.0
    )
    openclaw_gateway_pipeline_paths: str = settings_center.get_str(
        "FINQUANTA_OPENCLAW_GATEWAY_PIPELINE_PATHS",
        "/pipeline/run,/openclaw/pipeline/run,/api/openclaw/pipeline/run",
    )
    openclaw_gateway_learn_paths: str = settings_center.get_str(
        "FINQUANTA_OPENCLAW_GATEWAY_LEARN_PATHS",
        "/learn/run,/openclaw/learn/run,/api/openclaw/learn/run",
    )

    @property
    def is_local_mode(self) -> bool:
        return self.runtime_mode == "local"

    @property
    def is_platform_mode(self) -> bool:
        return self.runtime_mode == "platform"


settings = ApiSettings()
