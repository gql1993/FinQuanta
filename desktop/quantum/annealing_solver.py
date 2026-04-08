"""
退火求解器：模拟退火（SA）+ Tabu Search
支持量子隧穿模拟（Simulated Quantum Annealing）。
"""
import numpy as np
import time
from .config import QOptConfig


def solve_simulated_annealing(Q: np.ndarray, config: QOptConfig) -> dict:
    """
    模拟量子退火（Simulated Quantum Annealing）。
    在标准 SA 基础上加入量子隧穿概率，增强全局搜索。

    Returns:
        dict: best_x, best_energy, history, runtime_ms
    """
    np.random.seed(config.seed)
    n = Q.shape[0]
    K = config.max_holdings
    T_start = config.sa_temp_start
    T_end = config.sa_temp_end
    n_iter = config.sa_iterations
    tunnel = config.sa_tunnel_strength

    # 初始化：随机选 K 个
    x = np.zeros(n)
    idx = np.random.choice(n, min(K, n), replace=False)
    x[idx] = 1
    current_energy = float(x @ Q @ x)

    best_x = x.copy()
    best_energy = current_energy
    history = [best_energy]

    t0 = time.time()
    for it in range(n_iter):
        T = T_start * (T_end / T_start) ** (it / n_iter)
        tunnel_prob = tunnel * (T / T_start)

        # 提议：翻转一个比特
        flip = np.random.randint(n)
        new_x = x.copy()
        new_x[flip] = 1 - new_x[flip]

        if np.sum(new_x) < 1:
            continue

        new_energy = float(new_x @ Q @ new_x)
        delta = new_energy - current_energy

        # SA 接受准则 + 量子隧穿
        accept = False
        if delta < 0:
            accept = True
        elif np.random.random() < np.exp(-delta / max(T, 1e-12)):
            accept = True
        elif np.random.random() < tunnel_prob:
            accept = True

        if accept:
            x = new_x
            current_energy = new_energy
            if current_energy < best_energy:
                best_energy = current_energy
                best_x = x.copy()

        if it % 100 == 0:
            history.append(best_energy)

    runtime = round((time.time() - t0) * 1000, 1)
    return {
        "method": "Simulated Quantum Annealing",
        "best_x": best_x,
        "best_energy": round(best_energy, 6),
        "iterations": n_iter,
        "history": history,
        "runtime_ms": runtime,
    }


def solve_tabu_search(Q: np.ndarray, config: QOptConfig) -> dict:
    """
    Tabu Search 求解 QUBO。

    Returns:
        dict: best_x, best_energy, history, runtime_ms
    """
    np.random.seed(config.seed + 1)
    n = Q.shape[0]
    K = config.max_holdings
    tenure = config.tabu_tenure
    n_iter = config.tabu_iterations

    x = np.zeros(n)
    idx = np.random.choice(n, min(K, n), replace=False)
    x[idx] = 1
    current_energy = float(x @ Q @ x)

    best_x = x.copy()
    best_energy = current_energy
    tabu_list = {}
    history = [best_energy]

    t0 = time.time()
    for it in range(n_iter):
        best_neighbor = None
        best_neighbor_energy = float("inf")
        best_flip = -1

        for flip in range(n):
            if flip in tabu_list and tabu_list[flip] > it:
                continue
            new_x = x.copy()
            new_x[flip] = 1 - new_x[flip]
            if np.sum(new_x) < 1:
                continue
            energy = float(new_x @ Q @ new_x)
            if energy < best_neighbor_energy:
                best_neighbor_energy = energy
                best_neighbor = new_x.copy()
                best_flip = flip

        if best_neighbor is not None:
            x = best_neighbor
            current_energy = best_neighbor_energy
            tabu_list[best_flip] = it + tenure

            if current_energy < best_energy:
                best_energy = current_energy
                best_x = x.copy()

        if it % 100 == 0:
            history.append(best_energy)

    runtime = round((time.time() - t0) * 1000, 1)
    return {
        "method": "Tabu Search",
        "best_x": best_x,
        "best_energy": round(best_energy, 6),
        "iterations": n_iter,
        "history": history,
        "runtime_ms": runtime,
    }
