"""端到端测试：6只股票完整跑通。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import numpy as np
from desktop.quantum.preprocessing import compute_stats
from desktop.quantum.config import QOptConfig
from desktop.quantum.evaluation import run_full_comparison


def test_6_stock_full_pipeline():
    """6只股票端到端：数据→统计→QUBO→退火→QAOA→基线→对比。"""
    np.random.seed(42)
    codes = ["600519", "300750", "000858", "002594", "688981", "300502"]
    names = {"600519": "茅台", "300750": "宁德", "000858": "五粮液",
             "002594": "比亚迪", "688981": "中芯", "300502": "新易盛"}
    prices = {}
    for i, code in enumerate(codes):
        drift = 0.0003 * (i - 2)
        vol = 0.02 + 0.003 * i
        log_ret = np.random.normal(drift, vol, 120)
        prices[code] = 100 * np.exp(np.cumsum(log_ret))

    stats = compute_stats(prices, names)
    config = QOptConfig(max_holdings=3, risk_aversion=1.5, seed=42,
                        sa_iterations=2000, tabu_iterations=1000,
                        qaoa_layers=2, qaoa_optimizer_maxiter=50)

    print(f"统计量: {stats.n}只股票, 收益率范围 [{stats.mu.min()*100:.1f}%, {stats.mu.max()*100:.1f}%]")

    result = run_full_comparison(stats, config)

    print(f"\n{'='*70}")
    print(f"{'方法':<35} {'收益%':>8} {'风险%':>8} {'夏普':>6} {'选股数':>5} {'约束':>4} {'用时ms':>7}")
    print(f"{'='*70}")

    for m in result["methods"]:
        if not m.get("valid", True):
            print(f"{m['method']:<35} INVALID: {m.get('reason', '')}")
            continue
        star = " *BEST*" if m.get("is_best") else ""
        ck = "Y" if m["constraint_ok"] else "N"
        print(
            f"{m['method']:<35} {m['return_pct']:>+7.2f} {m['risk_pct']:>7.2f} "
            f"{m['sharpe']:>6.2f} {m['n_selected']:>5} {ck:>4} "
            f"{m['runtime_ms']:>6.1f}{star}"
        )

    print(f"\nQUBO info: {result['qubo_info']}")
    print("PASS: test_6_stock_full_pipeline")
    return result


if __name__ == "__main__":
    test_6_stock_full_pipeline()
