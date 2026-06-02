"""Read/write kv_store entries with updated_at for reconciliation."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from core.sync.registry import is_syncable_key


def _parse_ts(raw: str | None) -> datetime:
    if not raw:
        return datetime.min.replace(tzinfo=timezone.utc)
    text = str(raw).strip().replace(" ", "T")
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def list_syncable_kv(repo) -> dict[str, dict]:
    """Return syncable keys -> {value, updated_at}."""
    rows = repo.fetchall("SELECT key, value, updated_at FROM kv_store")
    out: dict[str, dict] = {}
    for row in rows or []:
        key = row[0]
        if not is_syncable_key(key):
            continue
        raw_val = row[1]
        try:
            value = json.loads(raw_val) if isinstance(raw_val, str) else raw_val
        except Exception:
            value = raw_val
        out[key] = {
            "value": value,
            "updated_at": str(row[2] or ""),
        }
    return out


def kv_set_with_timestamp(repo, key: str, value) -> str:
    ts = now_iso()
    payload = json.dumps(value, ensure_ascii=False, default=str)
    repo.execute(
        "INSERT OR REPLACE INTO kv_store VALUES (?,?,?)",
        (key, payload, ts),
    )
    return ts
