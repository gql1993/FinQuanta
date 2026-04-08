"""
Application-level trend verification service.
"""

from __future__ import annotations


def get_verify_records(limit: int = 100, status: str = "") -> list[dict]:
    from desktop.trend_verify import get_records

    return get_records(limit=limit, status=status)


def get_verify_accuracy_stats() -> dict:
    from desktop.trend_verify import get_accuracy_stats

    return get_accuracy_stats()


def calibrate_verify(max_age_days: int = 90) -> dict:
    from desktop.trend_verify import calibrate

    return calibrate(max_age_days=max_age_days)
