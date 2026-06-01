"""Trading-day scheduler hooks for Agent Arena."""

from __future__ import annotations

import logging
from datetime import date, datetime

from core.config.scheduler import get_arena_scheduler_settings
from desktop.data_access import get_kv_json, set_kv_json

_log = logging.getLogger("arena.scheduler")


def _should_run_today() -> bool:
    today = date.today()
    try:
        from desktop.ai_portfolio import is_trading_day

        return bool(is_trading_day(today))
    except Exception:
        return today.weekday() < 5


def _get_last_run() -> str:
    try:
        v = get_kv_json("arena_scheduler_last_run")
        if v is None:
            return ""
        if isinstance(v, str):
            return v
        return str(v)
    except Exception:
        return ""


def _set_last_run(ts: str) -> None:
    try:
        set_kv_json("arena_scheduler_last_run", ts)
    except Exception:
        pass


def _maybe_push_summary(result: dict) -> None:
    settings = get_arena_scheduler_settings()
    if not settings.push_summary:
        return
    try:
        from signal_push import push_signal

        text = result.get("leaderboard_text", "")
        if text:
            push_signal(f"🏆 策略竞技场 {date.today().isoformat()}", text)
    except Exception as exc:
        _log.warning("arena push skipped: %s", exc)


def run_arena_scheduled(boards: list[str] | None = None) -> dict:
    """Run one arena cycle (used by daemon / auto scheduler)."""
    from desktop.arena.runner import run_arena_cycle

    boards = boards or ["人工智能"]
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _log.info("arena scheduled run start: %s boards=%s", ts, boards)
    result = run_arena_cycle(boards)
    _set_last_run(ts)
    _maybe_push_summary(result)
    _log.info("arena scheduled run done: %s participants", len(result.get("participants_run", [])))
    return result


def check_and_run_arena(boards: list[str] | None = None) -> dict | None:
    """If enabled and a schedule slot is due on a trading day, run arena once."""
    settings = get_arena_scheduler_settings()
    if not settings.enabled:
        return None
    if not _should_run_today():
        return None

    now = datetime.now()
    current_time = now.strftime("%H:%M")
    last_run = _get_last_run()
    today_str = now.strftime("%Y-%m-%d")

    for schedule_time in settings.times:
        run_key = f"{today_str} {schedule_time}"
        if current_time >= schedule_time and last_run < run_key:
            _log.info("arena scheduler triggered: %s", run_key)
            return run_arena_scheduled(boards=boards)

    return None
