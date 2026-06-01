"""
Application-level OpenClaw service.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from core.config.feature_flags import is_feature_enabled
from core.observability.tracing import create_trace_id, finish_span, start_span

DEFAULT_OPENCLAW_BOARDS = ["人工智能", "芯片", "量子科技"]
_OPENCLAW_GUARD_REPLAY_LAST_KEY = "openclaw_guard_replay_last"
_OPENCLAW_GUARD_REPLAY_HISTORY_KEY = "openclaw_guard_replay_history"
_OPENCLAW_CONFIG_AUDIT_KEY = "openclaw_config_audit_history"


def _config_diff(before: dict, after: dict) -> dict:
    keys = sorted(set((before or {}).keys()) | set((after or {}).keys()))
    diff = {}
    for key in keys:
        old = (before or {}).get(key)
        new = (after or {}).get(key)
        if old != new:
            diff[key] = {"before": old, "after": new}
    return diff


def _record_openclaw_config_audit(domain: str, action: str, before: dict, after: dict, *, actor: str = "system") -> dict:
    from datetime import datetime

    from desktop.data_access import get_kv_json, set_kv_json

    diff = _config_diff(before or {}, after or {})
    item = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "domain": domain,
        "action": action,
        "actor": actor or "system",
        "changed_keys": sorted(diff.keys()),
        "diff": diff,
    }
    history = get_kv_json(_OPENCLAW_CONFIG_AUDIT_KEY, []) or []
    if isinstance(history, str):
        try:
            history = json.loads(history)
        except Exception:
            history = []
    if not isinstance(history, list):
        history = []
    history.insert(0, item)
    set_kv_json(_OPENCLAW_CONFIG_AUDIT_KEY, history[:100])
    try:
        from desktop.task_orchestrator import log_system_event

        log_system_event(
            "openclaw",
            "config",
            f"OpenClaw配置变更: {domain}/{action}",
            detail=",".join(item["changed_keys"])[:300],
            level="info",
        )
    except Exception:
        pass
    return item


def get_openclaw_config_audit(limit: int = 30) -> dict:
    from desktop.data_access import get_kv_json

    history = get_kv_json(_OPENCLAW_CONFIG_AUDIT_KEY, []) or []
    if isinstance(history, str):
        try:
            history = json.loads(history)
        except Exception:
            history = []
    if not isinstance(history, list):
        history = []
    limit = max(1, min(100, int(limit or 30)))
    return {"history": history[:limit], "count": len(history)}


def rollback_openclaw_config(audit_index: int = 0, *, actor: str = "system") -> dict:
    audit = get_openclaw_config_audit(limit=100)
    history = audit.get("history", []) or []
    idx = max(0, int(audit_index or 0))
    if idx >= len(history):
        raise ValueError(f"audit record not found: {idx}")
    record = history[idx] or {}
    domain = str(record.get("domain", "") or "")
    diff = record.get("diff", {}) or {}
    patch = {key: value.get("before") for key, value in diff.items() if isinstance(value, dict)}
    if not patch:
        raise ValueError("audit record has no rollback diff")

    if domain == "coordinator_policy":
        from desktop.agents import get_coordinator_policy_config, set_coordinator_policy_config

        before = get_coordinator_policy_config()
        after = set_coordinator_policy_config({**before, **patch})
    elif domain == "unattended_trade_guard":
        from desktop.agents import get_unattended_trade_guard_config, set_unattended_trade_guard_config

        before = get_unattended_trade_guard_config()
        after = set_unattended_trade_guard_config({**before, **patch})
    elif domain == "daemon_alert_policy":
        from desktop.daemon_scheduler import get_openclaw_alert_policy_config, set_openclaw_alert_policy_config

        before = get_openclaw_alert_policy_config()
        after = set_openclaw_alert_policy_config({**before, **patch})
    else:
        raise ValueError(f"unsupported config domain: {domain}")

    rollback_audit = _record_openclaw_config_audit(domain, "rollback", before, after, actor=actor)
    return {
        "rolled_back": True,
        "domain": domain,
        "source_audit": {
            "timestamp": record.get("timestamp", ""),
            "action": record.get("action", ""),
            "changed_keys": record.get("changed_keys", []),
        },
        "config": after,
        "audit": rollback_audit,
    }


def get_openclaw_strategy_weights() -> dict:
    from desktop.openclaw_learner import get_strategy_weights

    return get_strategy_weights()


def get_openclaw_data_sources() -> list[dict]:
    from desktop.openclaw_engine import get_data_sources_status

    return get_data_sources_status()


def get_coordinator_policy() -> dict:
    from desktop.agents import get_coordinator_policy_config

    return get_coordinator_policy_config()


def update_coordinator_policy(payload: dict, *, actor: str = "system") -> dict:
    from desktop.agents import get_coordinator_policy_config, set_coordinator_policy_config

    clean = {
        key: value
        for key, value in (payload or {}).items()
        if value is not None
    }
    before = get_coordinator_policy_config()
    after = set_coordinator_policy_config(clean)
    _record_openclaw_config_audit("coordinator_policy", "update", before, after, actor=actor)
    return after


def reset_coordinator_policy(*, actor: str = "system") -> dict:
    from desktop.agents import _COORDINATOR_POLICY_DEFAULTS, get_coordinator_policy_config, set_coordinator_policy_config

    before = get_coordinator_policy_config()
    after = set_coordinator_policy_config(dict(_COORDINATOR_POLICY_DEFAULTS))
    _record_openclaw_config_audit("coordinator_policy", "reset", before, after, actor=actor)
    return after


def get_unattended_trade_guard() -> dict:
    from desktop.agents import (
        get_unattended_trade_guard_config,
        get_unattended_trade_guard_simulation_state,
        get_unattended_trade_guard_usage,
    )

    return {
        "config": get_unattended_trade_guard_config(),
        "usage": get_unattended_trade_guard_usage(),
        "simulation": get_unattended_trade_guard_simulation_state(),
        "replay": get_unattended_trade_guard_replay_history(),
    }


def update_unattended_trade_guard(payload: dict, *, actor: str = "system") -> dict:
    from desktop.agents import (
        get_unattended_trade_guard_config,
        get_unattended_trade_guard_simulation_state,
        get_unattended_trade_guard_usage,
        set_unattended_trade_guard_config,
    )

    clean = {
        key: value
        for key, value in (payload or {}).items()
        if value is not None
    }
    before = get_unattended_trade_guard_config()
    after = set_unattended_trade_guard_config(clean)
    _record_openclaw_config_audit("unattended_trade_guard", "update", before, after, actor=actor)
    return {
        "config": after,
        "usage": get_unattended_trade_guard_usage(),
        "simulation": get_unattended_trade_guard_simulation_state(),
    }


def reset_unattended_trade_guard(*, actor: str = "system") -> dict:
    from desktop.agents import (
        _UNATTENDED_TRADE_GUARD_DEFAULTS,
        get_unattended_trade_guard_config,
        get_unattended_trade_guard_simulation_state,
        get_unattended_trade_guard_usage,
        set_unattended_trade_guard_config,
    )

    before = get_unattended_trade_guard_config()
    after = set_unattended_trade_guard_config(dict(_UNATTENDED_TRADE_GUARD_DEFAULTS))
    _record_openclaw_config_audit("unattended_trade_guard", "reset", before, after, actor=actor)
    return {
        "config": after,
        "usage": get_unattended_trade_guard_usage(),
        "simulation": get_unattended_trade_guard_simulation_state(),
        "replay": get_unattended_trade_guard_replay_history(),
    }


def get_unattended_trade_guard_replay_history() -> dict:
    from desktop.data_access import get_kv_json

    last = get_kv_json(_OPENCLAW_GUARD_REPLAY_LAST_KEY, {}) or {}
    history = get_kv_json(_OPENCLAW_GUARD_REPLAY_HISTORY_KEY, []) or []
    if isinstance(last, str):
        try:
            last = json.loads(last)
        except Exception:
            last = {}
    if isinstance(history, str):
        try:
            history = json.loads(history)
        except Exception:
            history = []
    return {
        "last": last if isinstance(last, dict) else {},
        "history": history[:30] if isinstance(history, list) else [],
    }


def _load_kv_list(key: str, limit: int = 30) -> list[dict]:
    from desktop.data_access import get_kv_json

    rows = get_kv_json(key, []) or []
    if isinstance(rows, str):
        try:
            rows = json.loads(rows)
        except Exception:
            rows = []
    if not isinstance(rows, list):
        return []
    return [item for item in rows[: max(1, min(200, int(limit or 30)))] if isinstance(item, dict)]


def _count_by_status(rows: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for item in rows:
        status = str(item.get("status", "") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _rate(part: int, total: int) -> float:
    return round((part / total * 100), 2) if total else 0.0


def _extract_daemon_replay_rows(history: list[dict]) -> list[dict]:
    for item in history:
        sample = item.get("decision_sample") or item.get("executed_sample") or []
        if isinstance(sample, list) and sample:
            return [row for row in sample if isinstance(row, dict)]
    try:
        from desktop.data_access import get_kv_json

        latest = get_kv_json("openclaw_last_daemon_run", {}) or {}
    except Exception:
        latest = {}
    if not isinstance(latest, dict):
        return []
    for key in ("decision_sample", "executed_sample"):
        sample = latest.get(key) or []
        if isinstance(sample, list) and sample:
            return [row for row in sample if isinstance(row, dict)]
    # Best-effort support for older records where only a trace output summary was stored.
    trace = latest.get("agent_trace", {}) or {}
    spans = trace.get("spans", []) if isinstance(trace, dict) else []
    for span in spans or []:
        if not isinstance(span, dict) or span.get("agent_key") != "decision":
            continue
        text = str((span.get("output_summary", {}) or {}).get("value", "") or "")
        match = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.S)
        if not match:
            continue
        try:
            parsed = json.loads(match.group(1))
            rows = parsed.get("decisions", []) if isinstance(parsed, dict) else []
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        except Exception:
            continue
    return []


def build_openclaw_historical_replay_report(payload: dict | None = None) -> dict:
    """Build a no-order historical replay report across daemon, guard, and learning records."""
    payload = payload or {}
    limit = max(1, min(100, int(payload.get("limit", 30) or 30)))
    history = _load_kv_list("openclaw_daemon_run_history", limit=limit)
    status_counts = _count_by_status(history)
    success_count = int(status_counts.get("success", 0) or 0)
    warning_count = int(status_counts.get("warning", 0) or 0)
    error_count = int(status_counts.get("error", 0) or 0)
    latest = history[0] if history else {}

    trade_guard = get_unattended_trade_guard()
    simulation = trade_guard.get("simulation", {}) or {}
    guard_replay = trade_guard.get("replay", {}) or {}
    guard_replay_result = None
    if bool(payload.get("include_guard_replay", True)):
        replay_payload = {
            "limit": int(payload.get("replay_limit", 10) or 10),
            "shares": int(payload.get("shares", 100) or 100),
            "mode": str(payload.get("mode", "auto") or "auto"),
            "use_real_price": bool(payload.get("use_real_price", False)),
        }
        rows = payload.get("items") or payload.get("decisions") or _extract_daemon_replay_rows(history)
        if isinstance(rows, list) and rows:
            replay_payload["items"] = rows
        guard_replay_result = run_unattended_trade_guard_replay(replay_payload)
        guard_replay = get_unattended_trade_guard_replay_history()

    decision_accuracy = {}
    try:
        from desktop.agents import get_decision_accuracy

        decision_accuracy = get_decision_accuracy(limit=limit)
    except Exception as exc:
        decision_accuracy = {"error": str(exc)}

    trend_verify = {}
    try:
        from desktop.trend_verify import get_accuracy_stats, get_failure_summary

        trend_verify = {
            "accuracy": get_accuracy_stats(),
            "failure_summary": get_failure_summary(limit=min(limit, 100), since_days=180),
        }
    except Exception as exc:
        trend_verify = {"error": str(exc)}

    findings: list[dict] = []
    if not history:
        findings.append({"level": "warning", "code": "no_daemon_history", "message": "暂无后台 OpenClaw 运行历史"})
    if latest and latest.get("status") != "success":
        findings.append({
            "level": "warning" if latest.get("status") == "warning" else "error",
            "code": "latest_run_not_success",
            "message": f"最近一次后台运行状态为 {latest.get('status', '-')}",
        })
    if error_count:
        findings.append({"level": "warning", "code": "historical_errors", "message": f"最近 {limit} 次中有 {error_count} 次 error"})
    if not bool(simulation.get("passed", False)):
        findings.append({"level": "warning", "code": "simulation_not_passed", "message": "无人值守买入仿真门禁未通过"})
    if guard_replay_result and guard_replay_result.get("ok") is False:
        findings.append({"level": "warning", "code": "guard_replay_empty", "message": guard_replay_result.get("message", "安全闸回放无输入")})
    if guard_replay_result and int(guard_replay_result.get("rejected_count", 0) or 0) > 0:
        findings.append({
            "level": "info",
            "code": "guard_replay_rejections",
            "message": f"安全闸回放拒绝 {guard_replay_result.get('rejected_count')} 条，说明保护规则生效",
        })

    verdict = "ready"
    if any(item.get("level") == "error" for item in findings):
        verdict = "error"
    elif any(item.get("level") == "warning" for item in findings):
        verdict = "warning"

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "verdict": verdict,
        "summary": "全链路历史回放就绪" if verdict == "ready" else "全链路历史回放存在需关注项",
        "window": {"limit": limit, "history_count": len(history)},
        "daemon": {
            "latest": latest,
            "status_counts": status_counts,
            "success_rate": _rate(success_count, len(history)),
            "warning_rate": _rate(warning_count, len(history)),
            "error_rate": _rate(error_count, len(history)),
            "history": history,
        },
        "trade_guard": {
            "config": trade_guard.get("config", {}),
            "simulation": simulation,
            "replay": guard_replay,
            "replay_result": guard_replay_result,
        },
        "decision_accuracy": decision_accuracy,
        "trend_verify": trend_verify,
        "findings": findings,
        "note": "historical replay report only; trade guard replay captures writes but does not place orders",
    }


def _record_unattended_trade_guard_replay(result: dict) -> None:
    from desktop.data_access import get_kv_json, set_kv_json

    item = {
        "timestamp": result.get("timestamp", ""),
        "ok": bool(result.get("ok", False)),
        "source": result.get("source", ""),
        "mode": result.get("mode", ""),
        "input_count": int(result.get("input_count", 0) or 0),
        "approved_count": int(result.get("approved_count", 0) or 0),
        "rejected_count": int(result.get("rejected_count", 0) or 0),
        "skipped_count": int(result.get("skipped_count", 0) or 0),
        "message": str(result.get("message", "") or ""),
    }
    history = get_kv_json(_OPENCLAW_GUARD_REPLAY_HISTORY_KEY, []) or []
    if isinstance(history, str):
        try:
            history = json.loads(history)
        except Exception:
            history = []
    if not isinstance(history, list):
        history = []
    history.insert(0, item)
    set_kv_json(_OPENCLAW_GUARD_REPLAY_LAST_KEY, item)
    set_kv_json(_OPENCLAW_GUARD_REPLAY_HISTORY_KEY, history[:30])


def _replay_to_float(value, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "").replace("¥", "").strip())
    except Exception:
        return default


def _replay_to_int(value, default: int = 0) -> int:
    try:
        return int(float(str(value).replace(",", "").strip()))
    except Exception:
        return default


def build_unattended_trade_guard_replay_decisions(
    rows: list[dict],
    *,
    default_shares: int = 100,
    limit: int = 10,
) -> list[dict]:
    decisions: list[dict] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        action = str(row.get("action") or row.get("操作") or "").lower()
        advice = str(row.get("建议买入") or row.get("signal") or row.get("信号") or "")
        if not action:
            action = "buy" if "买" in advice or not advice else "hold"
        if action in {"买入", "buy"}:
            action = "buy"
        elif action in {"卖出", "sell"}:
            action = "sell"
        elif action in {"持有", "hold"}:
            action = "hold"
        else:
            action = "buy"

        code = str(row.get("code") or row.get("代码") or "").strip()
        if not code:
            continue
        decisions.append(
            {
                "action": action,
                "code": code,
                "name": str(row.get("name") or row.get("名称") or code),
                "price": _replay_to_float(row.get("price") or row.get("价格") or row.get("close") or row.get("收盘价"), 10.0),
                "shares": _replay_to_int(row.get("shares") or row.get("数量"), default_shares),
                "sector": str(row.get("sector") or row.get("industry") or row.get("板块") or ""),
                "reason": str(row.get("reason") or row.get("理由") or advice or "openclaw replay"),
            }
        )
        if limit > 0 and len(decisions) >= limit:
            break
    return decisions


def run_unattended_trade_guard_replay_decisions(
    decisions: list[dict],
    *,
    mode: str = "auto",
    use_input_price: bool = True,
) -> dict:
    from datetime import datetime

    import desktop.agents as agents
    import desktop.ai_trader as ai_trader

    captured_writes: dict[str, object] = {}
    original_set_kv_json = agents.set_kv_json
    original_get_real_price = ai_trader._get_real_price
    try:
        agents.set_kv_json = lambda key, value: captured_writes.__setitem__(key, value)
        if use_input_price:
            ai_trader._get_real_price = lambda code: 0.0
        report = agents.ApprovalAgent.review_decisions(decisions, mode=mode)
    finally:
        agents.set_kv_json = original_set_kv_json
        ai_trader._get_real_price = original_get_real_price

    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "mode": mode,
        "input_count": len(decisions),
        "approved_count": len(report.get("approved_decisions", []) or []),
        "rejected_count": len(report.get("rejected_decisions", []) or []),
        "skipped_count": len(report.get("skipped_decisions", []) or []),
        "report": report,
        "captured_writes": captured_writes,
        "note": "replay only; captured_writes were not persisted",
    }


def run_unattended_trade_guard_replay(payload: dict | None = None) -> dict:
    from desktop.data_access import get_kv_json

    payload = payload or {}
    rows = payload.get("items") or payload.get("decisions") or []
    source = "request"
    if not isinstance(rows, list) or not rows:
        from desktop.scan_store import resolve_scan_results

        rows = resolve_scan_results()[0]
        source = "last_scan_results"
    if not isinstance(rows, list):
        rows = []
    decisions = build_unattended_trade_guard_replay_decisions(
        rows,
        default_shares=max(1, int(payload.get("shares", 100) or 100)),
        limit=int(payload.get("limit", 10) or 10),
    )
    if not decisions:
        result = {
            "ok": False,
            "source": source,
            "timestamp": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
            "mode": str(payload.get("mode", "auto") or "auto"),
            "input_count": 0,
            "approved_count": 0,
            "rejected_count": 0,
            "skipped_count": 0,
            "message": "no replay decisions found",
        }
        _record_unattended_trade_guard_replay(result)
        return result
    result = run_unattended_trade_guard_replay_decisions(
        decisions,
        mode=str(payload.get("mode", "auto") or "auto"),
        use_input_price=not bool(payload.get("use_real_price", False)),
    )
    result["ok"] = True
    result["source"] = source
    _record_unattended_trade_guard_replay(result)
    return result


def get_openclaw_daemon_alert_policy() -> dict:
    from desktop.daemon_scheduler import get_openclaw_alert_policy_config

    return get_openclaw_alert_policy_config()


def update_openclaw_daemon_alert_policy(payload: dict, *, actor: str = "system") -> dict:
    from desktop.daemon_scheduler import get_openclaw_alert_policy_config, set_openclaw_alert_policy_config

    clean = {
        key: value
        for key, value in (payload or {}).items()
        if value is not None
    }
    before = get_openclaw_alert_policy_config()
    after = set_openclaw_alert_policy_config(clean)
    _record_openclaw_config_audit("daemon_alert_policy", "update", before, after, actor=actor)
    return after


def reset_openclaw_daemon_alert_policy(*, actor: str = "system") -> dict:
    from desktop.daemon_scheduler import (
        _OPENCLAW_ALERT_POLICY_DEFAULTS,
        get_openclaw_alert_policy_config,
        set_openclaw_alert_policy_config,
    )

    before = get_openclaw_alert_policy_config()
    after = set_openclaw_alert_policy_config(dict(_OPENCLAW_ALERT_POLICY_DEFAULTS))
    _record_openclaw_config_audit("daemon_alert_policy", "reset", before, after, actor=actor)
    return after


def _build_openclaw_daemon_readiness(
    *,
    runtime: dict,
    config: dict,
    last_run: dict,
    alert_state: dict,
    alert_policy: dict,
    trade_guard: dict,
) -> dict:
    errors: list[str] = []
    warnings: list[str] = []

    if not bool(runtime.get("active", False)):
        errors.append("daemon 未运行")
    if not bool(config.get("enabled", False)):
        errors.append("OpenClaw 后台调度未启用")
    if not config.get("boards"):
        warnings.append("未配置关注板块")

    last_status = str(last_run.get("status", "") or "")
    if not last_run:
        warnings.append("暂无后台 OpenClaw 执行记录")
    elif last_status == "error":
        errors.append("最近一次后台 OpenClaw 执行失败")
    elif last_status == "warning":
        warnings.append("最近一次后台 OpenClaw 执行为告警状态")

    if not bool(alert_policy.get("enabled", True)):
        warnings.append("后台告警推送策略已关闭")
    consecutive_errors = int(alert_state.get("consecutive_errors", 0) or 0) if isinstance(alert_state, dict) else 0
    if consecutive_errors > 0:
        warnings.append(f"后台 OpenClaw 已连续失败 {consecutive_errors} 次")

    cfg = trade_guard.get("config", {}) or {}
    simulation = trade_guard.get("simulation", {}) or {}
    replay = trade_guard.get("replay", {}) or {}
    if not bool(cfg.get("enabled", True)):
        errors.append("无人值守交易安全闸已关闭")
    if bool(cfg.get("unattended_buy_enabled", False)):
        if bool(cfg.get("require_simulation_pass", True)) and not bool(simulation.get("passed", False)):
            errors.append("无人值守买入已开启但仿真门禁未通过")
        if not replay.get("last"):
            warnings.append("无人值守买入已开启但暂无安全闸回放记录")
    elif not bool(cfg.get("allow_sell_when_buy_disabled", True)):
        warnings.append("无人值守买入关闭时卖出也被禁止")

    status = "error" if errors else "warning" if warnings else "ready"
    return {
        "status": status,
        "ready": status == "ready",
        "errors": errors,
        "warnings": warnings,
        "summary": "就绪" if status == "ready" else "；".join(errors or warnings),
    }


def get_openclaw_daemon_status() -> dict:
    from desktop.daemon_scheduler import _load_openclaw_daemon_boards, get_daemon_runtime_status
    from desktop.data_access import get_kv_json

    runtime = get_daemon_runtime_status()
    overrides = get_kv_json("sched_time_overrides", {}) or {}
    if isinstance(overrides, str):
        try:
            overrides = json.loads(overrides)
        except Exception:
            overrides = {}
    if not isinstance(overrides, dict):
        overrides = {}
    last_run = get_kv_json("openclaw_last_daemon_run", {}) or {}
    if isinstance(last_run, str):
        try:
            last_run = json.loads(last_run)
        except Exception:
            last_run = {}
    alert_state = get_kv_json("openclaw_daemon_alert_state", {}) or {}
    if isinstance(alert_state, str):
        try:
            alert_state = json.loads(alert_state)
        except Exception:
            alert_state = {}
    history = get_kv_json("openclaw_daemon_run_history", []) or []
    if isinstance(history, str):
        try:
            history = json.loads(history)
        except Exception:
            history = []
    if not isinstance(history, list):
        history = []
    disabled = set(runtime.get("disabled_tasks", []) or [])
    config = {
        "enabled": "openclaw_pipeline" not in disabled,
        "time": str(overrides.get("openclaw_pipeline", "10:25") or "10:25"),
        "boards": _load_openclaw_daemon_boards(),
    }
    alert_policy = get_openclaw_daemon_alert_policy()
    trade_guard = get_unattended_trade_guard()
    readiness = _build_openclaw_daemon_readiness(
        runtime=runtime if isinstance(runtime, dict) else {},
        config=config,
        last_run=last_run if isinstance(last_run, dict) else {},
        alert_state=alert_state if isinstance(alert_state, dict) else {},
        alert_policy=alert_policy,
        trade_guard=trade_guard,
    )
    config_audit = get_openclaw_config_audit(limit=20)
    return {
        "daemon": runtime,
        "openclaw": {
            "config": config,
            "last_run": last_run if isinstance(last_run, dict) else {},
            "alert_state": alert_state if isinstance(alert_state, dict) else {},
            "alert_policy": alert_policy,
            "readiness": readiness,
            "config_audit": config_audit,
            "history": history[:30],
        },
        "trade_guard": trade_guard,
    }


def run_openclaw_pipeline(boards: list[str] | None = None, *, traceparent: str = "") -> dict:
    selected_boards = boards or DEFAULT_OPENCLAW_BOARDS
    span = start_span(
        "openclaw.pipeline",
        trace_id=create_trace_id("openclaw"),
        traceparent=traceparent,
        metadata={"boards": list(selected_boards)},
    )
    if not is_feature_enabled("openclaw_pipeline"):
        finished = finish_span(span, status="disabled")
        return {
            "ok": False,
            "disabled": True,
            "message": "openclaw_pipeline feature is disabled",
            "trace": _trace_payload(finished),
        }
    try:
        result = _run_pipeline_with_gateway_fallback(boards=selected_boards, traceparent=traceparent)
        finished = finish_span(span, status="ok")
        if isinstance(result, dict):
            result.setdefault("trace", _trace_payload(finished))
        return result
    except Exception:
        finish_span(span, status="error")
        raise


def run_openclaw_learning(*, traceparent: str = "") -> dict:
    span = start_span(
        "openclaw.learning",
        trace_id=create_trace_id("openclaw"),
        traceparent=traceparent,
    )
    if not is_feature_enabled("openclaw_learning"):
        finished = finish_span(span, status="disabled")
        return {
            "ok": False,
            "disabled": True,
            "message": "openclaw_learning feature is disabled",
            "trace": _trace_payload(finished),
        }
    try:
        result = _run_learning_with_gateway_fallback(traceparent=traceparent)
        finished = finish_span(span, status="ok")
        if isinstance(result, dict):
            result.setdefault("trace", _trace_payload(finished))
        return result
    except Exception:
        finish_span(span, status="error")
        raise


def _trace_payload(span: dict) -> dict:
    return {
        "trace_id": span.get("trace_id", ""),
        "traceparent": span.get("traceparent", ""),
        "span_id": span.get("span_id", ""),
        "parent_span_id": span.get("parent_span_id", ""),
        "status": span.get("status", ""),
    }


def _run_pipeline_with_gateway_fallback(*, boards: list[str], traceparent: str) -> dict:
    if _gateway_enabled():
        try:
            payload = _call_openclaw_gateway(
                "pipeline",
                {"boards": list(boards)},
                traceparent=traceparent,
            )
            payload.setdefault("gateway", {"used": True, "mode": "remote"})
            return payload
        except Exception as exc:
            result = _run_local_openclaw_pipeline(boards=boards)
            if isinstance(result, dict):
                result.setdefault(
                    "gateway",
                    {"used": False, "mode": "fallback_local", "error": str(exc)},
                )
            return result
    return _run_local_openclaw_pipeline(boards=boards)


def _run_learning_with_gateway_fallback(*, traceparent: str) -> dict:
    if _gateway_enabled():
        try:
            payload = _call_openclaw_gateway("learn", {}, traceparent=traceparent)
            payload.setdefault("gateway", {"used": True, "mode": "remote"})
            return payload
        except Exception as exc:
            result = _run_local_openclaw_learning()
            if isinstance(result, dict):
                result.setdefault(
                    "gateway",
                    {"used": False, "mode": "fallback_local", "error": str(exc)},
                )
            return result
    return _run_local_openclaw_learning()


def _run_local_openclaw_pipeline(*, boards: list[str]) -> dict:
    from desktop.openclaw_engine import run_full_pipeline

    return run_full_pipeline(boards=boards)


def _run_local_openclaw_learning() -> dict:
    from desktop.openclaw_learner import evaluate_and_learn

    return evaluate_and_learn()


def _gateway_enabled() -> bool:
    raw = str(os.environ.get("FINQUANTA_OPENCLAW_GATEWAY_ENABLED", "1")).strip().lower()
    return raw not in {"0", "false", "off", "no"}


def _call_openclaw_gateway(action: str, payload: dict, *, traceparent: str = "") -> dict:
    base_url = str(os.environ.get("FINQUANTA_OPENCLAW_GATEWAY_BASE", "http://127.0.0.1:18789")).strip()
    if not base_url:
        raise RuntimeError("FINQUANTA_OPENCLAW_GATEWAY_BASE is empty")
    timeout = _safe_float(os.environ.get("FINQUANTA_OPENCLAW_GATEWAY_TIMEOUT_SECONDS"), 8.0)
    token = str(os.environ.get("FINQUANTA_OPENCLAW_GATEWAY_TOKEN", "")).strip()
    headers = {"Content-Type": "application/json"}
    if traceparent:
        headers["traceparent"] = traceparent
    if token:
        headers["X-OpenClaw-Token"] = token
        headers["Authorization"] = f"Bearer {token}"
    body = dict(payload or {})
    if traceparent and "traceparent" not in body:
        body["traceparent"] = traceparent
    last_error = None
    for path in _gateway_paths(action):
        endpoint = _join_url(base_url, path)
        try:
            data = _http_post_json(endpoint, body, headers=headers, timeout=timeout)
            if isinstance(data, dict):
                data.setdefault("gateway", {"used": True, "endpoint": endpoint, "mode": "remote"})
                return data
            return {"ok": True, "data": data, "gateway": {"used": True, "endpoint": endpoint, "mode": "remote"}}
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"openclaw gateway call failed: {last_error}")


def _gateway_paths(action: str) -> list[str]:
    key = (
        "FINQUANTA_OPENCLAW_GATEWAY_PIPELINE_PATHS"
        if action == "pipeline"
        else "FINQUANTA_OPENCLAW_GATEWAY_LEARN_PATHS"
    )
    default = (
        "/pipeline/run,/openclaw/pipeline/run,/api/openclaw/pipeline/run"
        if action == "pipeline"
        else "/learn/run,/openclaw/learn/run,/api/openclaw/learn/run"
    )
    raw = str(os.environ.get(key, default)).strip()
    parts = [item.strip() for item in raw.split(",") if item.strip()]
    return parts or ["/pipeline/run" if action == "pipeline" else "/learn/run"]


def _join_url(base_url: str, path: str) -> str:
    base = base_url.rstrip("/")
    suffix = path if path.startswith("/") else f"/{path}"
    return f"{base}{suffix}"


def _http_post_json(endpoint: str, payload: dict, *, headers: dict[str, str], timeout: float) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(endpoint, method="POST", headers=headers, data=body)
    parsed = urllib.parse.urlparse(endpoint)
    opener = (
        urllib.request.build_opener(urllib.request.ProxyHandler({}))
        if parsed.hostname in {"127.0.0.1", "localhost", "0.0.0.0"}
        else urllib.request.build_opener()
    )
    with opener.open(req, timeout=max(0.5, timeout)) as resp:
        text = resp.read().decode("utf-8", errors="replace").strip()
    if not text:
        return {}
    data = json.loads(text)
    if isinstance(data, dict) and "data" in data and isinstance(data.get("data"), dict):
        return data["data"]
    return data if isinstance(data, dict) else {"raw": data}


def _safe_float(raw: str | None, default: float) -> float:
    try:
        return float(raw) if raw is not None else default
    except Exception:
        return default
