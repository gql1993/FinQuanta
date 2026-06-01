"""Shared daily snapshot — per-strategy scans for fair arena comparison."""

from __future__ import annotations

import logging
from datetime import date, datetime

from core.ai.context_builder import build_market_context_text
from desktop.arena.participants import list_arena_strategy_ids
from desktop.arena.strategy_runner import scan_with_strategy
from desktop.data_access import get_kv_json, set_kv_json

_log = logging.getLogger("arena.snapshot")

_SNAPSHOT_KEY_PREFIX = "arena_snapshot_"


def _snapshot_key(day: str | None = None) -> str:
    return f"{_SNAPSHOT_KEY_PREFIX}{day or date.today().isoformat()}"


def run_stock_scan(*, limit: int = 50) -> list[dict]:
    """Legacy helper: scan with default SEPA profile (does not touch last_scan_results)."""
    return scan_with_strategy("sepa", limit=limit)


def build_strategy_scans(*, limit: int = 40) -> dict[str, list[dict]]:
    """Run fixed scan for each arena strategy profile."""
    scans: dict[str, list[dict]] = {}
    for sid in list_arena_strategy_ids():
        scans[sid] = scan_with_strategy(sid, limit=limit)
    return scans


def build_shared_snapshot(
    boards: list[str] | None = None,
    *,
    force: bool = False,
) -> dict:
    """Build or reuse today's snapshot with per-strategy candidate pools."""
    today = date.today().isoformat()
    key = _snapshot_key(today)
    if not force:
        cached = get_kv_json(key)
        if isinstance(cached, dict) and cached.get("date") == today and cached.get("strategy_scans"):
            return cached

    boards = boards or ["人工智能"]
    strategy_scans = build_strategy_scans()
    strategy_ids = list_arena_strategy_ids()

    sector_top3: list[str] = []
    try:
        sector = get_kv_json("sector_rotation", {}) or {}
        sector_top3 = list(sector.get("top3", []) or [])
    except Exception:
        pass

    try:
        market_summary = build_market_context_text()
    except Exception as exc:
        _log.warning("market context failed: %s", exc)
        market_summary = ""

    snapshot = {
        "date": today,
        "boards": boards,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "strategy_count": len(strategy_ids),
        "sector_top3": sector_top3,
        "strategy_scans": strategy_scans,
        "candidate_count": sum(len(v) for v in strategy_scans.values()),
        "market_summary": market_summary[:4000],
    }
    set_kv_json(key, snapshot)
    set_kv_json("arena_snapshot_latest", snapshot)
    _log.info(
        "arena snapshot saved: date=%s strategies=%s candidates=%s",
        today,
        len(strategy_ids),
        snapshot["candidate_count"],
    )
    return snapshot


def get_shared_snapshot(day: str | None = None) -> dict | None:
    key = _snapshot_key(day) if day else "arena_snapshot_latest"
    payload = get_kv_json(key)
    return payload if isinstance(payload, dict) else None


def get_strategy_candidates(snapshot: dict | None, strategy_id: str) -> list[dict]:
    if not snapshot:
        return []
    scans = snapshot.get("strategy_scans", {}) or {}
    return list(scans.get(strategy_id, []) or [])
