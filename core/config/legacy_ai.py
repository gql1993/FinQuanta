from __future__ import annotations

from dataclasses import dataclass

from core.config.settings_center import settings_center


@dataclass(frozen=True)
class LegacyAiWarehouseSettings:
    """Legacy four AI warehouses (full_auto/auto/custom/quantum). Disabled under Plan A."""

    enabled: bool = False


def get_legacy_ai_warehouse_settings() -> LegacyAiWarehouseSettings:
    return LegacyAiWarehouseSettings(
        enabled=settings_center.get_bool("FINQUANTA_LEGACY_AI_WAREHOUSES", default=False),
    )
