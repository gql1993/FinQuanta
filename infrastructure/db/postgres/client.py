from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator


class PostgresBackend:
    """Low-level PostgreSQL implementation used by repository adapters."""

    def __init__(self, dsn: str, persistent: bool = False):
        self.dsn = dsn
        self.persistent = persistent
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
    def conn(self) -> Iterator:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            if not self.persistent:
                conn.close()

    @staticmethod
    def normalize_sql(sql: str) -> str:
        return sql.replace("?", "%s")

    def fetchone(self, sql: str, params: tuple = ()) -> tuple | None:
        with self.conn() as conn:
            with conn.cursor() as cur:
                cur.execute(self.normalize_sql(sql), params)
                return cur.fetchone()

    def fetchall(self, sql: str, params: tuple = ()) -> list[tuple]:
        with self.conn() as conn:
            with conn.cursor() as cur:
                cur.execute(self.normalize_sql(sql), params)
                return cur.fetchall()

    def execute(self, sql: str, params: tuple = ()) -> None:
        with self.conn() as conn:
            with conn.cursor() as cur:
                cur.execute(self.normalize_sql(sql), params)

    def executemany(self, sql: str, seq_of_params: list[tuple]) -> None:
        if not seq_of_params:
            return
        with self.conn() as conn:
            with conn.cursor() as cur:
                cur.executemany(self.normalize_sql(sql), seq_of_params)

    def executescript(self, sql: str) -> None:
        statements = [stmt.strip() for stmt in sql.split(";") if stmt.strip()]
        with self.conn() as conn:
            with conn.cursor() as cur:
                for stmt in statements:
                    cur.execute(stmt)
