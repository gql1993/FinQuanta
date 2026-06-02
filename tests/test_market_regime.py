"""Market environment filter for SEPA arena."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_ARENA_PKG = "desktop.arena"


@pytest.fixture(autouse=True)
def _stub_arena_package():
    import desktop

    if _ARENA_PKG not in sys.modules:
        pkg = types.ModuleType(_ARENA_PKG)
        pkg.__path__ = [str(Path(__file__).resolve().parents[1] / "desktop" / "arena")]
        sys.modules[_ARENA_PKG] = pkg
        desktop.arena = pkg
    yield


def _stage2_index_df(n: int = 300) -> pd.DataFrame:
    t = np.arange(n, dtype=float)
    close = 3000 + t * 5.0 + np.sin(t / 10) * 5
    high = close * 1.002
    low = close * 0.998
    vol = np.full(n, 50_000_000.0)
    return pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=n, freq="B").astype(str),
            "open": close,
            "high": high,
            "low": low,
            "close": close,
            "volume": vol,
        }
    )


def test_assess_market_regime_ok(monkeypatch):
    index_df = _stage2_index_df()

    class FakeRepo:
        def fetchall(self, sql, params=()):
            if "000300" in params or params == ("000300", 280):
                rows = [
                    (str(r.date), r.open, r.high, r.low, r.close, r.volume)
                    for r in index_df.itertuples(index=False)
                ]
                return rows[-280:]
            return []

    monkeypatch.setattr("desktop.arena.market_regime.load_index_dataframe", lambda *a, **k: (index_df, "000300"))

    from desktop.arena.market_regime import assess_market_regime, clear_market_regime_cache

    clear_market_regime_cache()
    result = assess_market_regime(FakeRepo(), use_cache=False)
    assert result["market_ok"] is True
    assert result["index_stage2"] is True
    assert result["sepa_market_ok"] is True


def test_assess_market_regime_blocks_on_distribution_days(monkeypatch):
    index_df = _stage2_index_df()
    monkeypatch.setattr("desktop.arena.market_regime.load_index_dataframe", lambda *a, **k: (index_df, "000300"))
    monkeypatch.setattr(
        "strategy.MarketRegimeFilter.compute_regime",
        lambda self, df: pd.DataFrame(
            {
                "market_ok": [False],
                "dist_count": [6],
            }
        ),
    )

    from desktop.arena.market_regime import assess_market_regime, clear_market_regime_cache

    clear_market_regime_cache()
    result = assess_market_regime(use_cache=False)
    assert result["market_ok"] is False
    assert result["sepa_market_ok"] is False
    assert "分布日" in result["block_reason"]


def test_evaluate_sepa_buy_blocked_by_market(monkeypatch):
    monkeypatch.setattr(
        "desktop.arena.sepa_rules.VCPDetector.detect",
        lambda self, df: {
            "has_vcp": True,
            "num_contractions": 3,
            "breakout_today": True,
            "pivot_price": 28.5,
        },
    )
    monkeypatch.setattr(
        "desktop.arena.sepa_rules.enrich_sepa_dataframe",
        lambda code, df: df.assign(
            trend_pass=True,
            vcp_signal=True,
            rs_rating=85,
            vol_ma50=1_000_000,
            volume=2_500_000,
            tight_closes=False,
        ),
    )

    from desktop.arena.sepa_rules import evaluate_sepa_buy

    result = evaluate_sepa_buy(
        "600000",
        _stage2_index_df(260),
        market_regime={
            "sepa_market_ok": False,
            "market_ok": False,
            "index_stage2": True,
            "block_reason": "分布日6≥5（需3日放量反弹确认）",
            "reason": "分布日6/5",
        },
    )
    assert result["buy_signal"] is False
    assert "分布日" in result["market_block_reason"]


def test_evaluate_sepa_buy_includes_market_in_reason(monkeypatch):
    monkeypatch.setattr(
        "desktop.arena.sepa_rules.VCPDetector.detect",
        lambda self, df: {
            "has_vcp": True,
            "num_contractions": 2,
            "breakout_today": True,
            "pivot_price": 30.0,
        },
    )
    monkeypatch.setattr(
        "desktop.arena.sepa_rules.enrich_sepa_dataframe",
        lambda code, df: df.assign(
            trend_pass=True,
            vcp_signal=True,
            rs_rating=88,
            vol_ma50=1_000_000,
            volume=2_000_000,
            tight_closes=False,
        ),
    )

    from desktop.arena.sepa_rules import evaluate_sepa_buy

    result = evaluate_sepa_buy(
        "600000",
        _stage2_index_df(260),
        market_regime={
            "sepa_market_ok": True,
            "market_ok": True,
            "index_stage2": True,
            "reason": "分布日2/5；大盘Stage2",
            "block_reason": "",
        },
    )
    assert result["buy_signal"] is True
    assert "大盘Stage2" in result["strategy_entry_reason"]
