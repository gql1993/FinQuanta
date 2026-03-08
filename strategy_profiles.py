"""
Multi-strategy profiles and rule mapping.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class StrategyProfile:
    strategy_id: str
    name: str
    category: str
    description: str
    region: str = "海外"
    camp: str = "大师"


STRATEGY_PROFILES: dict[str, StrategyProfile] = {
    "sepa": StrategyProfile("sepa", "SEPA / 股票魔法师", "趋势成长", "趋势模板 + VCP + 风控", "海外", "大师"),
    "canslim": StrategyProfile("canslim", "CAN SLIM / 欧奈尔", "趋势成长", "强势成长 + 放量突破 + RS", "海外", "大师"),
    "turtle": StrategyProfile("turtle", "海龟交易", "趋势跟随", "通道突破 + ATR 风险单位", "海外", "大师"),
    "graham": StrategyProfile("graham", "格雷厄姆价值", "价值投资", "低估值 + 安全边际", "海外", "大师"),
    "livermore": StrategyProfile("livermore", "利弗莫尔操盘", "趋势交易", "关键点突破 + 顺势加码", "海外", "大师"),
    "covell": StrategyProfile("covell", "卡沃尔趋势跟踪", "趋势跟随", "中长期突破 + 跟踪止损", "海外", "大师"),
    "dow": StrategyProfile("dow", "道氏理论", "趋势交易", "多级趋势确认 + 结构破坏退出", "海外", "大师"),
    "lynch": StrategyProfile("lynch", "彼得林奇 GARP", "成长价值", "成长与估值平衡", "海外", "大师"),
    "buffett": StrategyProfile("buffett", "巴菲特质量复利", "价值投资", "质量因子 + 长期持有", "海外", "大师"),
    "larry": StrategyProfile("larry", "拉里威廉姆斯短线", "波段交易", "动量/突破 + 资金管理", "海外", "大师"),

    # 国内体系：游资
    "cn_yz_yangjia": StrategyProfile(
        "cn_yz_yangjia", "养家 / 情绪周期", "短线情绪",
        "买分歧卖一致，情绪周期切换", "国内", "游资"
    ),
    "cn_yz_zhaolao": StrategyProfile(
        "cn_yz_zhaolao", "赵老哥 / 龙头接力", "龙头接力",
        "只做龙头主升与惯性强化", "国内", "游资"
    ),
    "cn_yz_asking": StrategyProfile(
        "cn_yz_asking", "Asking / 主升浪", "主升趋势",
        "截断亏损，让利润奔跑", "国内", "游资"
    ),

    # 国内体系：私募
    "cn_pm_danbin": StrategyProfile(
        "cn_pm_danbin", "但斌 / 时间玫瑰", "价值成长",
        "赛道龙头 + 长期复利", "国内", "私募"
    ),
    "cn_pm_linyuan": StrategyProfile(
        "cn_pm_linyuan", "林园 / 垄断与成瘾", "消费医药价值",
        "高景气行业 + 长期持有", "国内", "私募"
    ),

    # 国内体系：机构
    "emotion": StrategyProfile(
        "emotion", "情绪博弈", "短线情绪",
        "涨跌家数/连板高度/炸板率/赚钱效应 → 情绪阶段判定", "国内", "游资"
    ),
    "event": StrategyProfile(
        "event", "事件驱动", "事件交易",
        "地缘/政策/财报/公告 → 事件受益/受损短期行情", "国内", "游资"
    ),
    "cn_inst_qiuguolu": StrategyProfile(
        "cn_inst_qiuguolu", "邱国鹭 / 简单投资", "机构价值",
        "估值安全边际 + 基本面趋势", "国内", "机构"
    ),

    "fund_tracking": StrategyProfile(
        "fund_tracking", "基金持仓跟踪", "机构跟踪",
        "季报/半年报/年报重仓股变化 → 预测持仓公布后个股走势", "国内", "机构"
    ),
}


def get_strategy_catalog() -> list[dict]:
    return [
        {
            "id": p.strategy_id,
            "name": p.name,
            "category": p.category,
            "description": p.description,
            "region": p.region,
            "camp": p.camp,
        }
        for p in STRATEGY_PROFILES.values()
    ]


def strategy_name(strategy_id: str) -> str:
    profile = STRATEGY_PROFILES.get(strategy_id)
    return profile.name if profile else STRATEGY_PROFILES["sepa"].name


def get_strategy_default_params(strategy_id: str) -> dict:
    defaults = {
        "sepa": {
            "rs_min": 70,
            "pivot_distance_max_pct": 8.0,
            "volume_ratio_min": 0.8,
        },
        "canslim": {
            "rs_min": 80,
            "volume_ratio_min": 1.2,
            "near_high_52w_min_pct": -12.0,
            "c_mom_min_pct": 8.0,
            "a_trend_min_pct": 20.0,
        },
        "turtle": {
            "breakout_short": 20,
            "breakout_long": 55,
            "trend_ma_days": 50,
            "atr_window": 20,
            "atr_target_pct": 0.03,
            "max_unit_scale": 1.4,
            "min_unit_scale": 0.45,
        },
        "graham": {
            "pe_max": 20.0,
            "pb_max": 2.5,
            "trend_guard": True,
        },
        "livermore": {
            "breakout_days": 20,
            "rs_min": 65,
            "trend_ma_days": 50,
        },
        "covell": {
            "breakout_days": 55,
            "ma_days": 200,
            "vol_filter_min": 0.7,
        },
        "dow": {
            "ma_fast": 50,
            "ma_mid": 150,
            "ma_slow": 200,
            "rs_min": 60,
        },
        "lynch": {
            "pe_low": 8.0,
            "pe_high": 35.0,
            "rs_min": 60,
            "trend_guard": True,
        },
        "buffett": {
            "pe_max": 35.0,
            "pb_max": 6.0,
            "trend_guard": True,
        },
        "larry": {
            "breakout_days": 20,
            "volume_ratio_min": 1.2,
            "rs_min": 55,
        },
        "cn_yz_yangjia": {
            "breakout_days": 12,
            "volume_ratio_min": 1.25,
            "pullback_max_pct": 6.0,
            "rs_min": 60,
            "allow_phase_start": True,
            "allow_phase_ferment": True,
            "allow_phase_climax": False,
        },
        "cn_yz_zhaolao": {
            "leader_near_high_pct": -8.0,
            "volume_ratio_min": 1.35,
            "rs_min": 75,
            "breakout_days": 20,
            "allow_phase_start": True,
            "allow_phase_ferment": True,
            "allow_phase_climax": False,
        },
        "cn_yz_asking": {
            "breakout_days": 18,
            "volume_ratio_min": 1.15,
            "rs_min": 65,
            "exit_ma_days": 10,
            "allow_phase_start": True,
            "allow_phase_ferment": True,
            "allow_phase_climax": False,
        },
        "emotion": {
            "vol_ratio_min": 1.2,
            "profit_effect_min": 0.5,
            "streak_min": 2,
            "allow_phase_start": True,
            "allow_phase_ferment": True,
            "allow_phase_climax": False,
            "rs_min": 50,
        },
        "event": {
            "impact_threshold": 3.0,
            "vol_ratio_min": 1.5,
            "rs_min": 40,
            "hold_days_max": 10,
        },
        "cn_pm_danbin": {
            "pe_max": 45.0,
            "pb_max": 8.0,
            "trend_guard": True,
            "rs_min": 55,
            "heat_min": 50.0,
            "valuation_min": 35.0,
            "crowding_max": 75.0,
        },
        "cn_pm_linyuan": {
            "pe_max": 35.0,
            "pb_max": 7.0,
            "trend_guard": True,
            "rs_min": 50,
            "heat_min": 45.0,
            "valuation_min": 40.0,
            "crowding_max": 78.0,
        },
        "cn_inst_qiuguolu": {
            "pe_max": 28.0,
            "pb_max": 5.0,
            "trend_guard": True,
            "rs_min": 55,
            "ma_days": 150,
            "heat_min": 42.0,
            "valuation_min": 50.0,
            "crowding_max": 65.0,
        },
        "fund_tracking": {
            "min_funds": 50,
            "change_filter": "增持",
            "lookback_days": 60,
            "top_n": 30,
            "trend_guard": True,
            "ma_days": 20,
        },
    }
    return dict(defaults.get(strategy_id, {}))


def _emotion_phase_series(df: pd.DataFrame) -> pd.Series:
    """基于价格/量能构建情绪阶段代理标签（shift(1)防止前视偏差）。"""
    close = df["close"].shift(1)
    volume = df["volume"].shift(1)
    ma20 = close.rolling(20).mean()
    vol_ma20 = volume.rolling(20).mean()
    ret5 = close.pct_change(5) * 100
    ret20 = close.pct_change(20) * 100
    vol_ratio = volume / vol_ma20.replace(0, np.nan)

    phase = pd.Series("中性", index=df.index)
    phase[(ret5 <= -6) & (vol_ratio <= 0.95)] = "冰点"
    phase[(ret5 > -2) & (ret5 <= 4) & (ret20 > -5) & (vol_ratio >= 1.0)] = "启动"
    phase[(ret20 >= 8) & (ret20 <= 25) & (close > ma20) & (vol_ratio >= 1.05)] = "发酵"
    phase[(ret20 > 25) & (vol_ratio >= 1.45)] = "高潮"
    phase[(ret5 <= -3) & (close < ma20) & (vol_ratio >= 1.1)] = "退潮"
    return phase.fillna("中性")


def _sector_heat_series(df: pd.DataFrame) -> pd.Series:
    close = df["close"].shift(1)
    volume = df["volume"].shift(1)
    ret20 = close.pct_change(20).fillna(0) * 100
    ret60 = close.pct_change(60).fillna(0) * 100
    vol_ratio = (volume / volume.rolling(50).mean().replace(0, np.nan)).fillna(1.0)
    raw = ret20 * 0.9 + ret60 * 0.6 + (vol_ratio - 1.0) * 18
    return raw.clip(lower=-20, upper=80).add(20).clip(0, 100)


def _valuation_score(pe: float | None, pb: float | None, pe_max: float, pb_max: float) -> float:
    if pe is None and pb is None:
        return 50.0
    pe_s = 50.0 if pe is None else max(0.0, min(100.0, (1 - pe / max(pe_max, 1e-6)) * 100))
    pb_s = 50.0 if pb is None else max(0.0, min(100.0, (1 - pb / max(pb_max, 1e-6)) * 100))
    return float((pe_s + pb_s) / 2)


def _crowding_series(df: pd.DataFrame) -> pd.Series:
    close = df["close"].shift(1)
    volume = df["volume"].shift(1)
    ma50 = close.rolling(50).mean()
    vol_ma20 = volume.rolling(20).mean()
    premium = ((close / ma50.replace(0, np.nan)) - 1.0).fillna(0) * 120
    burst = ((volume / vol_ma20.replace(0, np.nan)) - 1.0).fillna(0) * 45
    raw = premium + burst + 35
    return raw.clip(0, 100)


def apply_screening_profile(candidate: dict, df: pd.DataFrame, strategy_id: str,
                            fundamental: dict | None = None,
                            params: dict | None = None) -> dict:
    c = dict(candidate)
    p = get_strategy_default_params(strategy_id)
    if params:
        p.update(params)
    score = float(c.get("评分", 0))
    close = float(df["close"].iloc[-1])
    ma50 = float(df["close"].iloc[-50:].mean()) if len(df) >= 50 else close
    ma200 = float(df["close"].iloc[-200:].mean()) if len(df) >= 200 else close
    high20 = float(df["high"].iloc[-20:].max()) if len(df) >= 20 else float(df["high"].max())
    high55 = float(df["high"].iloc[-55:].max()) if len(df) >= 55 else float(df["high"].max())
    vol20 = float(df["volume"].iloc[-20:].mean()) if len(df) >= 20 else 0
    vol50 = float(df["volume"].iloc[-50:].mean()) if len(df) >= 50 else (vol20 if vol20 > 0 else 1)
    vol_ratio = vol20 / vol50 if vol50 > 0 else 1.0

    pe = None
    pb = None
    if fundamental:
        try:
            v = fundamental.get("pe_dynamic")
            pe = float(v) if v not in (None, "", "-") else None
        except Exception:
            pe = None
        try:
            v = fundamental.get("pb")
            pb = float(v) if v not in (None, "", "-") else None
        except Exception:
            pb = None

    tags: list[str] = []
    breakout20 = close >= high20 * 0.995
    breakout55 = close >= high55 * 0.995
    trend_ok = close > ma50 > ma200

    if strategy_id == "sepa":
        rs_min = int(p.get("rs_min", 70))
        pivot_distance_max_pct = float(p.get("pivot_distance_max_pct", 8.0))
        volume_ratio_min = float(p.get("volume_ratio_min", 0.8))
        if c.get("RS", 0) >= rs_min:
            score += 6
            tags.append("RS达标")
        if abs(float(c.get("距枢纽%", 0))) <= pivot_distance_max_pct:
            score += 6
            tags.append("接近枢纽")
        if vol_ratio >= volume_ratio_min:
            score += 3
            tags.append("量能配合")
    elif strategy_id == "canslim":
        rs_min = int(p.get("rs_min", 80))
        vol_min = float(p.get("volume_ratio_min", 1.2))
        near_high_min_pct = float(p.get("near_high_52w_min_pct", -12.0))
        c_mom_min_pct = float(p.get("c_mom_min_pct", 8.0))
        a_trend_min_pct = float(p.get("a_trend_min_pct", 20.0))
        ret20 = (close / float(df["close"].iloc[-21]) - 1.0) * 100 if len(df) >= 21 else 0.0
        ret120 = (close / float(df["close"].iloc[-121]) - 1.0) * 100 if len(df) >= 121 else 0.0
        if c.get("RS", 0) >= rs_min:
            score += 8
            tags.append("L-领先股")
        if vol_ratio >= vol_min:
            score += 6
            tags.append("S-供需")
        if float(c.get("离高点%", -100)) >= near_high_min_pct:
            score += 6
            tags.append("N-新高")
        if ret20 >= c_mom_min_pct:
            score += 6
            tags.append("C-近期增长")
        if ret120 >= a_trend_min_pct:
            score += 5
            tags.append("A-中期增长")
        if trend_ok:
            score += 4
            tags.append("M-顺势")
        if c.get("VCP", "-") == "✓":
            score += 3
            tags.append("I-机构迹象")
    elif strategy_id == "turtle":
        b_short = int(p.get("breakout_short", 20))
        b_long = int(p.get("breakout_long", 55))
        ma_n = int(p.get("trend_ma_days", 50))
        high_short = float(df["high"].iloc[-b_short:].max()) if len(df) >= b_short else float(df["high"].max())
        high_long = float(df["high"].iloc[-b_long:].max()) if len(df) >= b_long else float(df["high"].max())
        ma_n_val = float(df["close"].iloc[-ma_n:].mean()) if len(df) >= ma_n else close
        atr_window = int(p.get("atr_window", 20))
        tr = np.maximum(df["high"] - df["low"], np.maximum(
            (df["high"] - df["close"].shift(1)).abs(),
            (df["low"] - df["close"].shift(1)).abs(),
        ))
        atr = float(tr.rolling(atr_window).mean().iloc[-1]) if len(df) >= atr_window else float(tr.iloc[-1])
        atr_pct = atr / close if close > 0 else 0
        if close >= high_short * 0.995:
            score += 12
            tags.append(f"{b_short}日突破")
        if close >= high_long * 0.995:
            score += 8
            tags.append(f"{b_long}日突破")
        if close > ma_n_val:
            score += 4
            tags.append("趋势方向")
        if atr_pct > 0:
            tags.append(f"N≈{atr_pct:.2%}")
    elif strategy_id == "graham":
        pe_max = float(p.get("pe_max", 20.0))
        pb_max = float(p.get("pb_max", 2.5))
        trend_guard = bool(p.get("trend_guard", True))
        if pe is not None and pe <= pe_max:
            score += 12
            tags.append("低PE")
        if pb is not None and pb <= pb_max:
            score += 10
            tags.append("低PB")
        if trend_guard and (not trend_ok):
            score -= 8
    elif strategy_id in ("livermore", "dow", "covell"):
        if strategy_id == "livermore":
            b_days = int(p.get("breakout_days", 20))
            rs_min = int(p.get("rs_min", 65))
            ma_n = int(p.get("trend_ma_days", 50))
            high_n = float(df["high"].iloc[-b_days:].max()) if len(df) >= b_days else float(df["high"].max())
            ma_n_val = float(df["close"].iloc[-ma_n:].mean()) if len(df) >= ma_n else close
            if close >= high_n * 0.995:
                score += 8
                tags.append("关键点突破")
            if c.get("RS", 0) >= rs_min:
                score += 5
                tags.append("强度确认")
            if close > ma_n_val:
                score += 4
                tags.append("趋势方向")
        elif strategy_id == "covell":
            b_days = int(p.get("breakout_days", 55))
            ma_n = int(p.get("ma_days", 200))
            vol_min = float(p.get("vol_filter_min", 0.7))
            high_n = float(df["high"].iloc[-b_days:].max()) if len(df) >= b_days else float(df["high"].max())
            ma_n_val = float(df["close"].iloc[-ma_n:].mean()) if len(df) >= ma_n else close
            if close >= high_n * 0.995:
                score += 9
                tags.append("长期突破")
            if close > ma_n_val:
                score += 6
                tags.append("顺势持有")
            if vol_ratio >= vol_min:
                score += 3
                tags.append("流动性")
        else:
            ma_fast = int(p.get("ma_fast", 50))
            ma_mid = int(p.get("ma_mid", 150))
            ma_slow = int(p.get("ma_slow", 200))
            rs_min = int(p.get("rs_min", 60))
            ma_f = float(df["close"].iloc[-ma_fast:].mean()) if len(df) >= ma_fast else close
            ma_m = float(df["close"].iloc[-ma_mid:].mean()) if len(df) >= ma_mid else close
            ma_s = float(df["close"].iloc[-ma_slow:].mean()) if len(df) >= ma_slow else close
            if ma_f > ma_m > ma_s:
                score += 9
                tags.append("道氏多头")
            if close > ma_f:
                score += 4
                tags.append("主升阶段")
            if c.get("RS", 0) >= rs_min:
                score += 3
                tags.append("相对强势")
    elif strategy_id in ("lynch", "buffett"):
        if strategy_id == "lynch":
            pe_low = float(p.get("pe_low", 8.0))
            pe_high = float(p.get("pe_high", 35.0))
            rs_min = int(p.get("rs_min", 60))
            trend_guard = bool(p.get("trend_guard", True))
            if pe is not None and pe_low <= pe <= pe_high:
                score += 8
                tags.append("GARP估值")
            if c.get("RS", 0) >= rs_min:
                score += 5
                tags.append("成长强度")
            if trend_guard and trend_ok:
                score += 3
                tags.append("趋势过滤")
        else:
            pe_max = float(p.get("pe_max", 35.0))
            pb_max = float(p.get("pb_max", 6.0))
            trend_guard = bool(p.get("trend_guard", True))
            if pe is not None and pe <= pe_max:
                score += 7
                tags.append("合理PE")
            if pb is not None and pb <= pb_max:
                score += 6
                tags.append("合理PB")
            if trend_guard and trend_ok:
                score += 3
                tags.append("价格不逆势")
    elif strategy_id == "larry":
        b_days = int(p.get("breakout_days", 20))
        vol_min = float(p.get("volume_ratio_min", 1.2))
        rs_min = int(p.get("rs_min", 55))
        high_n = float(df["high"].iloc[-b_days:].max()) if len(df) >= b_days else float(df["high"].max())
        if close >= high_n * 0.995 and vol_ratio >= vol_min:
            score += 12
            tags.append("短线动量")
        if c.get("RS", 0) >= rs_min:
            score += 4
            tags.append("强势优先")
    elif strategy_id == "cn_yz_yangjia":
        b_days = int(p.get("breakout_days", 12))
        vol_min = float(p.get("volume_ratio_min", 1.25))
        pullback_max = float(p.get("pullback_max_pct", 6.0))
        rs_min = int(p.get("rs_min", 60))
        phase = _emotion_phase_series(df).iloc[-1]
        high_n = float(df["high"].iloc[-b_days:].max()) if len(df) >= b_days else float(df["high"].max())
        pullback = abs(float(c.get("距枢纽%", 0)))
        if close >= high_n * 0.995 and pullback <= pullback_max:
            score += 10
            tags.append("分歧转一致")
        if vol_ratio >= vol_min:
            score += 5
            tags.append("合力放量")
        if c.get("RS", 0) >= rs_min:
            score += 4
            tags.append("情绪龙头")
        tags.append(f"情绪:{phase}")
        if phase == "发酵":
            score += 5
        elif phase == "启动":
            score += 2
        elif phase == "退潮":
            score -= 8
    elif strategy_id == "cn_yz_zhaolao":
        near_high = float(p.get("leader_near_high_pct", -8.0))
        vol_min = float(p.get("volume_ratio_min", 1.35))
        rs_min = int(p.get("rs_min", 75))
        b_days = int(p.get("breakout_days", 20))
        phase = _emotion_phase_series(df).iloc[-1]
        high_n = float(df["high"].iloc[-b_days:].max()) if len(df) >= b_days else float(df["high"].max())
        if float(c.get("离高点%", -100)) >= near_high:
            score += 7
            tags.append("龙头位")
        if close >= high_n * 0.995 and vol_ratio >= vol_min:
            score += 9
            tags.append("主升接力")
        if c.get("RS", 0) >= rs_min:
            score += 5
            tags.append("最强股")
        tags.append(f"情绪:{phase}")
        if phase in ("启动", "发酵"):
            score += 4
        elif phase == "退潮":
            score -= 10
    elif strategy_id == "cn_yz_asking":
        b_days = int(p.get("breakout_days", 18))
        vol_min = float(p.get("volume_ratio_min", 1.15))
        rs_min = int(p.get("rs_min", 65))
        phase = _emotion_phase_series(df).iloc[-1]
        high_n = float(df["high"].iloc[-b_days:].max()) if len(df) >= b_days else float(df["high"].max())
        if close >= high_n * 0.995 and vol_ratio >= vol_min:
            score += 10
            tags.append("主升浪启动")
        if c.get("RS", 0) >= rs_min:
            score += 5
            tags.append("强于市场")
        tags.append(f"情绪:{phase}")
        if phase in ("启动", "发酵"):
            score += 3
        elif phase == "退潮":
            score -= 8
    elif strategy_id == "cn_pm_danbin":
        pe_max = float(p.get("pe_max", 45.0))
        pb_max = float(p.get("pb_max", 8.0))
        trend_guard = bool(p.get("trend_guard", True))
        rs_min = int(p.get("rs_min", 55))
        heat_min = float(p.get("heat_min", 50.0))
        val_min = float(p.get("valuation_min", 35.0))
        crowd_max = float(p.get("crowding_max", 75.0))
        heat = float(_sector_heat_series(df).iloc[-1])
        val_score = _valuation_score(pe, pb, pe_max, pb_max)
        crowd = float(_crowding_series(df).iloc[-1])
        if pe is not None and pe <= pe_max:
            score += 6
            tags.append("赛道估值")
        if pb is not None and pb <= pb_max:
            score += 4
            tags.append("护城河溢价")
        if c.get("RS", 0) >= rs_min:
            score += 4
            tags.append("趋势延续")
        if trend_guard and (not trend_ok):
            score -= 6
        tags.append(f"热度{heat:.0f}")
        tags.append(f"估值分位{val_score:.0f}")
        tags.append(f"拥挤{crowd:.0f}")
        if heat >= heat_min:
            score += 4
        if val_score >= val_min:
            score += 5
        if crowd > crowd_max:
            score -= 6
    elif strategy_id == "cn_pm_linyuan":
        pe_max = float(p.get("pe_max", 35.0))
        pb_max = float(p.get("pb_max", 7.0))
        trend_guard = bool(p.get("trend_guard", True))
        rs_min = int(p.get("rs_min", 50))
        heat_min = float(p.get("heat_min", 45.0))
        val_min = float(p.get("valuation_min", 40.0))
        crowd_max = float(p.get("crowding_max", 78.0))
        heat = float(_sector_heat_series(df).iloc[-1])
        val_score = _valuation_score(pe, pb, pe_max, pb_max)
        crowd = float(_crowding_series(df).iloc[-1])
        if pe is not None and pe <= pe_max:
            score += 7
            tags.append("低估成长")
        if pb is not None and pb <= pb_max:
            score += 5
            tags.append("资产质量")
        if c.get("RS", 0) >= rs_min:
            score += 3
            tags.append("趋势向上")
        if trend_guard and (not trend_ok):
            score -= 6
        tags.append(f"热度{heat:.0f}")
        tags.append(f"估值分位{val_score:.0f}")
        tags.append(f"拥挤{crowd:.0f}")
        if heat >= heat_min:
            score += 3
        if val_score >= val_min:
            score += 5
        if crowd > crowd_max:
            score -= 5
    elif strategy_id == "cn_inst_qiuguolu":
        pe_max = float(p.get("pe_max", 28.0))
        pb_max = float(p.get("pb_max", 5.0))
        trend_guard = bool(p.get("trend_guard", True))
        rs_min = int(p.get("rs_min", 55))
        ma_days = int(p.get("ma_days", 150))
        heat_min = float(p.get("heat_min", 42.0))
        val_min = float(p.get("valuation_min", 50.0))
        crowd_max = float(p.get("crowding_max", 65.0))
        ma_n_val = float(df["close"].iloc[-ma_days:].mean()) if len(df) >= ma_days else close
        heat = float(_sector_heat_series(df).iloc[-1])
        val_score = _valuation_score(pe, pb, pe_max, pb_max)
        crowd = float(_crowding_series(df).iloc[-1])
        if pe is not None and pe <= pe_max:
            score += 8
            tags.append("安全边际")
        if pb is not None and pb <= pb_max:
            score += 6
            tags.append("资产定价")
        if c.get("RS", 0) >= rs_min:
            score += 3
            tags.append("基本面趋势")
        if trend_guard and close < ma_n_val:
            score -= 6
        tags.append(f"热度{heat:.0f}")
        tags.append(f"估值分位{val_score:.0f}")
        tags.append(f"拥挤{crowd:.0f}")
        if heat >= heat_min:
            score += 2
        if val_score >= val_min:
            score += 6
        if crowd > crowd_max:
            score -= 7

    elif strategy_id == "emotion":
        vol_ratio_min = float(p.get("vol_ratio_min", 1.2))
        rs_min = int(p.get("rs_min", 50))
        phase = str(_emotion_phase_series(df).iloc[-1])
        vol_ma20 = float(df["volume"].rolling(20).mean().iloc[-1]) if len(df) >= 20 else 1
        vol_now = float(df["volume"].iloc[-1])
        vr = vol_now / max(vol_ma20, 1)
        ret5 = (close / float(df["close"].iloc[-6]) - 1) * 100 if len(df) >= 6 else 0
        if phase in ("启动", "发酵"):
            score += 15
            tags.append(f"情绪{phase}")
        elif phase == "高潮":
            score -= 5
            tags.append("情绪高潮⚠")
        elif phase == "冰点":
            score += 5
            tags.append("情绪冰点")
        if vr >= vol_ratio_min:
            score += 8
            tags.append(f"量比{vr:.1f}")
        if c.get("RS", 0) >= rs_min:
            score += 5
        if ret5 > 5:
            score += 5
            tags.append("短期强势")

    elif strategy_id == "event":
        impact_threshold = float(p.get("impact_threshold", 3.0))
        vol_ratio_min = float(p.get("vol_ratio_min", 1.5))
        rs_min = int(p.get("rs_min", 40))
        vol_ma20 = float(df["volume"].rolling(20).mean().iloc[-1]) if len(df) >= 20 else 1
        vol_now = float(df["volume"].iloc[-1])
        vr = vol_now / max(vol_ma20, 1)
        ret1 = (close / float(df["close"].iloc[-2]) - 1) * 100 if len(df) >= 2 else 0
        if abs(ret1) >= impact_threshold and vr >= vol_ratio_min:
            score += 20
            if ret1 > 0:
                tags.append(f"利好冲击+{ret1:.1f}%")
            else:
                tags.append(f"利空冲击{ret1:.1f}%")
        elif abs(ret1) >= impact_threshold:
            score += 10
            tags.append(f"异动{ret1:+.1f}%")
        if vr >= vol_ratio_min:
            score += 5
            tags.append(f"异常放量{vr:.1f}")
        if c.get("RS", 0) >= rs_min:
            score += 3

    c["评分"] = round(score, 1)
    c["策略"] = strategy_name(strategy_id)
    c["策略标签"] = " / ".join(tags) if tags else "-"
    c["策略细分"] = c["策略标签"]
    return c


def apply_backtest_profile(df: pd.DataFrame, strategy_id: str,
                           fundamental: dict | None = None,
                           params: dict | None = None) -> pd.DataFrame:
    out = df.copy()
    p = get_strategy_default_params(strategy_id)
    if params:
        p.update(params)
    close = out["close"]
    ma50 = out["ma50"] if "ma50" in out.columns else close.rolling(50).mean()
    ma150 = out["ma150"] if "ma150" in out.columns else close.rolling(150).mean()
    ma200 = out["ma200"] if "ma200" in out.columns else close.rolling(200).mean()
    high20 = out["high"].shift(1).rolling(20).max()
    high55 = out["high"].shift(1).rolling(55).max()

    pe = None
    pb = None
    if fundamental:
        try:
            v = fundamental.get("pe_dynamic")
            pe = float(v) if v not in (None, "", "-") else None
        except Exception:
            pe = None
        try:
            v = fundamental.get("pb")
            pb = float(v) if v not in (None, "", "-") else None
        except Exception:
            pb = None

    out["emotion_phase"] = _emotion_phase_series(out)
    base = out.get("buy_signal", False).astype(bool)
    strategy_entry_reason = ""
    valuation_const = _valuation_score(pe, pb, 40.0, 6.0)
    if strategy_id == "sepa":
        rs_min = int(p.get("rs_min", 70))
        volume_ratio_min = float(p.get("volume_ratio_min", 0.8))
        rs_ok = out.get("rs_rating", 0) >= rs_min
        vol_ok = out.get("volume", 0) >= out.get("vol_ma50", 0) * volume_ratio_min
        new_buy = base & rs_ok & vol_ok
        strategy_entry_reason = f"SEPA: 趋势+VCP, RS≥{rs_min}, 量比≥{volume_ratio_min:.2f}"
    elif strategy_id == "canslim":
        rs_min = int(p.get("rs_min", 80))
        vol_min = float(p.get("volume_ratio_min", 1.2))
        near_high_min_pct = float(p.get("near_high_52w_min_pct", -12.0))
        c_mom_min_pct = float(p.get("c_mom_min_pct", 8.0))
        a_trend_min_pct = float(p.get("a_trend_min_pct", 20.0))
        rs_ok = out.get("rs_rating", 0) >= rs_min
        vol_ok = out.get("volume", 0) >= out.get("vol_ma50", 0) * vol_min
        near_high = ((close / out.get("week52_high", close)) - 1.0) * 100 >= near_high_min_pct
        c_growth = close.pct_change(20) * 100 >= c_mom_min_pct
        a_growth = close.pct_change(120) * 100 >= a_trend_min_pct
        market_ok = out.get("trend_pass", False)
        new_buy = base & rs_ok & vol_ok & near_high & c_growth & a_growth & market_ok
        strategy_entry_reason = (
            f"CANSLIM: C/A动量 + N新高 + S放量 + L强势 (RS≥{rs_min})"
        )
    elif strategy_id == "turtle":
        b_short = int(p.get("breakout_short", 20))
        b_long = int(p.get("breakout_long", 55))
        ma_n = int(p.get("trend_ma_days", 50))
        atr_window = int(p.get("atr_window", 20))
        atr_target_pct = float(p.get("atr_target_pct", 0.03))
        max_unit_scale = float(p.get("max_unit_scale", 1.4))
        min_unit_scale = float(p.get("min_unit_scale", 0.45))
        high_s = out["high"].shift(1).rolling(b_short).max()
        high_l = out["high"].shift(1).rolling(b_long).max()
        ma_n_val = close.rolling(ma_n).mean()
        new_buy = (close >= high_s) & (close >= high_l) & (close > ma_n_val)
        tr = np.maximum(out["high"] - out["low"], np.maximum(
            (out["high"] - out["close"].shift(1)).abs(),
            (out["low"] - out["close"].shift(1)).abs(),
        ))
        atr = tr.rolling(atr_window).mean()
        atr_pct = atr / close.replace(0, np.nan)
        scale = (atr_target_pct / atr_pct).replace([np.inf, -np.inf], np.nan).fillna(1.0)
        scale = scale.clip(lower=min_unit_scale, upper=max_unit_scale)
        out["risk_unit_scale"] = scale
        strategy_entry_reason = (
            f"海龟: {b_short}/{b_long}日突破, ATR目标={atr_target_pct:.2%}"
        )
    elif strategy_id == "graham":
        pe_max = float(p.get("pe_max", 20.0))
        pb_max = float(p.get("pb_max", 2.5))
        trend_guard = bool(p.get("trend_guard", True))
        val_ok = (pe is not None and pe <= pe_max) and (pb is not None and pb <= pb_max)
        new_buy = pd.Series(val_ok, index=out.index)
        if trend_guard:
            new_buy = new_buy & (close > ma200)
        strategy_entry_reason = f"格雷厄姆: PE≤{pe_max:.1f}, PB≤{pb_max:.1f}"
    elif strategy_id == "livermore":
        b_days = int(p.get("breakout_days", 20))
        rs_min = int(p.get("rs_min", 65))
        ma_n = int(p.get("trend_ma_days", 50))
        high_n = out["high"].shift(1).rolling(b_days).max()
        ma_n_val = close.rolling(ma_n).mean()
        rs_ok = out.get("rs_rating", 0) >= rs_min
        new_buy = (close >= high_n) & (close > ma_n_val) & rs_ok
        strategy_entry_reason = f"利弗莫尔: 关键点突破({b_days}) + RS≥{rs_min}"
    elif strategy_id == "covell":
        b_days = int(p.get("breakout_days", 55))
        ma_n = int(p.get("ma_days", 200))
        vol_min = float(p.get("vol_filter_min", 0.7))
        high_n = out["high"].shift(1).rolling(b_days).max()
        ma_n_val = close.rolling(ma_n).mean()
        vol_ok = out.get("volume", 0) >= out.get("vol_ma50", 0) * vol_min
        new_buy = (close > ma_n_val) & (close >= high_n) & vol_ok
        strategy_entry_reason = f"卡沃尔: {b_days}日突破 + MA{ma_n}顺势"
    elif strategy_id == "dow":
        ma_fast = int(p.get("ma_fast", 50))
        ma_mid = int(p.get("ma_mid", 150))
        ma_slow = int(p.get("ma_slow", 200))
        rs_min = int(p.get("rs_min", 60))
        ma_f = close.rolling(ma_fast).mean()
        ma_m = close.rolling(ma_mid).mean()
        ma_s = close.rolling(ma_slow).mean()
        rs_ok = out.get("rs_rating", 0) >= rs_min
        new_buy = (ma_f > ma_m) & (ma_m > ma_s) & (close > ma_f) & rs_ok
        strategy_entry_reason = f"道氏: MA{ma_fast}>{ma_mid}>{ma_slow} 且 RS≥{rs_min}"
    elif strategy_id == "lynch":
        pe_low = float(p.get("pe_low", 8.0))
        pe_high = float(p.get("pe_high", 35.0))
        rs_min = int(p.get("rs_min", 60))
        trend_guard = bool(p.get("trend_guard", True))
        val_ok = (pe is None) or (pe_low <= pe <= pe_high)
        new_buy = val_ok & (out.get("rs_rating", 0) >= rs_min)
        if trend_guard:
            new_buy = new_buy & out.get("trend_pass", False)
        strategy_entry_reason = f"林奇: GARP估值区间 + RS≥{rs_min}"
    elif strategy_id == "buffett":
        pe_max = float(p.get("pe_max", 35.0))
        pb_max = float(p.get("pb_max", 6.0))
        trend_guard = bool(p.get("trend_guard", True))
        val_ok = (pe is None or pe <= pe_max) and (pb is None or pb <= pb_max)
        new_buy = val_ok
        if trend_guard:
            new_buy = new_buy & (close > ma200)
        strategy_entry_reason = f"巴菲特: 质量估值过滤 PE≤{pe_max:.1f}, PB≤{pb_max:.1f}"
    elif strategy_id == "larry":
        b_days = int(p.get("breakout_days", 20))
        vol_min = float(p.get("volume_ratio_min", 1.2))
        rs_min = int(p.get("rs_min", 55))
        high_n = out["high"].shift(1).rolling(b_days).max()
        vol_ok = out.get("volume", 0) > out.get("vol_ma50", 0) * vol_min
        rs_ok = out.get("rs_rating", 0) >= rs_min
        new_buy = (close >= high_n) & vol_ok & rs_ok
        strategy_entry_reason = f"拉里: 短线突破({b_days}) + 放量 + RS≥{rs_min}"
    elif strategy_id == "cn_yz_yangjia":
        b_days = int(p.get("breakout_days", 12))
        vol_min = float(p.get("volume_ratio_min", 1.25))
        pullback_max = float(p.get("pullback_max_pct", 6.0))
        rs_min = int(p.get("rs_min", 60))
        allow_start = bool(p.get("allow_phase_start", True))
        allow_ferment = bool(p.get("allow_phase_ferment", True))
        allow_climax = bool(p.get("allow_phase_climax", False))
        high_n = out["high"].shift(1).rolling(b_days).max()
        pullback = ((high_n - close) / high_n * 100).abs()
        vol_ok = out.get("volume", 0) >= out.get("vol_ma50", 0) * vol_min
        rs_ok = out.get("rs_rating", 0) >= rs_min
        phase = _emotion_phase_series(out)
        phase_ok = (
            ((phase == "启动") & allow_start)
            | ((phase == "发酵") & allow_ferment)
            | ((phase == "高潮") & allow_climax)
        )
        new_buy = (close >= high_n * 0.995) & (pullback <= pullback_max) & vol_ok & rs_ok & phase_ok
        strategy_entry_reason = "养家: 分歧转一致 + 合力放量 + 情绪阶段过滤"
    elif strategy_id == "cn_yz_zhaolao":
        near_high = float(p.get("leader_near_high_pct", -8.0))
        vol_min = float(p.get("volume_ratio_min", 1.35))
        rs_min = int(p.get("rs_min", 75))
        b_days = int(p.get("breakout_days", 20))
        allow_start = bool(p.get("allow_phase_start", True))
        allow_ferment = bool(p.get("allow_phase_ferment", True))
        allow_climax = bool(p.get("allow_phase_climax", False))
        high_n = out["high"].shift(1).rolling(b_days).max()
        near_high_ok = ((close / out.get("week52_high", close)) - 1) * 100 >= near_high
        vol_ok = out.get("volume", 0) >= out.get("vol_ma50", 0) * vol_min
        rs_ok = out.get("rs_rating", 0) >= rs_min
        phase = _emotion_phase_series(out)
        phase_ok = (
            ((phase == "启动") & allow_start)
            | ((phase == "发酵") & allow_ferment)
            | ((phase == "高潮") & allow_climax)
        )
        new_buy = (close >= high_n) & near_high_ok & vol_ok & rs_ok & phase_ok
        strategy_entry_reason = "赵老哥: 龙头主升接力 + 情绪阶段过滤"
    elif strategy_id == "cn_yz_asking":
        b_days = int(p.get("breakout_days", 18))
        vol_min = float(p.get("volume_ratio_min", 1.15))
        rs_min = int(p.get("rs_min", 65))
        high_n = out["high"].shift(1).rolling(b_days).max()
        vol_ok = out.get("volume", 0) >= out.get("vol_ma50", 0) * vol_min
        rs_ok = out.get("rs_rating", 0) >= rs_min
        allow_start = bool(p.get("allow_phase_start", True))
        allow_ferment = bool(p.get("allow_phase_ferment", True))
        allow_climax = bool(p.get("allow_phase_climax", False))
        phase = _emotion_phase_series(out)
        phase_ok = (
            ((phase == "启动") & allow_start)
            | ((phase == "发酵") & allow_ferment)
            | ((phase == "高潮") & allow_climax)
        )
        new_buy = (close >= high_n) & vol_ok & rs_ok & phase_ok
        strategy_entry_reason = "Asking: 主升浪突破 + 情绪阶段过滤"
    elif strategy_id == "cn_pm_danbin":
        pe_max = float(p.get("pe_max", 45.0))
        pb_max = float(p.get("pb_max", 8.0))
        trend_guard = bool(p.get("trend_guard", True))
        rs_min = int(p.get("rs_min", 55))
        heat_min = float(p.get("heat_min", 50.0))
        val_min = float(p.get("valuation_min", 35.0))
        crowd_max = float(p.get("crowding_max", 75.0))
        heat = _sector_heat_series(out)
        crowd = _crowding_series(out)
        val_score = _valuation_score(pe, pb, pe_max, pb_max)
        val_ok = (pe is None or pe <= pe_max) and (pb is None or pb <= pb_max)
        rs_ok = out.get("rs_rating", 0) >= rs_min
        new_buy = val_ok & rs_ok & (heat >= heat_min) & (crowd <= crowd_max) & (val_score >= val_min)
        if trend_guard:
            new_buy = new_buy & (close > ma200)
        strategy_entry_reason = "但斌: 赛道热度 + 估值分位 + 拥挤度过滤"
    elif strategy_id == "cn_pm_linyuan":
        pe_max = float(p.get("pe_max", 35.0))
        pb_max = float(p.get("pb_max", 7.0))
        trend_guard = bool(p.get("trend_guard", True))
        rs_min = int(p.get("rs_min", 50))
        heat_min = float(p.get("heat_min", 45.0))
        val_min = float(p.get("valuation_min", 40.0))
        crowd_max = float(p.get("crowding_max", 78.0))
        heat = _sector_heat_series(out)
        crowd = _crowding_series(out)
        val_score = _valuation_score(pe, pb, pe_max, pb_max)
        val_ok = (pe is None or pe <= pe_max) and (pb is None or pb <= pb_max)
        rs_ok = out.get("rs_rating", 0) >= rs_min
        new_buy = val_ok & rs_ok & (heat >= heat_min) & (crowd <= crowd_max) & (val_score >= val_min)
        if trend_guard:
            new_buy = new_buy & (close > ma150)
        strategy_entry_reason = "林园: 赛道热度 + 估值分位 + 拥挤度过滤"
    elif strategy_id == "cn_inst_qiuguolu":
        pe_max = float(p.get("pe_max", 28.0))
        pb_max = float(p.get("pb_max", 5.0))
        trend_guard = bool(p.get("trend_guard", True))
        rs_min = int(p.get("rs_min", 55))
        ma_days = int(p.get("ma_days", 150))
        ma_n = close.rolling(ma_days).mean()
        heat_min = float(p.get("heat_min", 42.0))
        val_min = float(p.get("valuation_min", 50.0))
        crowd_max = float(p.get("crowding_max", 65.0))
        heat = _sector_heat_series(out)
        crowd = _crowding_series(out)
        val_score = _valuation_score(pe, pb, pe_max, pb_max)
        val_ok = (pe is None or pe <= pe_max) and (pb is None or pb <= pb_max)
        rs_ok = out.get("rs_rating", 0) >= rs_min
        new_buy = val_ok & rs_ok & (heat >= heat_min) & (crowd <= crowd_max) & (val_score >= val_min)
        if trend_guard:
            new_buy = new_buy & (close > ma_n)
        strategy_entry_reason = "邱国鹭: 安全边际 + 热度/估值/拥挤度"
    elif strategy_id == "emotion":
        vol_ratio_min = float(p.get("vol_ratio_min", 1.2))
        rs_min = int(p.get("rs_min", 50))
        phase = _emotion_phase_series(out)
        out["emotion_phase"] = phase
        vol_ma20 = volume.shift(1).rolling(20).mean()
        vol_ratio = volume / vol_ma20.replace(0, np.nan)
        allow_start = bool(p.get("allow_phase_start", True))
        allow_ferment = bool(p.get("allow_phase_ferment", True))
        phase_ok = ((phase == "启动") & allow_start) | ((phase == "发酵") & allow_ferment)
        vol_ok = vol_ratio >= vol_ratio_min
        rs_ok = out.get("rs_rating", 0) >= rs_min
        new_buy = phase_ok & vol_ok & rs_ok & (close > close.shift(1).rolling(50).mean())
        strategy_entry_reason = "情绪博弈: 启动/发酵阶段 + 量比放大"
    elif strategy_id == "event":
        impact_thresh = float(p.get("impact_threshold", 3.0))
        vol_ratio_min = float(p.get("vol_ratio_min", 1.5))
        rs_min = int(p.get("rs_min", 40))
        ret1 = close.pct_change() * 100
        vol_ma20 = volume.shift(1).rolling(20).mean()
        vol_ratio = volume / vol_ma20.replace(0, np.nan)
        event_hit = (ret1.abs() >= impact_thresh) & (vol_ratio >= vol_ratio_min) & (ret1 > 0)
        rs_ok = out.get("rs_rating", 0) >= rs_min
        new_buy = event_hit & rs_ok
        strategy_entry_reason = "事件驱动: 利好冲击 + 异常放量"
    else:
        new_buy = base
        strategy_entry_reason = "默认信号"

    out["buy_signal"] = new_buy.fillna(False).astype(bool)
    if "risk_unit_scale" not in out.columns:
        out["risk_unit_scale"] = 1.0
    out["strategy_id"] = strategy_id
    out["strategy_entry_reason"] = np.where(
        out["buy_signal"], strategy_entry_reason, ""
    )
    out["sector_heat_score"] = _sector_heat_series(out)
    out["crowding_score"] = _crowding_series(out)
    out["valuation_score"] = valuation_const

    # 策略特有退出规则（与通用风控并行，回测执行时优先触发）。
    strategy_exit = pd.Series(False, index=out.index)
    strategy_exit_reason = ""
    if strategy_id == "sepa":
        strategy_exit = pd.Series(False, index=out.index)
    elif strategy_id == "canslim":
        strategy_exit = close < ma50
        strategy_exit_reason = "CANSLIM 退出: 跌破MA50"
    elif strategy_id == "turtle":
        b_short = int(p.get("breakout_short", 20))
        ma_n = int(p.get("trend_ma_days", 50))
        low_s = out["low"].shift(1).rolling(b_short).min()
        ma_n_val = close.rolling(ma_n).mean()
        strategy_exit = (close < ma_n_val) | (close < low_s)
        strategy_exit_reason = f"海龟退出: 跌破MA{ma_n}或{b_short}日低点"
    elif strategy_id == "graham":
        if bool(p.get("trend_guard", True)):
            strategy_exit = close < ma200
            strategy_exit_reason = "格雷厄姆退出: 趋势保护失效(跌破MA200)"
    elif strategy_id == "livermore":
        ma_n = int(p.get("trend_ma_days", 50))
        strategy_exit = close < close.rolling(ma_n).mean()
        strategy_exit_reason = f"利弗莫尔退出: 跌破MA{ma_n}"
    elif strategy_id == "covell":
        ma_n = int(p.get("ma_days", 200))
        strategy_exit = close < close.rolling(ma_n).mean()
        strategy_exit_reason = f"卡沃尔退出: 跌破MA{ma_n}"
    elif strategy_id == "dow":
        ma_fast = int(p.get("ma_fast", 50))
        ma_mid = int(p.get("ma_mid", 150))
        ma_f = close.rolling(ma_fast).mean()
        ma_m = close.rolling(ma_mid).mean()
        strategy_exit = (ma_f < ma_m) | (close < ma_f)
        strategy_exit_reason = "道氏退出: 均线结构破坏"
    elif strategy_id == "lynch":
        if bool(p.get("trend_guard", True)):
            strategy_exit = close < ma200
            strategy_exit_reason = "林奇退出: 跌破MA200"
    elif strategy_id == "buffett":
        if bool(p.get("trend_guard", True)):
            strategy_exit = close < ma200
            strategy_exit_reason = "巴菲特退出: 跌破MA200"
    elif strategy_id == "larry":
        ma10 = close.rolling(10).mean()
        strategy_exit = close < ma10
        strategy_exit_reason = "拉里退出: 跌破MA10"
    elif strategy_id == "cn_yz_yangjia":
        ma5 = close.rolling(5).mean()
        strategy_exit = close < ma5
        strategy_exit_reason = "养家退出: 一致转分歧，跌破MA5"
    elif strategy_id == "cn_yz_zhaolao":
        ma10 = close.rolling(10).mean()
        strategy_exit = close < ma10
        strategy_exit_reason = "赵老哥退出: 龙头惯性失效，跌破MA10"
    elif strategy_id == "cn_yz_asking":
        exit_ma = int(p.get("exit_ma_days", 10))
        ma_n = close.rolling(exit_ma).mean()
        strategy_exit = close < ma_n
        strategy_exit_reason = f"Asking退出: 截断亏损，跌破MA{exit_ma}"
    elif strategy_id == "cn_pm_danbin":
        if bool(p.get("trend_guard", True)):
            strategy_exit = close < ma200
            strategy_exit_reason = "但斌退出: 长周期趋势破坏(MA200)"
    elif strategy_id == "cn_pm_linyuan":
        if bool(p.get("trend_guard", True)):
            strategy_exit = close < ma150
            strategy_exit_reason = "林园退出: 趋势保护失效(MA150)"
    elif strategy_id == "cn_inst_qiuguolu":
        ma_days = int(p.get("ma_days", 150))
        if bool(p.get("trend_guard", True)):
            strategy_exit = close < close.rolling(ma_days).mean()
            strategy_exit_reason = f"机构退出: 跌破MA{ma_days}"

    elif strategy_id == "emotion":
        ma5 = close.rolling(5).mean()
        phase = _emotion_phase_series(out)
        out["emotion_phase"] = phase
        strategy_exit = (close < ma5) | (phase == "退潮") | (phase == "冰点")
        strategy_exit_reason = "情绪退出: 情绪退潮/冰点或跌破MA5"
        entry_reason = "情绪博弈: 启动/发酵阶段 + 量比放大"

    elif strategy_id == "event":
        hold_max = int(p.get("hold_days_max", 10))
        ma10 = close.rolling(10).mean()
        strategy_exit = close < ma10
        strategy_exit_reason = f"事件退出: 跌破MA10或持有超{hold_max}天"
        entry_reason = "事件驱动: 异常涨跌幅 + 放量冲击"

    out["strategy_exit_signal"] = strategy_exit.fillna(False).astype(bool)
    out["strategy_exit_reason"] = np.where(out["strategy_exit_signal"], strategy_exit_reason, "")
    return out
