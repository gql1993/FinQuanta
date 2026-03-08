"""
策略参数优化器
支持网格搜索和贝叶斯优化两种模式，基于回测绩效目标函数自动寻找最优参数组合。

使用方式:
    opt = ParamOptimizer(strategy_id="sepa", mode="grid")
    best_params, results_df = opt.run(signal_data, market_df)
"""
from dataclasses import dataclass
from itertools import product
from typing import Callable

import numpy as np
import pandas as pd

from config import StrategyConfig
from backtester import Backtester, BacktestResult
from strategy_profiles import (
    get_strategy_default_params,
    apply_backtest_profile,
    strategy_name,
)


@dataclass
class OptResult:
    """单次参数组合的优化结果"""
    params: dict
    total_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    total_trades: int = 0
    score: float = 0.0


def default_objective(r: BacktestResult) -> float:
    """默认目标函数：夏普 × (1 - 回撤) × 根号(交易次数)"""
    if r.total_trades < 5:
        return -999.0
    dd_penalty = max(0.01, 1.0 - r.max_drawdown)
    trade_factor = min(np.sqrt(r.total_trades / 20.0), 2.0)
    return float(r.sharpe_ratio * dd_penalty * trade_factor)


class ParamOptimizer:
    def __init__(
        self,
        strategy_id: str = "sepa",
        mode: str = "grid",
        objective: Callable[[BacktestResult], float] | None = None,
        config: StrategyConfig | None = None,
    ):
        self.strategy_id = strategy_id
        self.mode = mode
        self.objective = objective or default_objective
        self.config = config or StrategyConfig()

    def run(
        self,
        signal_data: dict[str, pd.DataFrame],
        market_regime_df: pd.DataFrame | None = None,
        param_grid: dict[str, list] | None = None,
        start_date: str = "20220601",
        n_bayesian_iter: int = 30,
        fin_map: dict | None = None,
    ) -> tuple[dict, pd.DataFrame]:
        if param_grid is None:
            param_grid = self._default_grid()

        if self.mode == "grid":
            return self._grid_search(signal_data, market_regime_df, param_grid,
                                     start_date, fin_map)
        else:
            return self._bayesian_search(signal_data, market_regime_df, param_grid,
                                         start_date, n_bayesian_iter, fin_map)

    def _grid_search(self, signal_data, market_df, param_grid, start_date, fin_map):
        keys = list(param_grid.keys())
        combos = list(product(*[param_grid[k] for k in keys]))
        results: list[OptResult] = []

        for combo in combos:
            params = dict(zip(keys, combo))
            score, bt_result = self._evaluate(signal_data, market_df, params, start_date, fin_map)
            results.append(OptResult(
                params=params,
                total_return=bt_result.total_return,
                sharpe_ratio=bt_result.sharpe_ratio,
                max_drawdown=bt_result.max_drawdown,
                win_rate=bt_result.win_rate,
                total_trades=bt_result.total_trades,
                score=score,
            ))

        results.sort(key=lambda x: x.score, reverse=True)
        best = results[0] if results else OptResult(params={})
        df = self._to_dataframe(results)
        return best.params, df

    def _bayesian_search(self, signal_data, market_df, param_grid, start_date, n_iter, fin_map):
        keys = list(param_grid.keys())
        bounds = {k: (min(v), max(v)) for k, v in param_grid.items() if v}
        rng = np.random.default_rng(seed=42)
        results: list[OptResult] = []

        for _ in range(n_iter):
            params = {}
            for k in keys:
                lo, hi = bounds.get(k, (0, 1))
                if isinstance(param_grid[k][0], int):
                    params[k] = int(rng.integers(lo, hi + 1))
                else:
                    params[k] = round(float(rng.uniform(lo, hi)), 4)

            score, bt_result = self._evaluate(signal_data, market_df, params, start_date, fin_map)
            results.append(OptResult(
                params=params,
                total_return=bt_result.total_return,
                sharpe_ratio=bt_result.sharpe_ratio,
                max_drawdown=bt_result.max_drawdown,
                win_rate=bt_result.win_rate,
                total_trades=bt_result.total_trades,
                score=score,
            ))

        results.sort(key=lambda x: x.score, reverse=True)
        best = results[0] if results else OptResult(params={})
        df = self._to_dataframe(results)
        return best.params, df

    def _evaluate(self, signal_data, market_df, params, start_date, fin_map) -> tuple[float, BacktestResult]:
        base_params = get_strategy_default_params(self.strategy_id)
        base_params.update(params)

        profiled = {}
        for code, df in signal_data.items():
            fd = fin_map.get(code) if fin_map else None
            profiled[code] = apply_backtest_profile(df.copy(), self.strategy_id, fd, base_params)

        bt = Backtester(self.config)
        result = bt.run(profiled, market_regime_df=market_df, start_date=start_date)
        score = self.objective(result)
        return score, result

    def _default_grid(self) -> dict[str, list]:
        sid = self.strategy_id
        if sid in ("sepa", "canslim"):
            return {
                "rs_min": [60, 65, 70, 75, 80],
                "risk_per_trade": [0.008, 0.01, 0.012, 0.015],
            }
        if sid == "turtle":
            return {
                "breakout_window": [20, 30, 40, 55],
                "risk_per_trade": [0.008, 0.01, 0.015],
            }
        if sid in ("graham", "buffett", "lynch"):
            return {
                "pe_max": [15, 20, 25, 30],
                "pb_max": [2.0, 3.0, 5.0],
            }
        return {
            "rs_min": [55, 65, 75, 85],
            "risk_per_trade": [0.008, 0.01, 0.015],
        }

    @staticmethod
    def _to_dataframe(results: list[OptResult]) -> pd.DataFrame:
        rows = []
        for r in results:
            row = dict(r.params)
            row["总收益率"] = f"{r.total_return:.2%}"
            row["夏普"] = r.sharpe_ratio
            row["最大回撤"] = f"{r.max_drawdown:.2%}"
            row["胜率"] = f"{r.win_rate:.1%}"
            row["交易次数"] = r.total_trades
            row["综合评分"] = round(r.score, 3)
            rows.append(row)
        return pd.DataFrame(rows)
