"""
经典基线：贪心、暴力枚举、随机采样、均值-方差整数规划。
"""
import numpy as np
import time
from itertools import combinations
from .preprocessing import StockStats
from .config import QOptConfig
from .qubo_model import evaluate_solution


def greedy_baseline(stats: StockStats, config: QOptConfig) -> dict:
    """
    贪心基线：按夏普比率排序，选 Top K。
    """
    t0 = time.time()
    n = stats.n
    K = config.max_holdings

    sharpes = []
    for i in range(n):
        vol = stats.annual_vols[i]
        s = (stats.mu[i] - config.risk_free_rate) / vol if vol > 0 else 0
        sharpes.append(s)

    top_k = np.argsort(sharpes)[-K:]
    x = np.zeros(n)
    x[top_k] = 1

    result = evaluate_solution(x, stats, config)
    result["method"] = "Greedy (Top-K Sharpe)"
    result["runtime_ms"] = round((time.time() - t0) * 1000, 1)
    return result


def brute_force_baseline(stats: StockStats, config: QOptConfig) -> dict:
    """
    暴力枚举：遍历所有 C(n, K) 组合，找最优。
    仅限 n ≤ 20（否则组合爆炸）。
    """
    from .qubo_model import build_qubo
    t0 = time.time()
    n = stats.n
    K = config.max_holdings

    if n > 20:
        return {"method": "Brute Force", "valid": False, "reason": f"n={n}>20, 组合数太多"}

    Q, _ = build_qubo(stats, config)
    best_energy = float("inf")
    best_x = None
    total_combos = 0

    for combo in combinations(range(n), K):
        x = np.zeros(n)
        x[list(combo)] = 1
        energy = float(x @ Q @ x)
        total_combos += 1
        if energy < best_energy:
            best_energy = energy
            best_x = x.copy()

    result = evaluate_solution(best_x, stats, config)
    result["method"] = "Brute Force"
    result["runtime_ms"] = round((time.time() - t0) * 1000, 1)
    result["total_combos"] = total_combos
    return result


def random_sampling_baseline(stats: StockStats, config: QOptConfig,
                             n_samples: int = 10000) -> dict:
    """
    随机采样基线：随机生成 n_samples 个组合，取最优。
    """
    from .qubo_model import build_qubo
    np.random.seed(config.seed + 10)
    t0 = time.time()
    n = stats.n
    K = config.max_holdings
    Q, _ = build_qubo(stats, config)

    best_energy = float("inf")
    best_x = None

    for _ in range(n_samples):
        idx = np.random.choice(n, K, replace=False)
        x = np.zeros(n)
        x[idx] = 1
        energy = float(x @ Q @ x)
        if energy < best_energy:
            best_energy = energy
            best_x = x.copy()

    result = evaluate_solution(best_x, stats, config)
    result["method"] = f"Random Sampling ({n_samples})"
    result["runtime_ms"] = round((time.time() - t0) * 1000, 1)
    return result


def mean_variance_baseline(stats: StockStats, config: QOptConfig,
                           n_portfolios: int = 5000) -> dict:
    """
    经典均值-方差蒙特卡洛：生成随机权重组合，取最大夏普。
    """
    np.random.seed(config.seed + 20)
    t0 = time.time()
    n = stats.n

    best_sharpe = -999
    best_w = np.ones(n) / n

    for _ in range(n_portfolios):
        w = np.random.random(n)
        w /= w.sum()
        ret = float(np.dot(w, stats.mu))
        risk = float(np.sqrt(np.dot(w, np.dot(stats.sigma, w))))
        sharpe = (ret - config.risk_free_rate) / risk if risk > 0 else 0
        if sharpe > best_sharpe:
            best_sharpe = sharpe
            best_w = w.copy()

    # 取前K大权重
    top_k = np.argsort(best_w)[-config.max_holdings:]
    x = np.zeros(n)
    x[top_k] = 1

    result = evaluate_solution(x, stats, config)
    result["method"] = "Mean-Variance (Monte Carlo)"
    result["runtime_ms"] = round((time.time() - t0) * 1000, 1)
    result["continuous_weights"] = {stats.codes[i]: round(best_w[i] * 100, 2) for i in range(n)}
    return result
