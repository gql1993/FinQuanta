"""
Application-level trend verify service.
"""

from __future__ import annotations


def get_trend_verify_records(
    limit: int = 100,
    status: str = "",
    strategy: str = "",
    board: str = "",
    root_cause: str = "",
    market_regime: str = "",
    failed_only: bool = False,
    since_days: int = 0,
) -> list[dict]:
    from desktop.trend_verify import get_records

    return get_records(
        limit=limit,
        status=status,
        strategy=strategy,
        board=board,
        root_cause=root_cause,
        market_regime=market_regime,
        failed_only=failed_only,
        since_days=since_days,
    )


def get_trend_verify_stats() -> dict:
    from desktop.trend_verify import get_accuracy_stats

    return get_accuracy_stats()


def get_trend_failure_summary(
    limit: int = 200,
    strategy: str = "",
    board: str = "",
    market_regime: str = "",
    since_days: int = 365,
) -> dict:
    from desktop.trend_verify import get_failure_summary

    return get_failure_summary(
        limit=limit,
        strategy=strategy,
        board=board,
        market_regime=market_regime,
        since_days=since_days,
    )


def run_batch_failure_analysis(
    limit: int = 80,
    strategy: str = "",
    board: str = "",
    since_days: int = 365,
) -> dict:
    from desktop.trend_verify import batch_analyze_failures

    return batch_analyze_failures(
        limit=limit,
        strategy=strategy,
        board=board,
        since_days=since_days,
    )
