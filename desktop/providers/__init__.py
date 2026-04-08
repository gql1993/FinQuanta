"""数据源抽象：行情、实时、新闻、LLM。业务层应通过本包访问，便于替换实现。"""

from desktop.providers.llm import LLMProvider
from desktop.providers.market_data import MarketDataProvider
from desktop.providers.news import NewsProvider
from desktop.providers.realtime_quote import RealtimeQuoteProvider

__all__ = [
    "MarketDataProvider",
    "RealtimeQuoteProvider",
    "NewsProvider",
    "LLMProvider",
]
