from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from api_server.auth import (
    build_production_security_report,
    change_password,
    cleanup_expired_tokens,
    delete_user,
    ensure_auth_tables,
    get_auth_security_status,
    get_recent_auth_audit,
    has_permission,
    list_users,
    login,
    logout,
    revoke_other_user_tokens,
    revoke_user_tokens,
    upsert_user,
    verify_token,
)
from api_server.cache_provider import snapshot_cache
from api_server.config import settings
from api_server.schemas import (
    ApiResponse,
    ApprovalTradeRequest,
    AiConfigRequest,
    AssistantAskRequest,
    ChangePasswordRequest,
    CoordinatorPolicyRequest,
    LoginRequest,
    LoginResponse,
    OpenClawDaemonAlertPolicyRequest,
    OpenClawConfigRollbackRequest,
    OpenClawGuardReplayRequest,
    OpenClawHistoricalReplayRequest,
    PushConfigRequest,
    SyncExportRequest,
    SyncImportRequest,
    ArenaRunRequest,
    SyncReconcileRequest,
    ManualPortfolioBuyRequest,
    ManualPortfolioSellRequest,
    PushTestRequest,
    RevokeTokensRequest,
    TriggerRequest,
    UnattendedTradeGuardRequest,
    UserUpsertRequest,
)
from api_server.assistant_service import (
    ask_assistant,
    build_assistant_context_payload,
    get_session_messages,
    get_sessions,
)
from api_server.settings_service import get_ai_config, save_ai_config
from api_server.storage import repo
from core.application.openclaw_service import (
    get_coordinator_policy,
    get_openclaw_config_audit,
    get_openclaw_data_sources,
    get_openclaw_daemon_alert_policy,
    get_openclaw_daemon_status,
    get_openclaw_strategy_weights,
    get_unattended_trade_guard,
    build_openclaw_historical_replay_report,
    reset_coordinator_policy,
    reset_openclaw_daemon_alert_policy,
    reset_unattended_trade_guard,
    rollback_openclaw_config,
    run_openclaw_learning,
    run_openclaw_pipeline,
    run_unattended_trade_guard_replay,
    update_coordinator_policy,
    update_openclaw_daemon_alert_policy,
    update_unattended_trade_guard,
)
from core.application.ops_service import (
    build_operational_health_report,
    get_event_trend_report,
    get_message_feed,
    get_ops_center_payload,
    get_recent_system_events,
    get_recent_task_runs,
)
from core.application.portfolio_service import (
    get_portfolio_positions,
    get_portfolio_recommendations,
    get_portfolio_summary,
)
from core.application.arena_service import (
    get_arena_latest_run,
    get_arena_leaderboard,
    get_arena_positions,
    run_arena_cycle,
)
from core.application.manual_portfolio_service import (
    get_manual_portfolio_detail,
    manual_buy,
    manual_sell,
)
from core.application.short_term_service import (
    get_news_sentiment_snapshot,
    list_fund_holdings,
    list_recent_events,
)
from core.application.registry_service import (
    get_registered_agents,
    get_registered_notifiers,
    get_registered_providers,
    get_registered_strategies,
    get_registered_workflows,
    get_registry_overview,
)
from core.application.snapshot_service import get_system_snapshot
from core.application.sync_service import (
    export_runtime_state,
    export_runtime_state_to_file,
    import_runtime_state_from_file,
    reconcile_runtime_state,
)
from core.application.task_service import (
    get_task_governance_state,
    get_task_history,
    get_task_state,
    list_task_states,
    run_scan_task,
    start_background_task,
    trigger_named_task,
)
from core.application.trend_verify_service import (
    get_trend_failure_summary,
    get_trend_verify_records,
    get_trend_verify_stats,
    run_batch_failure_analysis,
)
from core.application.trade_approval_service import approve_trade
from core.application.verify_service import (
    calibrate_verify,
    get_verify_accuracy_stats,
    get_verify_records,
)
from core.observability.alert_policy import build_alert_policy
from core.observability.alert_router import (
    build_alert_routing_policy,
    get_alert_routing_state,
    route_alerts,
)
from core.observability.alert_dispatcher import dispatch_routed_alerts, get_dispatch_receipts
from core.observability.alerts import evaluate_observability_alerts
from core.observability.exporters import export_otel_metrics, export_prometheus_text
from core.observability.metrics import get_metrics_snapshot
from core.observability.otel_collector import get_collector_state, push_otel_collector
from core.observability.trace_backend_presets import build_trace_backend_preset, normalize_trace_backend
from core.observability.dashboard_templates import build_trace_dashboard_template
from core.observability.panel_input import build_observability_panel_input
from core.observability.tracing import (
    build_trace_graph,
    export_otel_traces,
    extract_trace_context,
    get_recent_trace_spans,
    get_trace_index,
    get_trace_spans,
    inject_trace_context,
    summarize_trace,
    start_span,
)

app = FastAPI(
    title="FinQuanta API",
    version="0.1.0",
    description="FinQuanta 产品化 API 骨架，用于 Web 端 / 小程序端 / 远程运维接入。",
)
_log = logging.getLogger("finquanta.api")

cors_origins = [x.strip() for x in settings.cors_origins.split(",")] if settings.cors_origins else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins if cors_origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ROLE_NAMES = {"admin", "operator", "viewer"}
_AUTH_BOOTSTRAP = {"ready": False, "error": ""}
_DAEMON_BOOTSTRAP = {"enabled": False, "started": False, "detail": ""}


@app.on_event("startup")
def bootstrap_runtime_dependencies():
    # Keep API process alive even if auth DB init is temporarily unavailable.
    auth_ok = False
    for attempt in range(1, 4):
        try:
            ensure_auth_tables()
            _AUTH_BOOTSTRAP["ready"] = True
            _AUTH_BOOTSTRAP["error"] = ""
            _log.info("auth tables initialized")
            auth_ok = True
            break
        except Exception as exc:
            _AUTH_BOOTSTRAP["ready"] = False
            _AUTH_BOOTSTRAP["error"] = str(exc)
            _log.exception("auth bootstrap failed (attempt %s/3): %s", attempt, exc)
            if attempt < 3:
                time.sleep(1)
    if not auth_ok:
        _log.error("auth subsystem degraded; protected endpoints will return 503")
    _log_prod_security_warnings()
    _autostart_daemon_if_enabled()


def _log_prod_security_warnings() -> None:
    """Warn on insecure prod defaults without blocking local dev startup."""
    env = str(os.environ.get("FINQUANTA_ENV", "dev")).strip().lower()
    if env not in {"prod", "production"}:
        return
    cors = str(os.environ.get("FINQUANTA_CORS_ORIGINS", "*")).strip()
    if cors in {"", "*"}:
        _log.warning(
            "P0 security: FINQUANTA_CORS_ORIGINS is wildcard in prod; restrict before exposure"
        )
    try:
        status = get_auth_security_status()
        if status.get("default_admin_password"):
            _log.warning(
                "P0 security: default admin/admin123 still active; change before API exposure"
            )
        for finding in status.get("findings", []) or []:
            if finding.get("level") == "error":
                _log.warning("P0 security: %s", finding.get("message", finding.get("code")))
    except Exception as exc:
        _log.warning("P0 security: auth security check skipped at startup: %s", exc)


def _autostart_daemon_if_enabled():
    enabled = str(os.environ.get("FINQUANTA_API_AUTOSTART_DAEMON", "1")).strip().lower() in {"1", "true", "yes"}
    _DAEMON_BOOTSTRAP["enabled"] = enabled
    if not enabled:
        _DAEMON_BOOTSTRAP["started"] = False
        _DAEMON_BOOTSTRAP["detail"] = "disabled by FINQUANTA_API_AUTOSTART_DAEMON"
        return
    try:
        from desktop.daemon_scheduler import start_daemon

        boards_cfg = str(os.environ.get("FINQUANTA_DAEMON_BOARDS", "") or "").strip()
        boards = [item.strip() for item in re.split(r"[,，\s]+", boards_cfg) if item.strip()] if boards_cfg else None
        if boards is None:
            raw_boards = repo.kv_get("openclaw_daemon_boards", []) or []
            if isinstance(raw_boards, str):
                try:
                    raw_boards = json.loads(raw_boards)
                except Exception:
                    raw_boards = []
            boards = [str(item).strip() for item in raw_boards if str(item).strip()] if isinstance(raw_boards, list) else None
        raw_disabled = repo.kv_get("sched_disabled_tasks", []) or []
        if isinstance(raw_disabled, str):
            try:
                raw_disabled = json.loads(raw_disabled)
            except Exception:
                raw_disabled = []
        disabled = set(raw_disabled) if isinstance(raw_disabled, list) else set()
        from core.config.kline_refresh import filter_protected_disabled_tasks

        disabled = filter_protected_disabled_tasks(disabled)
        start_daemon(boards=boards, disabled_tasks=disabled)
        _DAEMON_BOOTSTRAP["started"] = True
        _DAEMON_BOOTSTRAP["detail"] = "daemon scheduler started by api"
        _log.info("daemon scheduler started from api startup")
    except Exception as exc:
        _DAEMON_BOOTSTRAP["started"] = False
        _DAEMON_BOOTSTRAP["detail"] = str(exc)
        _log.warning("daemon autostart skipped: %s", exc)


def _require_auth_ready():
    if _AUTH_BOOTSTRAP["ready"]:
        return
    detail = "auth subsystem not ready"
    if _AUTH_BOOTSTRAP["error"]:
        detail = f"{detail}: {_AUTH_BOOTSTRAP['error']}"
    raise HTTPException(status_code=503, detail=detail)

def _decode_json_field(value, default):
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return default


def require_user(authorization: str | None):
    _require_auth_ready()
    if not authorization:
        raise HTTPException(status_code=401, detail="missing authorization")
    token = authorization.replace("Bearer ", "").strip()
    user = verify_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="invalid token")
    return user


def require_permission(user: dict | None, permission: str):
    if not has_permission(user, permission):
        raise HTTPException(status_code=403, detail=f"permission denied: {permission}")


def require_observability_reader(
    authorization: str | None,
    *,
    x_observability_token: str | None = None,
    obs_token: str = "",
):
    configured = str(settings.observability_read_token or "").strip()
    candidate = str(x_observability_token or obs_token or "").strip()
    if configured and candidate and candidate == configured:
        return {"username": "observability_reader", "role": "viewer"}
    return require_user(authorization)


@app.get("/")
def root():
    """Browser-friendly index when visiting the API port directly."""
    web_hint = os.environ.get("FINQUANTA_WEB_URL", "http://127.0.0.1:8501")
    return {
        "ok": True,
        "service": "finquanta-api",
        "message": "这是后端 API，不是图形界面。请用浏览器打开 Web 控制台。",
        "web_ui": web_hint,
        "health": "/health",
        "api_docs": "/docs",
        "login": "POST /api/auth/login",
    }


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "finquanta-api",
        "env": settings.app_env,
        "runtime_mode": settings.runtime_mode,
        "db_backend": settings.db_backend,
        "redis_cache": snapshot_cache.enabled,
        "auth_ready": _AUTH_BOOTSTRAP["ready"],
        "daemon_autostart_enabled": _DAEMON_BOOTSTRAP["enabled"],
        "daemon_started": _DAEMON_BOOTSTRAP["started"],
    }


@app.get("/health/deps")
def health_dependencies():
    db = repo.ping()
    cache = snapshot_cache.ping()
    return {
        "ok": bool(db.get("ok")) and bool(cache.get("ok")),
        "service": "finquanta-api",
        "dependencies": {
            "database": db,
            "cache": cache,
            "auth": {"ok": _AUTH_BOOTSTRAP["ready"], "detail": _AUTH_BOOTSTRAP["error"] or "ready"},
            "daemon": {
                "ok": _DAEMON_BOOTSTRAP["started"] if _DAEMON_BOOTSTRAP["enabled"] else True,
                "enabled": _DAEMON_BOOTSTRAP["enabled"],
                "detail": _DAEMON_BOOTSTRAP["detail"],
            },
        },
    }


@app.post("/api/auth/login", response_model=LoginResponse)
def api_login(req: LoginRequest):
    _require_auth_ready()
    ok, token, role = login(req.username, req.password)
    if not ok:
        return LoginResponse(ok=False, message="用户名或密码错误")
    return LoginResponse(ok=True, token=token, role=role, message="登录成功")


@app.get("/api/auth/profile", response_model=ApiResponse)
def api_auth_profile(authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    return ApiResponse(data=user)


@app.post("/api/auth/change-password", response_model=ApiResponse)
def api_auth_change_password(req: ChangePasswordRequest, authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    ok, msg = change_password(user["username"], req.old_password, req.new_password)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return ApiResponse(data={"changed": True}, message=msg)


@app.post("/api/auth/logout", response_model=ApiResponse)
def api_auth_logout(authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    ok = logout(user.get("token", ""), user["username"])
    if not ok:
        raise HTTPException(status_code=400, detail="logout failed")
    return ApiResponse(data={"logout": True}, message="已退出登录")


@app.get("/api/snapshot/system", response_model=ApiResponse)
def api_snapshot_system(authorization: str | None = Header(default=None)):
    require_user(authorization)
    cache_key = "api:snapshot:system"
    cached = snapshot_cache.get_json(cache_key)
    if cached:
        return ApiResponse(data=cached)
    data = get_system_snapshot()
    snapshot_cache.set_json(cache_key, data, ttl=settings.snapshot_cache_ttl)
    return ApiResponse(data=data)


@app.get("/api/ops/tasks", response_model=ApiResponse)
def api_ops_tasks(authorization: str | None = Header(default=None), limit: int = 30):
    require_user(authorization)
    return ApiResponse(data=get_recent_task_runs(limit))


@app.get("/api/ops/events", response_model=ApiResponse)
def api_ops_events(authorization: str | None = Header(default=None), limit: int = 30):
    require_user(authorization)
    return ApiResponse(data=get_recent_system_events(limit))


@app.get("/api/ops/center", response_model=ApiResponse)
def api_ops_center(
    authorization: str | None = Header(default=None),
    limit: int = 20,
    registry_token: str = "",
):
    require_user(authorization)
    return ApiResponse(data=get_ops_center_payload(limit=limit, registry_token=registry_token))


@app.get("/api/ops/health", response_model=ApiResponse)
def api_ops_health(authorization: str | None = Header(default=None), limit: int = 50):
    require_user(authorization)
    return ApiResponse(data=build_operational_health_report(limit=limit))


@app.get("/api/scan/latest", response_model=ApiResponse)
def api_scan_latest(authorization: str | None = Header(default=None)):
    require_user(authorization)
    from desktop.scan_store import get_scan_results, get_scan_results_meta, resolve_scan_results

    items, meta, warning = resolve_scan_results()
    return ApiResponse(
        data={
            "items": items,
            "updated_at": meta.get("written_at", ""),
            "count": len(items),
            "meta": meta,
            "warning": warning or "",
        }
    )


@app.post("/api/scan/run", response_model=ApiResponse)
def api_scan_run(
    req: TriggerRequest,
    authorization: str | None = Header(default=None),
    traceparent: str | None = Header(default=None),
):
    user = require_user(authorization)
    if not has_permission(user, "scan:run"):
        raise HTTPException(status_code=403, detail="permission denied")
    if req.dry_run:
        return ApiResponse(data={"dry_run": True, "task": "scan_stocks", "traceparent": traceparent or ""})
    if req.run_async:
        status = start_background_task(
            "scan",
            traceparent=traceparent or "",
            priority=req.priority,
            max_retries=req.max_retries,
        )
        if not status.get("accepted"):
            return ApiResponse(ok=False, message="scan task is not accepted", data=status)
        data = status.get("state", {})
        data["traceparent"] = traceparent or ""
        data["accepted"] = True
        return ApiResponse(data=data, message="scan task accepted")
    result = run_scan_task(traceparent=traceparent or "")
    return ApiResponse(data={"task": "scan", "result": result, "traceparent": traceparent or ""})


@app.get("/api/scan/status", response_model=ApiResponse)
def api_scan_status(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(data=get_task_state("scan"))


@app.get("/api/portfolio/summary", response_model=ApiResponse)
def api_portfolio_summary(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(data=get_portfolio_summary())


@app.get("/api/portfolio/positions", response_model=ApiResponse)
def api_portfolio_positions(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(data=get_portfolio_positions())


@app.get("/api/portfolio/recommendations", response_model=ApiResponse)
def api_portfolio_recommendations(authorization: str | None = Header(default=None), limit: int = 20):
    require_user(authorization)
    return ApiResponse(data=get_portfolio_recommendations(limit=limit))


@app.get("/api/portfolio/manual", response_model=ApiResponse)
def api_manual_portfolio(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(data=get_manual_portfolio_detail())


@app.post("/api/portfolio/manual/buy", response_model=ApiResponse)
def api_manual_portfolio_buy(
    req: ManualPortfolioBuyRequest,
    authorization: str | None = Header(default=None),
):
    user = require_user(authorization)
    if not has_permission(user, "task:trigger"):
        raise HTTPException(status_code=403, detail="permission denied")
    result = manual_buy(
        req.code,
        price=req.price,
        shares=req.shares,
        stop_loss_pct=req.stop_loss_pct,
    )
    return ApiResponse(ok=bool(result.get("ok")), message=result.get("message", ""), data=result)


@app.post("/api/portfolio/manual/sell", response_model=ApiResponse)
def api_manual_portfolio_sell(
    req: ManualPortfolioSellRequest,
    authorization: str | None = Header(default=None),
):
    user = require_user(authorization)
    if not has_permission(user, "task:trigger"):
        raise HTTPException(status_code=403, detail="permission denied")
    result = manual_sell(req.code, price=req.price, shares=req.shares)
    return ApiResponse(ok=bool(result.get("ok")), message=result.get("message", ""), data=result)


@app.get("/api/arena/leaderboard", response_model=ApiResponse)
def api_arena_leaderboard(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(data=get_arena_leaderboard())


@app.get("/api/arena/positions", response_model=ApiResponse)
def api_arena_positions(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(data=get_arena_positions())


@app.get("/api/arena/run/latest", response_model=ApiResponse)
def api_arena_run_latest(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(data=get_arena_latest_run())


@app.post("/api/arena/run", response_model=ApiResponse)
def api_arena_run(req: ArenaRunRequest, authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    if not has_permission(user, "task:trigger"):
        raise HTTPException(status_code=403, detail="permission denied")
    if req.dry_run:
        return ApiResponse(data={"dry_run": True, "boards": req.boards})
    result = run_arena_cycle(boards=req.boards or None)
    return ApiResponse(data=result, message="arena cycle completed")


@app.get("/api/short-term/events", response_model=ApiResponse)
def api_short_term_events(authorization: str | None = Header(default=None), limit: int = 50):
    require_user(authorization)
    return ApiResponse(data={"items": list_recent_events(limit=limit)})


@app.get("/api/short-term/fund-holdings", response_model=ApiResponse)
def api_short_term_fund_holdings(
    authorization: str | None = Header(default=None),
    report_period: str = "",
    limit: int = 100,
):
    require_user(authorization)
    return ApiResponse(
        data=list_fund_holdings(
            report_period=report_period.strip() or None,
            limit=limit,
        )
    )


@app.get("/api/short-term/sentiment", response_model=ApiResponse)
def api_short_term_sentiment(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(data=get_news_sentiment_snapshot())


@app.post("/api/sync/reconcile", response_model=ApiResponse)
def api_sync_reconcile(req: SyncReconcileRequest, authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    if not has_permission(user, "settings:write"):
        raise HTTPException(status_code=403, detail="permission denied")
    result = reconcile_runtime_state(
        device_id=req.device_id.strip(),
        kv_changes=req.kv_changes,
        positions=req.positions,
    )
    return ApiResponse(
        data=result,
        message=f"sync ok: server imported {result.get('imported_kv', 0)} kv keys",
    )


@app.get("/api/messages", response_model=ApiResponse)
def api_messages(authorization: str | None = Header(default=None), limit: int = 30):
    require_user(authorization)
    return ApiResponse(data=get_message_feed(limit))


@app.get("/api/observability/metrics", response_model=ApiResponse)
def api_observability_metrics(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(data=get_metrics_snapshot())


@app.get("/api/observability/metrics/prometheus")
def api_observability_metrics_prometheus(authorization: str | None = Header(default=None)):
    require_user(authorization)
    text = export_prometheus_text(get_metrics_snapshot())
    return Response(content=text, media_type="text/plain; version=0.0.4")


@app.get("/api/observability/metrics/otel", response_model=ApiResponse)
def api_observability_metrics_otel(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(data=export_otel_metrics(get_metrics_snapshot()))


@app.get("/api/observability/traces", response_model=ApiResponse)
def api_observability_traces(authorization: str | None = Header(default=None), limit: int = 100):
    require_user(authorization)
    items = get_recent_trace_spans(limit=limit)
    return ApiResponse(data={"items": items, "count": len(items)})


@app.get("/api/observability/traces/index", response_model=ApiResponse)
def api_observability_traces_index(authorization: str | None = Header(default=None), limit: int = 100):
    require_user(authorization)
    items = get_trace_index(limit=limit)
    return ApiResponse(data={"items": items, "count": len(items)})


@app.get("/api/observability/traces/trace/{trace_id}", response_model=ApiResponse)
def api_observability_trace_detail(trace_id: str, authorization: str | None = Header(default=None), limit: int = 500):
    require_user(authorization)
    items = get_trace_spans(trace_id=trace_id, limit=limit)
    return ApiResponse(
        data={
            "trace_id": trace_id,
            "summary": summarize_trace(items),
            "graph": build_trace_graph(items),
            "items": items,
            "count": len(items),
        }
    )


@app.get("/api/observability/traces/otel", response_model=ApiResponse)
def api_observability_traces_otel(
    authorization: str | None = Header(default=None),
    limit: int = 100,
    trace_id: str = "",
):
    require_user(authorization)
    return ApiResponse(data=export_otel_traces(limit=limit, trace_id=trace_id))


@app.get("/api/observability/traces/config", response_model=ApiResponse)
def api_observability_traces_config(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(
        data={
            "sample_ratio": settings.trace_sample_ratio,
            "span_buffer_size": settings.trace_span_buffer_size,
            "otel_collector_endpoint": settings.otel_collector_endpoint,
            "otel_export_timeout_seconds": settings.otel_export_timeout_seconds,
            "otel_export_retries": settings.otel_export_retries,
            "otel_export_backoff_seconds": settings.otel_export_backoff_seconds,
            "otel_breaker_fail_threshold": settings.otel_breaker_fail_threshold,
            "otel_breaker_cooldown_seconds": settings.otel_breaker_cooldown_seconds,
            "otel_batch_size": settings.otel_batch_size,
            "trace_visual_backend": settings.trace_visual_backend,
            "trace_visual_backend_base_url": settings.trace_visual_backend_base_url,
        }
    )


@app.get("/api/observability/traces/backends/presets", response_model=ApiResponse)
def api_observability_traces_backends_presets(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(
        data={
            "default_backend": normalize_trace_backend(settings.trace_visual_backend),
            "tempo": build_trace_backend_preset(
                backend="tempo",
                base_url=settings.trace_visual_backend_base_url,
                tenant_id=settings.trace_visual_tenant_id,
            ),
            "jaeger": build_trace_backend_preset(
                backend="jaeger",
                base_url=settings.trace_visual_backend_base_url,
                tenant_id=settings.trace_visual_tenant_id,
            ),
            "otlp": build_trace_backend_preset(
                backend="otlp",
                base_url=settings.trace_visual_backend_base_url,
                tenant_id=settings.trace_visual_tenant_id,
            ),
        }
    )


@app.get("/api/observability/dashboard/template", response_model=ApiResponse)
def api_observability_dashboard_template(
    authorization: str | None = Header(default=None),
    x_observability_token: str | None = Header(default=None),
    obs_token: str = "",
):
    require_observability_reader(
        authorization,
        x_observability_token=x_observability_token,
        obs_token=obs_token,
    )
    return ApiResponse(data=build_trace_dashboard_template())


@app.get("/api/observability/dashboard/panel-input", response_model=ApiResponse)
def api_observability_dashboard_panel_input(
    authorization: str | None = Header(default=None),
    x_observability_token: str | None = Header(default=None),
    obs_token: str = "",
    trace_id: str = "",
    index_limit: int = 50,
    trace_limit: int = 200,
    receipt_limit: int = 50,
):
    require_observability_reader(
        authorization,
        x_observability_token=x_observability_token,
        obs_token=obs_token,
    )
    index = get_trace_index(limit=index_limit)
    active_trace_id = str(trace_id or (index[0].get("trace_id_hex", "") if index else ""))
    trace_items = get_trace_spans(trace_id=active_trace_id, limit=trace_limit) if active_trace_id else []
    trace_summary = summarize_trace(trace_items)
    trace_graph = build_trace_graph(trace_items)
    trace_otel = export_otel_traces(limit=trace_limit, trace_id=active_trace_id)

    snapshot = get_metrics_snapshot()
    trend_report = get_event_trend_report(
        window_days=settings.observability_trend_window_days,
        event_limit=settings.observability_trend_event_limit,
    )
    policy = build_alert_policy(
        policy_name=settings.alert_policy_name,
        rejected_threshold=settings.alert_approval_rejected_threshold,
        duration_ms_threshold=float(settings.alert_approval_duration_ms_threshold),
        event_error_threshold=settings.alert_event_error_threshold,
        approval_rejected_daily_threshold=settings.alert_approval_rejected_daily_threshold,
    )
    alerts_payload = evaluate_observability_alerts(snapshot, trend_report, policy=policy)
    routing_state = get_alert_routing_state()
    dispatch_receipts = get_dispatch_receipts(limit=receipt_limit)
    collector_state = get_collector_state()
    backend_presets = {
        "default_backend": normalize_trace_backend(settings.trace_visual_backend),
        "tempo": build_trace_backend_preset(
            backend="tempo",
            base_url=settings.trace_visual_backend_base_url,
            tenant_id=settings.trace_visual_tenant_id,
        ),
        "jaeger": build_trace_backend_preset(
            backend="jaeger",
            base_url=settings.trace_visual_backend_base_url,
            tenant_id=settings.trace_visual_tenant_id,
        ),
        "otlp": build_trace_backend_preset(
            backend="otlp",
            base_url=settings.trace_visual_backend_base_url,
            tenant_id=settings.trace_visual_tenant_id,
        ),
    }
    template = build_trace_dashboard_template()
    payload = build_observability_panel_input(
        active_trace_id=active_trace_id,
        trace_index=index,
        trace_items=trace_items,
        trace_summary=trace_summary,
        trace_graph=trace_graph,
        trace_otel_export=trace_otel,
        alerts_payload=alerts_payload,
        routing_state=routing_state,
        dispatch_receipts=dispatch_receipts,
        collector_state=collector_state,
        backend_presets=backend_presets,
        dashboard_template=template,
    )
    return ApiResponse(data=payload)


@app.get("/api/observability/collector/state", response_model=ApiResponse)
def api_observability_collector_state(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(data=get_collector_state())


@app.post("/api/observability/collector/push", response_model=ApiResponse)
def api_observability_collector_push(
    authorization: str | None = Header(default=None),
    signal: str = "both",
    dry_run: bool = True,
    trace_limit: int = 500,
    trace_id: str = "",
    trace_backend: str = "",
    trace_backend_base_url: str = "",
    trace_tenant_id: str = "",
):
    require_user(authorization)
    normalized = str(signal or "both").lower()
    signals = ("metrics", "traces") if normalized == "both" else tuple(x.strip() for x in normalized.split(",") if x.strip())
    result = push_otel_collector(
        endpoint=settings.otel_collector_endpoint,
        metrics_snapshot=get_metrics_snapshot(),
        trace_limit=trace_limit,
        batch_size=settings.otel_batch_size,
        timeout_seconds=settings.otel_export_timeout_seconds,
        retries=settings.otel_export_retries,
        backoff_seconds=settings.otel_export_backoff_seconds,
        breaker_fail_threshold=settings.otel_breaker_fail_threshold,
        breaker_cooldown_seconds=settings.otel_breaker_cooldown_seconds,
        signals=signals,
        trace_id=trace_id,
        trace_backend=trace_backend or settings.trace_visual_backend,
        trace_backend_base_url=trace_backend_base_url or settings.trace_visual_backend_base_url,
        trace_tenant_id=trace_tenant_id or settings.trace_visual_tenant_id,
        dry_run=dry_run,
    )
    return ApiResponse(data=result)


@app.get("/api/observability/trace/context", response_model=ApiResponse)
def api_observability_trace_context(
    authorization: str | None = Header(default=None),
    traceparent: str | None = Header(default=None),
):
    require_user(authorization)
    incoming = extract_trace_context({"traceparent": traceparent or ""})
    span = start_span(
        "api.trace.context",
        traceparent=traceparent or "",
        metadata={"source": "api.observability.trace.context"},
    )
    outgoing = inject_trace_context({}, span)
    return ApiResponse(data={"incoming": incoming, "outgoing": outgoing, "sampled": bool(span.get("sampled", False))})


@app.get("/api/observability/trends", response_model=ApiResponse)
def api_observability_trends(
    authorization: str | None = Header(default=None),
    window_days: int = 0,
    event_limit: int = 0,
):
    require_user(authorization)
    actual_window_days = window_days or settings.observability_trend_window_days
    actual_event_limit = event_limit or settings.observability_trend_event_limit
    return ApiResponse(data=get_event_trend_report(window_days=actual_window_days, event_limit=actual_event_limit))


@app.get("/api/observability/alerts/policy", response_model=ApiResponse)
def api_observability_alerts_policy(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(
        data=build_alert_policy(
            policy_name=settings.alert_policy_name,
            rejected_threshold=settings.alert_approval_rejected_threshold,
            duration_ms_threshold=float(settings.alert_approval_duration_ms_threshold),
            event_error_threshold=settings.alert_event_error_threshold,
            approval_rejected_daily_threshold=settings.alert_approval_rejected_daily_threshold,
        )
    )


@app.get("/api/observability/alerts/routing", response_model=ApiResponse)
def api_observability_alerts_routing_policy(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(
        data=build_alert_routing_policy(
            policy_name=f"{settings.alert_policy_name}-routing",
            suppress_seconds=settings.alert_route_suppress_seconds,
            escalate_after=settings.alert_route_escalate_after,
            default_channels=[item.strip() for item in settings.alert_route_default_channels.split(",") if item.strip()],
            escalation_channels=[
                item.strip() for item in settings.alert_route_escalation_channels.split(",") if item.strip()
            ],
        )
    )


@app.post("/api/observability/alerts/route", response_model=ApiResponse)
def api_observability_alerts_route(
    authorization: str | None = Header(default=None),
    dry_run: bool = True,
):
    require_user(authorization)
    snapshot = get_metrics_snapshot()
    trend_report = get_event_trend_report(
        window_days=settings.observability_trend_window_days,
        event_limit=settings.observability_trend_event_limit,
    )
    policy = build_alert_policy(
        policy_name=settings.alert_policy_name,
        rejected_threshold=settings.alert_approval_rejected_threshold,
        duration_ms_threshold=float(settings.alert_approval_duration_ms_threshold),
        event_error_threshold=settings.alert_event_error_threshold,
        approval_rejected_daily_threshold=settings.alert_approval_rejected_daily_threshold,
    )
    observability_alerts = evaluate_observability_alerts(snapshot, trend_report, policy=policy)
    routing_policy = build_alert_routing_policy(
        policy_name=f"{settings.alert_policy_name}-routing",
        suppress_seconds=settings.alert_route_suppress_seconds,
        escalate_after=settings.alert_route_escalate_after,
        default_channels=[item.strip() for item in settings.alert_route_default_channels.split(",") if item.strip()],
        escalation_channels=[item.strip() for item in settings.alert_route_escalation_channels.split(",") if item.strip()],
    )
    routed = route_alerts(
        observability_alerts.get("alerts", []),
        routing_policy=routing_policy,
        notifiers=get_registered_notifiers(),
        dry_run=dry_run,
    )
    return ApiResponse(data={"alerts": observability_alerts, "routing": routed})


@app.get("/api/observability/alerts/routing/state", response_model=ApiResponse)
def api_observability_alerts_routing_state(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(data=get_alert_routing_state())


@app.post("/api/observability/alerts/dispatch", response_model=ApiResponse)
def api_observability_alerts_dispatch(
    authorization: str | None = Header(default=None),
    dry_run: bool = True,
):
    require_user(authorization)
    snapshot = get_metrics_snapshot()
    trend_report = get_event_trend_report(
        window_days=settings.observability_trend_window_days,
        event_limit=settings.observability_trend_event_limit,
    )
    policy = build_alert_policy(
        policy_name=settings.alert_policy_name,
        rejected_threshold=settings.alert_approval_rejected_threshold,
        duration_ms_threshold=float(settings.alert_approval_duration_ms_threshold),
        event_error_threshold=settings.alert_event_error_threshold,
        approval_rejected_daily_threshold=settings.alert_approval_rejected_daily_threshold,
    )
    observability_alerts = evaluate_observability_alerts(snapshot, trend_report, policy=policy)
    routing_policy = build_alert_routing_policy(
        policy_name=f"{settings.alert_policy_name}-routing",
        suppress_seconds=settings.alert_route_suppress_seconds,
        escalate_after=settings.alert_route_escalate_after,
        default_channels=[item.strip() for item in settings.alert_route_default_channels.split(",") if item.strip()],
        escalation_channels=[item.strip() for item in settings.alert_route_escalation_channels.split(",") if item.strip()],
    )
    routed = route_alerts(
        observability_alerts.get("alerts", []),
        routing_policy=routing_policy,
        notifiers=get_registered_notifiers(),
        dry_run=dry_run,
    )
    dispatch = dispatch_routed_alerts(
        observability_alerts.get("alerts", []),
        routed,
        dry_run=dry_run,
        receipt_limit=settings.alert_dispatch_receipt_limit,
    )
    return ApiResponse(data={"alerts": observability_alerts, "routing": routed, "dispatch": dispatch})


@app.get("/api/observability/alerts/dispatch/receipts", response_model=ApiResponse)
def api_observability_alerts_dispatch_receipts(
    authorization: str | None = Header(default=None),
    limit: int = 100,
):
    require_user(authorization)
    items = get_dispatch_receipts(limit=limit)
    return ApiResponse(data={"items": items, "count": len(items)})


@app.get("/api/observability/alerts", response_model=ApiResponse)
def api_observability_alerts(authorization: str | None = Header(default=None)):
    require_user(authorization)
    snapshot = get_metrics_snapshot()
    trend_report = get_event_trend_report(
        window_days=settings.observability_trend_window_days,
        event_limit=settings.observability_trend_event_limit,
    )
    policy = build_alert_policy(
        policy_name=settings.alert_policy_name,
        rejected_threshold=settings.alert_approval_rejected_threshold,
        duration_ms_threshold=float(settings.alert_approval_duration_ms_threshold),
        event_error_threshold=settings.alert_event_error_threshold,
        approval_rejected_daily_threshold=settings.alert_approval_rejected_daily_threshold,
    )
    payload = evaluate_observability_alerts(
        snapshot,
        trend_report,
        policy=policy,
    )
    return ApiResponse(data=payload)


@app.get("/api/registry", response_model=ApiResponse)
def api_registry_overview(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(data=get_registry_overview())


@app.get("/api/registry/providers", response_model=ApiResponse)
def api_registry_providers(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(data=get_registered_providers())


@app.get("/api/registry/strategies", response_model=ApiResponse)
def api_registry_strategies(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(data=get_registered_strategies())


@app.get("/api/registry/notifiers", response_model=ApiResponse)
def api_registry_notifiers(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(data=get_registered_notifiers())


@app.get("/api/registry/workflows", response_model=ApiResponse)
def api_registry_workflows(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(data=get_registered_workflows())


@app.get("/api/registry/agents", response_model=ApiResponse)
def api_registry_agents(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(data=get_registered_agents())


@app.get("/api/assistant/context", response_model=ApiResponse)
def api_assistant_context(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(data=build_assistant_context_payload())


@app.get("/api/assistant/sessions", response_model=ApiResponse)
def api_assistant_sessions(authorization: str | None = Header(default=None), limit: int = 30):
    require_user(authorization)
    return ApiResponse(data={"items": get_sessions(limit)})


@app.get("/api/assistant/session/{session_id}", response_model=ApiResponse)
def api_assistant_session(session_id: str, authorization: str | None = Header(default=None), limit: int = 100):
    require_user(authorization)
    return ApiResponse(data={"session_id": session_id, "messages": get_session_messages(session_id, limit=limit)})


@app.post("/api/assistant/ask", response_model=ApiResponse)
def api_assistant_ask(req: AssistantAskRequest, authorization: str | None = Header(default=None)):
    require_user(authorization)
    session_id = req.session_id.strip() or datetime.now().strftime("%Y%m%d_%H%M%S")
    return ApiResponse(data=ask_assistant(req.prompt, session_id))


@app.get("/api/settings/ai", response_model=ApiResponse)
def api_settings_ai(authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    if not has_permission(user, "settings:write"):
        raise HTTPException(status_code=403, detail="permission denied")
    return ApiResponse(data=get_ai_config())


@app.post("/api/settings/ai", response_model=ApiResponse)
def api_settings_ai_save(req: AiConfigRequest, authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    if not has_permission(user, "settings:write"):
        raise HTTPException(status_code=403, detail="permission denied")
    cfg = save_ai_config(req.api_key, req.base_url, req.model, req.provider)
    return ApiResponse(data=cfg, message="AI 配置已保存")


@app.get("/api/settings/push", response_model=ApiResponse)
def api_settings_push(authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    if not has_permission(user, "settings:write"):
        raise HTTPException(status_code=403, detail="permission denied")
    from signal_push import get_push_config
    return ApiResponse(data=get_push_config())


@app.post("/api/settings/push", response_model=ApiResponse)
def api_settings_push_save(req: PushConfigRequest, authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    if not has_permission(user, "settings:write"):
        raise HTTPException(status_code=403, detail="permission denied")
    from signal_push import get_push_config, save_push_config
    cfg = get_push_config()
    cfg["serverchan_key"] = req.serverchan_key
    cfg["wecom_webhook"] = req.wecom_webhook
    save_push_config(cfg)
    return ApiResponse(data=cfg, message="推送配置已保存")


@app.post("/api/settings/push/test", response_model=ApiResponse)
def api_settings_push_test(req: PushTestRequest, authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    if not has_permission(user, "settings:write"):
        raise HTTPException(status_code=403, detail="permission denied")
    from signal_push import push_signal
    result = push_signal(req.title, req.content)
    return ApiResponse(data=result, message="测试推送已执行")


@app.get("/api/stock/{code}", response_model=ApiResponse)
def api_stock_summary(code: str, authorization: str | None = Header(default=None)):
    require_user(authorization)
    name_row = repo.fetchone("SELECT name FROM stock_list WHERE code=?", (code,))
    rows = repo.fetchall(
        "SELECT date, open, high, low, close, volume FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 60",
        (code,),
    )
    if not rows:
        return ApiResponse(ok=False, message="no data", data={})
    rows = list(reversed(rows))
    closes = [r[4] for r in rows]
    latest = closes[-1]
    prev = closes[-2] if len(closes) >= 2 else latest
    pct = (latest / prev - 1) * 100 if prev > 0 else 0
    return ApiResponse(
        data={
            "code": code,
            "name": name_row[0] if name_row else code,
            "latest_price": round(latest, 2),
            "change_pct": round(pct, 2),
            "high_60d": round(max(r[2] for r in rows), 2),
            "low_60d": round(min(r[3] for r in rows), 2),
            "last_date": rows[-1][0],
        }
    )


@app.get("/api/stock/{code}/kline", response_model=ApiResponse)
def api_stock_kline(code: str, authorization: str | None = Header(default=None), limit: int = 120):
    require_user(authorization)
    rows = repo.fetchall(
        "SELECT date, open, high, low, close, volume FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT ?",
        (code, limit),
    )
    rows = list(reversed(rows))
    data = [
        {"date": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5]}
        for r in rows
    ]
    return ApiResponse(data={"code": code, "items": data, "count": len(data)})


@app.get("/api/stock/{code}/verify", response_model=ApiResponse)
def api_stock_verify(code: str, authorization: str | None = Header(default=None), limit: int = 30):
    require_user(authorization)
    rows = [r for r in get_verify_records(limit=500) if r.get("code") == code][:limit]
    return ApiResponse(data=rows)


@app.get("/api/verify/summary", response_model=ApiResponse)
def api_verify_summary(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(data=get_verify_accuracy_stats())


@app.get("/api/verify/records", response_model=ApiResponse)
def api_verify_records(
    authorization: str | None = Header(default=None),
    limit: int = 100,
    strategy: str = "",
):
    require_user(authorization)
    rows = get_verify_records(limit=limit)
    if strategy:
        rows = [r for r in rows if (r.get("strategy") or "").lower() == strategy.lower()]
    return ApiResponse(data=rows)


@app.post("/api/verify/calibrate", response_model=ApiResponse)
def api_verify_calibrate(authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    if not has_permission(user, "task:trigger"):
        raise HTTPException(status_code=403, detail="permission denied")
    return ApiResponse(data=calibrate_verify())


@app.get("/api/trend-verify/records", response_model=ApiResponse)
def api_trend_verify_records(
    authorization: str | None = Header(default=None),
    limit: int = 100,
    status: str = "",
    strategy: str = "",
    board: str = "",
    root_cause: str = "",
    market_regime: str = "",
    failed_only: bool = False,
    since_days: int = 0,
):
    require_user(authorization)
    rows = get_trend_verify_records(
        limit=limit,
        status=status,
        strategy=strategy,
        board=board,
        root_cause=root_cause,
        market_regime=market_regime,
        failed_only=failed_only,
        since_days=since_days,
    )
    return ApiResponse(data={"items": rows, "count": len(rows)})


@app.get("/api/trend-verify/stats", response_model=ApiResponse)
def api_trend_verify_stats(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(data=get_trend_verify_stats())


@app.get("/api/trend-verify/failure-summary", response_model=ApiResponse)
def api_trend_failure_summary(
    authorization: str | None = Header(default=None),
    limit: int = 200,
    strategy: str = "",
    board: str = "",
    market_regime: str = "",
    since_days: int = 365,
):
    require_user(authorization)
    return ApiResponse(
        data=get_trend_failure_summary(
            limit=limit,
            strategy=strategy,
            board=board,
            market_regime=market_regime,
            since_days=since_days,
        )
    )


@app.post("/api/trend-verify/batch-analyze", response_model=ApiResponse)
def api_trend_batch_analyze(
    authorization: str | None = Header(default=None),
    limit: int = 80,
    strategy: str = "",
    board: str = "",
    since_days: int = 365,
):
    user = require_user(authorization)
    if not has_permission(user, "task:trigger"):
        raise HTTPException(status_code=403, detail="permission denied")
    return ApiResponse(
        data=run_batch_failure_analysis(
            limit=limit,
            strategy=strategy,
            board=board,
            since_days=since_days,
        )
    )


@app.get("/api/openclaw/weights", response_model=ApiResponse)
def api_openclaw_weights(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(data=get_openclaw_strategy_weights())


@app.get("/api/openclaw/sources", response_model=ApiResponse)
def api_openclaw_sources(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(data=get_openclaw_data_sources())


@app.get("/api/openclaw/daemon/status", response_model=ApiResponse)
def api_openclaw_daemon_status(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(data=get_openclaw_daemon_status())


@app.get("/api/openclaw/config-audit", response_model=ApiResponse)
def api_openclaw_config_audit(
    limit: int = 30,
    authorization: str | None = Header(default=None),
):
    require_user(authorization)
    return ApiResponse(data=get_openclaw_config_audit(limit=limit))


@app.post("/api/openclaw/config-audit/rollback", response_model=ApiResponse)
def api_openclaw_config_audit_rollback(
    req: OpenClawConfigRollbackRequest,
    authorization: str | None = Header(default=None),
):
    user = require_user(authorization)
    require_permission(user, "openclaw:admin")
    try:
        return ApiResponse(data=rollback_openclaw_config(audit_index=req.audit_index, actor=user["username"]))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/openclaw/daemon/alert-policy", response_model=ApiResponse)
def api_openclaw_daemon_alert_policy(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(data=get_openclaw_daemon_alert_policy())


@app.post("/api/openclaw/daemon/alert-policy", response_model=ApiResponse)
def api_openclaw_daemon_alert_policy_update(
    req: OpenClawDaemonAlertPolicyRequest,
    authorization: str | None = Header(default=None),
):
    user = require_user(authorization)
    require_permission(user, "openclaw:admin")
    return ApiResponse(data=update_openclaw_daemon_alert_policy(req.model_dump(), actor=user["username"]))


@app.post("/api/openclaw/daemon/alert-policy/reset", response_model=ApiResponse)
def api_openclaw_daemon_alert_policy_reset(authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    require_permission(user, "openclaw:admin")
    return ApiResponse(data=reset_openclaw_daemon_alert_policy(actor=user["username"]))


@app.get("/api/openclaw/coordinator-policy", response_model=ApiResponse)
def api_openclaw_coordinator_policy(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(data=get_coordinator_policy())


@app.post("/api/openclaw/coordinator-policy", response_model=ApiResponse)
def api_openclaw_coordinator_policy_update(
    req: CoordinatorPolicyRequest,
    authorization: str | None = Header(default=None),
):
    user = require_user(authorization)
    require_permission(user, "openclaw:admin")
    return ApiResponse(data=update_coordinator_policy(req.model_dump(), actor=user["username"]))


@app.post("/api/openclaw/coordinator-policy/reset", response_model=ApiResponse)
def api_openclaw_coordinator_policy_reset(authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    require_permission(user, "openclaw:admin")
    return ApiResponse(data=reset_coordinator_policy(actor=user["username"]))


@app.get("/api/openclaw/unattended-trade-guard", response_model=ApiResponse)
def api_openclaw_unattended_trade_guard(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(data=get_unattended_trade_guard())


@app.post("/api/openclaw/unattended-trade-guard", response_model=ApiResponse)
def api_openclaw_unattended_trade_guard_update(
    req: UnattendedTradeGuardRequest,
    authorization: str | None = Header(default=None),
):
    user = require_user(authorization)
    require_permission(user, "openclaw:admin")
    return ApiResponse(data=update_unattended_trade_guard(req.model_dump(), actor=user["username"]))


@app.post("/api/openclaw/unattended-trade-guard/reset", response_model=ApiResponse)
def api_openclaw_unattended_trade_guard_reset(authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    require_permission(user, "openclaw:admin")
    return ApiResponse(data=reset_unattended_trade_guard(actor=user["username"]))


@app.post("/api/openclaw/unattended-trade-guard/replay", response_model=ApiResponse)
def api_openclaw_unattended_trade_guard_replay(
    req: OpenClawGuardReplayRequest,
    authorization: str | None = Header(default=None),
):
    user = require_user(authorization)
    require_permission(user, "openclaw:run")
    return ApiResponse(data=run_unattended_trade_guard_replay(req.model_dump()))


@app.post("/api/openclaw/replay/history", response_model=ApiResponse)
def api_openclaw_historical_replay(
    req: OpenClawHistoricalReplayRequest,
    authorization: str | None = Header(default=None),
):
    user = require_user(authorization)
    require_permission(user, "openclaw:run")
    return ApiResponse(data=build_openclaw_historical_replay_report(req.model_dump()))


@app.post("/api/openclaw/pipeline/run", response_model=ApiResponse)
def api_openclaw_pipeline_run(
    req: TriggerRequest,
    authorization: str | None = Header(default=None),
    traceparent: str | None = Header(default=None),
):
    user = require_user(authorization)
    require_permission(user, "openclaw:run")
    boards = req.boards or ["人工智能", "芯片", "量子科技"]
    if req.dry_run:
        return ApiResponse(data={"dry_run": True, "boards": boards, "traceparent": traceparent or ""})
    result = run_openclaw_pipeline(boards=boards, traceparent=traceparent or "")
    return ApiResponse(data=result)


@app.post("/api/openclaw/learn/run", response_model=ApiResponse)
def api_openclaw_learn_run(
    req: TriggerRequest,
    authorization: str | None = Header(default=None),
    traceparent: str | None = Header(default=None),
):
    user = require_user(authorization)
    if not has_permission(user, "openclaw:learn"):
        raise HTTPException(status_code=403, detail="permission denied")
    if req.dry_run:
        return ApiResponse(data={"dry_run": True, "traceparent": traceparent or ""})
    result = run_openclaw_learning(traceparent=traceparent or "")
    return ApiResponse(data=result)


@app.post("/api/task/trigger/{task_key}", response_model=ApiResponse)
def api_trigger_task(
    task_key: str,
    req: TriggerRequest,
    authorization: str | None = Header(default=None),
    traceparent: str | None = Header(default=None),
):
    user = require_user(authorization)
    if not has_permission(user, "task:trigger"):
        raise HTTPException(status_code=403, detail="permission denied")
    if req.dry_run:
        return ApiResponse(data={"dry_run": True, "task": task_key, "traceparent": traceparent or ""})
    if req.run_async:
        try:
            status = start_background_task(
                task_key,
                boards=req.boards,
                traceparent=traceparent or "",
                priority=req.priority,
                max_retries=req.max_retries,
            )
        except KeyError:
            raise HTTPException(status_code=404, detail="unknown task")
        if not status.get("accepted"):
            return ApiResponse(ok=False, message="task is not accepted", data=status)
        payload = status.get("state", {})
        payload["traceparent"] = traceparent or ""
        payload["accepted"] = True
        return ApiResponse(data=payload, message="task accepted")
    try:
        result = trigger_named_task(task_key, boards=req.boards, traceparent=traceparent or "")
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown task")
    return ApiResponse(data={"task": task_key, "result": result})


@app.get("/api/task/status/{task_key}", response_model=ApiResponse)
def api_task_status(task_key: str, authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(data=get_task_state(task_key))


@app.get("/api/task/status", response_model=ApiResponse)
def api_task_status_all(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(data={"items": list_task_states(), "governance": get_task_governance_state()})


@app.get("/api/task/history", response_model=ApiResponse)
def api_task_history(
    authorization: str | None = Header(default=None),
    limit: int = 50,
    task_key: str = "",
):
    require_user(authorization)
    return ApiResponse(data={"items": get_task_history(limit=limit, task_key=task_key)})


@app.post("/api/sync/export", response_model=ApiResponse)
def api_sync_export(req: SyncExportRequest, authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    if not has_permission(user, "settings:write"):
        raise HTTPException(status_code=403, detail="permission denied")
    keys = req.keys or []
    if req.file_path.strip():
        result = export_runtime_state_to_file(file_path=req.file_path.strip(), keys=keys)
        return ApiResponse(data=result, message="runtime state exported to file")
    return ApiResponse(data=export_runtime_state(keys=keys))


@app.post("/api/sync/import", response_model=ApiResponse)
def api_sync_import(req: SyncImportRequest, authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    if not has_permission(user, "settings:write"):
        raise HTTPException(status_code=403, detail="permission denied")
    if not req.file_path.strip():
        raise HTTPException(status_code=400, detail="file_path is required")
    try:
        result = import_runtime_state_from_file(
            file_path=req.file_path.strip(),
            overwrite=req.overwrite,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ApiResponse(data=result, message="runtime state imported")


@app.post("/api/approval/trade", response_model=ApiResponse)
def api_trade_approval(
    req: ApprovalTradeRequest,
    authorization: str | None = Header(default=None),
    traceparent: str | None = Header(default=None),
):
    """
    小程序/网页审批接口（第一版）：
    - mode 默认为 auto（AI推荐仓）
    - 支持 BUY / SELL
    """
    user = require_user(authorization)
    if not has_permission(user, "task:trigger"):
        raise HTTPException(status_code=403, detail="permission denied")

    mode = req.mode or "auto"
    action = (req.action or "").upper()
    if action not in ("BUY", "SELL"):
        raise HTTPException(status_code=400, detail="action must be BUY or SELL")
    return ApiResponse(
        data=approve_trade(
            mode=mode,
            action=action,
            code=req.code,
            name=req.name,
            price=req.price,
            shares=req.shares,
            reason=req.reason,
            traceparent=traceparent or "",
        )
    )


@app.get("/api/admin/users", response_model=ApiResponse)
def api_admin_users(authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    if not has_permission(user, "settings:write"):
        raise HTTPException(status_code=403, detail="permission denied")
    return ApiResponse(data={"items": list_users(), "roles": sorted(ROLE_NAMES)})


@app.post("/api/admin/users", response_model=ApiResponse)
def api_admin_upsert_user(req: UserUpsertRequest, authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    if not has_permission(user, "settings:write"):
        raise HTTPException(status_code=403, detail="permission denied")
    role = (req.role or "viewer").strip().lower()
    if role not in ROLE_NAMES:
        raise HTTPException(status_code=400, detail="invalid role")
    result = upsert_user(req.username.strip(), req.password, role)
    return ApiResponse(data=result)


@app.delete("/api/admin/users/{username}", response_model=ApiResponse)
def api_admin_delete_user(username: str, authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    if not has_permission(user, "settings:write"):
        raise HTTPException(status_code=403, detail="permission denied")
    ok = delete_user(username)
    if not ok:
        raise HTTPException(status_code=400, detail="delete failed")
    return ApiResponse(data={"deleted": True, "username": username})


@app.post("/api/admin/tokens/revoke", response_model=ApiResponse)
def api_admin_revoke_tokens(req: RevokeTokensRequest, authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    require_permission(user, "settings:write")
    count = revoke_user_tokens(req.username.strip(), actor=user["username"])
    return ApiResponse(data={"username": req.username.strip(), "revoked": count})


@app.post("/api/admin/tokens/revoke-others", response_model=ApiResponse)
def api_admin_revoke_other_tokens(req: RevokeTokensRequest, authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    require_permission(user, "settings:write")
    username = req.username.strip()
    count = revoke_other_user_tokens(username, keep_token=user.get("token", ""), actor=user["username"])
    return ApiResponse(data={"username": username, "revoked": count, "kept_current": username == user.get("username")})


@app.post("/api/admin/tokens/cleanup-expired", response_model=ApiResponse)
def api_admin_cleanup_expired_tokens(authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    require_permission(user, "settings:write")
    return ApiResponse(data=cleanup_expired_tokens(actor=user["username"]))


@app.get("/api/admin/auth-audit", response_model=ApiResponse)
def api_admin_auth_audit(authorization: str | None = Header(default=None), limit: int = 50):
    user = require_user(authorization)
    require_permission(user, "settings:write")
    return ApiResponse(data={"items": get_recent_auth_audit(limit)})


@app.get("/api/admin/security-check", response_model=ApiResponse)
def api_admin_security_check(authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    require_permission(user, "settings:write")
    return ApiResponse(data=get_auth_security_status())


@app.get("/api/admin/production-security-report", response_model=ApiResponse)
def api_admin_production_security_report(authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    require_permission(user, "settings:write")
    return ApiResponse(data=build_production_security_report())
