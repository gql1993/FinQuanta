"""
统一回测服务接口

封装 local_backtest，统一：
1. 单策略回测
2. 多策略批量回测
3. 回测结果摘要序列化
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from desktop.local_backtest import (
    LocalBacktestResult,
    run_local_backtest,
    run_multi_strategy_backtest,
    run_walk_forward,
)


def result_to_dict(result: LocalBacktestResult | None) -> dict[str, Any]:
    if result is None:
        return {}
    return {
        "total_return": result.total_return,
        "annual_return": result.annual_return,
        "max_drawdown": result.max_drawdown,
        "sharpe_ratio": result.sharpe_ratio,
        "win_rate": result.win_rate,
        "profit_loss_ratio": result.profit_loss_ratio,
        "total_trades": result.total_trades,
        "winning_trades": result.winning_trades,
        "losing_trades": result.losing_trades,
        "avg_hold_days": result.avg_hold_days,
        "max_consecutive_losses": result.max_consecutive_losses,
        "trades": result.trades,
        "equity_curve": result.equity_curve,
    }


def run_strategy_backtest(
    strategy_id: str,
    sample_size: int = 100,
    start_date: str = "2022-06-01",
    initial_capital: float = 1_000_000,
    stop_loss_pct: float = 0.08,
    max_positions: int = 5,
    progress_callback=None,
) -> dict[str, Any]:
    result = run_local_backtest(
        strategy=strategy_id,
        sample_size=sample_size,
        start_date=start_date,
        initial_capital=initial_capital,
        stop_loss_pct=stop_loss_pct,
        max_positions=max_positions,
        progress_callback=progress_callback,
    )
    data = result_to_dict(result)
    data["strategy"] = strategy_id
    return data


def run_strategy_suite(
    strategy_ids: list[str],
    sample_size: int = 100,
    start_date: str = "2022-06-01",
) -> list[dict[str, Any]]:
    outputs = []
    for sid in strategy_ids:
        data = run_strategy_backtest(
            strategy_id=sid,
            sample_size=sample_size,
            start_date=start_date,
        )
        outputs.append(data)
    return outputs


def run_walkforward_service(strategy_id: str, sample_size: int = 100, n_windows: int = 4) -> dict[str, Any]:
    return run_walk_forward(strategy_id, sample_size, n_windows=n_windows)


def run_multi_service(strategy_ids: list[str], sample_size: int = 120) -> list[dict[str, Any]]:
    return run_multi_strategy_backtest(strategy_ids, sample_size=sample_size)
