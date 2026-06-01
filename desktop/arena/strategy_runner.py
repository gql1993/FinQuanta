"""Per-strategy scan and rule-based buys for arena participants."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from desktop.data_access import get_repo
from strategy_profiles import (
    STRATEGY_PROFILES,
    apply_screening_profile,
    get_strategy_default_params,
    strategy_name,
)

_log = logging.getLogger("arena.strategy_runner")

_MIN_BARS = 50
_SCORE_FLOOR = 40


def _build_base_row(code: str, ctx, names: dict[str, str], board_map: dict[str, str]) -> dict:
    """SEPA-style base row before strategy_profiles overlay (aligned with run_screening)."""
    pivot = float(np.max(ctx.closes[-20:])) if ctx.n >= 20 else ctx.price
    dist_to_pivot = (ctx.price - pivot) / pivot if pivot > 0 else 0.0
    score = ctx.rs * 0.3
    score += (1 if ctx.vcp else 0) * 20
    score += (1 if ctx.breakout else 0) * 25
    score += max(0.0, -dist_to_pivot * 100) * 0.5
    score += (1 if ctx.vol_ratio and ctx.vol_ratio < 0.8 else 0) * 5
    score += (ctx.price / ctx.h52) * 10 if ctx.h52 > 0 else 0

    return {
        "代码": code,
        "名称": names.get(code, code),
        "板块": board_map.get(code, ""),
        "价格": round(ctx.price, 2),
        "RS": int(ctx.rs),
        "评分": round(score, 1),
        "VCP": "✓" if ctx.vcp else "-",
        "收缩": ctx.contraction if ctx.contraction else 0,
        "枢纽": round(pivot, 2),
        "距枢纽%": round(dist_to_pivot * 100, 1),
        "突破": "突破!" if ctx.breakout else ("~" if dist_to_pivot > -0.05 else "-"),
        "紧密": "-",
        "量比": ctx.vol_ratio if ctx.vol_ratio else 0,
        "离高点%": ctx.dist_high,
    }


def _kline_to_df(closes, highs, lows, vols) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "close": closes,
            "high": highs,
            "low": lows,
            "volume": vols,
        }
    )


def scan_with_strategy(strategy_id: str, *, limit: int = 50) -> list[dict]:
    """Scan universe with one strategy profile (same rules as 选股雷达)."""
    from desktop.strategy_engine import build_context

    sid = strategy_id if strategy_id in STRATEGY_PROFILES else "sepa"
    params = get_strategy_default_params(sid)

    repo = get_repo()
    codes = [
        r[0]
        for r in repo.fetchall(
            "SELECT code, COUNT(*) as cnt FROM daily_kline "
            "GROUP BY code HAVING cnt >= ? ORDER BY cnt DESC LIMIT 500",
            (_MIN_BARS,),
        )
    ]

    names: dict[str, str] = {}
    for r in repo.fetchall("SELECT code, name FROM stock_list", ()):
        names[r[0]] = r[1]

    board_map: dict[str, str] = {}
    for r in repo.fetchall("SELECT code, board FROM board_stocks", ()):
        if r[0] not in board_map:
            board_map[r[0]] = r[1]

    results: list[dict] = []
    for code in codes:
        rows = repo.fetchall(
            "SELECT close, high, low, volume FROM daily_kline "
            "WHERE code=? ORDER BY date DESC LIMIT 260",
            (code,),
        )
        if len(rows) < _MIN_BARS:
            continue
        rows = rows[::-1]
        closes = np.array([r[0] for r in rows], dtype=float)
        highs = np.array([r[1] for r in rows], dtype=float)
        lows = np.array([r[2] for r in rows], dtype=float)
        vols = np.array([r[3] for r in rows], dtype=float)
        if float(closes[-1]) <= 0:
            continue

        ctx = build_context(code, closes, highs, lows, vols)
        base = _build_base_row(code, ctx, names, board_map)
        df = _kline_to_df(closes, highs, lows, vols)
        try:
            row = apply_screening_profile(base, df, sid, None, params)
        except Exception as exc:
            _log.debug("profile scan skip %s %s: %s", sid, code, exc)
            continue

        try:
            score = float(row.get("评分", 0) or 0)
        except (TypeError, ValueError):
            score = 0.0
        if score < _SCORE_FLOOR:
            continue

        row["策略"] = strategy_name(sid)
        row["strategy_id"] = sid
        row["评分"] = str(int(score)) if score == int(score) else str(round(score, 1))
        row["价格"] = f"{float(row.get('价格', ctx.price)):.2f}"
        results.append(row)

    results.sort(key=lambda x: float(str(x.get("评分", "0")).replace(",", "") or 0), reverse=True)
    return results[:limit]


def buy_strategy_top(
    mode: str,
    candidates: list[dict],
    *,
    top_n: int = 1,
    reason_prefix: str = "竞技场",
) -> list[str]:
    """Buy top-N from pre-scored candidates into the given arena mode."""
    from desktop.ai_portfolio import buy, get_state
    from desktop.ai_trader import _calc_atr_stop

    if not candidates:
        return [f"[{mode}] 无候选股"]

    state = get_state(mode)
    existing = {p["code"] for p in state.get("positions", [])}
    results: list[str] = []
    bought = 0

    for item in candidates:
        if bought >= top_n:
            break
        code = str(item.get("代码", "") or "")
        if not code or code in existing:
            continue

        board = str(item.get("板块", "") or "")
        if board:
            try:
                from desktop.ai_trader import _WEAK_BOARD_5D_THRESHOLD
                from desktop.arena.loss_analysis import get_board_return_window

                board_5d = get_board_return_window(board)
                if board_5d is not None and board_5d <= _WEAK_BOARD_5D_THRESHOLD:
                    results.append(f"[{mode}] 跳过 {code}: 板块[{board}]近5日{board_5d:+.1f}%未上涨")
                    continue
            except Exception:
                pass

        try:
            price = float(str(item.get("价格", "0")).replace(",", ""))
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue

        try:
            from desktop.ai_trader import _get_real_price

            real_px = _get_real_price(code)
            if real_px > 0:
                price = real_px
        except Exception:
            pass

        slots_left = max(1, 10 - len(state.get("positions", [])))
        available = state["cash"]
        per_stock = available / max(slots_left, 1)
        shares = int(per_stock / price / 100) * 100
        if shares < 100:
            if available < price * 100 * 1.0003:
                results.append(f"[{mode}] 资金不足买入 {code}")
                continue
            shares = 100

        name = str(item.get("名称", code) or code)
        score = item.get("评分", "")
        strategy_label = item.get("策略", item.get("strategy_id", ""))
        stop_loss = _calc_atr_stop(code, price)
        msg = buy(
            mode,
            code,
            name,
            price,
            shares,
            stop_loss,
            f"{reason_prefix} {strategy_label} 评分{score}",
        )
        results.append(msg)
        existing.add(code)
        bought += 1
        state = get_state(mode)

    if bought == 0 and not results:
        results.append(f"[{mode}] 无新增买入（均已持有或无合适候选）")
    return results
