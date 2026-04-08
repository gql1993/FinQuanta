"""
统一任务编排与审计日志

作用：
1. 统一记录系统事件
2. 统一记录定时任务/流水线任务运行结果
3. 为 OpenClaw、daemon、UI 手工触发提供同一套审计轨迹
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable
from desktop.platform_store import (
    append_system_event,
    append_task_run,
    ensure_platform_tables,
    fetch_recent_system_events,
    fetch_recent_task_runs,
)

_log = logging.getLogger("task_orchestrator")


def ensure_tables():
    ensure_platform_tables()


def log_system_event(
    source: str,
    category: str,
    title: str,
    detail: str = "",
    level: str = "info",
):
    ensure_tables()
    try:
        append_system_event(source, category, title, detail=detail, level=level)
    except Exception as e:
        _log.warning("log_system_event failed: %s", e)


def log_task_run(
    task_name: str,
    trigger_source: str,
    status: str,
    elapsed_ms: float,
    summary: str = "",
    detail: str = "",
):
    ensure_tables()
    try:
        append_task_run(task_name, trigger_source, status, elapsed_ms, summary=summary, detail=detail)
    except Exception as e:
        _log.warning("log_task_run failed: %s", e)


@dataclass
class TaskSpec:
    name: str
    source: str
    func: Callable[..., Any]


def run_task(task_name: str, trigger_source: str, func: Callable[..., Any], *args, **kwargs):
    """
    统一包装任务执行，自动记录耗时、状态和异常。
    返回原函数返回值。
    """
    t0 = time.time()
    try:
        result = func(*args, **kwargs)
        elapsed_ms = (time.time() - t0) * 1000
        summary = ""
        if isinstance(result, dict):
            try:
                summary = json.dumps(result, ensure_ascii=False, default=str)[:300]
            except Exception:
                summary = str(result)[:300]
        else:
            summary = str(result)[:300]
        log_task_run(task_name, trigger_source, "success", elapsed_ms, summary=summary)
        return result
    except Exception as e:
        elapsed_ms = (time.time() - t0) * 1000
        msg = str(e)
        log_task_run(task_name, trigger_source, "error", elapsed_ms, summary=msg[:200], detail=msg)
        raise


def get_recent_task_runs(limit: int = 50) -> list[dict[str, Any]]:
    ensure_tables()
    return fetch_recent_task_runs(limit)


def get_recent_system_events(limit: int = 50) -> list[dict[str, Any]]:
    ensure_tables()
    return fetch_recent_system_events(limit)
