"""
平台中台数据访问层

统一经 desktop.data_access 访问 DB，支持 SQLite / PostgreSQL。
"""
from __future__ import annotations

from typing import Any

from desktop import data_access


def ensure_platform_tables():
    data_access.ensure_platform_tables()


def get_kv_json(key: str, default=None):
    return data_access.get_kv_json(key, default=default)


def set_kv_json(key: str, value: Any):
    data_access.set_kv_json(key, value)


def append_system_event(source: str, category: str, title: str, detail: str = "", level: str = "info"):
    data_access.append_system_event(source, category, title, detail=detail, level=level)


def append_task_run(
    task_name: str,
    trigger_source: str,
    status: str,
    elapsed_ms: float,
    summary: str = "",
    detail: str = "",
):
    data_access.append_task_run(
        task_name, trigger_source, status, elapsed_ms, summary=summary, detail=detail
    )


def fetch_recent_task_runs(limit: int = 50) -> list[dict[str, Any]]:
    return data_access.fetch_recent_task_runs(limit)


def fetch_recent_system_events(limit: int = 50) -> list[dict[str, Any]]:
    return data_access.fetch_recent_system_events(limit)
