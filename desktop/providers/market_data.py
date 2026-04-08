"""日 K / 历史行情：默认走 data_sync / db。"""
from __future__ import annotations

from typing import Any

from desktop.domain_models import MarketBar


class MarketDataProvider:
    """腾讯日 K 等，经统一数据层读取。"""

    def fetch_daily_bars(self, code: str, limit: int = 260) -> list[MarketBar]:
        from desktop import db

        df = db.get_daily(code)
        if df is None or df.empty:
            return []
        rows = []
        tail = df.tail(limit)
        for _, r in tail.iterrows():
            d = r.get("date")
            ds = str(d)[:10] if d is not None else ""
            rows.append(
                MarketBar(
                    symbol=code,
                    date=ds,
                    open=float(r.get("open", 0) or 0),
                    high=float(r.get("high", 0) or 0),
                    low=float(r.get("low", 0) or 0),
                    close=float(r.get("close", 0) or 0),
                    volume=float(r.get("volume", 0) or 0),
                    amount=float(r.get("amount", 0) or 0),
                )
            )
        return rows

    def refresh_latest_kline(self, codes: list[str] | None = None, **kwargs: Any) -> dict:
        from desktop.data_sync import refresh_latest_kline

        return refresh_latest_kline(codes=codes, **kwargs)
