"""Arena trades follow strategy buy/exit signals, not forced daily execution."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

_ARENA_PKG = "desktop.arena"


@pytest.fixture(autouse=True)
def _stub_arena_package():
    """Avoid desktop.arena.__init__ heavy imports during unit tests."""
    import desktop

    if _ARENA_PKG not in sys.modules:
        pkg = types.ModuleType(_ARENA_PKG)
        pkg.__path__ = [str(Path(__file__).resolve().parents[1] / "desktop" / "arena")]
        sys.modules[_ARENA_PKG] = pkg
        desktop.arena = pkg
    yield


def test_strategy_id_from_mode():
    from desktop.arena.strategy_signals import strategy_id_from_mode

    assert strategy_id_from_mode("arena_sepa") == "sepa"
    assert strategy_id_from_mode("full_auto") is None


def test_check_strategy_exit_for_arena_mode(monkeypatch):
    monkeypatch.setattr(
        "desktop.arena.strategy_signals.evaluate_strategy_signals",
        lambda code, sid, **k: {
            "strategy_exit_signal": True,
            "strategy_exit_reason": "CANSLIM 退出: 跌破MA50",
        },
    )
    from desktop.auto_sell import _check_strategy_exit_signal

    out = _check_strategy_exit_signal("arena_canslim", "600000")
    assert out is not None
    assert out["rule"] == "canslim退出"
    assert "MA50" in out["reason"]


def test_arena_mode_skips_generic_stop_loss(monkeypatch):
    """Arena positions must not trigger unified stop-loss rules."""
    fake_ai = types.ModuleType("desktop.ai_portfolio")
    fake_ai.get_state = lambda mode: {
        "positions": [{
            "code": "600000",
            "name": "测试",
            "entry_price": 10.0,
            "stop_loss": 9.5,
            "shares": 100,
            "entry_date": "2020-01-01",
        }]
    }
    sys.modules["desktop.ai_portfolio"] = fake_ai

    monkeypatch.setattr(
        "desktop.auto_sell._check_strategy_exit_signal",
        lambda mode, code, **kwargs: None,
    )
    monkeypatch.setattr(
        "desktop.auto_sell._get_price",
        lambda code, repo: 8.0,
    )
    monkeypatch.setattr(
        "desktop.auto_sell._get_prev_close",
        lambda code, repo: 8.5,
    )

    from desktop.auto_sell import check_sell_signals

    assert check_sell_signals("arena_sepa") == []


def test_legacy_mode_still_uses_stop_loss(monkeypatch):
    fake_ai = types.ModuleType("desktop.ai_portfolio")
    fake_ai.get_state = lambda mode: {
        "positions": [{
            "code": "600000",
            "name": "测试",
            "entry_price": 10.0,
            "stop_loss": 9.5,
            "shares": 100,
            "entry_date": "2020-01-01",
        }]
    }
    sys.modules["desktop.ai_portfolio"] = fake_ai

    monkeypatch.setattr(
        "desktop.auto_sell._get_price",
        lambda code, repo: 8.0,
    )
    monkeypatch.setattr(
        "desktop.auto_sell._get_prev_close",
        lambda code, repo: 8.5,
    )
    monkeypatch.setattr(
        "desktop.auto_sell._calc_atr",
        lambda *a, **k: 0.0,
    )

    from desktop.auto_sell import check_sell_signals

    signals = check_sell_signals("full_auto")
    assert signals and signals[0]["rule"] == "止损触发"


def test_scan_skips_without_buy_signal(monkeypatch):
    import numpy as np

    closes = np.full(60, 12.0)
    highs = closes * 1.01
    lows = closes * 0.99
    vols = np.full(60, 1_000_000.0)
    monkeypatch.setattr(
        "desktop.arena.strategy_runner.get_repo",
        lambda: type(
            "R",
            (),
            {
                "fetchall": lambda self, sql, params=(): (
                    [("600000",)]
                    if "GROUP BY code" in sql
                    else list(zip(closes, highs, lows, vols))
                    if "daily_kline" in sql
                    else [("600000", "测试")]
                    if "stock_list" in sql
                    else []
                )
            },
        )(),
    )
    monkeypatch.setattr(
        "desktop.strategy_engine.build_context",
        lambda code, c, h, l, v: type(
            "C",
            (),
            {
                "price": 12.0,
                "n": 60,
                "rs": 80,
                "vcp": True,
                "breakout": True,
                "vol_ratio": 1.0,
                "contraction": 0.5,
                "dist_high": -5.0,
                "h52": 13.0,
                "closes": c,
                "highs": h,
                "lows": l,
                "vols": v,
            },
        )(),
    )
    monkeypatch.setattr(
        "desktop.arena.strategy_runner.apply_screening_profile",
        lambda base, df, sid, fin, params: {**base, "评分": 88},
    )
    monkeypatch.setattr(
        "desktop.arena.strategy_runner.evaluate_strategy_signals",
        lambda code, sid, **k: {"buy_signal": False, "strategy_entry_reason": ""},
    )
    monkeypatch.setattr(
        "desktop.arena.market_regime.assess_market_regime",
        lambda *a, **k: {"sepa_market_ok": True, "reason": "分布日0/5；大盘Stage2", "block_reason": ""},
    )
    monkeypatch.setattr(
        "desktop.arena.sepa_rules.evaluate_sepa_buy",
        lambda code, df, params=None, **k: {"buy_signal": False, "strategy_entry_reason": ""},
    )

    from desktop.arena.strategy_runner import scan_with_strategy

    assert scan_with_strategy("sepa", limit=5) == []


def test_buy_strategy_top_skips_without_signal(monkeypatch):
    fake_ai = types.ModuleType("desktop.ai_portfolio")
    fake_ai.get_state = lambda mode: {"positions": [], "cash": 1_000_000}
    fake_ai.buy = lambda *a, **k: "buy called"
    fake_ai.sell = lambda *a, **k: "sell called"
    fake_ai.get_log = lambda *a, **k: []
    sys.modules["desktop.ai_portfolio"] = fake_ai

    monkeypatch.setattr(
        "desktop.arena.strategy_runner.evaluate_strategy_signals",
        lambda code, sid, **k: {"buy_signal": False},
    )

    from desktop.arena.strategy_runner import buy_strategy_top

    logs = buy_strategy_top(
        "arena_sepa",
        [{"代码": "600000", "名称": "测试", "价格": "10.00", "评分": "90", "策略": "SEPA"}],
    )
    assert any("入场条件未满足" in x for x in logs)


def test_sepa_buy_uses_risk_based_position_size(monkeypatch):
    captured = {}
    fake_ai = types.ModuleType("desktop.ai_portfolio")
    fake_ai.get_state = lambda mode: {
        "positions": [{"code": f"60000{i}"} for i in range(9)],
        "cash": 1_000_000.0,
        "initial_capital": 1_000_000.0,
    }

    def fake_buy(mode, code, name, price, shares, stop_loss, reason=""):
        captured.update(
            {
                "mode": mode,
                "code": code,
                "price": price,
                "shares": shares,
                "stop_loss": stop_loss,
                "reason": reason,
            }
        )
        return "ok"

    fake_ai.buy = fake_buy
    sys.modules["desktop.ai_portfolio"] = fake_ai

    monkeypatch.setattr(
        "desktop.arena.strategy_runner.evaluate_strategy_signals",
        lambda code, sid, **k: {"buy_signal": True},
    )
    monkeypatch.setattr("desktop.ai_trader._get_real_price", lambda code: 0)

    from desktop.arena.strategy_runner import buy_strategy_top

    logs = buy_strategy_top(
        "arena_sepa",
        [{"代码": "600100", "名称": "测试", "价格": "100.00", "评分": "95", "策略": "SEPA"}],
    )

    assert logs == ["ok"]
    assert captured["shares"] == 1200
    assert captured["stop_loss"] == 92.0
    assert "风险定仓" in captured["reason"]


def test_non_sepa_arena_buy_uses_risk_based_position_size(monkeypatch):
    captured = {}
    fake_ai = types.ModuleType("desktop.ai_portfolio")
    fake_ai.get_state = lambda mode: {
        "positions": [{"code": f"60000{i}"} for i in range(9)],
        "cash": 1_000_000.0,
        "initial_capital": 1_000_000.0,
    }

    def fake_buy(mode, code, name, price, shares, stop_loss, reason=""):
        captured.update(
            {
                "mode": mode,
                "code": code,
                "price": price,
                "shares": shares,
                "stop_loss": stop_loss,
                "reason": reason,
            }
        )
        return "ok"

    fake_ai.buy = fake_buy
    sys.modules["desktop.ai_portfolio"] = fake_ai

    monkeypatch.setattr(
        "desktop.arena.strategy_runner.evaluate_strategy_signals",
        lambda code, sid, **k: {"buy_signal": True},
    )
    monkeypatch.setattr("desktop.ai_trader._get_real_price", lambda code: 0)
    monkeypatch.setattr("desktop.ai_trader._calc_atr_stop", lambda code, price: 90.0)

    from desktop.arena.strategy_runner import buy_strategy_top

    logs = buy_strategy_top(
        "arena_turtle",
        [{"代码": "600101", "名称": "海龟", "价格": "100.00", "评分": "90", "策略": "海龟"}],
    )

    assert logs == ["ok"]
    assert captured["shares"] == 1000
    assert captured["stop_loss"] == 90.0
    assert "风险定仓" in captured["reason"]
