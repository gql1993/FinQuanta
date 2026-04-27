"""
Application-level operations service.

This module centralizes read-oriented operational views first so the API layer
does not depend directly on desktop orchestration modules.
"""

from __future__ import annotations
from datetime import datetime

from core.application.registry_service import get_registry_overview
from core.application.snapshot_service import get_system_snapshot
from core.observability.metrics import get_metrics_snapshot, inc_counter
from core.observability.trends import build_event_trend_report
from core.observability.structured_logging import emit_structured_log
from core.repositories.task_repo import TaskRepository

task_repo = TaskRepository()


def get_recent_task_runs(limit: int = 50) -> list[dict]:
    return task_repo.get_recent_task_runs(limit)


def get_recent_system_events(limit: int = 50) -> list[dict]:
    return task_repo.get_recent_system_events(limit)


def log_system_event(
    source: str,
    category: str,
    title: str,
    detail: str = "",
    level: str = "info",
    *,
    trace_id: str = "",
    decision_id: str = "",
    metadata: dict | None = None,
) -> None:
    normalized_level = (level or "info").lower()
    inc_counter(
        "system_events_total",
        labels={
            "source": source or "unknown",
            "category": category or "unknown",
            "level": normalized_level,
        },
    )
    emit_structured_log(
        event="system_event",
        level=normalized_level,
        source=source,
        category=category,
        trace_id=trace_id,
        decision_id=decision_id,
        title=title,
        detail=detail,
        metadata=metadata or {},
    )
    task_repo.log_system_event(
        source,
        category,
        title,
        detail=detail,
        level=level,
        trace_id=trace_id,
        decision_id=decision_id,
        metadata=metadata,
    )


def run_task(task_name: str, trigger_source: str, func, *args, **kwargs):
    from desktop.task_orchestrator import run_task as _run_task

    return _run_task(task_name, trigger_source, func, *args, **kwargs)


def get_operation_log(limit: int = 50) -> list[dict]:
    return task_repo.get_operation_log(limit)


def get_event_trend_report(window_days: int = 7, event_limit: int = 500) -> dict:
    events = get_recent_system_events(limit=event_limit)
    return build_event_trend_report(events, window_days=window_days)


def get_ops_center_payload(
    limit: int = 20,
    refresh_snapshot: bool = False,
    registry_token: str = "",
) -> dict:
    daemon_status = {}
    try:
        from desktop.daemon_scheduler import get_daemon_runtime_status

        daemon_status = get_daemon_runtime_status()
    except Exception:
        daemon_status = {
            "active": False,
            "leader_pid": 0,
            "leader_token": "",
            "heartbeat_at": "",
            "heartbeat_age_seconds": -1,
            "disabled_tasks": [],
            "next_task": {"task_key": "", "task_name": "", "time": "", "scheduled_at": ""},
        }
    registry = get_registry_overview()
    registry_meta = registry.get("meta", {}) or {}
    current_token = str(registry_meta.get("change_token", "") or "")
    cached = bool(registry_meta.get("cached", False))
    registry_changed = (not registry_token) or (registry_token != current_token)
    payload_mode = "full" if registry_changed else "compact"
    if not registry_changed:
        # Keep summary metadata/counts but skip full list payload for incremental refresh.
        registry = {
            "provider_count": registry.get("provider_count", 0),
            "strategy_count": registry.get("strategy_count", 0),
            "notifier_count": registry.get("notifier_count", 0),
            "workflow_count": registry.get("workflow_count", 0),
            "agent_count": registry.get("agent_count", 0),
            "providers": [],
            "strategies": [],
            "notifiers": [],
            "workflows": [],
            "agents": [],
            "meta": registry_meta,
        }
    return {
        "snapshot": get_system_snapshot(refresh=refresh_snapshot),
        "tasks": get_recent_task_runs(limit),
        "events": get_recent_system_events(limit),
        "operations": get_operation_log(limit),
        "daemon": daemon_status,
        "daemon_health": build_daemon_health_report(daemon_status),
        "registry": registry,
        "registry_changed": registry_changed,
        "registry_sync": {
            "requested_token": registry_token or "",
            "active_token": current_token,
            "changed": registry_changed,
            "cached": cached,
            "payload_mode": payload_mode,
        },
    }


def build_operational_health_report(limit: int = 50) -> dict:
    """Build a compact on-call health snapshot for unattended operation."""
    limit = max(1, min(200, int(limit or 50)))
    generated_at = datetime.now().isoformat(timespec="seconds")
    findings: list[dict] = []
    runbook: list[str] = []

    daemon_status = _safe_call(
        lambda: __import__("desktop.daemon_scheduler", fromlist=["get_daemon_runtime_status"]).get_daemon_runtime_status(),
        fallback={},
    )
    daemon_health = build_daemon_health_report(daemon_status if isinstance(daemon_status, dict) else {})
    daemon_failed = {
        str(item.get("name", ""))
        for item in daemon_health.get("checks", [])
        if not bool(item.get("ok", False))
    }
    daemon_level = "error" if daemon_failed.intersection({"daemon_leader", "duplicate_instance"}) else "warning"
    _add_finding(
        findings,
        not bool(daemon_health.get("ok", False)),
        daemon_level,
        "daemon_unhealthy",
        "后台 daemon 自检未通过。",
        details={"jump_target": daemon_health.get("jump_target", ""), "checks": daemon_health.get("checks", [])},
    )

    openclaw_status = _safe_call(
        lambda: __import__("core.application.openclaw_service", fromlist=["get_openclaw_daemon_status"]).get_openclaw_daemon_status(),
        fallback={},
    )
    readiness = ((openclaw_status or {}).get("openclaw", {}) or {}).get("readiness", {}) if isinstance(openclaw_status, dict) else {}
    _add_finding(
        findings,
        not bool(readiness.get("ready", False)),
        "error",
        "openclaw_not_ready",
        str(readiness.get("summary", "") or "OpenClaw 后台未就绪。"),
        details={"errors": readiness.get("errors", []), "warnings": readiness.get("warnings", [])},
    )
    openclaw = (openclaw_status.get("openclaw", {}) if isinstance(openclaw_status, dict) else {}) or {}
    last_run = openclaw.get("last_run", {}) if isinstance(openclaw, dict) else {}
    alert_state = openclaw.get("alert_state", {}) if isinstance(openclaw, dict) else {}
    trade_guard = _safe_call(
        lambda: __import__(
            "core.application.openclaw_service",
            fromlist=["get_unattended_trade_guard"],
        ).get_unattended_trade_guard(),
        fallback={},
    )
    simulation = (trade_guard.get("simulation", {}) if isinstance(trade_guard, dict) else {}) or {}
    _add_finding(
        findings,
        not bool(simulation.get("passed", False)),
        "error",
        "simulation_gate_not_passed",
        "无人值守仿真门禁未通过。",
        details=simulation,
    )

    security = _safe_call(
        lambda: __import__("api_server.auth", fromlist=["get_auth_security_status"]).get_auth_security_status(),
        fallback={"status": "error", "findings": [{"level": "error", "code": "security_check_failed"}]},
    )
    for item in security.get("findings", []) if isinstance(security, dict) else []:
        findings.append(
            {
                "level": str(item.get("level", "warning") or "warning"),
                "code": f"security_{item.get('code', 'finding')}",
                "message": str(item.get("message", "") or "认证安全检查存在风险。"),
            }
        )

    recent_events = get_recent_system_events(limit)
    recent_tasks = get_recent_task_runs(limit)
    metrics = get_metrics_snapshot()
    event_level_counts = _count_event_levels(recent_events)
    _add_finding(
        findings,
        event_level_counts.get("error", 0) > 0,
        "warning",
        "recent_error_events",
        f"最近 {limit} 条系统事件包含 {event_level_counts.get('error', 0)} 条 error。",
        details={"level_counts": event_level_counts},
    )

    consecutive_errors = int(alert_state.get("consecutive_errors", 0) or 0) if isinstance(alert_state, dict) else 0
    _add_finding(
        findings,
        consecutive_errors > 0,
        "warning",
        "openclaw_consecutive_errors",
        f"OpenClaw 连续失败 {consecutive_errors} 次。",
        details={"alert_state": alert_state},
    )

    status = _status_from_findings(findings)
    if status != "ready":
        runbook.extend(_build_operational_runbook(findings))
    else:
        runbook.append("系统处于无人值守可运行状态，继续保持买入安全闸和告警策略。")

    return {
        "status": status,
        "ready": status == "ready",
        "generated_at": generated_at,
        "summary": "运维健康检查通过" if status == "ready" else "运维健康检查存在需处理项",
        "findings": findings,
        "runbook": runbook,
        "signals": {
            "daemon": {
                "active": bool((daemon_status or {}).get("active", False)) if isinstance(daemon_status, dict) else False,
                "heartbeat_age_seconds": (daemon_status or {}).get("heartbeat_age_seconds", -1)
                if isinstance(daemon_status, dict)
                else -1,
                "next_task": (daemon_status or {}).get("next_task", {}) if isinstance(daemon_status, dict) else {},
                "health": daemon_health,
            },
            "openclaw": {
                "readiness": readiness,
                "last_run_status": last_run.get("status", "") if isinstance(last_run, dict) else "",
                "last_run_summary": last_run.get("summary", "") if isinstance(last_run, dict) else "",
                "alert_state": alert_state if isinstance(alert_state, dict) else {},
                "simulation": simulation,
            },
            "security": security,
            "events": {
                "count": len(recent_events),
                "level_counts": event_level_counts,
            },
            "tasks": {
                "count": len(recent_tasks),
                "latest": recent_tasks[:5],
            },
            "metrics": {
                "counter_count": len(metrics.get("counters", {}) or {}),
                "histogram_count": len(metrics.get("histograms", {}) or {}),
                "sample_counters": dict(list((metrics.get("counters", {}) or {}).items())[:10]),
            },
        },
    }


def build_daemon_health_report(daemon_status: dict | None = None) -> dict:
    status = daemon_status or {}
    next_task = status.get("next_task", {}) if isinstance(status, dict) else {}
    push_status = status.get("push_status", {}) if isinstance(status, dict) else {}
    duplicate = status.get("duplicate_lock", {}) if isinstance(status, dict) else {}
    active = bool(status.get("active", False))
    has_scheduled_task = bool(next_task.get("scheduled_at", ""))
    next_task_detail = (
        f"{next_task.get('task_name', '-') } @ {next_task.get('scheduled_at', '-')}"
        if has_scheduled_task
        else "no pending task; daemon active"
        if active
        else "no pending task"
    )

    checks = [
        {
            "name": "daemon_leader",
            "ok": active,
            "detail": f"leader_pid={status.get('leader_pid', 0)}",
        },
        {
            "name": "next_task",
            "ok": active or has_scheduled_task,
            "detail": next_task_detail,
        },
        {
            "name": "push_channel",
            "ok": str(push_status.get("last_result", "")).lower() in {"success", "skipped_limit", "skipped_no_channel"},
            "detail": (
                f"result={push_status.get('last_result', '-')}, "
                f"last_success={push_status.get('last_success_at', '-')}, "
                f"count_today={push_status.get('count_today', 0)}"
            ),
        },
        {
            "name": "duplicate_instance",
            "ok": not bool(duplicate.get("detected", False)),
            "detail": (
                f"detected={duplicate.get('detected', False)}, "
                f"holder_pid={duplicate.get('holder_pid', 0)}, "
                f"at={duplicate.get('detected_at', '-')}"
            ),
        },
    ]
    overall_ok = all(bool(item.get("ok", False)) for item in checks)
    jump_target = _resolve_daemon_health_jump_target(checks)
    suggestions = _build_daemon_health_suggestions(checks)
    diagnostics = _build_daemon_health_diagnostics(status, checks, suggestions)
    return {
        "ok": overall_ok,
        "checks": checks,
        "jump_target": jump_target,
        "suggestions": suggestions,
        "diagnostics": diagnostics,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def _resolve_daemon_health_jump_target(checks: list[dict]) -> str:
    failed = {str(item.get("name", "")): item for item in checks if not bool(item.get("ok", False))}
    if "push_channel" in failed:
        return "settings_push"
    if "next_task" in failed or "daemon_leader" in failed:
        return "settings_schedule"
    if "duplicate_instance" in failed:
        return "settings_schedule"
    return ""


def _build_daemon_health_suggestions(checks: list[dict]) -> list[str]:
    failed = {str(item.get("name", "")): item for item in checks if not bool(item.get("ok", False))}
    if not failed:
        return ["链路健康，保持当前配置即可。"]

    suggestions: list[str] = []
    if "daemon_leader" in failed:
        suggestions.append("启动 daemon：运行 start_daemon.bat，或设置 FINQUANTA_API_AUTOSTART_DAEMON=1 后重启 API。")
    if "next_task" in failed:
        suggestions.append("检查调度配置：确认未把全部任务禁用，并校验任务时间格式（HH:MM）。")
    if "push_channel" in failed:
        suggestions.append("检查推送配置：在设置页验证 Server酱/邮箱参数，并执行一次测试推送。")
    if "duplicate_instance" in failed:
        suggestions.append("检测到重复实例：关闭多余 FinQuanta/API 进程，仅保留一个 daemon 领导实例。")
    suggestions.append("如仍异常，复制诊断信息并提交给运维/开发继续定位。")
    return suggestions


def _build_daemon_health_diagnostics(status: dict, checks: list[dict], suggestions: list[str]) -> str:
    now_text = datetime.now().isoformat(timespec="seconds")
    lines = [
        f"[FinQuanta Daemon Self Check] {now_text}",
        f"active={status.get('active', False)}",
        f"leader_pid={status.get('leader_pid', 0)}",
        f"heartbeat_at={status.get('heartbeat_at', '-')}",
        f"next_task={status.get('next_task', {})}",
        f"push_status={status.get('push_status', {})}",
        f"duplicate_lock={status.get('duplicate_lock', {})}",
        "",
        "checks:",
    ]
    for item in checks:
        lines.append(f"- {item.get('name', '-')}: ok={item.get('ok', False)}; detail={item.get('detail', '-')}")
    lines.append("")
    lines.append("suggestions:")
    for tip in suggestions:
        lines.append(f"- {tip}")
    return "\n".join(lines)


def _safe_call(func, fallback):
    try:
        result = func()
        return result if result is not None else fallback
    except Exception:
        return fallback


def _add_finding(
    findings: list[dict],
    condition: bool,
    level: str,
    code: str,
    message: str,
    *,
    details: dict | list | None = None,
) -> None:
    if not condition:
        return
    item = {"level": level, "code": code, "message": message}
    if details is not None:
        item["details"] = details
    findings.append(item)


def _status_from_findings(findings: list[dict]) -> str:
    if any(str(item.get("level", "")).lower() == "error" for item in findings):
        return "error"
    if findings:
        return "warning"
    return "ready"


def _count_event_levels(events: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in events or []:
        level = str(item.get("level", "info") or "info").lower()
        counts[level] = counts.get(level, 0) + 1
    return counts


def _build_operational_runbook(findings: list[dict]) -> list[str]:
    codes = {str(item.get("code", "")) for item in findings}
    steps: list[str] = []
    if "daemon_unhealthy" in codes:
        steps.append("检查计划任务/API 常驻进程，确认只有一个 daemon leader，并查看 logs/api_service.log。")
    if "openclaw_not_ready" in codes:
        steps.append("打开 OpenClaw 运行中心或调用 /api/openclaw/daemon/status，优先处理 readiness.errors。")
    if "simulation_gate_not_passed" in codes:
        steps.append("保持无人值守买入关闭，连续完成仿真运行后再考虑放开买入权限。")
    if any(code.startswith("security_") for code in codes):
        steps.append("处理认证安全项：修改默认 admin 密码、清理异常 token，并限制 admin 日常使用。")
    if "recent_error_events" in codes:
        steps.append("查看 /api/ops/events 中最近 error，按 trace_id 或 decision_id 追踪具体链路。")
    if "openclaw_consecutive_errors" in codes:
        steps.append("检查 OpenClaw alert_state.routing 和最近 last_run，确认告警是否已升级到值班通道。")
    steps.append("处理完成后重新运行 e2e_openclaw_unattended.bat 和 check_trade_channel_safety.bat。")
    return steps


def get_message_feed(limit: int = 30) -> list[dict]:
    messages = []
    for event in get_recent_system_events(limit):
        messages.append(
            {
                "time": event.get("timestamp", ""),
                "type": event.get("category", ""),
                "title": event.get("title", ""),
                "detail": event.get("detail", ""),
                "level": event.get("level", "info"),
            }
        )
    for operation in get_operation_log(limit):
        messages.append(
            {
                "time": operation.get("time", ""),
                "type": operation.get("module", ""),
                "title": operation.get("action", ""),
                "detail": operation.get("detail", ""),
                "level": "info",
            }
        )
    messages.sort(key=lambda item: item.get("time", ""), reverse=True)
    return messages[:limit]
