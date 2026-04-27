"""
Runtime data export service.

M3-08 focuses on turning ad-hoc scripts into reusable capabilities. The first
cut exports selected kv_store keys into a JSON snapshot.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from api_server.config import settings
from api_server.storage import repo as default_repo

DEFAULT_EXPORT_KEYS = [
    "manual_portfolio",
    "portfolio_risk",
    "system_snapshot",
    "ai_config",
    "push_config",
    "last_scan_results",
]


def build_export_payload(keys: list[str] | None = None, repository=None) -> dict:
    repo = repository or default_repo
    selected_keys = [k for k in (keys or DEFAULT_EXPORT_KEYS) if k]
    data = {key: repo.kv_get(key, None) for key in selected_keys}
    return {
        "schema_version": "1.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "db_backend": settings.db_backend,
        "keys": selected_keys,
        "data": data,
    }


def export_to_file(file_path: str, keys: list[str] | None = None, repository=None) -> dict:
    payload = build_export_payload(keys=keys, repository=repository)
    target = Path(file_path).expanduser()
    if not target.is_absolute():
        target = Path.cwd() / target
    target.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    target.write_text(body, encoding="utf-8")
    return {
        "file_path": str(target),
        "key_count": len(payload.get("keys", [])),
        "bytes": len(body.encode("utf-8")),
        "exported_at": payload.get("exported_at", ""),
    }
