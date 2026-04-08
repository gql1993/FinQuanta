"""
Runtime mode resolution.

The product currently supports a local desktop-first mode and a platform/API-
first mode. This module centralizes how that mode is derived from environment
and deployment choices.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

LOCAL_MODE = "local"
PLATFORM_MODE = "platform"


@dataclass(frozen=True)
class RuntimeModeContext:
    runtime_mode: str
    db_backend: str
    api_base: str

    @property
    def is_local_mode(self) -> bool:
        return self.runtime_mode == LOCAL_MODE

    @property
    def is_platform_mode(self) -> bool:
        return self.runtime_mode == PLATFORM_MODE


def normalize_runtime_mode(value: str | None, db_backend: str | None = None) -> str:
    normalized = (value or "").strip().lower()
    if normalized in {"platform", "remote", "server", "service"}:
        return PLATFORM_MODE
    if normalized in {"local", "desktop", "standalone", "sqlite"}:
        return LOCAL_MODE
    backend = (db_backend or "").strip().lower()
    if backend == "postgres":
        return PLATFORM_MODE
    return LOCAL_MODE


def resolve_runtime_mode_context(
    *,
    runtime_mode: str | None = None,
    db_backend: str | None = None,
    api_base: str | None = None,
) -> RuntimeModeContext:
    resolved_backend = (db_backend or os.environ.get("FINQUANTA_DB_BACKEND", "sqlite")).strip().lower()
    resolved_api_base = api_base or os.environ.get("FINQUANTA_API_BASE", "http://127.0.0.1:9000")
    resolved_mode = normalize_runtime_mode(
        runtime_mode or os.environ.get("FINQUANTA_RUNTIME_MODE"),
        db_backend=resolved_backend,
    )
    return RuntimeModeContext(
        runtime_mode=resolved_mode,
        db_backend=resolved_backend,
        api_base=resolved_api_base,
    )
