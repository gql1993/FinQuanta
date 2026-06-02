"""SEPA market environment filter — distribution days + index Stage 2."""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from config import MarketRegimeConfig

_log = logging.getLogger("arena.market_regime")

_INDEX_FALLBACKS = ("000300", "000001")
_MIN_INDEX_BARS = 260
_regime_cache: dict[str, tuple[str, dict]] = {}


def _index_candidates(index_code: str | None) -> tuple[str, ...]:
    cfg = MarketRegimeConfig()
    primary = (index_code or cfg.index_code or "000300").strip()
    out: list[str] = []
    for code in (primary, *_INDEX_FALLBACKS):
        if code and code not in out:
            out.append(code)
    return tuple(out)


def load_index_dataframe(
    repo=None,
    *,
    index_code: str | None = None,
    limit: int = _MIN_INDEX_BARS,
) -> tuple[pd.DataFrame | None, str]:
    """Load index OHLCV from daily_kline; fetch remotely when DB is sparse."""
    from desktop.data_access import get_repo

    repo = repo or get_repo()
    for code in _index_candidates(index_code):
        rows = repo.fetchall(
            "SELECT date, open, high, low, close, volume FROM daily_kline "
            "WHERE code=? ORDER BY date DESC LIMIT ?",
            (code, limit),
        )
        if len(rows) >= 30:
            rows = rows[::-1]
            df = pd.DataFrame(
                rows, columns=["date", "open", "high", "low", "close", "volume"]
            )
            for col in ("open", "high", "low", "close", "volume"):
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df = df.dropna(subset=["close"])
            if len(df) >= 30:
                return df, code

        try:
            from desktop.data_sync import fetch_index_daily

            fetched = fetch_index_daily(code)
        except Exception as exc:
            _log.debug("fetch_index_daily %s failed: %s", code, exc)
            fetched = []
        if len(fetched) >= 30:
            df = pd.DataFrame(
                fetched,
                columns=[
                    "code",
                    "date",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "amount",
                    "pct_chg",
                ],
            )
            df = df[["date", "open", "high", "low", "close", "volume"]]
            for col in ("open", "high", "low", "close", "volume"):
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df = df.dropna(subset=["close"]).tail(limit)
            if len(df) >= 30:
                return df.reset_index(drop=True), code

    return None, index_code or MarketRegimeConfig().index_code


def assess_index_stage(index_df: pd.DataFrame) -> bool:
    """Index trend template (Stage 2) — same 8 conditions as individual stocks."""
    if index_df is None or index_df.empty or len(index_df) < 30:
        return True
    from config import StrategyConfig
    from trend_template import TrendTemplate

    tt = TrendTemplate(StrategyConfig().trend)
    return bool(tt.check(index_df).get("passed", False))


def assess_market_regime(
    repo=None,
    *,
    index_code: str | None = None,
    use_cache: bool = True,
) -> dict:
    """
    SEPA buy precondition (Ch 9):
    - distribution-day filter via MarketRegimeFilter.market_ok
    - index Stage 2 via trend template on benchmark index
    """
    cache_key = index_code or "default"
    today = date.today().isoformat()
    if use_cache and cache_key in _regime_cache:
        cached_date, cached = _regime_cache[cache_key]
        if cached_date == today:
            return dict(cached)

    cfg = MarketRegimeConfig()
    index_df, resolved_code = load_index_dataframe(repo, index_code=index_code)

    result = {
        "index_code": resolved_code,
        "market_ok": True,
        "index_stage2": True,
        "sepa_market_ok": True,
        "dist_count": 0,
        "in_correction": False,
        "reason": "指数数据不足，默认允许买入",
        "block_reason": "",
    }

    if index_df is None or index_df.empty:
        if use_cache:
            _regime_cache[cache_key] = (today, result)
        return result

    from strategy import MarketRegimeFilter

    mrf = MarketRegimeFilter(cfg)
    regime_df = mrf.compute_regime(index_df)
    latest = regime_df.iloc[-1]
    market_ok = bool(latest.get("market_ok", True))
    dist_count = int(latest.get("dist_count", 0) or 0)
    index_stage2 = assess_index_stage(index_df)
    sepa_market_ok = market_ok and index_stage2

    parts: list[str] = []
    block_parts: list[str] = []
    if market_ok:
        parts.append(f"分布日{dist_count}/{cfg.max_distribution_days}")
    else:
        block_parts.append(
            f"分布日{dist_count}≥{cfg.max_distribution_days}（需{cfg.rally_confirmation_days}日放量反弹确认）"
        )
    if index_stage2:
        parts.append("大盘Stage2")
    else:
        block_parts.append("大盘未处Stage2上升趋势")

    result.update(
        {
            "market_ok": market_ok,
            "index_stage2": index_stage2,
            "sepa_market_ok": sepa_market_ok,
            "dist_count": dist_count,
            "in_correction": not market_ok,
            "reason": "；".join(parts) if parts else "市场环境待确认",
            "block_reason": "；".join(block_parts),
        }
    )

    if use_cache:
        _regime_cache[cache_key] = (today, result)
    return result


def clear_market_regime_cache() -> None:
    _regime_cache.clear()
