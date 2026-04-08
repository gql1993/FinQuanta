"""
Task and operations repository.
"""

from __future__ import annotations

from datetime import datetime

from desktop.data_access import (
    append_system_event,
    append_task_run,
    fetch_recent_system_events,
    fetch_recent_task_runs,
    get_repo,
)


class TaskRepository:
    def get_recent_task_runs(self, limit: int = 50) -> list[dict]:
        return fetch_recent_task_runs(limit)

    def get_recent_system_events(self, limit: int = 50) -> list[dict]:
        return fetch_recent_system_events(limit)

    def log_system_event(
        self,
        source: str,
        category: str,
        title: str,
        detail: str = "",
        level: str = "info",
    ) -> None:
        append_system_event(source, category, title, detail=detail, level=level)

    def log_task_run(
        self,
        task_name: str,
        trigger_source: str,
        status: str,
        elapsed_ms: float,
        summary: str = "",
        detail: str = "",
    ) -> None:
        append_task_run(
            task_name,
            trigger_source,
            status,
            elapsed_ms,
            summary=summary,
            detail=detail,
        )

    def get_operation_log(self, limit: int = 50) -> list[dict]:
        repo = get_repo()
        try:
            rows = repo.fetchall(
                "SELECT timestamp, module, action, detail FROM operation_log ORDER BY id DESC LIMIT ?",
                (limit,),
            )
        except Exception:
            return []
        return [
            {"time": row[0], "module": row[1], "action": row[2], "detail": row[3]}
            for row in rows
        ]

    def log_operation(self, module: str, action: str, detail: str) -> None:
        repo = get_repo()
        try:
            repo.execute(
                "INSERT INTO operation_log (timestamp, module, action, detail) VALUES (?,?,?,?)",
                (datetime.now().isoformat(), module, action, detail),
            )
        except Exception:
            pass
