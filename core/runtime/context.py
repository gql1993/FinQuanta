"""
Runtime context assembly.
"""

from __future__ import annotations

from core.runtime.mode import RuntimeModeContext, resolve_runtime_mode_context


def build_runtime_context(
    *,
    runtime_mode: str | None = None,
    db_backend: str | None = None,
    api_base: str | None = None,
) -> RuntimeModeContext:
    return resolve_runtime_mode_context(
        runtime_mode=runtime_mode,
        db_backend=db_backend,
        api_base=api_base,
    )
