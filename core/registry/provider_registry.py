"""
Provider registry skeleton.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderDefinition:
    key: str
    display_name: str
    module_path: str
    capabilities: tuple[str, ...]


def get_provider_registry() -> dict[str, ProviderDefinition]:
    return {
        "llm": ProviderDefinition(
            key="llm",
            display_name="LLM Provider",
            module_path="desktop.providers.llm",
            capabilities=("chat_completion",),
        ),
        "market_data": ProviderDefinition(
            key="market_data",
            display_name="Market Data Provider",
            module_path="desktop.providers.market_data",
            capabilities=("daily_kline", "quotes"),
        ),
        "realtime_quote": ProviderDefinition(
            key="realtime_quote",
            display_name="Realtime Quote Provider",
            module_path="desktop.providers.realtime_quote",
            capabilities=("realtime_quotes",),
        ),
        "news": ProviderDefinition(
            key="news",
            display_name="News Provider",
            module_path="desktop.providers.news",
            capabilities=("news_feed",),
        ),
    }


def list_registered_providers() -> list[dict]:
    return [
        {
            "key": definition.key,
            "display_name": definition.display_name,
            "module_path": definition.module_path,
            "capabilities": list(definition.capabilities),
        }
        for definition in get_provider_registry().values()
    ]
