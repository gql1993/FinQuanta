"""
组合优化模块
基于均值-方差（Markowitz）和风险平价模型优化多股票持仓权重。
"""
import os
import sqlite3
import numpy as np
from datetime import datetime

DB_PATH = os.path.join("data_cache", "quant.db")


def get_returns_matrix(codes: list[str], lookback: int = 60) -> tuple:
    """获取多只股票的日收益率矩阵。"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    all_returns = {}

    for code in codes:
        cur = conn.execute(
            "SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT ?",
            (code, lookback + 1),
        )
        rows = [r[0] for r in cur.fetchall()]
        if len(rows) < lookback:
            continue
        rows = rows[::-1]
        prices = np.array(rows)
        rets = np.diff(prices) / prices[:-1]
        all_returns[code] = rets[-lookback:]

    conn.close()

    common_len = min(len(v) for v in all_returns.values()) if all_returns else 0
    if common_len < 20:
        return [], np.array([])

    valid_codes = [c for c in codes if c in all_returns]
    matrix = np.column_stack([all_returns[c][-common_len:] for c in valid_codes])
    return valid_codes, matrix


def optimize_mean_variance(codes: list[str], lookback: int = 60,
                           risk_free: float = 0.03 / 250,
                           n_portfolios: int = 5000) -> dict:
    """
    均值-方差优化（蒙特卡洛模拟法）。
    返回最大夏普比率的权重组合。
    """
    valid_codes, returns = get_returns_matrix(codes, lookback)
    if len(valid_codes) < 2:
        return {"error": "有效股票不足2只"}

    n = len(valid_codes)
    mean_rets = np.mean(returns, axis=0)
    cov_matrix = np.cov(returns.T)

    best_sharpe = -999
    best_weights = np.ones(n) / n
    all_results = []

    for _ in range(n_portfolios):
        w = np.random.random(n)
        w /= w.sum()

        port_ret = float(np.dot(w, mean_rets)) * 250
        port_vol = float(np.sqrt(np.dot(w, np.dot(cov_matrix, w)))) * np.sqrt(250)
        sharpe = (port_ret - 0.03) / port_vol if port_vol > 0 else 0

        all_results.append((w, port_ret, port_vol, sharpe))

        if sharpe > best_sharpe:
            best_sharpe = sharpe
            best_weights = w.copy()

    port_ret = float(np.dot(best_weights, mean_rets)) * 250
    port_vol = float(np.sqrt(np.dot(best_weights, np.dot(cov_matrix, best_weights)))) * np.sqrt(250)

    weights = {valid_codes[i]: round(float(best_weights[i]) * 100, 1) for i in range(n)}
    weights = dict(sorted(weights.items(), key=lambda x: x[1], reverse=True))

    return {
        "method": "均值-方差（最大夏普）",
        "weights": weights,
        "expected_return": round(port_ret * 100, 2),
        "expected_vol": round(port_vol * 100, 2),
        "sharpe": round(best_sharpe, 2),
        "stocks": valid_codes,
    }


def optimize_risk_parity(codes: list[str], lookback: int = 60) -> dict:
    """
    风险平价优化：每只股票对组合的风险贡献相等。
    """
    valid_codes, returns = get_returns_matrix(codes, lookback)
    if len(valid_codes) < 2:
        return {"error": "有效股票不足2只"}

    n = len(valid_codes)
    cov_matrix = np.cov(returns.T)

    # 迭代法求风险平价权重
    w = np.ones(n) / n
    for _ in range(200):
        sigma = np.sqrt(np.dot(w, np.dot(cov_matrix, w)))
        if sigma < 1e-10:
            break
        mrc = np.dot(cov_matrix, w) / sigma
        rc = w * mrc
        target = sigma / n
        for i in range(n):
            if mrc[i] > 1e-10:
                w[i] = target / mrc[i]
        w = np.maximum(w, 0.01)
        w /= w.sum()

    port_ret = float(np.dot(w, np.mean(returns, axis=0))) * 250
    port_vol = float(np.sqrt(np.dot(w, np.dot(cov_matrix, w)))) * np.sqrt(250)
    sharpe = (port_ret - 0.03) / port_vol if port_vol > 0 else 0

    weights = {valid_codes[i]: round(float(w[i]) * 100, 1) for i in range(n)}
    weights = dict(sorted(weights.items(), key=lambda x: x[1], reverse=True))

    return {
        "method": "风险平价",
        "weights": weights,
        "expected_return": round(port_ret * 100, 2),
        "expected_vol": round(port_vol * 100, 2),
        "sharpe": round(sharpe, 2),
        "stocks": valid_codes,
    }


def optimize_portfolio(codes: list[str]) -> dict:
    """运行两种优化方法并对比。"""
    mv = optimize_mean_variance(codes)
    rp = optimize_risk_parity(codes)

    better = "mean_variance"
    if "error" not in rp and "error" not in mv:
        if rp["sharpe"] > mv["sharpe"]:
            better = "risk_parity"

    return {
        "mean_variance": mv,
        "risk_parity": rp,
        "recommended": better,
        "summary": (
            f"均值-方差: 预期收益{mv.get('expected_return', 0)}% 波动{mv.get('expected_vol', 0)}% 夏普{mv.get('sharpe', 0)} | "
            f"风险平价: 预期收益{rp.get('expected_return', 0)}% 波动{rp.get('expected_vol', 0)}% 夏普{rp.get('sharpe', 0)}"
        ) if "error" not in mv and "error" not in rp else "数据不足",
    }
