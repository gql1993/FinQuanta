"""
蒙特卡洛模拟框架
对回测交易序列做随机重排/随机抽样，评估策略鲁棒性。

核心思路：
  1. 从实际回测的交易列表中提取逐笔收益率。
  2. 对收益率序列做 N 次随机重排（Bootstrap），每次生成一条模拟资金曲线。
  3. 统计 N 条曲线的收益分布、最大回撤分布、夏普分布。
  4. 得到"策略在随机排列下的表现区间"——如果实际表现显著优于随机区间，说明策略有真实优势。

使用方式:
    from monte_carlo import MonteCarloSimulator
    mc = MonteCarloSimulator(n_simulations=1000)
    summary = mc.run(backtest_result)
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class MCResult:
    """蒙特卡洛模拟结果"""
    n_simulations: int = 0
    n_trades: int = 0

    actual_return: float = 0.0
    actual_sharpe: float = 0.0
    actual_max_dd: float = 0.0

    sim_return_mean: float = 0.0
    sim_return_median: float = 0.0
    sim_return_p5: float = 0.0
    sim_return_p95: float = 0.0

    sim_sharpe_mean: float = 0.0
    sim_sharpe_p5: float = 0.0
    sim_sharpe_p95: float = 0.0

    sim_maxdd_mean: float = 0.0
    sim_maxdd_p5: float = 0.0
    sim_maxdd_p95: float = 0.0

    return_percentile: float = 0.0
    sharpe_percentile: float = 0.0
    maxdd_percentile: float = 0.0

    robustness_grade: str = ""
    robustness_note: str = ""

    sim_equity_curves: list = field(default_factory=list)


class MonteCarloSimulator:
    def __init__(self, n_simulations: int = 1000, initial_capital: float = 1_000_000):
        self.n_simulations = max(100, n_simulations)
        self.initial_capital = initial_capital

    def run(self, backtest_result) -> MCResult:
        trades = getattr(backtest_result, "trades", [])
        if not trades or len(trades) < 5:
            return MCResult(
                n_simulations=0, n_trades=len(trades) if trades else 0,
                robustness_grade="N/A", robustness_note="交易次数不足，无法进行蒙特卡洛模拟。",
            )

        pnl_pcts = []
        for t in trades:
            pct = t.pnl_pct if hasattr(t, "pnl_pct") else t.get("pnl_pct", 0)
            pnl_pcts.append(float(pct))
        pnl_arr = np.array(pnl_pcts)
        n_trades = len(pnl_arr)

        actual_equity = self._build_equity(pnl_arr)
        actual_return = actual_equity[-1] / self.initial_capital - 1.0
        actual_sharpe = self._sharpe(pnl_arr)
        actual_max_dd = self._max_drawdown(actual_equity)

        sim_returns = []
        sim_sharpes = []
        sim_maxdds = []
        sim_curves = []
        rng = np.random.default_rng(seed=42)

        for _ in range(self.n_simulations):
            shuffled = rng.permutation(pnl_arr)
            eq = self._build_equity(shuffled)
            sim_returns.append(eq[-1] / self.initial_capital - 1.0)
            sim_sharpes.append(self._sharpe(shuffled))
            sim_maxdds.append(self._max_drawdown(eq))
            if len(sim_curves) < 50:
                sim_curves.append(eq.tolist())

        sim_returns = np.array(sim_returns)
        sim_sharpes = np.array(sim_sharpes)
        sim_maxdds = np.array(sim_maxdds)

        return_pctl = float(np.mean(sim_returns <= actual_return) * 100)
        sharpe_pctl = float(np.mean(sim_sharpes <= actual_sharpe) * 100)
        maxdd_pctl = float(np.mean(sim_maxdds >= actual_max_dd) * 100)

        grade, note = self._grade(return_pctl, sharpe_pctl, maxdd_pctl, n_trades)

        return MCResult(
            n_simulations=self.n_simulations,
            n_trades=n_trades,
            actual_return=round(actual_return, 4),
            actual_sharpe=round(actual_sharpe, 2),
            actual_max_dd=round(actual_max_dd, 4),
            sim_return_mean=round(float(np.mean(sim_returns)), 4),
            sim_return_median=round(float(np.median(sim_returns)), 4),
            sim_return_p5=round(float(np.percentile(sim_returns, 5)), 4),
            sim_return_p95=round(float(np.percentile(sim_returns, 95)), 4),
            sim_sharpe_mean=round(float(np.mean(sim_sharpes)), 2),
            sim_sharpe_p5=round(float(np.percentile(sim_sharpes, 5)), 2),
            sim_sharpe_p95=round(float(np.percentile(sim_sharpes, 95)), 2),
            sim_maxdd_mean=round(float(np.mean(sim_maxdds)), 4),
            sim_maxdd_p5=round(float(np.percentile(sim_maxdds, 5)), 4),
            sim_maxdd_p95=round(float(np.percentile(sim_maxdds, 95)), 4),
            return_percentile=round(return_pctl, 1),
            sharpe_percentile=round(sharpe_pctl, 1),
            maxdd_percentile=round(maxdd_pctl, 1),
            robustness_grade=grade,
            robustness_note=note,
            sim_equity_curves=sim_curves,
        )

    def _build_equity(self, pnl_pcts: np.ndarray) -> np.ndarray:
        equity = [self.initial_capital]
        for pct in pnl_pcts:
            equity.append(equity[-1] * (1.0 + pct))
        return np.array(equity)

    @staticmethod
    def _max_drawdown(equity: np.ndarray) -> float:
        peak = np.maximum.accumulate(equity)
        dd = (peak - equity) / np.maximum(peak, 1e-9)
        return float(np.max(dd)) if len(dd) > 0 else 0.0

    @staticmethod
    def _sharpe(pnl_pcts: np.ndarray) -> float:
        if len(pnl_pcts) < 2 or np.std(pnl_pcts) == 0:
            return 0.0
        excess = np.mean(pnl_pcts) - 0.03 / 250
        return float(excess / np.std(pnl_pcts) * np.sqrt(250))

    @staticmethod
    def _grade(ret_pctl, sharpe_pctl, dd_pctl, n_trades) -> tuple[str, str]:
        if n_trades < 20:
            return "待定", f"样本仅 {n_trades} 笔，需更多交易验证。"
        avg_pctl = (ret_pctl + sharpe_pctl + dd_pctl) / 3
        if avg_pctl >= 80:
            return "优秀", (
                f"实际表现处于模拟分布的 {avg_pctl:.0f}% 分位，"
                f"策略优势显著，不太可能来自运气。"
            )
        if avg_pctl >= 60:
            return "良好", (
                f"实际表现处于模拟分布的 {avg_pctl:.0f}% 分位，"
                f"策略有一定优势，但需关注市场环境变化。"
            )
        if avg_pctl >= 40:
            return "一般", (
                f"实际表现处于模拟分布的 {avg_pctl:.0f}% 分位，"
                f"策略优势边际不大，可能受序列依赖影响。"
            )
        return "偏弱", (
            f"实际表现处于模拟分布的 {avg_pctl:.0f}% 分位，"
            f"策略可能未展现显著优势，建议复查逻辑或参数。"
        )

    @staticmethod
    def summarize(mc_result: MCResult) -> pd.DataFrame:
        rows = [
            {"指标": "实际总收益率", "实际值": f"{mc_result.actual_return:.2%}",
             "模拟均值": f"{mc_result.sim_return_mean:.2%}",
             "模拟5%分位": f"{mc_result.sim_return_p5:.2%}",
             "模拟95%分位": f"{mc_result.sim_return_p95:.2%}",
             "百分位排名": f"{mc_result.return_percentile:.0f}%"},
            {"指标": "实际夏普比率", "实际值": f"{mc_result.actual_sharpe:.2f}",
             "模拟均值": f"{mc_result.sim_sharpe_mean:.2f}",
             "模拟5%分位": f"{mc_result.sim_sharpe_p5:.2f}",
             "模拟95%分位": f"{mc_result.sim_sharpe_p95:.2f}",
             "百分位排名": f"{mc_result.sharpe_percentile:.0f}%"},
            {"指标": "实际最大回撤", "实际值": f"{mc_result.actual_max_dd:.2%}",
             "模拟均值": f"{mc_result.sim_maxdd_mean:.2%}",
             "模拟5%分位": f"{mc_result.sim_maxdd_p5:.2%}",
             "模拟95%分位": f"{mc_result.sim_maxdd_p95:.2%}",
             "百分位排名": f"{mc_result.maxdd_percentile:.0f}%"},
        ]
        return pd.DataFrame(rows)
