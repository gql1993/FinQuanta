"""
实盘底座准备：统一订单/成交/风控事件总线

当前用于模拟事件分发与日志留痕，后续可接券商成交回报、风控引擎和 Web 推送。
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from desktop.task_orchestrator import log_system_event

_log = logging.getLogger("order_bus")


@dataclass
class BusEvent:
    event_type: str
    source: str
    payload: dict
    timestamp: str


class EventBus:
    def __init__(self):
        self._handlers: dict[str, list[Callable[[BusEvent], None]]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: Callable[[BusEvent], None]):
        self._handlers[event_type].append(handler)

    def publish(self, event_type: str, source: str, payload: dict):
        event = BusEvent(
            event_type=event_type,
            source=source,
            payload=payload,
            timestamp=datetime.now().isoformat(),
        )
        log_system_event(source, "order_bus", f"事件: {event_type}", detail=str(payload)[:300])
        for h in self._handlers.get(event_type, []):
            try:
                h(event)
            except Exception as e:
                _log.warning("handler error on %s: %s", event_type, e)


GLOBAL_EVENT_BUS = EventBus()
