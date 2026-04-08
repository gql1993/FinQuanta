"""
QUBO 模型构造器
将均值-方差组合优化问题转为 QUBO（二次无约束二进制优化）。

决策变量: x_i ∈ {0, 1}，表示是否持有第 i 只股票
目标: min x^T Q x
     = -收益项 + λ·风险项 + penalty·(Σx_i - K)²

简化假设：被选中股票等权配置 w_i = x_i / K
这是一个合理的近似，使问题保持纯二进制 QUBO 形式。
"""
import numpy as np
from .preprocessing import StockStats
from .config import QOptConfig


def build_qubo(stats: StockStats, config: QOptConfig) -> tuple[np.ndarray, dict]:
    """
    构造 QUBO 矩阵 Q，使得最优解 x* = argmin x^T Q x。

    Returns:
        Q: (n, n) 对称矩阵
        info: 构造信息（用于调试和报告）
    """
    n = stats.n
    K = config.max_holdings
    lam = config.risk_aversion
    mu = stats.mu
    sigma = stats.sigma

    Q = np.zeros((n, n))

    # 收益项: -Σ mu_i x_i / K → 对角线 Q_ii -= mu_i / K
    for i in range(n):
        Q[i, i] -= mu[i] / K

    # 风险项: λ Σ_ij sigma_ij x_i x_j / K² → Q_ij += λ sigma_ij / K²
    Q += lam * sigma / (K * K)

    # 持仓数量约束: penalty * (Σ x_i - K)²
    # 展开: penalty * (Σ_i x_i² - 2K Σ_i x_i + K² + 2 Σ_{i<j} x_i x_j)
    # 因为 x_i ∈ {0,1}，x_i² = x_i，所以:
    #   Q_ii += penalty * (1 - 2K)
    #   Q_ij += penalty * 2  (i ≠ j)
    #   常数项: penalty * K² (不影响优化)

    # 自动计算 penalty 强度
    if config.penalty_strength > 0:
        penalty = config.penalty_strength
    else:
        max_Q = np.max(np.abs(Q)) if np.max(np.abs(Q)) > 0 else 1.0
        penalty = config.penalty_auto_scale * max_Q

    for i in range(n):
        Q[i, i] += penalty * (1 - 2 * K)
        for j in range(n):
            if i != j:
                Q[i, j] += penalty

    # 对称化（数值保险）
    Q = (Q + Q.T) / 2

    info = {
        "n": n,
        "K": K,
        "lambda": lam,
        "penalty": round(penalty, 4),
        "Q_shape": Q.shape,
        "Q_max": round(float(np.max(Q)), 4),
        "Q_min": round(float(np.min(Q)), 4),
        "Q_symmetric": bool(np.allclose(Q, Q.T)),
    }
    return Q, info


def evaluate_solution(x: np.ndarray, stats: StockStats, config: QOptConfig) -> dict:
    """
    评估一个二进制解 x。

    Args:
        x: (n,) 二进制向量
        stats: 股票统计量
        config: 配置
    Returns:
        dict: 各项指标
    """
    selected = np.where(x > 0.5)[0]
    n_selected = len(selected)

    if n_selected == 0:
        return {"valid": False, "reason": "未选中任何股票"}

    # 等权配置
    w = np.zeros(stats.n)
    w[selected] = 1.0 / n_selected

    # 组合收益
    port_return = float(np.dot(w, stats.mu))

    # 组合风险
    port_risk = float(np.sqrt(np.dot(w, np.dot(stats.sigma, w))))

    # 夏普比率
    sharpe = (port_return - config.risk_free_rate) / port_risk if port_risk > 0 else 0

    # QUBO 目标值
    Q, _ = build_qubo(stats, config)
    energy = float(x @ Q @ x)

    # 约束检查
    constraint_satisfied = (n_selected == config.max_holdings)

    return {
        "valid": True,
        "selected_indices": selected.tolist(),
        "selected_codes": [stats.codes[i] for i in selected],
        "selected_names": [stats.names[i] for i in selected],
        "n_selected": n_selected,
        "weights": [round(1 / n_selected, 4)] * n_selected,
        "portfolio_return": round(port_return * 100, 2),
        "portfolio_risk": round(port_risk * 100, 2),
        "sharpe_ratio": round(sharpe, 2),
        "energy": round(energy, 6),
        "constraint_K": config.max_holdings,
        "constraint_satisfied": constraint_satisfied,
    }
