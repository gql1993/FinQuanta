"""Services behind Web/desktop parity API."""

from __future__ import annotations

import pytest


@pytest.fixture
def kv_memory(monkeypatch):
    store: dict = {}

    def get_k(key, default=None):
        return store.get(key, default)

    def set_k(key, value):
        store[key] = value

    monkeypatch.setattr("desktop.data_access.get_kv_json", get_k)
    monkeypatch.setattr("desktop.data_access.set_kv_json", set_k)
    return store


def test_arena_leaderboard_service():
    from core.application.arena_service import get_arena_leaderboard

    lb = get_arena_leaderboard()
    assert "rows" in lb


def test_manual_portfolio_detail(kv_memory):
    from core.application.manual_portfolio_service import get_manual_portfolio_detail

    detail = get_manual_portfolio_detail()
    assert detail["cash"] == 1_000_000
    assert detail["positions"] == []
