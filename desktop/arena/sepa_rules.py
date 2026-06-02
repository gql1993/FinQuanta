"""Minervini SEPA (《股票魔法师》) — professional buy/sell for arena_sepa."""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from config import RiskConfig, StrategyConfig, VCPConfig
from risk_manager import Position, RiskManager
from vcp_detector import VCPDetector

_log = logging.getLogger("arena.sepa_rules")


def enrich_sepa_dataframe(code: str, df: pd.DataFrame) -> pd.DataFrame:
    """Trend template + VCP scan (same pipeline as backtest signal generation)."""
    from strategy import SEPAStrategy

    cfg = StrategyConfig()
    strat = SEPAStrategy(cfg)
    enriched = strat._enrich_with_indicators(df.copy())
    enriched = strat.vcp_detector.scan_signals(enriched)
    from desktop.strategy_engine import build_context

    ctx = build_context(
        code,
        enriched["close"].to_numpy(dtype=float),
        enriched["high"].to_numpy(dtype=float),
        enriched["low"].to_numpy(dtype=float),
        enriched["volume"].to_numpy(dtype=float),
    )
    enriched["rs_rating"] = ctx.rs
    enriched["tight_closes"] = strat._compute_tight_closes_series(enriched)
    enriched["buy_signal"] = enriched["trend_pass"] & enriched["vcp_signal"]
    return enriched


def evaluate_sepa_buy(
    code: str,
    df: pd.DataFrame,
    params: dict | None = None,
    *,
    market_regime: dict | None = None,
) -> dict:
    """
    SEPA entry (Ch 5 trend template + Ch 8 VCP pivot breakout):
    - Market environment (Ch 9): distribution days + index Stage 2
    - Stage-2 trend_pass
    - VCP contraction + pivot breakout + breakout volume
    - RS rating floor
    - Optional tight closes (confirmation)
    """
    from desktop.arena.market_regime import assess_market_regime
    from strategy_profiles import get_strategy_default_params

    p = dict(get_strategy_default_params("sepa"))
    if params:
        p.update(params)
    vcp_cfg = VCPConfig()
    rs_min = int(p.get("rs_min", 70))
    breakout_vol = float(p.get("breakout_volume_ratio", vcp_cfg.breakout_volume_ratio))
    require_tight = bool(p.get("require_tight_closes", False))
    require_market = bool(p.get("require_market_filter", True))
    require_vcp_volume_contracting = bool(p.get("require_vcp_volume_contracting", True))
    max_pivot_extension_pct = float(p.get("max_pivot_extension_pct", 5.0))
    min_avg_volume = float(p.get("min_avg_volume", 400_000) or 0)

    regime = market_regime if market_regime is not None else assess_market_regime()
    market_ok = bool(regime.get("sepa_market_ok", True)) if require_market else True

    enriched = enrich_sepa_dataframe(code, df)
    vcp_detail = VCPDetector(vcp_cfg).detect(df)

    latest = enriched.iloc[-1]
    trend_ok = bool(latest.get("trend_pass", False))
    vcp_ok = bool(latest.get("vcp_signal", False))
    rs_ok = float(latest.get("rs_rating", 0) or 0) >= rs_min
    vol_ma50 = float(latest.get("vol_ma50", 0) or 0)
    vol = float(latest.get("volume", 0) or 0)
    vol_surge = vol_ma50 > 0 and vol >= vol_ma50 * breakout_vol
    liquidity_ok = vol_ma50 >= min_avg_volume if min_avg_volume > 0 else True
    tight_ok = bool(latest.get("tight_closes", False)) if require_tight else True
    prior_window = min(vcp_cfg.contraction_window, max(1, len(df) - 1))
    prior_pivot = 0.0
    if len(df) > 1:
        prior_pivot = float(pd.to_numeric(df["high"].iloc[-(prior_window + 1):-1], errors="coerce").max() or 0)
    pivot_price = prior_pivot if prior_pivot > 0 else float(vcp_detail.get("pivot_price", 0) or 0)
    pivot_break = (pivot_price > 0 and float(latest.get("close", 0) or 0) >= pivot_price) or bool(vcp_detail.get("breakout_today")) or vcp_ok
    pivot_extension_pct = (
        (float(latest.get("close", 0) or 0) / pivot_price - 1.0) * 100
        if pivot_price > 0
        else 0.0
    )
    pivot_extension_ok = pivot_extension_pct <= max_pivot_extension_pct
    vcp_volume_ok = bool(vcp_detail.get("volume_contracting", True)) if require_vcp_volume_contracting else True

    stock_ok = (
        trend_ok
        and pivot_break
        and pivot_extension_ok
        and rs_ok
        and vol_surge
        and liquidity_ok
        and tight_ok
        and vcp_volume_ok
    )
    buy = stock_ok and market_ok

    tags: list[str] = []
    missing: list[str] = []
    if market_ok and require_market:
        tags.append(regime.get("reason") or "市场环境OK")
    elif require_market:
        missing.append(regime.get("block_reason") or "市场环境不允许买入")
    if trend_ok:
        tags.append("趋势模板")
    else:
        missing.append("趋势模板未通过")
    if vcp_detail.get("has_vcp"):
        tags.append(f"VCP×{vcp_detail.get('num_contractions', 0)}")
    else:
        missing.append("VCP形态不足")
    if vcp_volume_ok:
        tags.append("量能收缩")
    else:
        missing.append("VCP量能未收缩")
    if pivot_break:
        tags.append("枢纽突破")
    else:
        missing.append("未突破枢纽")
    if pivot_break and pivot_extension_ok:
        tags.append(f"距枢纽{pivot_extension_pct:.1f}%")
    elif pivot_break:
        missing.append(f"突破过远{pivot_extension_pct:.1f}%>{max_pivot_extension_pct:.1f}%")
    if vol_surge:
        tags.append(f"放量{vol / vol_ma50:.1f}x" if vol_ma50 else "放量")
    else:
        missing.append(f"突破量能不足(<{breakout_vol:.1f}x)")
    if liquidity_ok:
        tags.append(f"流动性≥{int(min_avg_volume):,}" if min_avg_volume > 0 else "流动性OK")
    else:
        missing.append(f"流动性不足: 50日均量{vol_ma50:,.0f}<{min_avg_volume:,.0f}")
    if rs_ok:
        tags.append(f"RS≥{rs_min}")
    else:
        missing.append(f"RS<{rs_min}")
    if require_tight and tight_ok:
        tags.append("紧密收盘")
    elif require_tight:
        missing.append("紧密收盘不足")

    reason = "SEPA: " + (" + ".join(tags) if tags else "条件未满足")
    if pivot_price > 0:
        reason += f" (枢纽{pivot_price:.2f})"

    block_reason = ""
    if stock_ok and not market_ok:
        block_reason = str(regime.get("block_reason") or "市场环境不允许买入")

    return {
        "code": code,
        "strategy_id": "sepa",
        "buy_signal": buy,
        "strategy_exit_signal": False,
        "strategy_entry_reason": reason if buy else "",
        "strategy_exit_reason": "",
        "market_block_reason": block_reason,
        "missing_conditions": missing,
        "market_regime": regime,
        "rs_rating": float(latest.get("rs_rating", 0) or 0),
        "pivot_price": pivot_price,
        "pivot_extension_pct": pivot_extension_pct,
        "vcp": vcp_detail,
    }


def check_sepa_position_exit(
    *,
    code: str,
    entry_date: str,
    entry_price: float,
    stop_loss: float = 0,
    shares: int = 0,
    partial_sold: bool = False,
    highest_since_entry: float = 0,
    repo=None,
) -> dict | None:
    """
    SEPA exit via RiskManager (Ch 10-12):
    hard stop, climax top, stage 3/4, progressive stop, partial profit, time stop, etc.
    """
    from desktop.data_access import get_repo

    if entry_price <= 0:
        return None

    repo = repo or get_repo()
    rows = repo.fetchall(
        "SELECT date, open, high, low, close, volume FROM daily_kline "
        "WHERE code=? ORDER BY date DESC LIMIT 260",
        (code,),
    )
    if len(rows) < 50:
        return None

    rows = rows[::-1]
    hist = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
    for col in ("open", "high", "low", "close", "volume"):
        hist[col] = pd.to_numeric(hist[col], errors="coerce")

    latest = hist.iloc[-1]
    current_price = float(latest["close"])
    current_high = float(latest["high"])
    current_low = float(latest["low"])
    current_volume = float(latest["volume"])

    try:
        hold_days = max(0, (date.today() - date.fromisoformat(str(entry_date)[:10])).days)
    except Exception:
        hold_days = 0

    rm = RiskManager(RiskConfig())
    initial_stop = stop_loss if stop_loss > 0 else rm.get_stop_loss_price(entry_price)

    position = Position(
        code=code,
        entry_date=str(entry_date)[:10],
        entry_price=float(entry_price),
        shares=int(shares or 0),
        stop_loss=float(initial_stop),
        partial_sold=bool(partial_sold),
        highest_since_entry=float(highest_since_entry or entry_price),
        days_held=max(0, hold_days - 1),
        strategy_id="sepa",
    )

    day_data = {
        "open": float(latest["open"]),
        "high": current_high,
        "low": current_low,
        "close": current_price,
        "volume": current_volume,
        "code": code,
    }

    try:
        exit_sig = rm.check_exit_signals(
            position=position,
            current_price=current_price,
            current_high=current_high,
            current_low=current_low,
            current_volume=current_volume,
            day_data=day_data,
            df_history=hist,
        )
    except Exception as exc:
        _log.debug("sepa exit check failed %s: %s", code, exc)
        return None

    action = str(exit_sig.get("action", "hold"))
    if action in ("full_sell", "partial_sell"):
        return {
            "action": "sell_half" if action == "partial_sell" else "sell_all",
            "rule": "SEPA风控",
            "reason": str(exit_sig.get("reason", "SEPA退出")),
            "shares_pct": 50 if action == "partial_sell" else 100,
            "updated_stop_loss": position.stop_loss,
        }
    return None


def sepa_initial_stop_loss(entry_price: float) -> float:
    return RiskManager(RiskConfig()).get_stop_loss_price(entry_price)
