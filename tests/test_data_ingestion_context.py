"""Data ingestion for richer strategy context."""

from __future__ import annotations

import json
from datetime import date


def test_sync_financial_csv_to_db(tmp_path, monkeypatch):
    csv_path = tmp_path / "financial.csv"
    csv_path.write_text(
        "code,name,pe_dynamic,pb,total_mv,circ_mv\n"
        "600000,浦发银行,6.5,0.55,1000000,800000\n",
        encoding="utf-8",
    )
    calls = {}

    class FakeRepo:
        def executemany(self, sql, rows):
            calls["sql"] = sql
            calls["rows"] = rows

    monkeypatch.setattr("desktop.data_sync.get_repo", lambda: FakeRepo())

    from desktop.data_sync import sync_financial_csv_to_db

    result = sync_financial_csv_to_db(str(csv_path))
    assert result["financial"] == 1
    assert calls["rows"][0][:6] == ("600000", "浦发银行", 6.5, 0.55, 1000000.0, 800000.0)


def test_persist_news_events_and_sentiment(monkeypatch):
    executed = []
    kv = {}

    class FakeConn:
        def execute(self, sql, params=()):
            executed.append((sql, params))
            return self

        def fetchone(self):
            return None

        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr("desktop.event_strategy.RepoCompatConnection", lambda: FakeConn())
    monkeypatch.setattr("desktop.data_access.set_kv_json", lambda key, value: kv.__setitem__(key, value))

    from desktop.event_strategy import persist_news_events_and_sentiment

    result = persist_news_events_and_sentiment(
        [
            {"title": "人工智能政策支持 利好算力", "digest": "AI产业增长", "date": "2026-06-02", "source": "测试"},
            {"title": "公司亏损 风险提示", "digest": "业绩下滑", "date": "2026-06-02", "source": "测试"},
        ]
    )

    assert result["saved_events"] >= 1
    assert kv["news_sentiment_snapshot"]["total"] == 2
    assert kv["news_sentiment_snapshot"]["positive"] >= 1
    assert any("INSERT INTO events" in sql for sql, _ in executed)


def test_load_latest_fund_holdings(monkeypatch):
    saved = {}

    monkeypatch.setattr("desktop.fund_strategy.get_holdings", lambda period: [])
    monkeypatch.setattr(
        "desktop.fund_strategy.fetch_fund_top_holdings",
        lambda period: [
            {"code": "600000", "name": "测试", "holding_funds": 120, "sector": "银行"},
        ],
    )
    monkeypatch.setattr(
        "desktop.fund_strategy.get_builtin_top_holdings",
        lambda period: [
            {"code": "600000", "name": "测试", "holding_funds": 100, "sector": "银行"},
        ],
    )

    def fake_save(period, holdings):
        saved.setdefault(period, []).extend([dict(h) for h in holdings])

    monkeypatch.setattr("desktop.fund_strategy.save_holdings", fake_save)

    from desktop.fund_strategy import load_latest_fund_holdings

    result = load_latest_fund_holdings("2025-Q4")
    assert result["period"] == "2025-Q4"
    assert result["rows"] == 1
    assert saved["2025-Q4"][0]["code"] == "600000"
