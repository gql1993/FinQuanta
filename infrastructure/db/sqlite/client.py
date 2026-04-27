from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator


class SQLiteBackend:
    """Low-level SQLite implementation used by repository adapters."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

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

    def execute(self, sql: str, params: tuple = ()) -> None:
        with self.conn() as conn:
            conn.execute(sql, params)

    def executemany(self, sql: str, seq_of_params: list[tuple]) -> None:
        if not seq_of_params:
            return
        with self.conn() as conn:
            conn.executemany(sql, seq_of_params)

    def executescript(self, sql: str) -> None:
        with self.conn() as conn:
            conn.executescript(sql)
