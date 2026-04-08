"""统一评估：对比所有方法的结果。"""
import numpy as np
from .preprocessing import StockStats
from .config import QOptConfig
from .qubo_model import build_qubo, evaluate_solution


def compare_methods(results: list[dict], stats: StockStats) -> dict:
    """
    统一对比所有方法的结果，保留完整数据。
    """
    table = []
    for r in results:
        if not r.get("valid", True):
            table.append({"method": r.get("method", "?"), "valid": False, "reason": r.get("reason", "")})
            continue
        entry = {
            "method": r.get("method", "?"),
            "valid": True,
            "selected_codes": r.get("selected_codes", []),
            "selected_names": r.get("selected_names", []),
            "n_selected": r.get("n_selected", 0),
            "weights": r.get("weights", []),
            "portfolio_return": r.get("portfolio_return", 0),
            "portfolio_risk": r.get("portfolio_risk", 0),
            "sharpe_ratio": r.get("sharpe_ratio", 0),
            "energy": r.get("energy", 0),
            "constraint_satisfied": r.get("constraint_satisfied", False),
            "runtime_ms": r.get("runtime_ms", 0),
        }
        table.append(entry)

    valid = [t for t in table if t.get("valid")]
    if valid:
        best = max(valid, key=lambda t: t["sharpe_ratio"])
        best["is_best"] = True

    return {"methods": table, "n_methods": len(table)}


def run_full_comparison(stats: StockStats, config: QOptConfig) -> dict:
    """
    运行所有方法并对比（端到端）。
    """
    from .qubo_model import build_qubo
    from .annealing_solver import solve_simulated_annealing, solve_tabu_search
    from .qaoa_solver import solve_qaoa_classical
    from .classical_baselines import (
        greedy_baseline, brute_force_baseline,
        random_sampling_baseline, mean_variance_baseline,
    )

    Q, qubo_info = build_qubo(stats, config)
    results = []

    # 1. 退火
    sa_result = solve_simulated_annealing(Q, config)
    sa_eval = evaluate_solution(sa_result["best_x"], stats, config)
    sa_eval["method"] = sa_result["method"]
    sa_eval["runtime_ms"] = sa_result["runtime_ms"]
    sa_eval["history"] = sa_result["history"]
    results.append(sa_eval)

    # 2. Tabu
    tabu_result = solve_tabu_search(Q, config)
    tabu_eval = evaluate_solution(tabu_result["best_x"], stats, config)
    tabu_eval["method"] = tabu_result["method"]
    tabu_eval["runtime_ms"] = tabu_result["runtime_ms"]
    results.append(tabu_eval)

    # 3. QAOA
    qaoa_result = solve_qaoa_classical(Q, config)
    qaoa_eval = evaluate_solution(qaoa_result["best_x"], stats, config)
    qaoa_eval["method"] = qaoa_result["method"]
    qaoa_eval["runtime_ms"] = qaoa_result["runtime_ms"]
    qaoa_eval["convergence"] = qaoa_result.get("convergence", [])
    results.append(qaoa_eval)

    # 4. 经典基线
    results.append(greedy_baseline(stats, config))
    if stats.n <= 20:
        results.append(brute_force_baseline(stats, config))
    results.append(random_sampling_baseline(stats, config))
    results.append(mean_variance_baseline(stats, config))

    comparison = compare_methods(results, stats)
    comparison["qubo_info"] = qubo_info
    comparison["stats_summary"] = {
        "n_stocks": stats.n,
        "codes": stats.codes,
        "mu_range": [round(float(np.min(stats.mu)) * 100, 2), round(float(np.max(stats.mu)) * 100, 2)],
        "vol_range": [round(float(np.min(stats.annual_vols)) * 100, 2), round(float(np.max(stats.annual_vols)) * 100, 2)],
    }
    return comparison
