from __future__ import annotations

"""
Redis 快照缓存适配骨架

当前默认不强依赖 redis-py。
若环境变量中配置 `FINQUANTA_REDIS_URL`，后续可接入真实 Redis。
"""

import json
from typing import Any

from api_server.config import settings


class SnapshotCache:
    def __init__(self):
        self.url = settings.redis_url
        self._client = None
        self._enabled = False
        if self.url:
            try:
                import redis  # type: ignore

                self._client = redis.from_url(self.url, decode_responses=True)
                self._enabled = True
            except Exception:
                self._client = None
                self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled and self._client is not None

    def get_json(self, key: str):
        if not self.enabled:
            return None
        try:
            raw = self._client.get(key)
            return json.loads(raw) if raw else None
        except Exception:
            return None

    def set_json(self, key: str, value: Any, ttl: int = 300):
        if not self.enabled:
            return False
        try:
            self._client.setex(key, ttl, json.dumps(value, ensure_ascii=False, default=str))
            return True
        except Exception:
            return False

    def ping(self):
        if not self.enabled:
            return {"ok": True, "backend": "redis", "detail": "disabled"}
        try:
            pong = self._client.ping()
            return {"ok": bool(pong), "backend": "redis", "detail": "connected"}
        except Exception as exc:
            return {"ok": False, "backend": "redis", "detail": str(exc)}


snapshot_cache = SnapshotCache()
