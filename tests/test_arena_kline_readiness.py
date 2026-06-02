"""Arena K-line readiness preflight."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

_ARENA_PKG = "desktop.arena"


@pytest.fixture(autouse=True)
def _stub_arena_package():
    """Load data_readiness without executing desktop.arena.__init__ (heavy imports)."""
    if _ARENA_PKG not in sys.modules:
        pkg = types.ModuleType(_ARENA_PKG)
        pkg.__path__ = [str(Path(__file__).resolve().parents[1] / "desktop" / "arena")]
        sys.modules[_ARENA_PKG] = pkg
    yield


@pytest.fixture
def mock_repo(monkeypatch):
    state = {"total": 0, "eligible": 0, "error": None}

    class FakeRepo:
        def fetchone(self, sql, params=()):
            if state["error"]:
                raise state["error"]
            if "DISTINCT code" in sql and "GROUP BY" not in sql:
                return (state["total"],)
            if "HAVING COUNT" in sql:
                return (state["eligible"],)
            return (0,)

    monkeypatch.setattr("desktop.data_access.get_repo", lambda: FakeRepo())
    return state


def test_kline_readiness_ok(mock_repo):
    from desktop.arena.data_readiness import assess_kline_readiness

    mock_repo["total"] = 500
    mock_repo["eligible"] = 120
    result = assess_kline_readiness(min_eligible_codes=10)
    assert result.ok is True
    assert result.message == ""


def test_kline_readiness_insufficient(mock_repo):
    from desktop.arena.data_readiness import assess_kline_readiness

    mock_repo["total"] = 3
    mock_repo["eligible"] = 2
    result = assess_kline_readiness(min_eligible_codes=10)
    assert result.ok is False
    assert "请先刷新 K 线" in result.message


def test_kline_readiness_missing_table(mock_repo):
    from desktop.arena.data_readiness import assess_kline_readiness

    mock_repo["error"] = Exception("no such table: daily_kline")
    result = assess_kline_readiness()
    assert result.ok is False
    assert "请先刷新 K 线" in result.message
