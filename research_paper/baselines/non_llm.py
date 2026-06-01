"""Strategy baselines for the paper sandbox."""

from __future__ import annotations

from typing import Any

import pandas as pd

from research_paper.evaluation.metrics import BacktestResult


NON_LLM_METHODS = {
    "equal_weight",
    "multifactor_topk",
    "sepa_stock_magician_topk",
    "vcp_topk",
    "fixed_multistrategy_fusion",
    "llm_strategy_agent_mock",
}


def _rank_01(series: pd.Series) -> pd.Series:
    if series.nunique(dropna=True) <= 1:
        return pd.Series(0.5, index=series.index)
    return series.rank(pct=True).fillna(0.5)


def rebalance_dates(dates: pd.DatetimeIndex) -> pd.DatetimeIndex:
    return pd.Series(dates, index=dates).resample("ME").last().dropna().values.astype("datetime64[ns]")


def build_strategy_scores(
    returns: pd.DataFrame,
    metadata: pd.DataFrame,
    as_of_date: pd.Timestamp,
) -> pd.DataFrame:
    history = returns.loc[:as_of_date].tail(126)
    if len(history) < 21:
        raise ValueError("At least 21 business days of history are required for baseline scoring.")

    momentum = (1.0 + history.tail(63)).prod() - 1.0
    short_momentum = (1.0 + history.tail(21)).prod() - 1.0
    realized_vol = history.tail(63).std()
    value_quality = 0.55 * _rank_01(metadata["quality"]) + 0.45 * _rank_01(metadata["value"])
    low_volatility = 1.0 - _rank_01(realized_vol)

    score_frame = pd.DataFrame(index=returns.columns)
    score_frame["momentum"] = _rank_01(momentum)
    score_frame["value_quality"] = _rank_01(value_quality)
    score_frame["low_volatility"] = _rank_01(low_volatility)
    score_frame["sepa_stock_magician"] = _rank_01(
        0.40 * score_frame["momentum"]
        + 0.30 * _rank_01(short_momentum)
        + 0.20 * _rank_01(metadata["growth"])
        + 0.10 * _rank_01(metadata["liquidity"])
    )
    score_frame["vcp"] = _rank_01(
        0.35 * score_frame["momentum"]
        + 0.35 * score_frame["low_volatility"]
        + 0.20 * _rank_01(short_momentum)
        + 0.10 * _rank_01(metadata["liquidity"])
    )
    score_frame["multifactor"] = score_frame[
        ["momentum", "value_quality", "low_volatility", "sepa_stock_magician", "vcp"]
    ].mean(axis=1)
    score_frame["sector"] = metadata["sector"]
    return score_frame


def select_weights(
    method: str,
    scores: pd.DataFrame,
    target_count: int,
    strategy_agent: Any | None = None,
    as_of_date: pd.Timestamp | None = None,
    market_regime: dict[str, Any] | None = None,
) -> pd.Series:
    weights = pd.Series(0.0, index=scores.index)

    if method == "equal_weight":
        selected = scores.index
    elif method == "multifactor_topk":
        selected = scores["multifactor"].nlargest(target_count).index
    elif method == "sepa_stock_magician_topk":
        selected = scores["sepa_stock_magician"].nlargest(target_count).index
    elif method == "vcp_topk":
        selected = scores["vcp"].nlargest(target_count).index
    elif method == "fixed_multistrategy_fusion":
        fusion = scores[["sepa_stock_magician", "vcp", "momentum", "value_quality", "low_volatility"]].mean(axis=1)
        selected = fusion.nlargest(target_count).index
    elif method == "llm_strategy_agent_mock":
        if strategy_agent is None or as_of_date is None:
            raise ValueError("llm_strategy_agent_mock requires a strategy_agent and as_of_date.")
        fusion = strategy_agent.weighted_scores(as_of_date, scores, market_regime)
        selected = fusion.nlargest(target_count).index
    else:
        raise ValueError(f"Unsupported baseline method: {method}")

    weights.loc[selected] = 1.0 / len(selected)
    return weights


def run_backtest(
    method: str,
    returns: pd.DataFrame,
    benchmark: pd.Series,
    metadata: pd.DataFrame,
    config: dict[str, Any],
    strategy_agent: Any | None = None,
    market_regime_agent: Any | None = None,
) -> BacktestResult:
    dates = returns.index
    all_rebalance_dates = pd.DatetimeIndex(rebalance_dates(dates))
    all_rebalance_dates = all_rebalance_dates[all_rebalance_dates >= dates[min(126, len(dates) - 1)]]
    holdings_cfg = config["strategy_scores"]["final_holdings_range"]
    target_count = int(holdings_cfg.get("max", 30))
    cost_cfg = config["transaction_costs"]
    one_way_cost = (
        float(cost_cfg.get("commission_bps", 0))
        + float(cost_cfg.get("slippage_bps", 0))
        + 0.5 * float(cost_cfg.get("stamp_duty_bps_sell", 0))
    ) / 10000.0

    prev_weights = pd.Series(0.0, index=returns.columns)
    equity = 1.0
    equity_points: dict[pd.Timestamp, float] = {}
    period_returns: dict[pd.Timestamp, float] = {}
    turnovers: dict[pd.Timestamp, float] = {}
    costs: dict[pd.Timestamp, float] = {}

    for idx, rebalance_date in enumerate(all_rebalance_dates[:-1]):
        next_rebalance = all_rebalance_dates[idx + 1]
        scores = build_strategy_scores(returns, metadata, rebalance_date)
        market_regime = None
        if method == "llm_strategy_agent_mock" and market_regime_agent is not None:
            market_regime = market_regime_agent.generate(rebalance_date, benchmark)
        weights = select_weights(
            method,
            scores,
            target_count,
            strategy_agent=strategy_agent,
            as_of_date=rebalance_date,
            market_regime=market_regime,
        )
        turnover = float((weights - prev_weights).abs().sum())
        trade_cost = turnover * one_way_cost
        period_slice = returns.loc[(returns.index > rebalance_date) & (returns.index <= next_rebalance)]
        gross_return = float((1.0 + period_slice.dot(weights)).prod() - 1.0)
        net_return = gross_return - trade_cost
        equity *= 1.0 + net_return

        equity_points[next_rebalance] = equity
        period_returns[next_rebalance] = net_return
        turnovers[next_rebalance] = turnover
        costs[next_rebalance] = trade_cost
        prev_weights = weights

    if not equity_points:
        raise RuntimeError("No backtest periods were generated. Check date range and rebalance settings.")

    return BacktestResult(
        method=method,
        equity_curve=pd.Series(equity_points, name=method),
        period_returns=pd.Series(period_returns, name=method),
        turnover=pd.Series(turnovers, name=method),
        costs=pd.Series(costs, name=method),
    )
