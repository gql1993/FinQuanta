"""Evaluate per-strategy buy/exit signals (same rules as backtester)."""

from __future__ import annotations

import logging

import pandas as pd

from desktop.data_access import get_repo
from strategy_profiles import (
    STRATEGY_PROFILES,
    apply_backtest_profile,
    get_strategy_default_params,
)

_log = logging.getLogger("arena.strategy_signals")

_MIN_BARS = 50


def strategy_id_from_mode(mode: str) -> str | None:
    if not mode.startswith("arena_"):
        return None
    sid = mode[len("arena_") :]
    return sid if sid in STRATEGY_PROFILES else None


def _load_fundamental(code: str, repo) -> dict | None:
    from desktop.arena.strategy_context import build_strategy_context

    data = build_strategy_context(code, repo)
    return data or None


def load_kline_dataframe(code: str, repo=None, limit: int = 260) -> pd.DataFrame | None:
    repo = repo or get_repo()
    rows = repo.fetchall(
        "SELECT date, open, high, low, close, volume FROM daily_kline "
        "WHERE code=? ORDER BY date DESC LIMIT ?",
        (code, limit),
    )
    if len(rows) < _MIN_BARS:
        return None
    rows = rows[::-1]
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["close"])
    return df if len(df) >= _MIN_BARS else None


def ohlcv_dataframe(closes, highs, lows, vols) -> pd.DataFrame:
    """Build OHLCV frame from arrays (used during arena scan loop)."""
    n = len(closes)
    return pd.DataFrame(
        {
            "date": pd.RangeIndex(n),
            "open": closes,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": vols,
        }
    )


def _enrich_dataframe(code: str, df: pd.DataFrame) -> pd.DataFrame:
    from desktop.arena.sepa_rules import enrich_sepa_dataframe

    return enrich_sepa_dataframe(code, df)


def evaluate_strategy_signals(
    code: str,
    strategy_id: str,
    *,
    df: pd.DataFrame | None = None,
    fundamental: dict | None = None,
    params: dict | None = None,
    entry_date: str | None = None,
    entry_price: float = 0,
    stop_loss: float = 0,
    shares: int = 0,
    partial_sold: bool = False,
    highest_since_entry: float = 0,
) -> dict:
    """Return latest-bar buy/exit flags for one code under one strategy profile."""
    sid = strategy_id if strategy_id in STRATEGY_PROFILES else "sepa"
    p = params or get_strategy_default_params(sid)
    repo = get_repo()
    if df is None:
        df = load_kline_dataframe(code, repo)
    if df is None or df.empty:
        return {
            "code": code,
            "strategy_id": sid,
            "buy_signal": False,
            "strategy_exit_signal": False,
            "strategy_entry_reason": "",
            "strategy_exit_reason": "",
            "error": "insufficient_kline",
        }

    # SEPA：完整 Minervini 规则（《股票魔法师》）
    if sid == "sepa":
        from desktop.arena.sepa_rules import check_sepa_position_exit, evaluate_sepa_buy
        from desktop.arena.market_regime import assess_market_regime

        if entry_price and entry_price > 0:
            exit = check_sepa_position_exit(
                code=code,
                entry_date=str(entry_date or "")[:10],
                entry_price=float(entry_price),
                stop_loss=float(stop_loss or 0),
                shares=int(shares or 0),
                partial_sold=partial_sold,
                highest_since_entry=float(highest_since_entry or entry_price),
                repo=repo,
            )
            if exit:
                return {
                    "code": code,
                    "strategy_id": sid,
                    "buy_signal": False,
                    "strategy_exit_signal": True,
                    "strategy_entry_reason": "",
                    "strategy_exit_reason": str(exit.get("reason", "SEPA退出")),
                    "exit_action": exit.get("action", "sell_all"),
                    "exit_shares_pct": exit.get("shares_pct", 100),
                    "rs_rating": 0.0,
                }
            return {
                "code": code,
                "strategy_id": sid,
                "buy_signal": False,
                "strategy_exit_signal": False,
                "strategy_entry_reason": "",
                "strategy_exit_reason": "",
                "rs_rating": 0.0,
            }

        market_regime = assess_market_regime(repo)
        return evaluate_sepa_buy(code, df, p, market_regime=market_regime)

    try:
        enriched = _enrich_dataframe(code, df)
        if fundamental is None:
            fundamental = _load_fundamental(code, repo)
        profiled = apply_backtest_profile(
            enriched,
            sid,
            fundamental,
            p,
        )
        latest = profiled.iloc[-1]
        exit_signal = bool(latest.get("strategy_exit_signal", False))
        exit_reason = str(latest.get("strategy_exit_reason") or "")

        if entry_price and entry_price > 0:
            latest_close = float(latest.get("close", 0) or 0)
            if sid == "canslim":
                stop_pct = float(p.get("stop_loss_pct", 7.5))
                if latest_close > 0 and latest_close <= float(entry_price) * (1 - stop_pct / 100):
                    exit_signal = True
                    exit_reason = f"CANSLIM 退出: 亏损超过{stop_pct:.1f}%"
            elif sid == "turtle" and not exit_signal:
                atr_window = int(p.get("atr_window", 20))
                atr_mult = float(p.get("atr_stop_multiple", 2.0))
                if len(df) >= atr_window + 1:
                    high = df["high"]
                    low = df["low"]
                    close = df["close"]
                    tr = pd.concat(
                        [
                            high - low,
                            (high - close.shift(1)).abs(),
                            (low - close.shift(1)).abs(),
                        ],
                        axis=1,
                    ).max(axis=1)
                    atr = float(tr.rolling(atr_window).mean().iloc[-1] or 0)
                    if atr > 0 and latest_close <= float(entry_price) - atr * atr_mult:
                        exit_signal = True
                        exit_reason = f"海龟退出: 跌破{atr_mult:.1f}ATR防守线"
            elif sid == "livermore":
                stop_pct = float(p.get("stop_loss_pct", 10.0))
                if latest_close > 0 and latest_close <= float(entry_price) * (1 - stop_pct / 100):
                    exit_signal = True
                    exit_reason = f"利弗莫尔退出: 关键点止损超过{stop_pct:.1f}%"

        if sid in ("event", "larry") and entry_date and not exit_signal:
            from datetime import date

            try:
                hold_days = (date.today() - date.fromisoformat(str(entry_date)[:10])).days
                hold_max = int(p.get("hold_days_max", p.get("max_hold_days", 10)))
                if hold_days > hold_max:
                    exit_signal = True
                    label = "事件" if sid == "event" else "拉里"
                    exit_reason = f"{label}退出: 持有超{hold_max}天"
            except Exception:
                pass

        return {
            "code": code,
            "strategy_id": sid,
            "buy_signal": bool(latest.get("buy_signal", False)),
            "strategy_exit_signal": exit_signal,
            "strategy_entry_reason": str(latest.get("strategy_entry_reason", "") or ""),
            "strategy_exit_reason": exit_reason,
            "rs_rating": float(latest.get("rs_rating", 0) or 0),
        }
    except Exception as exc:
        _log.debug("evaluate_strategy_signals %s %s: %s", sid, code, exc)
        return {
            "code": code,
            "strategy_id": sid,
            "buy_signal": False,
            "strategy_exit_signal": False,
            "strategy_entry_reason": "",
            "strategy_exit_reason": "",
            "error": str(exc),
        }
