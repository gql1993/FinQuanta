"""
Alert dispatch executor with delivery receipts.
"""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any

_LOCK = Lock()
_RECEIPTS: list[dict[str, Any]] = []


def dispatch_routed_alerts(
    alerts: list[dict[str, Any]],
    routing_result: dict[str, Any],
    *,
    dry_run: bool = True,
    receipt_limit: int = 1000,
) -> dict[str, Any]:
    alerts_by_code = {str(item.get("code", "")): dict(item) for item in alerts or []}
    decisions = list((routing_result or {}).get("decisions", []) or [])
    receipts: list[dict[str, Any]] = []

    for decision in decisions:
        code = str(decision.get("code", "unknown") or "unknown")
        suppressed = bool(decision.get("suppressed", False))
        channels = [str(x) for x in decision.get("channels", []) or []]
        alert = alerts_by_code.get(code, {})
        title = f"[Alert] {code}"
        content = str(alert.get("message", "") or f"alert {code}")

        if suppressed:
            receipt = _make_receipt(
                code=code,
                channel="(suppressed)",
                status="skipped",
                detail="suppressed by routing policy",
                dry_run=dry_run,
                action=str(decision.get("action", "")),
                severity=str(decision.get("severity", "warning")),
            )
            receipts.append(receipt)
            _append_receipt(receipt, receipt_limit=receipt_limit)
            continue

        if not channels:
            receipt = _make_receipt(
                code=code,
                channel="(none)",
                status="failed",
                detail="no channel selected",
                dry_run=dry_run,
                action=str(decision.get("action", "")),
                severity=str(decision.get("severity", "warning")),
            )
            receipts.append(receipt)
            _append_receipt(receipt, receipt_limit=receipt_limit)
            continue

        for channel in channels:
            ok, detail = _dispatch_single_channel(channel, title, content, dry_run=dry_run)
            receipt = _make_receipt(
                code=code,
                channel=channel,
                status="sent" if ok else "failed",
                detail=detail,
                dry_run=dry_run,
                action=str(decision.get("action", "")),
                severity=str(decision.get("severity", "warning")),
            )
            receipts.append(receipt)
            _append_receipt(receipt, receipt_limit=receipt_limit)

    sent = len([r for r in receipts if r.get("status") == "sent"])
    failed = len([r for r in receipts if r.get("status") == "failed"])
    skipped = len([r for r in receipts if r.get("status") == "skipped"])
    return {
        "dry_run": bool(dry_run),
        "dispatch_count": len(receipts),
        "sent": sent,
        "failed": failed,
        "skipped": skipped,
        "receipts": receipts,
    }


def get_dispatch_receipts(limit: int = 100) -> list[dict[str, Any]]:
    with _LOCK:
        items = list(_RECEIPTS[-max(1, int(limit)):])
    return [dict(item) for item in reversed(items)]


def _dispatch_single_channel(channel: str, title: str, content: str, *, dry_run: bool) -> tuple[bool, str]:
    normalized = str(channel or "").strip().lower()
    if dry_run:
        return True, "dry_run"

    if normalized == "in_app_feed":
        from core.repositories.task_repo import TaskRepository

        repo = TaskRepository()
        repo.log_system_event(
            "alert_dispatcher",
            "notify",
            title,
            detail=content,
            level="warning",
            metadata={"channel": normalized},
        )
        return True, "logged to in_app_feed"

    channel_map = {
        "wechat_personal": "serverchan",
        "wecom_group_bot": "wecom",
        "email": "email",
        "serverchan": "serverchan",
        "wecom": "wecom",
    }
    mapped = channel_map.get(normalized)
    if not mapped:
        return False, f"unsupported channel: {normalized}"

    from signal_push import push_signal

    result = push_signal(title, content, channels=[mapped])
    ok = bool(result.get(mapped, False))
    return ok, f"push_signal[{mapped}]={ok}"


def _append_receipt(receipt: dict[str, Any], *, receipt_limit: int) -> None:
    max_items = max(100, int(receipt_limit))
    with _LOCK:
        _RECEIPTS.append(dict(receipt))
        if len(_RECEIPTS) > max_items:
            del _RECEIPTS[: len(_RECEIPTS) - max_items]


def _make_receipt(
    *,
    code: str,
    channel: str,
    status: str,
    detail: str,
    dry_run: bool,
    action: str,
    severity: str,
) -> dict[str, Any]:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "code": code,
        "channel": channel,
        "status": status,
        "detail": detail,
        "dry_run": bool(dry_run),
        "action": action,
        "severity": severity,
    }
