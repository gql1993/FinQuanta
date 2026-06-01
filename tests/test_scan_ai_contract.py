"""P0 contract: scan store + arena must not clobber radar results."""

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


def test_save_scan_results_writes_meta(kv_memory):
    from desktop.scan_store import get_scan_results, get_scan_results_meta, save_scan_results

    rows = [{"代码": "600519", "名称": "贵州茅台", "评分": "88"}]
    save_scan_results(rows, source="daemon", strategy_id="sepa")

    assert get_scan_results() == rows
    meta = get_scan_results_meta()
    assert meta["source"] == "daemon"
    assert meta["strategy_id"] == "sepa"
    assert meta["count"] == 1
    assert meta.get("written_at")


def test_arena_snapshot_does_not_overwrite_last_scan_results(kv_memory, monkeypatch):
    from desktop.arena.snapshot import build_shared_snapshot
    from desktop.scan_store import get_scan_results, get_scan_results_meta, save_scan_results

    save_scan_results(
        [{"代码": "600000", "名称": "浦发银行", "评分": "70"}],
        source="daemon",
        strategy_id="sepa",
    )
    meta_before = dict(get_scan_results_meta())

    monkeypatch.setattr(
        "desktop.arena.snapshot.build_strategy_scans",
        lambda limit=40: {sid: [] for sid in ("sepa", "canslim")},
    )
    monkeypatch.setattr("desktop.arena.snapshot.build_market_context_text", lambda: "market ok")

    snap = build_shared_snapshot(force=True)

    assert get_scan_results()[0]["代码"] == "600000"
    assert get_scan_results_meta() == meta_before
    assert snap["date"] == date.today().isoformat()
    assert "sepa" in snap.get("strategy_scans", {})


def test_build_scan_context_includes_meta(kv_memory):
    from core.ai.context_builder import build_scan_context
    from desktop.scan_store import save_scan_results

    save_scan_results(
        [{"代码": "601318", "名称": "中国平安", "板块": "保险", "评分": "75", "建议买入": "建议买入"}],
        source="ui",
        strategy_id="canslim",
    )

    ctx = build_scan_context(limit=5)

    assert len(ctx["items"]) == 1
    assert ctx["items"][0]["code"] == "601318"
    assert ctx["meta"]["source"] == "ui"
    assert ctx["meta"]["strategy_id"] == "canslim"


def test_is_trading_day_respects_merged_holidays(monkeypatch):
    import desktop.ai_portfolio as ap

    extra = set(ap._CN_HOLIDAYS_BUILTIN)
    extra.add(date(2099, 6, 1))
    monkeypatch.setattr(ap, "_merged_cn_holidays", lambda: extra)

    assert ap.is_trading_day(date(2099, 6, 1)) is False
    assert ap.is_trading_day(date(2099, 6, 2)) is True
