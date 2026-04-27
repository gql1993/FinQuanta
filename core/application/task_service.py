"""
Application-level task triggering service.
"""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime

from core.application.openclaw_service import (
    DEFAULT_OPENCLAW_BOARDS,
    run_openclaw_learning,
    run_openclaw_pipeline,
)
from core.observability.tracing import create_trace_id, finish_span, inject_trace_context, start_span

_TASK_STATUS_LOCK = threading.Lock()
_TASK_QUEUE_CV = threading.Condition(_TASK_STATUS_LOCK)
_TASK_STATUS: dict[str, dict] = {}
_TASK_HISTORY: list[dict] = []
_RUNNING_TASKS: set[str] = set()
_QUEUED_TASKS: set[str] = set()
_TASK_QUEUE: list[dict] = []
_QUEUE_SEQ = 0
_SUPPORTED_TASK_KEYS = {"scan", "learn", "pipeline", "risk", "backtest", "watchlist", "short_term"}
_TASK_STATE_STORE_KEY = "api_task_state_v1"
_TASK_HISTORY_STORE_KEY = "api_task_history_v1"
_MAX_CONCURRENT_TASKS = max(1, int(os.environ.get("FINQUANTA_TASK_MAX_CONCURRENCY", "2")))
_TASK_TIMEOUT_SECONDS = max(5.0, float(os.environ.get("FINQUANTA_TASK_TIMEOUT_SECONDS", "900")))
_TASK_HISTORY_LIMIT = max(20, int(os.environ.get("FINQUANTA_TASK_HISTORY_LIMIT", "200")))
_MAX_QUEUE_SIZE = max(1, int(os.environ.get("FINQUANTA_TASK_MAX_QUEUE", "100")))
_DEFAULT_MAX_RETRIES = max(0, int(os.environ.get("FINQUANTA_TASK_RETRY_MAX", "2")))
_RETRY_BACKOFF_BASE_SECONDS = max(0.5, float(os.environ.get("FINQUANTA_TASK_RETRY_BACKOFF_BASE", "2")))
_TASK_DEFAULT_PRIORITY = {
    "risk": 90,
    "watchlist": 85,
    "scan": 80,
    "pipeline": 70,
    "short_term": 60,
    "learn": 50,
    "backtest": 40,
}


def _now_ts() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _resolve_repo():
    try:
        from api_server.storage import repo as runtime_repo

        return runtime_repo
    except Exception:
        return None


def _persist_locked() -> None:
    runtime_repo = _resolve_repo()
    if not runtime_repo:
        return
    try:
        runtime_repo.kv_set(_TASK_STATE_STORE_KEY, _TASK_STATUS)
        runtime_repo.kv_set(_TASK_HISTORY_STORE_KEY, _TASK_HISTORY[-_TASK_HISTORY_LIMIT:])
    except Exception:
        # Persistence is best-effort and should not break task execution.
        return


def _load_persisted_state() -> None:
    runtime_repo = _resolve_repo()
    if not runtime_repo:
        return
    try:
        raw_state = runtime_repo.kv_get(_TASK_STATE_STORE_KEY, {})
        raw_history = runtime_repo.kv_get(_TASK_HISTORY_STORE_KEY, [])
    except Exception:
        return
    with _TASK_STATUS_LOCK:
        if isinstance(raw_state, dict):
            for key, value in raw_state.items():
                if not isinstance(value, dict):
                    continue
                normalized = dict(value)
                normalized["task"] = str(key or normalized.get("task", "")).strip().lower()
                normalized["running"] = bool(normalized.get("running", False))
                previous_status = str(normalized.get("status", "")).strip().lower()
                if normalized["running"] or previous_status in {"queued", "running", "retry_wait"}:
                    normalized["running"] = False
                    normalized["status"] = "interrupted"
                    normalized["error"] = "service restarted while task was running"
                    normalized["finished_at"] = _now_ts()
                _TASK_STATUS[normalized["task"]] = normalized
        if isinstance(raw_history, list):
            _TASK_HISTORY.extend(item for item in raw_history if isinstance(item, dict))
            del _TASK_HISTORY[:-_TASK_HISTORY_LIMIT]
        _persist_locked()


def _running_count_locked() -> int:
    return len(_RUNNING_TASKS)


def _queue_count_locked() -> int:
    return len(_TASK_QUEUE)


def get_task_governance_state() -> dict:
    with _TASK_STATUS_LOCK:
        return {
            "max_concurrency": _MAX_CONCURRENT_TASKS,
            "timeout_seconds": _TASK_TIMEOUT_SECONDS,
            "running_count": _running_count_locked(),
            "running_tasks": sorted(_RUNNING_TASKS),
            "max_queue_size": _MAX_QUEUE_SIZE,
            "queued_count": _queue_count_locked(),
            "queued_tasks": [item.get("task", "") for item in sorted(_TASK_QUEUE, key=_queue_sort_key)],
            "default_max_retries": _DEFAULT_MAX_RETRIES,
            "retry_backoff_base_seconds": _RETRY_BACKOFF_BASE_SECONDS,
            "history_size": len(_TASK_HISTORY),
            "history_limit": _TASK_HISTORY_LIMIT,
        }


def get_task_state(task_key: str) -> dict:
    key = str(task_key or "").strip().lower()
    with _TASK_STATUS_LOCK:
        state = _TASK_STATUS.get(key)
        if state:
            return dict(state)
    return {
        "task": key,
        "running": False,
        "status": "idle",
        "queued": False,
        "started_at": "",
        "finished_at": "",
        "error": "",
        "last_result_type": "",
        "timed_out_at": "",
        "queued_at": "",
        "retry_count": 0,
        "max_retries": _DEFAULT_MAX_RETRIES,
        "next_retry_at": "",
        "priority": _TASK_DEFAULT_PRIORITY.get(key, 50),
        "timeout_seconds": _TASK_TIMEOUT_SECONDS,
        "duration_ms": 0,
    }


def list_task_states() -> list[dict]:
    with _TASK_STATUS_LOCK:
        return [dict(value) for _, value in sorted(_TASK_STATUS.items(), key=lambda item: item[0])]


def get_task_history(limit: int = 50, task_key: str = "") -> list[dict]:
    key = str(task_key or "").strip().lower()
    size = max(1, int(limit))
    with _TASK_STATUS_LOCK:
        items = list(_TASK_HISTORY)
    if key:
        items = [item for item in items if str(item.get("task", "")).strip().lower() == key]
    return list(reversed(items[-size:]))


def _append_history_locked(record: dict) -> None:
    _TASK_HISTORY.append(record)
    del _TASK_HISTORY[:-_TASK_HISTORY_LIMIT]


def _record_rejected_attempt(task_key: str, reason: str) -> None:
    key = str(task_key or "").strip().lower()
    with _TASK_STATUS_LOCK:
        _append_history_locked(
            {
                "task": key,
                "status": "rejected",
                "started_at": _now_ts(),
                "finished_at": _now_ts(),
                "duration_ms": 0,
                "error": reason,
                "timed_out_at": "",
                "last_result_type": "",
                "retry_count": 0,
            }
        )
        _persist_locked()


def _queue_sort_key(item: dict) -> tuple:
    # Higher priority first, then earliest available time, then FIFO sequence.
    return (-int(item.get("priority", 50)), float(item.get("not_before_ts", 0.0)), int(item.get("seq", 0)))


def _enqueue_task_locked(task_key: str, *, boards: list[str] | None = None, traceparent: str = "", priority: int | None = None, max_retries: int | None = None) -> dict:
    key = str(task_key or "").strip().lower()
    state = _TASK_STATUS.get(key)
    if state and state.get("running"):
        return {
            "accepted": False,
            "task": key,
            "reason": "already_running",
            "state": dict(state),
        }
    if key in _QUEUED_TASKS:
        fallback_state = dict(state) if state else {
            "task": key,
            "running": False,
            "queued": True,
            "status": "queued",
            "started_at": "",
            "finished_at": "",
            "error": "",
            "last_result_type": "",
            "timed_out_at": "",
            "queued_at": "",
            "retry_count": 0,
            "max_retries": _DEFAULT_MAX_RETRIES,
            "next_retry_at": "",
            "priority": _TASK_DEFAULT_PRIORITY.get(key, 50),
            "timeout_seconds": _TASK_TIMEOUT_SECONDS,
            "duration_ms": 0,
        }
        return {
            "accepted": False,
            "task": key,
            "reason": "already_queued",
            "state": fallback_state,
        }
    if _queue_count_locked() >= _MAX_QUEUE_SIZE:
        fallback_state = dict(state) if state else {
            "task": key,
            "running": False,
            "queued": False,
            "status": "idle",
            "started_at": "",
            "finished_at": "",
            "error": "",
            "last_result_type": "",
            "timed_out_at": "",
            "queued_at": "",
            "retry_count": 0,
            "max_retries": _DEFAULT_MAX_RETRIES,
            "next_retry_at": "",
            "priority": _TASK_DEFAULT_PRIORITY.get(key, 50),
            "timeout_seconds": _TASK_TIMEOUT_SECONDS,
            "duration_ms": 0,
        }
        governance = {
            "max_concurrency": _MAX_CONCURRENT_TASKS,
            "timeout_seconds": _TASK_TIMEOUT_SECONDS,
            "running_count": _running_count_locked(),
            "running_tasks": sorted(_RUNNING_TASKS),
            "max_queue_size": _MAX_QUEUE_SIZE,
            "queued_count": _queue_count_locked(),
            "queued_tasks": [item.get("task", "") for item in sorted(_TASK_QUEUE, key=_queue_sort_key)],
            "default_max_retries": _DEFAULT_MAX_RETRIES,
            "retry_backoff_base_seconds": _RETRY_BACKOFF_BASE_SECONDS,
            "history_size": len(_TASK_HISTORY),
            "history_limit": _TASK_HISTORY_LIMIT,
        }
        return {
            "accepted": False,
            "task": key,
            "reason": "queue_full",
            "state": fallback_state,
            "governance": governance,
        }
    global _QUEUE_SEQ
    _QUEUE_SEQ += 1
    normalized_priority = int(priority if priority is not None else _TASK_DEFAULT_PRIORITY.get(key, 50))
    normalized_retries = max(0, int(max_retries if max_retries is not None else _DEFAULT_MAX_RETRIES))
    queued_at = _now_ts()
    item = {
        "seq": _QUEUE_SEQ,
        "task": key,
        "boards": boards,
        "traceparent": traceparent,
        "priority": normalized_priority,
        "retry_count": 0,
        "max_retries": normalized_retries,
        "queued_at": queued_at,
        "not_before_ts": time.time(),
        "next_retry_at": "",
    }
    _TASK_QUEUE.append(item)
    _TASK_QUEUE.sort(key=_queue_sort_key)
    _QUEUED_TASKS.add(key)
    new_state = {
        "task": key,
        "running": False,
        "queued": True,
        "status": "queued",
        "queued_at": queued_at,
        "started_at": "",
        "finished_at": "",
        "error": "",
        "last_result_type": "",
        "timed_out_at": "",
        "timeout_seconds": _TASK_TIMEOUT_SECONDS,
        "duration_ms": 0,
        "retry_count": 0,
        "max_retries": normalized_retries,
        "next_retry_at": "",
        "priority": normalized_priority,
    }
    _TASK_STATUS[key] = new_state
    _persist_locked()
    _TASK_QUEUE_CV.notify_all()
    return {"accepted": True, "task": key, "state": dict(new_state)}


def _mark_task_timeout(task_key: str, started_at: str) -> None:
    key = str(task_key or "").strip().lower()
    with _TASK_STATUS_LOCK:
        state = _TASK_STATUS.get(key) or {"task": key}
        if not state.get("running"):
            return
        if state.get("started_at") != started_at:
            return
        if state.get("timed_out_at"):
            return
        state["status"] = "timeout"
        state["timed_out_at"] = _now_ts()
        state["error"] = f"task exceeded timeout {_TASK_TIMEOUT_SECONDS:.0f}s"
        _TASK_STATUS[key] = state
        _persist_locked()


def _pop_next_ready_task_locked() -> tuple[dict | None, float]:
    if _running_count_locked() >= _MAX_CONCURRENT_TASKS:
        return None, 1.0
    if not _TASK_QUEUE:
        return None, 0.0
    _TASK_QUEUE.sort(key=_queue_sort_key)
    now_ts = time.time()
    next_wait = 0.0
    for idx, item in enumerate(_TASK_QUEUE):
        wait_seconds = float(item.get("not_before_ts", 0.0)) - now_ts
        if wait_seconds <= 0:
            picked = _TASK_QUEUE.pop(idx)
            return picked, 0.0
        if next_wait <= 0 or wait_seconds < next_wait:
            next_wait = wait_seconds
    return None, max(0.1, next_wait)


def _start_task_execution_locked(item: dict) -> tuple[str, float]:
    task_key = str(item.get("task", "")).strip().lower()
    started_at = _now_ts()
    started_ts = time.time()
    state = _TASK_STATUS.get(task_key) or {"task": task_key}
    state.update(
        {
            "task": task_key,
            "running": True,
            "queued": False,
            "status": "running",
            "started_at": started_at,
            "finished_at": "",
            "error": "",
            "last_result_type": "",
            "timed_out_at": "",
            "timeout_seconds": _TASK_TIMEOUT_SECONDS,
            "duration_ms": 0,
            "retry_count": int(item.get("retry_count", 0)),
            "max_retries": int(item.get("max_retries", _DEFAULT_MAX_RETRIES)),
            "next_retry_at": "",
            "priority": int(item.get("priority", _TASK_DEFAULT_PRIORITY.get(task_key, 50))),
            "queued_at": state.get("queued_at", item.get("queued_at", "")),
        }
    )
    _TASK_STATUS[task_key] = state
    _RUNNING_TASKS.add(task_key)
    _persist_locked()
    return started_at, started_ts


def _timeout_watch(task_key: str, started_at: str):
    time.sleep(_TASK_TIMEOUT_SECONDS)
    _mark_task_timeout(task_key, started_at)


def _enqueue_retry_locked(item: dict, error: str, retry_count: int) -> float:
    task_key = str(item.get("task", "")).strip().lower()
    delay_seconds = _RETRY_BACKOFF_BASE_SECONDS * (2 ** max(0, retry_count - 1))
    next_retry_ts = time.time() + delay_seconds
    retry_item = dict(item)
    retry_item["retry_count"] = retry_count
    retry_item["not_before_ts"] = next_retry_ts
    retry_item["next_retry_at"] = datetime.fromtimestamp(next_retry_ts).isoformat(timespec="seconds")
    _TASK_QUEUE.append(retry_item)
    _TASK_QUEUE.sort(key=_queue_sort_key)

    state = _TASK_STATUS.get(task_key) or {"task": task_key}
    state["running"] = False
    state["queued"] = True
    state["status"] = "retry_wait"
    state["error"] = error
    state["retry_count"] = retry_count
    state["next_retry_at"] = retry_item["next_retry_at"]
    _TASK_STATUS[task_key] = state
    _RUNNING_TASKS.discard(task_key)
    _append_history_locked(
        {
            "task": task_key,
            "status": "retrying",
            "started_at": state.get("started_at", ""),
            "finished_at": _now_ts(),
            "duration_ms": state.get("duration_ms", 0),
            "error": error,
            "timed_out_at": state.get("timed_out_at", ""),
            "last_result_type": "",
            "retry_count": retry_count,
            "next_retry_at": retry_item["next_retry_at"],
        }
    )
    _persist_locked()
    _TASK_QUEUE_CV.notify_all()
    return delay_seconds


def _should_retry_locked(task_key: str, started_at: str) -> bool:
    state = _TASK_STATUS.get(task_key) or {}
    if not state:
        return False
    if state.get("started_at") != started_at:
        return False
    if state.get("timed_out_at"):
        return False
    return True


def _execute_queue_item(item: dict, started_at: str, started_ts: float) -> None:
    task_key = str(item.get("task", "")).strip().lower()
    result = None
    error = ""
    try:
        result = _run_task_once(
            task_key,
            boards=item.get("boards"),
            traceparent=str(item.get("traceparent", "")),
        )
    except Exception as exc:
        error = str(exc)

    if error:
        max_retries = int(item.get("max_retries", _DEFAULT_MAX_RETRIES))
        retry_count = int(item.get("retry_count", 0))
        with _TASK_QUEUE_CV:
            should_retry = retry_count < max_retries and _should_retry_locked(task_key, started_at)
            if should_retry:
                _enqueue_retry_locked(item, error, retry_count + 1)
                return
        _mark_task_finish(task_key, error=error, result=result, started_ts=started_ts)
        return

    _mark_task_finish(task_key, error="", result=result, started_ts=started_ts)


def _task_dispatcher_loop():
    while True:
        with _TASK_QUEUE_CV:
            task_item, wait_timeout = _pop_next_ready_task_locked()
            if not task_item:
                _TASK_QUEUE_CV.wait(timeout=wait_timeout if wait_timeout > 0 else None)
                continue
            task_key = str(task_item.get("task", "")).strip().lower()
            started_at, started_ts = _start_task_execution_locked(task_item)
        worker = threading.Thread(
            target=_execute_queue_item,
            kwargs={"item": task_item, "started_at": started_at, "started_ts": started_ts},
            daemon=True,
            name=f"finquanta-task-{task_key}",
        )
        timeout_watcher = threading.Thread(
            target=_timeout_watch,
            kwargs={"task_key": task_key, "started_at": started_at},
            daemon=True,
            name=f"finquanta-timeout-{task_key}",
        )
        worker.start()
        timeout_watcher.start()


def _mark_task_finish(task_key: str, *, error: str = "", result=None, started_ts: float = 0.0) -> None:
    key = str(task_key or "").strip().lower()
    with _TASK_STATUS_LOCK:
        state = _TASK_STATUS.get(key) or {"task": key}
        state["running"] = False
        state["queued"] = False
        state["finished_at"] = _now_ts()
        state["duration_ms"] = int(max(0.0, (time.time() - started_ts) * 1000)) if started_ts else 0
        if error:
            state["status"] = "error"
            state["error"] = error
        else:
            state["status"] = "timeout" if state.get("timed_out_at") else "success"
            state["error"] = state.get("error", "")
        state["last_result_type"] = type(result).__name__ if result is not None else ""
        _TASK_STATUS[key] = state
        _RUNNING_TASKS.discard(key)
        _QUEUED_TASKS.discard(key)
        _append_history_locked(
            {
                "task": key,
                "status": state.get("status", ""),
                "started_at": state.get("started_at", ""),
                "finished_at": state.get("finished_at", ""),
                "duration_ms": state.get("duration_ms", 0),
                "error": state.get("error", ""),
                "timed_out_at": state.get("timed_out_at", ""),
                "last_result_type": state.get("last_result_type", ""),
                "retry_count": state.get("retry_count", 0),
            }
        )
        _persist_locked()
        _TASK_QUEUE_CV.notify_all()
    try:
        from desktop.task_orchestrator import log_task_run

        log_task_run(
            task_name=key,
            trigger_source="api_async",
            status=state.get("status", ""),
            elapsed_ms=float(state.get("duration_ms", 0)),
            summary=state.get("error", "")[:200] if state.get("error") else state.get("status", ""),
            detail=state.get("error", ""),
        )
    except Exception:
        return


def _run_task_once(task_key: str, *, boards: list[str] | None = None, traceparent: str = ""):
    key = str(task_key or "").strip().lower()
    if key == "scan":
        return run_scan_task(traceparent=traceparent)
    return trigger_named_task(key, boards=boards, traceparent=traceparent)


def start_background_task(
    task_key: str,
    *,
    boards: list[str] | None = None,
    traceparent: str = "",
    priority: int | None = None,
    max_retries: int | None = None,
) -> dict:
    key = str(task_key or "").strip().lower()
    if key not in _SUPPORTED_TASK_KEYS:
        raise KeyError(key)
    rejected_reason = ""
    with _TASK_QUEUE_CV:
        status = _enqueue_task_locked(
            key,
            boards=boards,
            traceparent=traceparent,
            priority=priority,
            max_retries=max_retries,
        )
        if not status.get("accepted"):
            rejected_reason = str(status.get("reason", "rejected"))
    if rejected_reason:
        _record_rejected_attempt(key, rejected_reason)
    return status


def run_scan_task(*, traceparent: str = "") -> dict | None:
    from desktop.daemon_scheduler import DaemonScheduler

    span = start_span(
        "task.scan",
        trace_id=create_trace_id("task"),
        traceparent=traceparent,
    )
    scheduler = DaemonScheduler()
    try:
        result = scheduler._task_scan_stocks()
        _finish_trace_result(result, finish_span(span, status="ok"))
        return result
    except Exception:
        finish_span(span, status="error")
        raise


def trigger_named_task(task_key: str, boards: list[str] | None = None, *, traceparent: str = ""):
    from desktop.daemon_scheduler import DaemonScheduler

    task_key = str(task_key or "").strip().lower()
    scheduler = DaemonScheduler()
    task_span = start_span(
        f"task.trigger.{task_key}",
        trace_id=create_trace_id("task"),
        traceparent=traceparent,
        metadata={"task_key": task_key},
    )
    child_traceparent = inject_trace_context({}, task_span).get("traceparent", "")
    mapping = {
        "scan": ("workflow.scan_pipeline", scheduler._task_scan_stocks),
        "learn": (
            "workflow.openclaw_learning",
            lambda: run_openclaw_learning(traceparent=child_traceparent),
        ),
        "pipeline": (
            "workflow.openclaw_pipeline",
            lambda: run_openclaw_pipeline(
                boards=boards or DEFAULT_OPENCLAW_BOARDS,
                traceparent=child_traceparent,
            ),
        ),
        "risk": ("workflow.risk_calc", scheduler._task_risk_calc),
        "backtest": ("workflow.auto_backtest", scheduler._task_auto_backtest),
        "watchlist": ("workflow.watchlist_scan", scheduler._task_watchlist_scan),
        "short_term": ("workflow.short_term_scan", scheduler._task_short_term),
    }
    flow = mapping.get(task_key)
    if not flow:
        finish_span(task_span, status="invalid_task")
        raise KeyError(task_key)
    workflow_name, task = flow
    workflow_span = start_span(
        workflow_name,
        trace_id=task_span.get("trace_id", ""),
        traceparent=child_traceparent,
        metadata={"task_key": task_key},
    )
    try:
        result = task()
        finished_workflow = finish_span(workflow_span, status="ok")
        finished_task = finish_span(task_span, status="ok")
        _finish_trace_result(result, finished_task, workflow_span=finished_workflow)
        return result
    except Exception:
        finish_span(workflow_span, status="error")
        finish_span(task_span, status="error")
        raise


def _finish_trace_result(result, task_span: dict, *, workflow_span: dict | None = None) -> None:
    if not isinstance(result, dict):
        return
    trace = {
        "trace_id": task_span.get("trace_id", ""),
        "traceparent": task_span.get("traceparent", ""),
        "span_id": task_span.get("span_id", ""),
        "parent_span_id": task_span.get("parent_span_id", ""),
        "status": task_span.get("status", ""),
    }
    if isinstance(workflow_span, dict):
        trace["workflow"] = {
            "name": workflow_span.get("name", ""),
            "traceparent": workflow_span.get("traceparent", ""),
            "span_id": workflow_span.get("span_id", ""),
            "parent_span_id": workflow_span.get("parent_span_id", ""),
            "status": workflow_span.get("status", ""),
        }
    result.setdefault("trace", trace)


_load_persisted_state()
_DISPATCHER_THREAD = threading.Thread(
    target=_task_dispatcher_loop,
    daemon=True,
    name="finquanta-task-dispatcher",
)
_DISPATCHER_THREAD.start()
