"""
Shared repository abstraction.

This is the first M3 step: define a stable contract for storage backends before
moving more business code away from direct SQLite/PostgreSQL assumptions.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from typing import Any, Iterable


class BaseRepository(ABC):
    """Common contract for storage backends."""

    @abstractmethod
    def conn(self) -> AbstractContextManager[Any]:
        raise NotImplementedError

    @abstractmethod
    def fetchone(self, sql: str, params: tuple = ()) -> tuple | None:
        raise NotImplementedError

    @abstractmethod
    def fetchall(self, sql: str, params: tuple = ()) -> list[tuple]:
        raise NotImplementedError

    @abstractmethod
    def execute(self, sql: str, params: tuple = ()) -> None:
        raise NotImplementedError

    @abstractmethod
    def executemany(self, sql: str, seq_of_params: Iterable[tuple]) -> None:
        raise NotImplementedError

    @abstractmethod
    def executescript(self, sql: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def kv_get(self, key: str, default=None):
        raise NotImplementedError

    @abstractmethod
    def kv_set(self, key: str, value: Any) -> None:
        raise NotImplementedError

    @abstractmethod
    def ping(self) -> dict:
        raise NotImplementedError
