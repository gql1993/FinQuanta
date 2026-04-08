"""
Application-level task triggering service.
"""

from __future__ import annotations

from core.application.openclaw_service import (
    DEFAULT_OPENCLAW_BOARDS,
    run_openclaw_pipeline,
)


def run_scan_task() -> dict | None:
    from desktop.daemon_scheduler import DaemonScheduler

    scheduler = DaemonScheduler()
    return scheduler._task_scan_stocks()


def trigger_named_task(task_key: str, boards: list[str] | None = None):
    from desktop.daemon_scheduler import DaemonScheduler

    scheduler = DaemonScheduler()
    mapping = {
        "scan": scheduler._task_scan_stocks,
        "learn": scheduler._task_auto_learn,
        "pipeline": lambda: run_openclaw_pipeline(
            boards=boards or DEFAULT_OPENCLAW_BOARDS
        ),
        "risk": scheduler._task_risk_calc,
        "backtest": scheduler._task_auto_backtest,
        "watchlist": scheduler._task_watchlist_scan,
        "short_term": scheduler._task_short_term,
    }
    task = mapping.get(task_key)
    if not task:
        raise KeyError(task_key)
    return task()
