"""
市场状态机

目标：
1. 统一对市场环境的判断口径
2. 让选股、AI决策、风险控制、OpenClaw 共享同一个“市场状态”
"""
from __future__ import annotations

import json
from datetime import datetime

import numpy as np

from desktop.data_access import get_kv_json, get_repo, set_kv_json


def compute_market_state() -> dict:
    """
    输出统一市场状态：
    - strong_trend
    - rotation
    - risk_off
    - neutral
    """
    repo = get_repo()

    state = {
        "state": "neutral",
        "dist_count": 0,
        "index_return_5d": 0.0,
        "sector_top3": [],
        "sector_bottom3": [],
        "negative_news_ratio": 0.0,
        "risk_var95": 0.0,
        "reason": "",
        "updated_at": datetime.now().isoformat(),
    }

    # 指数环境
    idx_rows = repo.fetchall(
        "SELECT close, volume FROM daily_kline WHERE code='000300' ORDER BY date DESC LIMIT 25",
        (),
    )
    if len(idx_rows) >= 20:
        idx_rows = list(reversed(idx_rows))
        closes = np.array([r[0] for r in idx_rows], dtype=float)
        vols = np.array([r[1] for r in idx_rows], dtype=float)
        dist = 0
        for i in range(1, len(closes)):
            pct = (closes[i] - closes[i - 1]) / closes[i - 1] if closes[i - 1] > 0 else 0
            if pct < -0.002 and vols[i] > vols[i - 1]:
                dist += 1
        state["dist_count"] = dist
        if len(closes) >= 6:
            state["index_return_5d"] = round((closes[-1] / closes[-6] - 1) * 100, 2)

    # 板块轮动
    try:
        data = get_kv_json("sector_rotation") or {}
        state["sector_top3"] = data.get("top3", [])
        state["sector_bottom3"] = data.get("bottom3", [])
    except Exception:
        pass

    # 舆情
    try:
        data = get_kv_json("news_sentiment_snapshot") or {}
        state["negative_news_ratio"] = float(data.get("negative_ratio", 0))
    except Exception:
        pass

    # 风险缓存
    try:
        data = get_kv_json("portfolio_risk") or {}
        state["risk_var95"] = abs(float(data.get("var95", 0)))
    except Exception:
        pass

    # 状态机判定
    if state["dist_count"] >= 5 or state["risk_var95"] > 100000 or state["negative_news_ratio"] >= 0.6:
        state["state"] = "risk_off"
        state["reason"] = "分布日偏多/组合风险高/负面舆情偏强"
    elif state["index_return_5d"] > 2 and len(state["sector_top3"]) >= 2:
        state["state"] = "strong_trend"
        state["reason"] = "指数强势 + 热门板块明确"
    elif state["index_return_5d"] > 0 and len(state["sector_top3"]) >= 2:
        state["state"] = "rotation"
        state["reason"] = "指数温和向上 + 板块轮动明显"
    else:
        state["state"] = "neutral"
        state["reason"] = "无明显单边趋势"

    return state


def save_market_state_snapshot():
    state = compute_market_state()
    set_kv_json("market_state_snapshot", state)
    return state


def get_market_state_snapshot() -> dict:
    row = get_kv_json("market_state_snapshot")
    if row and isinstance(row, dict):
        return row
    if isinstance(row, str):
        try:
            return json.loads(row)
        except Exception:
            pass
    return compute_market_state()
