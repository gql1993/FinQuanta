"""Professionalized non-SEPA strategy profile rules."""

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


def _profile_df(close: np.ndarray, volume: np.ndarray | None = None) -> pd.DataFrame:
    volume = volume if volume is not None else np.full(len(close), 1_000_000.0)
    df = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=len(close), freq="B").astype(str),
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": volume,
        }
    )
    df["ma50"] = df["close"].rolling(50).mean()
    df["ma150"] = df["close"].rolling(150).mean()
    df["ma200"] = df["close"].rolling(200).mean()
    df["vol_ma50"] = df["volume"].rolling(50).mean()
    df["week52_high"] = df["high"].rolling(250, min_periods=1).max()
    df["week52_low"] = df["low"].rolling(250, min_periods=1).min()
    df["rs_rating"] = 90
    df["trend_pass"] = True
    df["buy_signal"] = True
    return df


def test_canslim_requires_stage2_and_breakout_volume():
    close = np.linspace(10, 40, 260)
    close[-1] = close[-2] * 1.04
    volume = np.full(260, 1_000_000.0)
    volume[-1] = 2_000_000.0
    df = _profile_df(close, volume)

    from strategy_profiles import apply_backtest_profile

    out = apply_backtest_profile(df, "canslim")
    assert bool(out.iloc[-1]["buy_signal"]) is True
    assert "Stage2" in out.iloc[-1]["strategy_entry_reason"]

    weak = df.copy()
    weak.loc[weak.index[-1], "volume"] = 500_000.0
    weak_out = apply_backtest_profile(weak, "canslim")
    assert bool(weak_out.iloc[-1]["buy_signal"]) is False


def test_turtle_accepts_20_day_breakout_without_55_day_breakout():
    close = np.linspace(20, 30, 120)
    close[65] = 45.0
    close[-21:-1] = np.linspace(27, 29, 20)
    close[-1] = 30.5
    df = _profile_df(close)

    from strategy_profiles import apply_backtest_profile

    out = apply_backtest_profile(df, "turtle", params={"trend_ma_days": 30})
    assert bool(out.iloc[-1]["buy_signal"]) is True
    assert out.iloc[-1]["turtle_system"] == "S1-20日突破"


def test_graham_requires_margin_of_safety():
    close = np.linspace(10, 18, 260)
    df = _profile_df(close)

    from strategy_profiles import apply_backtest_profile

    cheap = apply_backtest_profile(df, "graham", {"pe_dynamic": 8, "pb": 1.0})
    expensive = apply_backtest_profile(df, "graham", {"pe_dynamic": 19, "pb": 2.4})
    assert bool(cheap.iloc[-1]["buy_signal"]) is True
    assert bool(expensive.iloc[-1]["buy_signal"]) is False


def test_strategy_position_risk_overlays(monkeypatch):
    close = np.linspace(20, 30, 260)
    close[-1] = 18.0
    df = _profile_df(close)

    monkeypatch.setattr("desktop.arena.strategy_signals.get_repo", lambda: object())
    monkeypatch.setattr("desktop.arena.strategy_signals._load_fundamental", lambda code, repo: None)

    from desktop.arena.strategy_signals import evaluate_strategy_signals

    out = evaluate_strategy_signals("600000", "canslim", df=df, entry_price=20.0)
    assert out["strategy_exit_signal"] is True
    assert "亏损超过" in out["strategy_exit_reason"]


def test_livermore_key_pivot_breakout_needs_volume():
    close = np.linspace(10, 30, 260)
    close[-1] = 31.5
    volume = np.full(260, 1_000_000.0)
    volume[-1] = 1_500_000.0
    df = _profile_df(close, volume)

    from strategy_profiles import apply_backtest_profile

    out = apply_backtest_profile(df, "livermore")
    assert bool(out.iloc[-1]["buy_signal"]) is True
    assert "关键点突破" in out.iloc[-1]["strategy_entry_reason"]

    weak_volume = df.copy()
    weak_volume.loc[weak_volume.index[-1], "volume"] = 800_000.0
    weak = apply_backtest_profile(weak_volume, "livermore")
    assert bool(weak.iloc[-1]["buy_signal"]) is False


def test_covell_requires_rising_long_term_trend_and_controlled_atr():
    close = np.linspace(20, 45, 260)
    close[-1] = 46.5
    df = _profile_df(close)

    from strategy_profiles import apply_backtest_profile

    out = apply_backtest_profile(df, "covell")
    assert bool(out.iloc[-1]["buy_signal"]) is True
    assert "波动可控" in out.iloc[-1]["strategy_entry_reason"]

    choppy = df.copy()
    choppy.loc[choppy.index[-20:], "high"] = choppy.loc[choppy.index[-20:], "close"] * 1.25
    choppy.loc[choppy.index[-20:], "low"] = choppy.loc[choppy.index[-20:], "close"] * 0.75
    choppy.loc[choppy.index[-1], "close"] = float(choppy["high"].iloc[-2]) * 1.02
    blocked = apply_backtest_profile(choppy, "covell")
    assert bool(blocked.iloc[-1]["buy_signal"]) is False


def test_dow_requires_higher_highs_and_higher_lows():
    close = np.linspace(10, 35, 260)
    df = _profile_df(close)

    from strategy_profiles import apply_backtest_profile

    out = apply_backtest_profile(df, "dow")
    assert bool(out.iloc[-1]["buy_signal"]) is True
    assert "高低点抬升" in out.iloc[-1]["strategy_entry_reason"]

    broken = df.copy()
    broken.loc[broken.index[-5:], "low"] = 5.0
    blocked = apply_backtest_profile(broken, "dow")
    assert bool(blocked.iloc[-1]["buy_signal"]) is False


def test_larry_buys_contraction_breakout_and_exits_fast(monkeypatch):
    close = np.linspace(20, 30, 80)
    close[-21:-6] = 28.0
    close[-6:-1] = np.linspace(28.8, 29.0, 5)
    close[-1] = 30.8
    volume = np.full(80, 1_000_000.0)
    volume[-1] = 1_700_000.0
    df = _profile_df(close, volume)

    from strategy_profiles import apply_backtest_profile

    out = apply_backtest_profile(df, "larry")
    assert bool(out.iloc[-1]["buy_signal"]) is True
    assert "波动收缩" in out.iloc[-1]["strategy_entry_reason"]

    monkeypatch.setattr("desktop.arena.strategy_signals.get_repo", lambda: object())
    monkeypatch.setattr("desktop.arena.strategy_signals._load_fundamental", lambda code, repo: None)

    from desktop.arena.strategy_signals import evaluate_strategy_signals

    hold_exit = evaluate_strategy_signals("600000", "larry", df=df, entry_date="2020-01-01")
    assert hold_exit["strategy_exit_signal"] is True
    assert "持有超" in hold_exit["strategy_exit_reason"]


def test_event_requires_matching_event_context():
    close = np.linspace(20, 25, 80)
    close[-1] = close[-2] * 1.04
    volume = np.full(80, 1_000_000.0)
    volume[-1] = 2_000_000.0
    df = _profile_df(close, volume)
    df["rs_rating"] = 60

    from strategy_profiles import apply_backtest_profile

    no_event = apply_backtest_profile(df, "event")
    with_event = apply_backtest_profile(
        df,
        "event",
        {"matched_events": [{"date": "2026-06-01", "boards": ["人工智能"]}], "latest_event_days": 1},
    )
    stale_event = apply_backtest_profile(
        df,
        "event",
        {"matched_events": [{"date": "2026-05-01", "boards": ["人工智能"]}], "latest_event_days": 30},
    )
    assert bool(no_event.iloc[-1]["buy_signal"]) is False
    assert bool(with_event.iloc[-1]["buy_signal"]) is True
    assert bool(stale_event.iloc[-1]["buy_signal"]) is False


def test_fund_tracking_requires_position_change_context():
    close = np.linspace(20, 35, 260)
    df = _profile_df(close)
    df["rs_rating"] = 70

    from strategy_profiles import apply_backtest_profile

    no_fund = apply_backtest_profile(df, "fund_tracking")
    increased = apply_backtest_profile(
        df,
        "fund_tracking",
        {"holding_funds": 120, "fund_change_type": "🔺 增持"},
    )
    reduced = apply_backtest_profile(
        df,
        "fund_tracking",
        {"holding_funds": 120, "fund_change_type": "🔻 减持", "fund_is_reducing": True},
    )
    assert bool(no_fund.iloc[-1]["buy_signal"]) is False
    assert bool(increased.iloc[-1]["buy_signal"]) is True
    assert bool(reduced.iloc[-1]["buy_signal"]) is False


def test_private_value_group_uses_quality_or_margin_filters():
    close = np.linspace(20, 32, 260)
    df = _profile_df(close)
    df["rs_rating"] = 70

    from strategy_profiles import apply_backtest_profile

    danbin = apply_backtest_profile(
        df,
        "cn_pm_danbin",
        {"pe_dynamic": 20, "pb": 3},
        params={"heat_min": 20.0},
    )
    qiuguolu_ok = apply_backtest_profile(
        df,
        "cn_inst_qiuguolu",
        {"pe_dynamic": 10, "pb": 1.5},
        params={"heat_min": 20.0},
    )
    qiuguolu_no_margin = apply_backtest_profile(
        df,
        "cn_inst_qiuguolu",
        {"pe_dynamic": 27, "pb": 4.8},
        params={"heat_min": 20.0},
    )
    danbin_weak_sector = apply_backtest_profile(
        df,
        "cn_pm_danbin",
        {"pe_dynamic": 20, "pb": 3, "sector_composite": 20, "sector_is_bottom3": True},
        params={"heat_min": 20.0},
    )

    assert bool(danbin.iloc[-1]["buy_signal"]) is True
    assert bool(qiuguolu_ok.iloc[-1]["buy_signal"]) is True
    assert bool(qiuguolu_no_margin.iloc[-1]["buy_signal"]) is False
    assert bool(danbin_weak_sector.iloc[-1]["buy_signal"]) is False
