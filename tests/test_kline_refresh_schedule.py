"""K-line refresh: weekday schedule 10:00 / 13:30, protected from disable."""

from __future__ import annotations

import pytest


def test_kline_refresh_enabled_by_default(monkeypatch):
    monkeypatch.delenv("FINQUANTA_KLINE_REFRESH_ENABLED", raising=False)
    from core.config.kline_refresh import get_kline_refresh_settings

    cfg = get_kline_refresh_settings()
    assert cfg.enabled is True
    assert cfg.morning_time == "10:00"
    assert cfg.afternoon_time == "13:30"


def test_filter_protected_disabled_tasks():
    from core.config.kline_refresh import filter_protected_disabled_tasks

    disabled = {"refresh_kline", "scan_stocks", "refresh_kline_am"}
    filtered = filter_protected_disabled_tasks(disabled)
    assert "refresh_kline" not in filtered
    assert "refresh_kline_am" not in filtered
    assert "scan_stocks" in filtered


def test_schedule_has_kline_slots():
    from desktop.daemon_scheduler import SCHEDULE

    keys = [t["key"] for t in SCHEDULE if str(t.get("func")) == "_task_refresh_kline"]
    assert "refresh_kline_am" in keys
    assert "refresh_kline_pm" in keys


def test_daemon_strips_protected_on_init(monkeypatch):
    monkeypatch.setattr(
        "desktop.daemon_scheduler._load_openclaw_daemon_boards",
        lambda *a, **k: ["人工智能"],
    )
    monkeypatch.setattr("desktop.daemon_scheduler.get_kv_json", lambda *a, **k: None)
    from desktop.daemon_scheduler import DaemonScheduler

    daemon = DaemonScheduler(disabled_tasks={"refresh_kline", "refresh_kline_pm", "ai_decision"})
    assert "refresh_kline" not in daemon.disabled_tasks
    assert "refresh_kline_pm" not in daemon.disabled_tasks
    assert "ai_decision" in daemon.disabled_tasks


def test_collect_kline_refresh_codes(monkeypatch):
    class FakeRepo:
        def fetchall(self, sql, params=()):
            if "ai_positions" in sql:
                return [("600000",)]
            if "board_stocks" in sql:
                return [("600000",), ("000001",)]
            return []

    monkeypatch.setattr(
        "desktop.data_access.get_kv_json",
        lambda *a, **k: {"positions": [{"code": "300750"}]},
    )
    from desktop.data_sync import collect_kline_refresh_codes

    codes = collect_kline_refresh_codes(FakeRepo())
    assert codes[0] == "600000"
    assert "300750" in codes
    assert "000001" in codes
