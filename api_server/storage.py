from __future__ import annotations

"""
存储抽象层

当前实现：
- SQLiteRepository: 实际可用
- PostgresRepository: 占位骨架
- CacheProvider: Redis 占位骨架

目标：
- API 层不直接依赖 sqlite3 细节
- 后续切 PostgreSQL / Redis 时，业务接口尽量不变
"""

import json
import os
from contextlib import contextmanager
from typing import Any

from api_server.config import settings
from core.repositories.base import BaseRepository
from infrastructure.db.postgres import PostgresBackend
from infrastructure.db.sqlite import SQLiteBackend


class SQLiteRepository(BaseRepository):
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or settings.sqlite_path
        self.backend = SQLiteBackend(self.db_path)

    @contextmanager
    def conn(self):
        with self.backend.conn() as conn:
            yield conn

    def fetchone(self, sql: str, params: tuple = ()) -> tuple | None:
        return self.backend.fetchone(sql, params)

    def fetchall(self, sql: str, params: tuple = ()) -> list[tuple]:
        return self.backend.fetchall(sql, params)

    def execute(self, sql: str, params: tuple = ()):
        self.backend.execute(sql, params)

    def executemany(self, sql: str, seq_of_params: list[tuple]):
        self.backend.executemany(sql, seq_of_params)

    def executescript(self, sql: str):
        self.backend.executescript(sql)

    def kv_get(self, key: str, default=None):
        row = self.fetchone("SELECT value FROM kv_store WHERE key=?", (key,))
        if not row:
            return default
        try:
            return json.loads(row[0])
        except Exception:
            return row[0]

    def kv_set(self, key: str, value: Any):
        payload = json.dumps(value, ensure_ascii=False, default=str)
        self.execute(
            "INSERT OR REPLACE INTO kv_store VALUES (?,?,datetime('now'))",
            (key, payload),
        )

    def ping(self) -> dict:
        try:
            row = self.fetchone("SELECT 1")
            return {"ok": bool(row and row[0] == 1), "backend": "sqlite", "detail": "connected"}
        except Exception as exc:
            return {"ok": False, "backend": "sqlite", "detail": str(exc)}


class PostgresRepository(BaseRepository):
    """真实 PostgreSQL 仓储实现。"""

    def __init__(self, dsn: str | None = None):
        self.dsn = dsn or settings.postgres_dsn
        self.persistent = os.environ.get("FINQUANTA_PG_PERSISTENT", "").strip().lower() in {"1", "true", "yes"}
        self.backend = PostgresBackend(self.dsn, persistent=self.persistent)

    @contextmanager
    def conn(self):
        with self.backend.conn() as conn:
            yield conn

    def fetchone(self, sql: str, params: tuple = ()):
        return self.backend.fetchone(sql, params)

    def fetchall(self, sql: str, params: tuple = ()):
        return self.backend.fetchall(sql, params)

    def execute(self, sql: str, params: tuple = ()):
        self.backend.execute(sql, params)

    def executemany(self, sql: str, seq_of_params: list[tuple]):
        self.backend.executemany(sql, seq_of_params)

    def executescript(self, sql: str):
        self.backend.executescript(sql)

    def kv_get(self, key: str, default=None):
        row = self.fetchone("SELECT value FROM kv_store WHERE key=%s", (key,))
        if not row:
            return default
        try:
            return row[0] if isinstance(row[0], dict) else json.loads(row[0])
        except Exception:
            return row[0]

    def kv_set(self, key: str, value: Any):
        payload = json.dumps(value, ensure_ascii=False, default=str)
        sql = (
            "INSERT INTO kv_store(key, value, updated_at) VALUES (%s, %s::jsonb, CURRENT_TIMESTAMP) "
            "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=CURRENT_TIMESTAMP"
        )
        self.execute(sql, (key, payload))

    def ping(self) -> dict:
        try:
            row = self.fetchone("SELECT 1")
            return {"ok": bool(row and row[0] == 1), "backend": "postgres", "detail": "connected"}
        except Exception as exc:
            return {"ok": False, "backend": "postgres", "detail": str(exc)}


class CacheProvider:
    """
    Redis 占位骨架。当前仍使用 kv_store / system_snapshot。
    """

    def __init__(self, url: str | None = None):
        self.url = url or settings.redis_url

    def enabled(self) -> bool:
        return bool(self.url)

    def get(self, key: str):
        return None

    def set(self, key: str, value: Any, ttl: int | None = None):
        return False

    def ping(self) -> dict:
        return {"ok": not self.enabled(), "backend": "redis", "detail": "disabled" if not self.enabled() else "not_implemented"}


def get_repository() -> BaseRepository:
    if settings.db_backend == "postgres":
        if not str(settings.postgres_dsn or "").strip():
            raise RuntimeError("FINQUANTA_POSTGRES_DSN is required when FINQUANTA_DB_BACKEND=postgres")
        return PostgresRepository()
    return SQLiteRepository()


repo = get_repository()
cache = CacheProvider()
