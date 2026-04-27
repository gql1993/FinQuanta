"""
Application-facing sync service wrappers.
"""

from __future__ import annotations

from core.sync.export_service import build_export_payload, export_to_file
from core.sync.import_service import import_from_file


def export_runtime_state(keys: list[str] | None = None) -> dict:
    return build_export_payload(keys=keys)


def export_runtime_state_to_file(file_path: str, keys: list[str] | None = None) -> dict:
    return export_to_file(file_path=file_path, keys=keys)


def import_runtime_state_from_file(file_path: str, overwrite: bool = True) -> dict:
    return import_from_file(file_path=file_path, overwrite=overwrite)
