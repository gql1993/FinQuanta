from __future__ import annotations

from dataclasses import dataclass

from core.config.settings_center import settings_center

# 工作日 10:00 / 13:30 自动刷新；设置页不可关闭（方案 A / 竞技场依赖）
PROTECTED_SCHEDULE_KEYS = frozenset({"refresh_kline", "refresh_kline_am", "refresh_kline_pm"})


@dataclass(frozen=True)
class KlineRefreshSettings:
    enabled: bool = True
    morning_time: str = "10:00"
    afternoon_time: str = "13:30"
    max_codes: int = 1200
    threads: int = 8
    stale_after_days: int = 2


def get_kline_refresh_settings() -> KlineRefreshSettings:
    return KlineRefreshSettings(
        enabled=settings_center.get_bool("FINQUANTA_KLINE_REFRESH_ENABLED", default=True),
        morning_time=settings_center.get_str("FINQUANTA_KLINE_REFRESH_MORNING_TIME", "10:00"),
        afternoon_time=settings_center.get_str("FINQUANTA_KLINE_REFRESH_AFTERNOON_TIME", "13:30"),
        max_codes=settings_center.get_int("FINQUANTA_KLINE_REFRESH_MAX_CODES", 1200),
        threads=settings_center.get_int("FINQUANTA_KLINE_REFRESH_THREADS", 8),
        stale_after_days=settings_center.get_int("FINQUANTA_KLINE_REFRESH_STALE_DAYS", 2),
    )


def filter_protected_disabled_tasks(disabled: set[str] | list[str] | None) -> set[str]:
    """Remove protected tasks so K-line refresh always runs on trading days."""
    if not disabled:
        return set()
    return {k for k in set(disabled) if k not in PROTECTED_SCHEDULE_KEYS}
