"""
Application-level operations service.

This module centralizes read-oriented operational views first so the API layer
does not depend directly on desktop orchestration modules.
"""

from __future__ import annotations

from core.application.snapshot_service import get_system_snapshot


def get_recent_task_runs(limit: int = 50) -> list[dict]:
    from desktop.task_orchestrator import get_recent_task_runs as _get_recent_task_runs

    return _get_recent_task_runs(limit)


def get_recent_system_events(limit: int = 50) -> list[dict]:
    from desktop.task_orchestrator import (
        get_recent_system_events as _get_recent_system_events,
    )

    return _get_recent_system_events(limit)


def log_system_event(
    source: str,
    category: str,
    title: str,
    detail: str = "",
    level: str = "info",
) -> None:
    from desktop.task_orchestrator import log_system_event as _log_system_event

    _log_system_event(source, category, title, detail=detail, level=level)


def run_task(task_name: str, trigger_source: str, func, *args, **kwargs):
    from desktop.task_orchestrator import run_task as _run_task

    return _run_task(task_name, trigger_source, func, *args, **kwargs)


def get_operation_log(limit: int = 50) -> list[dict]:
    from desktop.portfolio_tracker import get_operation_log as _get_operation_log

    return _get_operation_log(limit)


def get_ops_center_payload(limit: int = 20, refresh_snapshot: bool = False) -> dict:
    return {
        "snapshot": get_system_snapshot(refresh=refresh_snapshot),
        "tasks": get_recent_task_runs(limit),
        "events": get_recent_system_events(limit),
        "operations": get_operation_log(limit),
    }


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
