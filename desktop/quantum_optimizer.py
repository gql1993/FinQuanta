"""
量子组合优化选股模块
基于 QAOA（量子近似优化算法）和量子退火（Quantum Annealing）的经典模拟，
对候选股票做组合优化，找到收益-风险最优的股票组合。

在无量子硬件时，用经典模拟器近似量子效果：
- QAOA 模拟：变分优化 + 随机搜索
- QA 模拟：模拟退火（Simulated Annealing）
"""
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime

from desktop.data_access import get_repo


@dataclass
class QuantumResult:
    method: str = ""
    selected_codes: list = field(default_factory=list)
    selected_names: list = field(default_factory=list)
    weights: list = field(default_factory=list)
    expected_return: float = 0.0
    expected_risk: float = 0.0
    sharpe: float = 0.0
    diversity_score: float = 0.0
    iterations: int = 0
    energy: float = 0.0


def _load_candidate_returns(codes: list[str], lookback: int = 60) -> tuple:
    """加载候选股票收益率矩阵。"""
    repo = get_repo()
    valid_codes = []
    returns_list = []
    names = {}

    try:
        names = {r[0]: r[1] for r in repo.fetchall("SELECT code, name FROM stock_list", ())}
    except Exception:
        pass

    for code in codes:
        rows = [r[0] for r in repo.fetchall(
            "SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT ?",
            (code, lookback + 1),
        )]
        if len(rows) < lookback:
            continue
        rows = rows[::-1]
        prices = np.array(rows)
        rets = np.diff(prices) / prices[:-1]
        valid_codes.append(code)
        returns_list.append(rets[-lookback:])

    if len(valid_codes) < 3:
        return [], [], np.array([]), names

    min_len = min(len(r) for r in returns_list)
    matrix = np.column_stack([r[-min_len:] for r in returns_list])
    return valid_codes, [names.get(c, c) for c in valid_codes], matrix, names


def _build_qubo_matrix(returns: np.ndarray, n_select: int, risk_aversion: float = 1.0) -> np.ndarray:
    """
    构建 QUBO（二次无约束二进制优化）矩阵。
    目标：最大化收益 - risk_aversion × 风险，选 n_select 只股票。
    """
    n = returns.shape[1]
    mean_rets = np.mean(returns, axis=0) * 250
    cov = np.cov(returns.T) * 250

    # QUBO: minimize x^T Q x
    # Q_ij = risk_aversion * cov_ij - (mean_ret_i + mean_ret_j) / 2
    Q = risk_aversion * cov.copy()
    for i in range(n):
        Q[i, i] -= mean_rets[i]

    # 约束：恰好选 n_select 只（惩罚项）
    penalty = 10.0 * np.max(np.abs(Q))
    for i in range(n):
        Q[i, i] += penalty * (1 - 2 * n_select)
        for j in range(n):
            Q[i, j] += 2 * penalty

    return Q


def run_qaoa_simulation(codes: list[str], n_select: int = 5,
                        n_layers: int = 3, n_iterations: int = 500) -> QuantumResult:
    """
    QAOA 模拟（变分量子优化的经典近似）。
    用变分参数搜索最优二进制组合。
    """
    valid_codes, valid_names, returns, names = _load_candidate_returns(codes)
    if len(valid_codes) < 3:
        return QuantumResult(method="QAOA", selected_codes=[], energy=999)

    n = len(valid_codes)
    n_select = min(n_select, n)
    mean_rets = np.mean(returns, axis=0) * 250
    cov = np.cov(returns.T) * 250

    best_solution = None
    best_cost = float("inf")

    for iteration in range(n_iterations):
        # 变分参数（gamma, beta for each layer）
        gamma = np.random.uniform(0, 2 * np.pi, n_layers)
        beta = np.random.uniform(0, np.pi, n_layers)

        # 量子态模拟：概率振幅
        probs = np.ones(n) / n

        for layer in range(n_layers):
            # Phase separation (模拟 QAOA 的 cost Hamiltonian)
            phase = np.exp(-1j * gamma[layer] * mean_rets / np.max(np.abs(mean_rets) + 1e-9))
            probs = probs * np.abs(phase.real)

            # Mixing (模拟 QAOA 的 mixer Hamiltonian)
            mix_factor = np.cos(beta[layer])
            probs = mix_factor * probs + (1 - mix_factor) * np.ones(n) / n

        probs = np.abs(probs)
        probs /= probs.sum() + 1e-9

        # 采样：选概率最高的 n_select 只
        selected_idx = np.argsort(probs)[-n_select:]
        x = np.zeros(n)
        x[selected_idx] = 1

        # 计算目标函数
        w = x / x.sum()
        port_ret = float(np.dot(w, mean_rets))
        port_risk = float(np.sqrt(np.dot(w, np.dot(cov, w))))
        cost = -port_ret + port_risk

        if cost < best_cost:
            best_cost = cost
            best_solution = selected_idx.copy()

    # 构建结果
    sel_codes = [valid_codes[i] for i in best_solution]
    sel_names = [valid_names[i] for i in best_solution]
    w = np.ones(n_select) / n_select
    sel_rets = mean_rets[best_solution]
    sel_cov = cov[np.ix_(best_solution, best_solution)]

    port_ret = float(np.dot(w, sel_rets))
    port_risk = float(np.sqrt(np.dot(w, np.dot(sel_cov, w))))
    sharpe = (port_ret - 0.03) / port_risk if port_risk > 0 else 0

    boards = set()
    try:
        repo = get_repo()
        for c in sel_codes:
            r = repo.fetchone("SELECT board FROM board_stocks WHERE code=? LIMIT 1", (c,))
            if r:
                boards.add(r[0])
    except Exception:
        pass
    diversity = len(boards) / max(n_select, 1)

    return QuantumResult(
        method="QAOA（变分量子优化模拟）",
        selected_codes=sel_codes, selected_names=sel_names,
        weights=[round(1 / n_select * 100, 1)] * n_select,
        expected_return=round(port_ret * 100, 2),
        expected_risk=round(port_risk * 100, 2),
        sharpe=round(sharpe, 2),
        diversity_score=round(diversity, 2),
        iterations=n_iterations,
        energy=round(best_cost, 4),
    )


def run_quantum_annealing(codes: list[str], n_select: int = 5,
                          n_iterations: int = 2000,
                          temp_start: float = 100.0,
                          temp_end: float = 0.01) -> QuantumResult:
    """
    量子退火模拟（Simulated Quantum Annealing）。
    模拟量子隧穿效应在解空间中搜索全局最优。
    """
    valid_codes, valid_names, returns, names = _load_candidate_returns(codes)
    if len(valid_codes) < 3:
        return QuantumResult(method="QA", selected_codes=[], energy=999)

    n = len(valid_codes)
    n_select = min(n_select, n)
    mean_rets = np.mean(returns, axis=0) * 250
    cov = np.cov(returns.T) * 250

    def _cost(x):
        idx = np.where(x == 1)[0]
        if len(idx) == 0:
            return 999
        w = np.ones(len(idx)) / len(idx)
        r = float(np.dot(w, mean_rets[idx]))
        risk = float(np.sqrt(np.dot(w, np.dot(cov[np.ix_(idx, idx)], w))))
        penalty = abs(len(idx) - n_select) * 5.0
        return -r + risk + penalty

    # 初始解
    x = np.zeros(n)
    init_idx = np.random.choice(n, n_select, replace=False)
    x[init_idx] = 1
    current_cost = _cost(x)
    best_x = x.copy()
    best_cost = current_cost

    for i in range(n_iterations):
        temp = temp_start * (temp_end / temp_start) ** (i / n_iterations)
        # 量子隧穿模拟：以概率翻转一个比特
        tunnel_strength = temp / temp_start
        flip_idx = np.random.randint(n)

        new_x = x.copy()
        new_x[flip_idx] = 1 - new_x[flip_idx]

        # 保持选股数量约束（软约束）
        if np.sum(new_x) < 2:
            continue

        new_cost = _cost(new_x)
        delta = new_cost - current_cost

        # 退火接受准则 + 量子隧穿项
        tunnel_prob = tunnel_strength * 0.3
        if delta < 0 or np.random.random() < np.exp(-delta / (temp + 1e-9)) + tunnel_prob:
            x = new_x
            current_cost = new_cost
            if current_cost < best_cost:
                best_cost = current_cost
                best_x = x.copy()

    selected_idx = np.where(best_x == 1)[0]
    if len(selected_idx) == 0:
        selected_idx = np.argsort(mean_rets)[-n_select:]

    sel_codes = [valid_codes[i] for i in selected_idx]
    sel_names = [valid_names[i] for i in selected_idx]
    ns = len(selected_idx)
    w = np.ones(ns) / ns
    port_ret = float(np.dot(w, mean_rets[selected_idx]))
    port_risk = float(np.sqrt(np.dot(w, np.dot(cov[np.ix_(selected_idx, selected_idx)], w))))
    sharpe = (port_ret - 0.03) / port_risk if port_risk > 0 else 0

    return QuantumResult(
        method="QA（量子退火模拟）",
        selected_codes=sel_codes, selected_names=sel_names,
        weights=[round(1 / ns * 100, 1)] * ns,
        expected_return=round(port_ret * 100, 2),
        expected_risk=round(port_risk * 100, 2),
        sharpe=round(sharpe, 2),
        diversity_score=0,
        iterations=n_iterations,
        energy=round(best_cost, 4),
    )


def run_quantum_optimization(boards: list[str] = None, n_select: int = 5) -> dict:
    """运行两种量子方法并对比。"""
    repo = get_repo()
    all_codes = set()
    if boards:
        for b in boards:
            for r in repo.fetchall("SELECT code FROM board_stocks WHERE board=?", (b,)):
                all_codes.add(r[0])
    if not all_codes:
        all_codes = {r[0] for r in repo.fetchall("SELECT DISTINCT code FROM daily_kline LIMIT 200", ())}

    codes = list(all_codes)
    qaoa = run_qaoa_simulation(codes, n_select)
    qa = run_quantum_annealing(codes, n_select)

    better = "qaoa" if qaoa.sharpe >= qa.sharpe else "qa"

    return {
        "qaoa": qaoa,
        "qa": qa,
        "recommended": better,
        "candidate_count": len(codes),
    }
