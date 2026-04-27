"""
Application-facing registry service wrappers.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import time
from datetime import datetime, timezone

from core.registry import (
    list_registered_agents,
    list_registered_notifiers,
    list_registered_providers,
    list_registered_strategies,
    list_registered_workflows,
)

_REGISTRY_CACHE: dict = {}


def _registry_cache_ttl_seconds() -> int:
    raw = str(os.environ.get("FINQUANTA_REGISTRY_CACHE_TTL", "30") or "30").strip()
    try:
        ttl = int(raw)
    except Exception:
        ttl = 30
    return max(1, ttl)


def _build_registry_change_token(
    providers: list[dict],
    strategies: list[dict],
    notifiers: list[dict],
    workflows: list[dict],
    agents: list[dict],
) -> str:
    payload = {
        "providers": sorted(
            [
                {
                    "key": item.get("key", ""),
                    "module_path": item.get("module_path", ""),
                    "capabilities": sorted(item.get("capabilities", [])),
                }
                for item in providers
            ],
            key=lambda item: item["key"],
        ),
        "strategies": sorted(
            [
                {
                    "key": item.get("key", ""),
                    "name": item.get("name", ""),
                    "source": item.get("source", ""),
                }
                for item in strategies
            ],
            key=lambda item: item["key"],
        ),
        "notifiers": sorted(
            [
                {
                    "key": item.get("key", ""),
                    "module_path": item.get("module_path", ""),
                    "channels": sorted(item.get("channels", [])),
                }
                for item in notifiers
            ],
            key=lambda item: item["key"],
        ),
        "workflows": sorted(
            [
                {
                    "key": item.get("key", ""),
                    "trigger": item.get("trigger", ""),
                    "handler_path": item.get("handler_path", ""),
                }
                for item in workflows
            ],
            key=lambda item: item["key"],
        ),
        "agents": sorted(
            [
                {
                    "key": item.get("key", ""),
                    "entrypoint": item.get("entrypoint", ""),
                    "capabilities": sorted(item.get("capabilities", [])),
                    "safety_level": item.get("safety_level", ""),
                }
                for item in agents
            ],
            key=lambda item: item["key"],
        ),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha1(encoded).hexdigest()


def get_registry_overview(force_refresh: bool = False) -> dict:
    now_ts = time.time()
    cached_payload = _REGISTRY_CACHE.get("payload")
    expires_at_ts = float(_REGISTRY_CACHE.get("expires_at_ts", 0) or 0)
    if (not force_refresh) and cached_payload and now_ts < expires_at_ts:
        payload = copy.deepcopy(cached_payload)
        payload.setdefault("meta", {})
        payload["meta"]["cached"] = True
        return payload

    providers = list_registered_providers()
    strategies = list_registered_strategies()
    notifiers = list_registered_notifiers()
    workflows = list_registered_workflows()
    agents = list_registered_agents()
    refreshed_at = datetime.now(timezone.utc).isoformat()
    change_token = _build_registry_change_token(providers, strategies, notifiers, workflows, agents)
    ttl_seconds = _registry_cache_ttl_seconds()
    expires_at = datetime.fromtimestamp(now_ts + ttl_seconds, timezone.utc).isoformat()
    payload = {
        "providers": providers,
        "strategies": strategies,
        "provider_count": len(providers),
        "strategy_count": len(strategies),
        "notifiers": notifiers,
        "workflows": workflows,
        "agents": agents,
        "notifier_count": len(notifiers),
        "workflow_count": len(workflows),
        "agent_count": len(agents),
        "meta": {
            "refreshed_at": refreshed_at,
            "expires_at": expires_at,
            "source": "core.registry",
            "provider_source": "core.registry.provider_registry",
            "strategy_source": "core.registry.strategy_registry",
            "notifier_source": "core.registry.notifier_registry",
            "workflow_source": "core.registry.workflow_registry",
            "agent_source": "core.registry.agent_registry",
            "change_token": change_token,
            "cache_ttl_seconds": ttl_seconds,
            "cached": False,
        },
    }
    _REGISTRY_CACHE["payload"] = copy.deepcopy(payload)
    _REGISTRY_CACHE["expires_at_ts"] = now_ts + ttl_seconds
    return payload


def get_registered_providers() -> list[dict]:
    return list_registered_providers()


def get_registered_strategies() -> list[dict]:
    return list_registered_strategies()


def get_registered_notifiers() -> list[dict]:
    return list_registered_notifiers()


def get_registered_workflows() -> list[dict]:
    return list_registered_workflows()


def get_registered_agents() -> list[dict]:
    return list_registered_agents()
