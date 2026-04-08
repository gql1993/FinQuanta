"""
轻量事件引擎（参考 vn.py EventEngine：发布 / 订阅）

用于解耦网关、OMS、风控与 UI；与 order_bus.GLOBAL_EVENT_BUS 可并存，
后续可合并为单一总线。
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Callable

_log = logging.getLogger("event_engine")

Handler = Callable[[str, dict[str, Any]], None]


class EventEngine:
    def __init__(self):
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    def register(self, event_type: str, handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    def unregister(self, event_type: str, handler: Handler) -> None:
        try:
            self._handlers[event_type].remove(handler)
        except ValueError:
            pass

    def put(self, event_type: str, data: dict[str, Any]) -> None:
        for h in list(self._handlers.get(event_type, [])):
            try:
                h(event_type, data)
            except Exception as e:
                _log.warning("handler error on %s: %s", event_type, e)

    def put_many(self, pairs: list[tuple[str, dict[str, Any]]]) -> None:
        for et, data in pairs:
            self.put(et, data)


def get_default_engine() -> EventEngine:
    return _DEFAULT_ENGINE


_DEFAULT_ENGINE = EventEngine()
