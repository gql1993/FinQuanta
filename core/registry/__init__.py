"""
Registry helpers for extensible FinQuanta components.
"""

from __future__ import annotations

from importlib import import_module

_EXPORTS = {
    "get_provider_registry": "core.registry.provider_registry",
    "list_registered_providers": "core.registry.provider_registry",
    "get_strategy_registry": "core.registry.strategy_registry",
    "list_registered_strategies": "core.registry.strategy_registry",
    "get_notifier_registry": "core.registry.notifier_registry",
    "list_registered_notifiers": "core.registry.notifier_registry",
    "get_workflow_registry": "core.registry.workflow_registry",
    "list_registered_workflows": "core.registry.workflow_registry",
    "get_agent_registry": "core.registry.agent_registry",
    "list_registered_agents": "core.registry.agent_registry",
}


def __getattr__(name: str):
    module_name = _EXPORTS.get(name)
    if not module_name:
        raise AttributeError(name)
    module = import_module(module_name)
    return getattr(module, name)


__all__ = list(_EXPORTS.keys())
