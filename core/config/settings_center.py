"""
Centralized settings access.

The first version is intentionally environment-backed so the project gains a
single read path before introducing richer user/project settings layers.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _coerce_bool(value: str | bool | int | None, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on", "enabled"}:
        return True
    if normalized in {"0", "false", "no", "off", "disabled"}:
        return False
    return default


@dataclass
class SettingsCenter:
    def get(self, key: str, default=None):
        return os.environ.get(key, default)

    def get_bool(self, key: str, default: bool = False) -> bool:
        return _coerce_bool(os.environ.get(key), default=default)

    def get_int(self, key: str, default: int = 0) -> int:
        try:
            return int(os.environ.get(key, default))
        except (TypeError, ValueError):
            return default

    def get_str(self, key: str, default: str = "") -> str:
        value = os.environ.get(key)
        return default if value is None else str(value)


settings_center = SettingsCenter()
