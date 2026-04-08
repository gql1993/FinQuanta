"""
Feature flag helpers.

Flags are currently environment-driven with a stable naming convention so the
project can add richer configuration sources later without changing callers.
"""

from __future__ import annotations

from core.config.settings_center import settings_center


DEFAULT_FEATURE_FLAGS: dict[str, bool] = {
    "openclaw_pipeline": True,
    "openclaw_learning": True,
    "trade_approval": True,
}


def _env_key(feature_name: str) -> str:
    normalized = feature_name.strip().upper().replace("-", "_")
    return f"FINQUANTA_FEATURE_{normalized}"


def is_feature_enabled(feature_name: str, default: bool | None = None) -> bool:
    fallback = (
        DEFAULT_FEATURE_FLAGS.get(feature_name, False)
        if default is None
        else default
    )
    return settings_center.get_bool(_env_key(feature_name), default=fallback)
