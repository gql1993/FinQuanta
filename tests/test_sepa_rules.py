"""Minervini SEPA rules for arena."""

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


def _uptrend_df(n: int = 260) -> pd.DataFrame:
    """Synthetic stage-2 uptrend with late breakout volume."""
    t = np.arange(n, dtype=float)
    close = 10 + t * 0.08 + np.sin(t / 8) * 0.15
    close[-1] = close[-2] * 1.03
    high = close * 1.01
    low = close * 0.99
    vol = np.full(n, 1_000_000.0)
    vol[-1] = 2_500_000.0
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


def test_evaluate_sepa_buy_requires_trend_and_volume(monkeypatch):
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
    monkeypatch.setattr(
        "desktop.arena.market_regime.assess_market_regime",
        lambda *a, **k: {"sepa_market_ok": True, "reason": "分布日0/5；大盘Stage2", "block_reason": ""},
    )

    from desktop.arena.sepa_rules import evaluate_sepa_buy

    result = evaluate_sepa_buy("600000", _uptrend_df())
    assert result["buy_signal"] is True
    assert "SEPA" in result["strategy_entry_reason"]
    assert result["pivot_price"] > 0


def test_evaluate_sepa_buy_blocks_low_liquidity(monkeypatch):
    monkeypatch.setattr(
        "desktop.arena.sepa_rules.VCPDetector.detect",
        lambda self, df: {
            "has_vcp": True,
            "num_contractions": 3,
            "breakout_today": True,
            "volume_contracting": True,
            "pivot_price": 28.5,
        },
    )
    monkeypatch.setattr(
        "desktop.arena.sepa_rules.enrich_sepa_dataframe",
        lambda code, df: df.assign(
            trend_pass=True,
            vcp_signal=True,
            rs_rating=85,
            vol_ma50=100_000,
            volume=250_000,
            tight_closes=False,
        ),
    )

    from desktop.arena.sepa_rules import evaluate_sepa_buy

    result = evaluate_sepa_buy(
        "600000",
        _uptrend_df(),
        market_regime={"sepa_market_ok": True, "reason": "分布日0/5；大盘Stage2"},
    )
    assert result["buy_signal"] is False
    assert any("流动性不足" in x for x in result["missing_conditions"])


def test_evaluate_sepa_buy_blocks_no_vcp_volume_contraction(monkeypatch):
    monkeypatch.setattr(
        "desktop.arena.sepa_rules.VCPDetector.detect",
        lambda self, df: {
            "has_vcp": True,
            "num_contractions": 3,
            "breakout_today": True,
            "volume_contracting": False,
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
        _uptrend_df(),
        market_regime={"sepa_market_ok": True, "reason": "分布日0/5；大盘Stage2"},
    )
    assert result["buy_signal"] is False
    assert "VCP量能未收缩" in result["missing_conditions"]


def test_evaluate_sepa_buy_blocks_extended_from_pivot(monkeypatch):
    df = _uptrend_df()
    df.loc[df.index[-21:-1], "close"] = 20.0
    df.loc[df.index[-21:-1], "high"] = 20.0
    df.loc[df.index[-21:-1], "low"] = 19.6
    df.loc[df.index[-1], "close"] = 24.0
    df.loc[df.index[-1], "high"] = 24.2

    monkeypatch.setattr(
        "desktop.arena.sepa_rules.VCPDetector.detect",
        lambda self, df: {
            "has_vcp": True,
            "num_contractions": 3,
            "breakout_today": True,
            "volume_contracting": True,
            "pivot_price": 20.0,
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
        df,
        market_regime={"sepa_market_ok": True, "reason": "分布日0/5；大盘Stage2"},
    )
    assert result["buy_signal"] is False
    assert result["pivot_extension_pct"] > 5
    assert any("突破过远" in x for x in result["missing_conditions"])


def test_check_sepa_hard_stop(monkeypatch):
    df = _uptrend_df()
    df.iloc[-1, df.columns.get_loc("close")] = 8.0
    df.iloc[-1, df.columns.get_loc("low")] = 7.8

    class FakeRepo:
        def fetchall(self, sql, params=()):
            rows = [
                (str(r.date), r.open, r.high, r.low, r.close, r.volume)
                for r in df.itertuples(index=False)
            ]
            return rows[-260:]

    monkeypatch.setattr("desktop.data_access.get_repo", lambda: FakeRepo())

    from desktop.arena.sepa_rules import check_sepa_position_exit

    out = check_sepa_position_exit(
        code="600000",
        entry_date="2025-01-01",
        entry_price=10.0,
        stop_loss=9.2,
        shares=100,
        repo=FakeRepo(),
    )
    assert out is not None
    assert out["action"] == "sell_all"
    assert "SEPA" in out["rule"] or "Stage" in out["reason"] or "止损" in out["reason"]
