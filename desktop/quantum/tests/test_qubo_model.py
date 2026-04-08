"""QUBO 模型单元测试"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import numpy as np
from desktop.quantum.preprocessing import compute_stats
from desktop.quantum.qubo_model import build_qubo, evaluate_solution
from desktop.quantum.config import QOptConfig


def _make_sample_data(n: int = 6, T: int = 100):
    """生成合成价格数据。"""
    np.random.seed(42)
    prices = {}
    codes = [f"TEST{i:03d}" for i in range(n)]
    for i, code in enumerate(codes):
        drift = 0.0005 * (i - n // 2)
        vol = 0.02 + 0.005 * i
        log_returns = np.random.normal(drift, vol, T)
        p = 100 * np.exp(np.cumsum(log_returns))
        prices[code] = p
    return prices, codes


def test_qubo_symmetry():
    """Q 矩阵必须对称。"""
    prices, _ = _make_sample_data(6, 100)
    stats = compute_stats(prices)
    config = QOptConfig(max_holdings=3, risk_aversion=1.0)
    Q, info = build_qubo(stats, config)
    assert Q.shape == (6, 6), f"Q shape wrong: {Q.shape}"
    assert np.allclose(Q, Q.T), "Q is not symmetric"
    assert info["Q_symmetric"]
    print("PASS: test_qubo_symmetry")


def test_qubo_dimension():
    """Q 矩阵维度 = 股票数。"""
    for n in [4, 6, 8]:
        prices, _ = _make_sample_data(n, 80)
        stats = compute_stats(prices)
        config = QOptConfig(max_holdings=min(3, n))
        Q, _ = build_qubo(stats, config)
        assert Q.shape == (n, n)
    print("PASS: test_qubo_dimension")


def test_penalty_effective():
    """持仓约束 penalty 必须生效：选错数量的能量更高。"""
    prices, _ = _make_sample_data(6, 100)
    stats = compute_stats(prices)
    config = QOptConfig(max_holdings=3, risk_aversion=1.0)
    Q, _ = build_qubo(stats, config)

    # 选3个
    x_good = np.array([1, 1, 1, 0, 0, 0], dtype=float)
    e_good = float(x_good @ Q @ x_good)

    # 选5个（违反约束）
    x_bad = np.array([1, 1, 1, 1, 1, 0], dtype=float)
    e_bad = float(x_bad @ Q @ x_bad)

    assert e_good < e_bad, f"Penalty not effective: e_good={e_good:.4f} >= e_bad={e_bad:.4f}"
    print("PASS: test_penalty_effective")


def test_evaluate_solution():
    """评估函数返回完整指标。"""
    prices, _ = _make_sample_data(6, 100)
    stats = compute_stats(prices)
    config = QOptConfig(max_holdings=3)
    x = np.array([1, 0, 1, 0, 1, 0], dtype=float)
    result = evaluate_solution(x, stats, config)
    assert result["valid"]
    assert result["n_selected"] == 3
    assert result["constraint_satisfied"]
    assert "portfolio_return" in result
    assert "sharpe_ratio" in result
    print("PASS: test_evaluate_solution")


if __name__ == "__main__":
    test_qubo_symmetry()
    test_qubo_dimension()
    test_penalty_effective()
    test_evaluate_solution()
    print("\nAll QUBO tests passed!")
