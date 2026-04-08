"""
统一策略引擎

目标：
1. 将 8 大策略从 UI/daemon/OpenClaw 中抽离
2. 对外暴露统一接口，后续可接回测、因子研究、OpenClaw、多端 API
3. 保持当前业务逻辑一致，同时减少重复代码
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class StrategyContext:
    code: str
    closes: np.ndarray
    highs: np.ndarray
    lows: np.ndarray
    vols: np.ndarray
    price: float
    n: int
    ma50: float
    ma150: float
    ma200: float
    h52: float
    l52: float
    dist_high: float
    vcp: bool
    vol_early: float
    vol_recent: float
    breakout: bool
    vol_ratio: float
    contraction: float
    pct_1m: float
    pct_3m: float
    pct_250: float
    rs: int


def build_context(code: str, closes: np.ndarray, highs: np.ndarray, lows: np.ndarray, vols: np.ndarray) -> StrategyContext:
    n = len(closes)
    price = float(closes[-1])
    ma50 = float(np.mean(closes[-50:])) if n >= 50 else price
    ma150 = float(np.mean(closes[-150:])) if n >= 150 else ma50
    ma200 = float(np.mean(closes[-200:])) if n >= 200 else ma150

    pct_250 = (price / float(closes[0]) - 1) * 100 if closes[0] > 0 else 0
    h52 = float(np.max(highs[-250:])) if n >= 250 else float(np.max(highs))
    l52 = float(np.min(lows[-250:])) if n >= 250 else float(np.min(lows))
    dist_high = round((price / h52 - 1) * 100, 1) if h52 > 0 else 0

    vcp = False
    vol_early = 0.0
    vol_recent = 0.0
    if n >= 40:
        vol_early = float(np.std(closes[-40:-20]) / max(np.mean(closes[-40:-20]), 1e-6))
        vol_recent = float(np.std(closes[-20:]) / max(np.mean(closes[-20:]), 1e-6))
        if vol_recent < vol_early * 0.7:
            vcp = True

    breakout = False
    if n >= 20:
        high20 = float(np.max(closes[-21:-1]))
        if price >= high20:
            breakout = True

    vol_ratio = 0.0
    if n >= 20 and np.mean(vols[-20:]) > 0:
        vol_ratio = round(float(vols[-1]) / float(np.mean(vols[-20:])), 1)

    contraction = 0.0
    if n >= 40 and vol_early > 0:
        contraction = round(vol_recent / vol_early, 2)

    pct_1m = (price / float(closes[-22]) - 1) * 100 if n >= 22 and closes[-22] > 0 else 0
    pct_3m = (price / float(closes[-66]) - 1) * 100 if n >= 66 and closes[-66] > 0 else 0
    rs = min(99, max(1, int(50 + pct_250 * 0.3)))

    return StrategyContext(
        code=code,
        closes=closes,
        highs=highs,
        lows=lows,
        vols=vols,
        price=price,
        n=n,
        ma50=ma50,
        ma150=ma150,
        ma200=ma200,
        h52=h52,
        l52=l52,
        dist_high=dist_high,
        vcp=vcp,
        vol_early=vol_early,
        vol_recent=vol_recent,
        breakout=breakout,
        vol_ratio=vol_ratio,
        contraction=contraction,
        pct_1m=pct_1m,
        pct_3m=pct_3m,
        pct_250=pct_250,
        rs=rs,
    )


def _score_sepa(ctx: StrategyContext) -> tuple[int, list[str]]:
    score = 0
    signals: list[str] = []
    if ctx.price > ctx.ma50:
        score += 8
    if ctx.n >= 200 and ctx.ma50 > ctx.ma150 > ctx.ma200:
        score += 18
        signals.append("多头排列")
    if ctx.n >= 200:
        ma200_prev = float(np.mean(ctx.closes[-222:-22])) if ctx.n >= 222 else ctx.ma200
        if ctx.ma200 > ma200_prev:
            score += 8
            signals.append("MA200上升")
    if ctx.h52 > 0 and ctx.price >= ctx.h52 * 0.75:
        score += 6
    if ctx.l52 > 0 and ctx.price >= ctx.l52 * 1.3:
        score += 5
        signals.append("距底部+30%")
    if ctx.vcp:
        score += 12
        signals.append("VCP收缩")
    if ctx.breakout:
        score += 12
        signals.append("突破")
    if ctx.n >= 10:
        recent_closes = ctx.closes[-10:]
        tight = (float(np.max(recent_closes)) - float(np.min(recent_closes))) / float(np.mean(recent_closes))
        if tight < 0.03:
            score += 10
            signals.append("紧密收盘")
        elif tight < 0.05:
            score += 5
            signals.append("收盘较紧")
    if ctx.n >= 20 and ctx.vcp:
        vol_ratio_vcp = float(np.mean(ctx.vols[-5:])) / max(float(np.mean(ctx.vols[-20:])), 1)
        if vol_ratio_vcp < 0.5:
            score += 8
            signals.append("量能枯竭")
        elif vol_ratio_vcp < 0.7:
            score += 4
            signals.append("缩量")
    return score, signals


def _score_canslim(ctx: StrategyContext) -> tuple[int, list[str]]:
    score = 0
    signals: list[str] = []
    if ctx.rs >= 80:
        score += 20
        signals.append(f"RS{ctx.rs}极强")
    elif ctx.rs >= 70:
        score += 15
        signals.append(f"RS{ctx.rs}")
    if ctx.pct_3m > 30:
        score += 15
        signals.append(f"季涨{ctx.pct_3m:.0f}%")
    elif ctx.pct_3m > 15:
        score += 10
        signals.append(f"季涨{ctx.pct_3m:.0f}%")
    if ctx.breakout:
        score += 12
        signals.append("新高突破")
    if ctx.price > ctx.ma50 > ctx.ma200:
        score += 10
        signals.append("趋势良好")
    if ctx.vol_ratio > 1.5 and ctx.breakout:
        score += 12
        signals.append("放量突破")
    if ctx.vcp:
        score += 8
        signals.append("杯柄形态")
    if ctx.dist_high > -5:
        score += 8
        signals.append("近52周高点")
    if ctx.pct_3m > 25 and ctx.rs >= 75:
        score += 5
        signals.append("板块领涨")
    return score, signals


def _score_turtle(ctx: StrategyContext) -> tuple[int, list[str]]:
    score = 0
    signals: list[str] = []
    if ctx.n >= 20 and ctx.price >= float(np.max(ctx.highs[-20:])):
        score += 25
        signals.append("20日新高")
    if ctx.n >= 55 and ctx.price >= float(np.max(ctx.highs[-55:])):
        score += 18
        signals.append("55日新高")
    if ctx.price > ctx.ma50:
        score += 8
        signals.append("趋势向上")
    if ctx.n >= 20:
        tr_list = []
        for k in range(1, min(20, ctx.n)):
            tr = max(
                ctx.highs[-k] - ctx.lows[-k],
                abs(ctx.highs[-k] - ctx.closes[-k - 1]),
                abs(ctx.lows[-k] - ctx.closes[-k - 1]),
            )
            tr_list.append(tr)
        atr20 = float(np.mean(tr_list)) if tr_list else 0
    else:
        atr20 = 0
    if atr20 > 0 and ctx.price > 0:
        atr_pct = atr20 / ctx.price * 100
        if atr_pct < 3:
            score += 10
            signals.append(f"ATR{atr_pct:.1f}%低")
        elif atr_pct < 5:
            score += 6
            signals.append(f"ATR{atr_pct:.1f}%适中")
    if ctx.vol_ratio > 1.3:
        score += 8
        signals.append("放量")
    if ctx.breakout and ctx.n >= 3 and ctx.closes[-1] > ctx.closes[-2] > ctx.closes[-3]:
        score += 5
        signals.append("可加仓")
    return score, signals


def _score_graham(ctx: StrategyContext) -> tuple[int, list[str]]:
    score = 0
    signals: list[str] = []
    if ctx.dist_high < -30:
        score += 25
        signals.append(f"距高点{ctx.dist_high}%")
    if ctx.dist_high < -50:
        score += 10
        signals.append("深度回调")
    if ctx.price < ctx.ma200:
        score += 15
        signals.append("低于MA200")
    if ctx.pct_250 < -10:
        score += 10
        signals.append("年跌幅大")
    if ctx.vol_recent < 0.03:
        score += 10
        signals.append("波动极低")
    if ctx.l52 > 0 and ctx.price < ctx.l52 * 1.15:
        score += 15
        signals.append("接近52周低点")
    return score, signals


def _score_buffett(ctx: StrategyContext) -> tuple[int, list[str]]:
    score = 0
    signals: list[str] = []
    if ctx.price > ctx.ma200:
        score += 10
        signals.append("长期趋势向上")
    if ctx.n >= 200 and ctx.ma50 > ctx.ma200:
        score += 10
        signals.append("中期趋势良好")
    if 0 < ctx.pct_250 < 50:
        score += 15
        signals.append("稳健增长")
    if ctx.vol_recent < 0.04:
        score += 15
        signals.append("波动稳定")
    if ctx.dist_high > -20:
        score += 10
        signals.append("接近高点")
    ma_diff = abs(ctx.ma50 - ctx.ma200) / ctx.ma200 * 100 if ctx.ma200 > 0 else 999
    if ma_diff < 10:
        score += 10
        signals.append("均线收敛")
    return score, signals


def _score_lynch(ctx: StrategyContext) -> tuple[int, list[str]]:
    score = 0
    signals: list[str] = []
    if ctx.pct_1m > 10:
        score += 20
        signals.append(f"月涨{ctx.pct_1m:.0f}%")
    elif ctx.pct_1m > 5:
        score += 10
        signals.append(f"月涨{ctx.pct_1m:.0f}%")
    if ctx.pct_3m > 30:
        score += 15
        signals.append(f"季涨{ctx.pct_3m:.0f}%")
    elif ctx.pct_3m > 15:
        score += 10
    if ctx.breakout:
        score += 15
        signals.append("突破")
    if ctx.vol_ratio > 1.5:
        score += 10
        signals.append("放量")
    if ctx.price > ctx.ma50 > ctx.ma150:
        score += 10
        signals.append("多头排列")
    return score, signals


def _score_domestic_trend(ctx: StrategyContext) -> tuple[int, list[str]]:
    score = 0
    signals: list[str] = []
    if ctx.price > ctx.ma50 > ctx.ma150:
        score += 15
        signals.append("多头排列")
    if ctx.breakout and ctx.vol_ratio > 1.3:
        score += 18
        signals.append("放量突破")
    if ctx.pct_1m > 5:
        score += 8
        signals.append(f"月涨{ctx.pct_1m:.0f}%")
    if ctx.vcp:
        score += 12
        signals.append("收缩整理")
    if ctx.n >= 5:
        consec_up = 0
        for k in range(-1, -6, -1):
            if ctx.closes[k] > ctx.closes[k - 1]:
                consec_up += 1
            else:
                break
        if consec_up >= 4:
            score += 10
            signals.append(f"{consec_up}连阳")
        elif consec_up >= 3:
            score += 6
            signals.append(f"{consec_up}连阳")
    if ctx.n >= 2:
        day_pct = (ctx.closes[-1] / ctx.closes[-2] - 1) * 100
        if day_pct >= 9.5:
            score += 10
            signals.append("涨停")
        elif day_pct >= 7:
            score += 5
            signals.append(f"大涨{day_pct:.1f}%")
    if ctx.n >= 10:
        ma5 = float(np.mean(ctx.closes[-5:]))
        ma10 = float(np.mean(ctx.closes[-10:]))
        ma5_prev = float(np.mean(ctx.closes[-6:-1]))
        ma10_prev = float(np.mean(ctx.closes[-11:-1]))
        if ma5 > ma10 and ma5_prev <= ma10_prev:
            score += 8
            signals.append("金叉")
    return score, signals


def _score_domestic_value(ctx: StrategyContext) -> tuple[int, list[str]]:
    score = 0
    signals: list[str] = []
    if ctx.price < ctx.ma200:
        score += 12
        signals.append("破年线")
    if ctx.dist_high < -40:
        score += 18
        signals.append(f"距高{ctx.dist_high:.0f}%")
    elif ctx.dist_high < -30:
        score += 10
        signals.append(f"距高{ctx.dist_high:.0f}%")
    if ctx.vol_recent < 0.02:
        score += 12
        signals.append("极度缩量")
    elif ctx.vol_recent < 0.03:
        score += 8
        signals.append("缩量企稳")
    if ctx.n >= 5:
        recent_up = sum(1 for i in range(-5, 0) if ctx.closes[i] > ctx.closes[i - 1])
        if recent_up >= 4:
            score += 10
            signals.append("强反弹")
        elif recent_up >= 3:
            score += 6
            signals.append("止跌")
    if ctx.n >= 20 and ctx.vol_ratio > 2.0 and ctx.dist_high < -30:
        score += 10
        signals.append("底部放量")
    if ctx.n >= 40:
        low20_prev = float(np.min(ctx.lows[-40:-20]))
        low20_now = float(np.min(ctx.lows[-20:]))
        close20_prev = float(np.mean(ctx.closes[-40:-20]))
        close20_now = float(np.mean(ctx.closes[-20:]))
        if low20_now < low20_prev and close20_now > close20_prev:
            score += 8
            signals.append("底背离")
    return score, signals


STRATEGY_META = {
    "sepa": ("SEPA", _score_sepa),
    "minervini": ("SEPA", _score_sepa),
    "canslim": ("CANSLIM", _score_canslim),
    "turtle": ("TURTLE", _score_turtle),
    "graham": ("GRAHAM", _score_graham),
    "value": ("GRAHAM", _score_graham),
    "buffett": ("BUFFETT", _score_buffett),
    "quality": ("BUFFETT", _score_buffett),
    "lynch": ("LYNCH", _score_lynch),
    "momentum": ("LYNCH", _score_lynch),
    "domestic_trend": ("DOMESTIC_TREND", _score_domestic_trend),
    "cn_trend": ("DOMESTIC_TREND", _score_domestic_trend),
    "domestic_value": ("DOMESTIC_VALUE", _score_domestic_value),
    "cn_value": ("DOMESTIC_VALUE", _score_domestic_value),
}


def score_candidate(strategy_id: str, ctx: StrategyContext) -> dict[str, Any]:
    sid = strategy_id.lower()
    canonical, scorer = STRATEGY_META.get(sid, ("SEPA", _score_sepa))
    score, signals = scorer(ctx)

    signal_str = " ".join(signals)
    pct5 = (ctx.price / float(ctx.closes[-6]) - 1) * 100 if ctx.n >= 6 and ctx.closes[-6] > 0 else 0
    pct1 = (ctx.price / float(ctx.closes[-2]) - 1) * 100 if ctx.n >= 2 and ctx.closes[-2] > 0 else 0

    buy_advice = ""
    action_advice = ""
    if score >= 60 and ctx.breakout:
        buy_advice = "🟢 强烈买入"
    elif score >= 50 and (ctx.breakout or ctx.vcp):
        buy_advice = "🔵 建议买入"
    elif score >= 40 and "多头排列" in signal_str:
        buy_advice = "🔵 建议买入"
    elif score >= 30:
        buy_advice = "⚪ 观望"
    elif score > 0:
        buy_advice = "⚪ 暂不买入"
    else:
        buy_advice = "⛔ 不买入"

    if score >= 50 and ctx.breakout and pct5 > 0:
        action_advice = "📈 加仓"
    elif score >= 40 and pct1 > 0:
        action_advice = "💎 持有"
    elif pct5 < -8:
        action_advice = "🔴 卖出止损"
    elif score < 15 and pct5 < -3:
        action_advice = "🟡 减仓"
    elif score < 10:
        action_advice = "🔴 卖出"
    else:
        action_advice = "💎 持有"

    return {
        "strategy": canonical,
        "score": int(score),
        "signals": signals,
        "signal_str": signal_str,
        "buy_advice": buy_advice,
        "action_advice": action_advice,
        "rs": ctx.rs,
        "vcp": ctx.vcp,
        "breakout": ctx.breakout,
        "contraction": ctx.contraction,
        "vol_ratio": ctx.vol_ratio,
        "dist_high": ctx.dist_high,
    }
