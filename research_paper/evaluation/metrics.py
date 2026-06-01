"""Metrics for paper baseline experiments."""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class BacktestResult:
    method: str
    equity_curve: pd.Series
    period_returns: pd.Series
    turnover: pd.Series
    costs: pd.Series


def calculate_metrics(result: BacktestResult, benchmark_period_returns: pd.Series) -> dict[str, float | str]:
    returns = result.period_returns
    periods_per_year = 12.0
    total_years = len(returns) / periods_per_year
    total_return = float(result.equity_curve.iloc[-1] - 1.0)
    annual_return = (1.0 + total_return) ** (1.0 / total_years) - 1.0 if total_years > 0 else math.nan
    annual_volatility = float(returns.std(ddof=1) * math.sqrt(periods_per_year))
    sharpe = annual_return / annual_volatility if annual_volatility > 0 else math.nan
    downside = returns[returns < 0].std(ddof=1) * math.sqrt(periods_per_year)
    sortino = annual_return / downside if downside and downside > 0 else math.nan
    running_peak = result.equity_curve.cummax()
    drawdown = result.equity_curve / running_peak - 1.0
    max_drawdown = float(drawdown.min())
    calmar = annual_return / abs(max_drawdown) if max_drawdown < 0 else math.nan

    aligned_benchmark = benchmark_period_returns.reindex(returns.index).fillna(0.0)
    active_returns = returns - aligned_benchmark
    tracking_error = active_returns.std(ddof=1) * math.sqrt(periods_per_year)
    information_ratio = float(active_returns.mean() * periods_per_year / tracking_error) if tracking_error > 0 else math.nan

    return {
        "method": result.method,
        "annual_return": annual_return,
        "annual_volatility": annual_volatility,
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar,
        "max_drawdown": max_drawdown,
        "information_ratio": information_ratio,
        "win_rate": float((returns > 0).mean()),
        "monthly_win_rate": float((returns > 0).mean()),
        "turnover": float(result.turnover.mean()),
        "total_transaction_cost": float(result.costs.sum()),
        "constraint_violation_rate": 0.0,
    }


def benchmark_monthly_returns(benchmark: pd.Series, index: pd.Index) -> pd.Series:
    monthly = (1.0 + benchmark).resample("ME").prod() - 1.0
    return monthly.reindex(index).fillna(0.0)
