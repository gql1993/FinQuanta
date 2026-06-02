"""
Application-facing sync service wrappers.
"""

from __future__ import annotations

from core.sync.export_service import build_export_payload, export_to_file
from core.sync.import_service import import_from_file
from core.sync.reconcile_service import reconcile_with_repository


def export_runtime_state(keys: list[str] | None = None) -> dict:
    return build_export_payload(keys=keys)


def export_runtime_state_to_file(file_path: str, keys: list[str] | None = None) -> dict:
    return export_to_file(file_path=file_path, keys=keys)


def import_runtime_state_from_file(file_path: str, overwrite: bool = True) -> dict:
    return import_from_file(file_path=file_path, overwrite=overwrite)


def reconcile_runtime_state(
    *,
    device_id: str = "",
    kv_changes: dict | None = None,
    positions: list[dict] | None = None,
    repository=None,
) -> dict:
    from api_server.storage import repo as default_repo

    repo = repository or default_repo
    result = reconcile_with_repository(
        repo,
        incoming_kv=kv_changes or {},
        incoming_positions=positions or [],
        prefer="remote",
    )
    result["device_id"] = device_id
    return result
