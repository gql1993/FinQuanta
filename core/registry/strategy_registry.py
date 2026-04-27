"""
Strategy registry skeleton.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyDefinition:
    key: str
    name: str
    source: str = "desktop.strategy_rotator"


def get_strategy_registry() -> dict[str, StrategyDefinition]:
    from desktop.strategy_rotator import STRATEGY_NAMES

    return {
        key: StrategyDefinition(key=key, name=value)
        for key, value in STRATEGY_NAMES.items()
    }


def list_registered_strategies() -> list[dict]:
    return [
        {
            "key": definition.key,
            "name": definition.name,
            "source": definition.source,
        }
        for definition in get_strategy_registry().values()
    ]
