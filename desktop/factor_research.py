"""
因子研究模块
支持自定义因子回测：换手率、市值、动量、波动率、量价因子等。
单因子IC/IR分析 + 分层回测。
"""
import os
import sqlite3
import numpy as np
from dataclasses import dataclass
from datetime import datetime

DB_PATH = os.path.join("data_cache", "quant.db")


@dataclass
class FactorResult:
    factor_name: str = ""
    ic_mean: float = 0.0
    ic_std: float = 0.0
    ir: float = 0.0
    ic_positive_pct: float = 0.0
    top_group_return: float = 0.0
    bottom_group_return: float = 0.0
    long_short_return: float = 0.0
    monotonicity: float = 0.0
    sample_count: int = 0


BUILTIN_FACTORS = {
    "momentum_5d": "5日动量（近5日涨幅）",
    "momentum_20d": "20日动量（近20日涨幅）",
    "momentum_60d": "60日动量（近60日涨幅）",
    "volatility_20d": "20日波动率（标准差/均值）",
    "volume_ratio": "量比（最新量/20日均量）",
    "turnover_proxy": "换手率代理（量/流通盘估算）",
    "price_ma_distance": "MA偏离度（现价/MA20-1）",
    "high_distance": "离高点距离（现价/52周高-1）",
    "vcp_contraction": "VCP收缩度（后20日波动/前20日波动）",
}


def _load_stock_data(min_days: int = 60, max_stocks: int = 300) -> dict:
    """加载所有有足够数据的股票日线。"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cur = conn.execute("""
        SELECT code FROM daily_kline GROUP BY code
        HAVING COUNT(*) >= ? ORDER BY COUNT(*) DESC LIMIT ?
    """, (min_days, max_stocks))
    codes = [r[0] for r in cur.fetchall()]

    stock_data = {}
    for code in codes:
        cur2 = conn.execute(
            "SELECT date, close, high, low, volume FROM daily_kline WHERE code=? ORDER BY date",
            (code,),
        )
        rows = cur2.fetchall()
        if len(rows) >= min_days:
            stock_data[code] = {
                "dates": [r[0] for r in rows],
                "close": np.array([r[1] for r in rows]),
                "high": np.array([r[2] for r in rows]),
                "low": np.array([r[3] for r in rows]),
                "volume": np.array([r[4] for r in rows]),
            }
    conn.close()
    return stock_data


def compute_factor(stock_data: dict, factor_name: str) -> dict[str, float]:
    """计算单个因子值（返回 {code: factor_value}）。"""
    result = {}
    for code, data in stock_data.items():
        c = data["close"]
        v = data["volume"]
        h = data["high"]
        n = len(c)
        if n < 60:
            continue

        try:
            if factor_name == "momentum_5d":
                result[code] = float((c[-1] / c[-6] - 1) * 100) if c[-6] > 0 else 0
            elif factor_name == "momentum_20d":
                result[code] = float((c[-1] / c[-21] - 1) * 100) if n >= 21 and c[-21] > 0 else 0
            elif factor_name == "momentum_60d":
                result[code] = float((c[-1] / c[-61] - 1) * 100) if n >= 61 and c[-61] > 0 else 0
            elif factor_name == "volatility_20d":
                result[code] = float(np.std(c[-20:]) / max(np.mean(c[-20:]), 1e-6))
            elif factor_name == "volume_ratio":
                avg_v = float(np.mean(v[-20:])) if np.mean(v[-20:]) > 0 else 1
                result[code] = float(v[-1]) / avg_v
            elif factor_name == "turnover_proxy":
                avg_v = float(np.mean(v[-5:]))
                result[code] = avg_v / max(float(np.mean(v[-60:])), 1) if n >= 60 else 1
            elif factor_name == "price_ma_distance":
                ma20 = float(np.mean(c[-20:]))
                result[code] = float(c[-1] / ma20 - 1) * 100 if ma20 > 0 else 0
            elif factor_name == "high_distance":
                h52 = float(np.max(h[-250:])) if n >= 250 else float(np.max(h))
                result[code] = float(c[-1] / h52 - 1) * 100 if h52 > 0 else 0
            elif factor_name == "vcp_contraction":
                if n >= 40:
                    std_e = float(np.std(c[-40:-20]))
                    std_l = float(np.std(c[-20:]))
                    result[code] = std_l / max(std_e, 1e-6)
                else:
                    result[code] = 1.0
        except Exception:
            continue
    return result


def run_factor_analysis(factor_name: str, forward_days: int = 5,
                        n_groups: int = 5, max_stocks: int = 300) -> FactorResult:
    """
    单因子分析：
    1. 计算因子值
    2. 计算IC（因子与未来收益的相关性）
    3. 分层回测（按因子值分5组，看各组收益）
    """
    stock_data = _load_stock_data(min_days=60 + forward_days, max_stocks=max_stocks)
    if len(stock_data) < 20:
        return FactorResult(factor_name=factor_name)

    factors = compute_factor(stock_data, factor_name)
    if len(factors) < 20:
        return FactorResult(factor_name=factor_name)

    # 计算未来 N 日收益
    forward_returns = {}
    for code, data in stock_data.items():
        if code not in factors:
            continue
        c = data["close"]
        if len(c) >= forward_days + 1:
            fwd = (c[-1] / c[-(forward_days + 1)] - 1) * 100
            forward_returns[code] = float(fwd)

    common = set(factors.keys()) & set(forward_returns.keys())
    if len(common) < 20:
        return FactorResult(factor_name=factor_name)

    codes = sorted(common)
    f_arr = np.array([factors[c] for c in codes])
    r_arr = np.array([forward_returns[c] for c in codes])

    # IC（秩相关）
    from scipy.stats import spearmanr
    try:
        ic, _ = spearmanr(f_arr, r_arr)
    except Exception:
        ic = float(np.corrcoef(f_arr, r_arr)[0, 1]) if np.std(f_arr) > 0 else 0

    # 分层回测
    sorted_idx = np.argsort(f_arr)
    group_size = len(sorted_idx) // n_groups
    group_returns = []
    for g in range(n_groups):
        start = g * group_size
        end = start + group_size if g < n_groups - 1 else len(sorted_idx)
        g_returns = r_arr[sorted_idx[start:end]]
        group_returns.append(float(np.mean(g_returns)))

    # 单调性（组间收益是否递增/递减）
    diffs = [group_returns[i + 1] - group_returns[i] for i in range(len(group_returns) - 1)]
    if all(d > 0 for d in diffs):
        monotonicity = 1.0
    elif all(d < 0 for d in diffs):
        monotonicity = -1.0
    else:
        positive = sum(1 for d in diffs if d > 0)
        monotonicity = round((positive / len(diffs) - 0.5) * 2, 2)

    result = FactorResult(
        factor_name=factor_name,
        ic_mean=round(float(ic), 4),
        ic_std=0.0,
        ir=round(float(ic) / 0.1, 2) if abs(ic) > 0.001 else 0,
        ic_positive_pct=100.0 if ic > 0 else 0.0,
        top_group_return=round(group_returns[-1], 2),
        bottom_group_return=round(group_returns[0], 2),
        long_short_return=round(group_returns[-1] - group_returns[0], 2),
        monotonicity=monotonicity,
        sample_count=len(common),
    )
    return result


def run_all_factors(forward_days: int = 5) -> list[dict]:
    """运行所有内置因子的分析。"""
    results = []
    for name, desc in BUILTIN_FACTORS.items():
        try:
            r = run_factor_analysis(name, forward_days=forward_days)
            results.append({
                "name": name,
                "desc": desc,
                "ic": r.ic_mean,
                "ir": r.ir,
                "top_return": r.top_group_return,
                "bottom_return": r.bottom_group_return,
                "long_short": r.long_short_return,
                "monotonicity": r.monotonicity,
                "samples": r.sample_count,
            })
        except Exception:
            results.append({"name": name, "desc": desc, "error": True})
    results.sort(key=lambda x: abs(x.get("ic", 0)), reverse=True)
    return results
