"""
Walk-Forward 分析框架
将历史数据切分为多个"训练期 + 验证期"窗口，避免参数过拟合。

使用方式:
    wf = WalkForward(train_months=12, test_months=6, step_months=6)
    results = wf.run(signal_data, strategy_config, market_df)
    # results: list[WFWindow]，每个窗口包含训练期绩效和样本外绩效。
"""
from dataclasses import dataclass, field
from datetime import timedelta

import numpy as np
import pandas as pd

from config import StrategyConfig
from backtester import Backtester, BacktestResult


@dataclass
class WFWindow:
    """单个 Walk-Forward 窗口结果"""
    window_id: int = 0
    train_start: str = ""
    train_end: str = ""
    test_start: str = ""
    test_end: str = ""
    train_result: BacktestResult = field(default_factory=BacktestResult)
    test_result: BacktestResult = field(default_factory=BacktestResult)


class WalkForward:
    def __init__(
        self,
        train_months: int = 12,
        test_months: int = 6,
        step_months: int = 6,
        config: StrategyConfig | None = None,
    ):
        self.train_months = train_months
        self.test_months = test_months
        self.step_months = step_months
        self.config = config or StrategyConfig()

    def run(
        self,
        signal_data: dict[str, pd.DataFrame],
        market_regime_df: pd.DataFrame | None = None,
    ) -> list[WFWindow]:
        all_dates = self._collect_dates(signal_data)
        if all_dates.empty:
            return []

        first_date = all_dates[0]
        last_date = all_dates[-1]
        windows = self._generate_windows(first_date, last_date)
        if not windows:
            return []

        results: list[WFWindow] = []
        for i, (train_s, train_e, test_s, test_e) in enumerate(windows):
            bt = Backtester(self.config)
            train_result = bt.run(
                signal_data,
                market_regime_df=market_regime_df,
                start_date=train_s.strftime("%Y%m%d"),
                end_date=train_e.strftime("%Y%m%d"),
            )
            bt2 = Backtester(self.config)
            test_result = bt2.run(
                signal_data,
                market_regime_df=market_regime_df,
                start_date=test_s.strftime("%Y%m%d"),
                end_date=test_e.strftime("%Y%m%d"),
            )
            results.append(WFWindow(
                window_id=i + 1,
                train_start=train_s.strftime("%Y-%m-%d"),
                train_end=train_e.strftime("%Y-%m-%d"),
                test_start=test_s.strftime("%Y-%m-%d"),
                test_end=test_e.strftime("%Y-%m-%d"),
                train_result=train_result,
                test_result=test_result,
            ))

        return results

    def _generate_windows(self, first_date, last_date):
        train_delta = timedelta(days=self.train_months * 30)
        test_delta = timedelta(days=self.test_months * 30)
        step_delta = timedelta(days=self.step_months * 30)
        windows = []
        cursor = first_date
        while True:
            train_s = cursor
            train_e = cursor + train_delta
            test_s = train_e + timedelta(days=1)
            test_e = test_s + test_delta
            if test_e > last_date:
                if test_s < last_date:
                    test_e = last_date
                else:
                    break
            windows.append((train_s, train_e, test_s, test_e))
            cursor += step_delta
            if cursor + train_delta >= last_date:
                break
        return windows

    @staticmethod
    def _collect_dates(signal_data) -> pd.DatetimeIndex:
        all_dates = set()
        for df in signal_data.values():
            if "date" in df.columns:
                all_dates.update(df["date"].tolist())
        if not all_dates:
            return pd.DatetimeIndex([])
        return pd.DatetimeIndex(sorted(all_dates))

    @staticmethod
    def summarize(windows: list[WFWindow]) -> pd.DataFrame:
        rows = []
        for w in windows:
            rows.append({
                "窗口": w.window_id,
                "训练期": f"{w.train_start} ~ {w.train_end}",
                "验证期": f"{w.test_start} ~ {w.test_end}",
                "训练收益率": f"{w.train_result.total_return:.2%}",
                "训练夏普": w.train_result.sharpe_ratio,
                "训练胜率": f"{w.train_result.win_rate:.1%}",
                "验证收益率": f"{w.test_result.total_return:.2%}",
                "验证夏普": w.test_result.sharpe_ratio,
                "验证胜率": f"{w.test_result.win_rate:.1%}",
                "验证回撤": f"{w.test_result.max_drawdown:.2%}",
                "衰减率": _decay_rate(w.train_result.sharpe_ratio, w.test_result.sharpe_ratio),
            })
        return pd.DataFrame(rows)


def _decay_rate(train_sharpe: float, test_sharpe: float) -> str:
    if train_sharpe == 0:
        return "-"
    ratio = test_sharpe / train_sharpe
    if ratio >= 0.8:
        return f"良好({ratio:.0%})"
    if ratio >= 0.5:
        return f"一般({ratio:.0%})"
    return f"衰减明显({ratio:.0%})"
