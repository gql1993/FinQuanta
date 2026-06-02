"""Bidirectional sync reconcile logic."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest


@pytest.fixture
def kv_repo(tmp_path, monkeypatch):
    db = tmp_path / "quant.db"
    monkeypatch.setenv("FINQUANTA_SQLITE_PATH", str(db))
    monkeypatch.setenv("FINQUANTA_DB_BACKEND", "sqlite")
    from desktop.db import init_db
    from desktop.data_access import get_repo
    from core.sync.kv_meta import kv_set_with_timestamp

    init_db()
    from desktop.ai_portfolio import _init_table

    _init_table()
    repo = get_repo()
    kv_set_with_timestamp(repo, "manual_portfolio", {"cash": 900000, "positions": []})
    return repo


def test_reconcile_client_wins_newer_kv(kv_repo):
    from core.sync.kv_meta import kv_set_with_timestamp, list_syncable_kv
    from core.sync.reconcile_service import reconcile_with_repository

    newer = datetime.now(timezone.utc).isoformat()
    incoming = {
        "manual_portfolio": {
            "value": {"cash": 800000, "positions": []},
            "updated_at": newer,
        }
    }
    result = reconcile_with_repository(kv_repo, incoming_kv=incoming, incoming_positions=[])
    assert result["imported_kv"] >= 1
    local = list_syncable_kv(kv_repo)["manual_portfolio"]["value"]
    assert local["cash"] == 800000


def test_reconcile_server_wins_outbound(kv_repo):
    from core.sync.kv_meta import kv_set_with_timestamp
    from core.sync.reconcile_service import reconcile_with_repository

    kv_set_with_timestamp(kv_repo, "manual_portfolio", {"cash": 950000, "positions": []})
    old_time = "2020-01-01T00:00:00+00:00"
    incoming = {
        "manual_portfolio": {
            "value": {"cash": 100000, "positions": []},
            "updated_at": old_time,
        }
    }
    result = reconcile_with_repository(kv_repo, incoming_kv=incoming, incoming_positions=[])
    assert "manual_portfolio" in result["outbound_kv"]
    assert result["outbound_kv"]["manual_portfolio"]["value"]["cash"] == 950000
