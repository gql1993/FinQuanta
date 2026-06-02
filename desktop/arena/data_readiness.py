"""Pre-flight checks before Agent Arena scans (K-line coverage)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

_log = logging.getLogger("arena.data_readiness")

# Keep aligned with desktop.arena.strategy_runner._MIN_BARS
MIN_BARS = 50
DEFAULT_MIN_ELIGIBLE_CODES = 10


@dataclass(frozen=True)
class KlineReadiness:
    ok: bool
    eligible_codes: int
    total_codes: int
    min_bars: int
    min_eligible_codes: int
    message: str


def assess_kline_readiness(
    *,
    min_bars: int = MIN_BARS,
    min_eligible_codes: int = DEFAULT_MIN_ELIGIBLE_CODES,
) -> KlineReadiness:
    """Return whether local daily_kline has enough history for arena scans."""
    from desktop.data_access import get_repo

    repo = get_repo()
    try:
        total_row = repo.fetchone("SELECT COUNT(DISTINCT code) FROM daily_kline", ())
        total_codes = int(total_row[0] or 0) if total_row else 0
    except Exception as exc:
        _log.warning("kline readiness: daily_kline unavailable: %s", exc)
        return KlineReadiness(
            ok=False,
            eligible_codes=0,
            total_codes=0,
            min_bars=min_bars,
            min_eligible_codes=min_eligible_codes,
            message=(
                "请先刷新 K 线：本地缺少 daily_kline 表或数据尚未导入。"
                " 请在 daemon 中执行「刷新K线日线」(10:00) 或先同步行情后再运行竞技场。"
            ),
        )

    try:
        eligible_row = repo.fetchone(
            "SELECT COUNT(*) FROM ("
            "SELECT code FROM daily_kline GROUP BY code HAVING COUNT(*) >= ?"
            ")",
            (min_bars,),
        )
        eligible_codes = int(eligible_row[0] or 0) if eligible_row else 0
    except Exception as exc:
        _log.warning("kline readiness count failed: %s", exc)
        eligible_codes = 0

    if eligible_codes >= min_eligible_codes:
        return KlineReadiness(
            ok=True,
            eligible_codes=eligible_codes,
            total_codes=total_codes,
            min_bars=min_bars,
            min_eligible_codes=min_eligible_codes,
            message="",
        )

    message = (
        f"请先刷新 K 线：当前仅 {eligible_codes} 只股票满足 ≥{min_bars} 根日线"
        f"（共 {total_codes} 只有 K 线记录，竞技场至少需要 {min_eligible_codes} 只）。"
        " 请先执行「刷新K线日线」(10:00 定时任务) 或数据同步后再运行竞技场。"
    )
    return KlineReadiness(
        ok=False,
        eligible_codes=eligible_codes,
        total_codes=total_codes,
        min_bars=min_bars,
        min_eligible_codes=min_eligible_codes,
        message=message,
    )
