"""Bidirectional reconcile: desktop ↔ server runtime state."""

from __future__ import annotations

from typing import Any

from core.sync.kv_meta import _parse_ts, kv_set_with_timestamp, list_syncable_kv, now_iso
from core.sync.positions_sync import apply_positions_bundle, export_positions_bundle, merge_position_rows
from core.sync.registry import is_syncable_key


def _pick_kv_winner(
    local: dict | None,
    remote: dict | None,
    *,
    prefer: str = "remote",
) -> tuple[dict | None, str]:
    """Return (winner_entry, source) where entry is {value, updated_at}."""
    if not local and not remote:
        return None, ""
    if not local:
        return remote, "remote"
    if not remote:
        return local, "local"
    lt = _parse_ts(local.get("updated_at"))
    rt = _parse_ts(remote.get("updated_at"))
    if lt > rt:
        return local, "local"
    if rt > lt:
        return remote, "remote"
    return (remote if prefer == "remote" else local), prefer


def reconcile_state(
    *,
    local_kv: dict[str, dict],
    remote_kv: dict[str, dict],
    local_positions: list[dict],
    remote_positions: list[dict],
    prefer: str = "remote",
) -> dict[str, Any]:
    """Pure merge; returns payloads each side should apply."""
    keys = set(local_kv) | set(remote_kv)
    apply_local_kv: dict[str, dict] = {}
    apply_remote_kv: dict[str, dict] = {}
    for key in keys:
        if not is_syncable_key(key):
            continue
        winner, source = _pick_kv_winner(local_kv.get(key), remote_kv.get(key), prefer=prefer)
        if not winner:
            continue
        if source == "local":
            apply_remote_kv[key] = winner
        elif source == "remote":
            apply_local_kv[key] = winner

    merged_positions = merge_position_rows(local_positions, remote_positions)

    return {
        "apply_local_kv": apply_local_kv,
        "apply_remote_kv": apply_remote_kv,
        "merged_positions": merged_positions,
        "server_time": now_iso(),
    }


def reconcile_with_repository(
    repository,
    *,
    incoming_kv: dict[str, dict] | None = None,
    incoming_positions: list[dict] | None = None,
    prefer: str = "remote",
) -> dict[str, Any]:
    """Run reconcile against a single repo; apply remote-side updates (server path)."""
    local_kv = list_syncable_kv(repository)
    incoming_kv = incoming_kv or {}
    local_positions = export_positions_bundle(repository)
    incoming_positions = incoming_positions or []

    plan = reconcile_state(
        local_kv=local_kv,
        remote_kv=incoming_kv,
        local_positions=local_positions,
        remote_positions=incoming_positions,
        prefer=prefer,
    )

    imported_kv = 0
    for key, entry in plan["apply_local_kv"].items():
        kv_set_with_timestamp(repository, key, entry.get("value"))
        imported_kv += 1

    pos_stats = apply_positions_bundle(repository, plan["merged_positions"])

    outbound_kv = dict(plan["apply_remote_kv"])
    fresh = list_syncable_kv(repository)
    for key in outbound_kv:
        if key in fresh:
            outbound_kv[key] = fresh[key]

    return {
        "imported_kv": imported_kv,
        "outbound_kv": outbound_kv,
        "positions": export_positions_bundle(repository),
        "positions_stats": pos_stats,
        "server_time": plan["server_time"],
    }
