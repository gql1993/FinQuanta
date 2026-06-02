"""Scan consumer config + daemon schedule contract tests."""

from __future__ import annotations

from datetime import date

import pytest


@pytest.fixture
def kv_memory(monkeypatch):
    store: dict = {}

    def get_k(key, default=None):
        return store.get(key, default)

    def set_k(key, value):
        store[key] = value

    monkeypatch.setattr("desktop.data_access.get_kv_json", get_k)
    monkeypatch.setattr("desktop.data_access.set_kv_json", set_k)
    monkeypatch.setattr("desktop.scan_store.get_kv_json", get_k)
    monkeypatch.setattr("desktop.scan_store.set_kv_json", set_k)
    return store


def test_scan_consumer_source_daemon_filter(kv_memory, monkeypatch):
    from desktop.scan_store import resolve_scan_results, save_scan_results

    monkeypatch.setenv("FINQUANTA_AI_SCAN_SOURCE", "daemon")
    save_scan_results(
        [{"代码": "600519", "评分": "80"}],
        source="ui",
        strategy_id="sepa",
    )

    rows, _, warning = resolve_scan_results()

    assert rows == []
    assert warning and "daemon" in warning


def test_scan_consumer_resonance_filter(kv_memory, monkeypatch):
    from desktop.scan_store import resolve_scan_results, save_scan_results

    monkeypatch.setenv("FINQUANTA_AI_SCAN_SOURCE", "resonance")
    save_scan_results(
        [
            {"代码": "600000", "评分": "70", "命中数": 1},
            {"代码": "600519", "评分": "90", "命中数": 3},
        ],
        source="ui",
        strategy_id="multi",
    )

    rows, _, _ = resolve_scan_results()

    assert len(rows) == 1
    assert rows[0]["代码"] == "600519"


def test_daemon_schedule_scan_before_ai_and_arena():
    from desktop.daemon_scheduler import SCHEDULE

    def _minutes(t: str) -> int:
        h, m = t.split(":")
        return int(h) * 60 + int(m)

    arena_am = _minutes(next(x["time"] for x in SCHEDULE if x["key"] == "arena_cycle_am"))
    scan_t = _minutes(next(x["time"] for x in SCHEDULE if x["key"] == "scan_stocks"))
    ai_am = _minutes(next(x["time"] for x in SCHEDULE if x["key"] == "ai_decision" and "上午" in x["name"]))

    assert arena_am < scan_t < ai_am
    assert not any(x["key"] == "strat_rotate" for x in SCHEDULE)


def test_scheduled_pipeline_scan_survives_arena(kv_memory, monkeypatch):
    """Mock trading-day pipeline: daemon scan -> AI context -> arena snapshot."""
    from core.ai.context_builder import build_scan_context
    from desktop.arena.snapshot import build_shared_snapshot
    from desktop.scan_store import get_scan_results, get_scan_results_meta, save_scan_results

    save_scan_results(
        [{"代码": "601318", "名称": "中国平安", "评分": "82", "建议买入": "建议买入"}],
        source="daemon",
        strategy_id="sepa",
    )
    meta_before = dict(get_scan_results_meta())

    monkeypatch.setattr(
        "desktop.arena.snapshot.build_strategy_scans",
        lambda limit=40: {"sepa": [{"代码": "000001", "评分": "99"}]},
    )
    monkeypatch.setattr("desktop.arena.snapshot.build_market_context_text", lambda: "")

    snap = build_shared_snapshot(force=True)

    ctx = build_scan_context()
    assert get_scan_results()[0]["代码"] == "601318"
    assert get_scan_results_meta() == meta_before
    assert ctx["meta"]["source"] == "daemon"
    assert snap["date"] == date.today().isoformat()
