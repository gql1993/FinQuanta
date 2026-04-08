"""新闻 / 事件：默认东方财富等。"""
from __future__ import annotations

from typing import Any


class NewsProvider:
    def fetch_headlines(self, limit: int = 20) -> list[dict[str, Any]]:
        try:
            from desktop.event_strategy import fetch_news_eastmoney

            return fetch_news_eastmoney(limit=limit) or []
        except Exception:
            return []
