"""
Repository abstractions for FinQuanta.

Exports are resolved lazily to avoid storage-layer circular imports during the
transition from desktop-bound data access to shared repositories.
"""

from __future__ import annotations

from importlib import import_module

_EXPORTS = {
    "BaseRepository": "core.repositories.base",
    "DecisionRepository": "core.repositories.decision_repo",
    "PortfolioRepository": "core.repositories.portfolio_repo",
    "SnapshotRepository": "core.repositories.snapshot_repo",
    "TaskRepository": "core.repositories.task_repo",
}


def __getattr__(name: str):
    module_name = _EXPORTS.get(name)
    if not module_name:
        raise AttributeError(name)
    module = import_module(module_name)
    return getattr(module, name)


__all__ = list(_EXPORTS.keys())
