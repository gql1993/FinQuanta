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
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator

from api_server.config import settings
from core.repositories.base import BaseRepository


class SQLiteRepository(BaseRepository):
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or settings.sqlite_path

    @contextmanager
    def conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def fetchone(self, sql: str, params: tuple = ()) -> tuple | None:
        with self.conn() as conn:
            return conn.execute(sql, params).fetchone()

    def fetchall(self, sql: str, params: tuple = ()) -> list[tuple]:
        with self.conn() as conn:
            return conn.execute(sql, params).fetchall()

    def execute(self, sql: str, params: tuple = ()):
        with self.conn() as conn:
            conn.execute(sql, params)

    def executemany(self, sql: str, seq_of_params: list[tuple]):
        if not seq_of_params:
            return
        with self.conn() as conn:
            conn.executemany(sql, seq_of_params)

    def executescript(self, sql: str):
        with self.conn() as conn:
            conn.executescript(sql)

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
        self._shared_conn = None

    def _connect(self):
        if self.persistent and self._shared_conn is not None and not self._shared_conn.closed:
            return self._shared_conn
        if not self.dsn:
            raise RuntimeError("FINQUANTA_POSTGRES_DSN is not configured.")
        try:
            import psycopg
        except Exception as exc:
            raise RuntimeError("psycopg is required for PostgreSQL backend.") from exc
        conn = psycopg.connect(self.dsn)
        if self.persistent:
            self._shared_conn = conn
        return conn

    @contextmanager
    def conn(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            if not self.persistent:
                conn.close()

    def _sql(self, sql: str) -> str:
        return sql.replace("?", "%s")

    def fetchone(self, sql: str, params: tuple = ()):
        with self.conn() as conn:
            with conn.cursor() as cur:
                cur.execute(self._sql(sql), params)
                return cur.fetchone()

    def fetchall(self, sql: str, params: tuple = ()):
        with self.conn() as conn:
            with conn.cursor() as cur:
                cur.execute(self._sql(sql), params)
                return cur.fetchall()

    def execute(self, sql: str, params: tuple = ()):
        with self.conn() as conn:
            with conn.cursor() as cur:
                cur.execute(self._sql(sql), params)

    def executemany(self, sql: str, seq_of_params: list[tuple]):
        if not seq_of_params:
            return
        with self.conn() as conn:
            with conn.cursor() as cur:
                cur.executemany(self._sql(sql), seq_of_params)

    def executescript(self, sql: str):
        statements = [stmt.strip() for stmt in sql.split(";") if stmt.strip()]
        with self.conn() as conn:
            with conn.cursor() as cur:
                for stmt in statements:
                    cur.execute(stmt)

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
        return PostgresRepository()
    return SQLiteRepository()


repo = get_repository()
cache = CacheProvider()
