"""
Desktop ↔ server bidirectional sync over FinQuanta API.

Enable with environment variables or kv `finquanta_sync_config`:
  FINQUANTA_SYNC_ENABLED=1
  FINQUANTA_API_BASE=http://10.70.0.150:9000
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

_log = logging.getLogger("desktop.sync")

_SYNC_STATE_KEY = "_finquanta_sync_state"
_SYNC_PENDING_KEY = "_finquanta_sync_pending"
_SYNC_CONFIG_KEY = "finquanta_sync_config"
_APPLYING = False


def _device_id() -> str:
    import platform
    import socket

    host = socket.gethostname()
    return f"desktop-{platform.system()}-{host}"[:120]


def load_sync_config() -> dict:
    cfg: dict[str, Any] = {
        "enabled": os.environ.get("FINQUANTA_SYNC_ENABLED", "").strip().lower() in {"1", "true", "yes"},
        "api_base": os.environ.get("FINQUANTA_API_BASE", "http://127.0.0.1:9000").rstrip("/"),
        "username": os.environ.get("FINQUANTA_SYNC_USER", "admin"),
        "password": os.environ.get("FINQUANTA_SYNC_PASSWORD", "admin123"),
        "interval_seconds": int(os.environ.get("FINQUANTA_SYNC_INTERVAL", "30") or 30),
        "disable_local_daemon": os.environ.get("FINQUANTA_SYNC_DISABLE_LOCAL_DAEMON", "1").strip().lower()
        in {"1", "true", "yes"},
    }
    try:
        from desktop.data_access import get_kv_json

        saved = get_kv_json(_SYNC_CONFIG_KEY, {}) or {}
        if isinstance(saved, dict):
            cfg.update({k: v for k, v in saved.items() if v is not None})
    except Exception:
        pass
    cfg["interval_seconds"] = max(10, int(cfg.get("interval_seconds", 30) or 30))
    cfg["api_base"] = str(cfg.get("api_base", cfg["api_base"])).rstrip("/")
    return cfg


def save_sync_config(cfg: dict) -> None:
    from core.sync.kv_meta import now_iso
    from desktop.data_access import get_repo

    repo = get_repo()
    repo.execute(
        "INSERT OR REPLACE INTO kv_store VALUES (?,?,?)",
        (_SYNC_CONFIG_KEY, json.dumps(cfg, ensure_ascii=False, default=str), now_iso()),
    )


def is_sync_enabled() -> bool:
    return bool(load_sync_config().get("enabled"))


def should_disable_local_daemon() -> bool:
    cfg = load_sync_config()
    return bool(cfg.get("enabled")) and bool(cfg.get("disable_local_daemon", True))


def record_pending_key(key: str, value: Any) -> None:
    if _APPLYING:
        return
    from core.sync.registry import is_syncable_key
    from core.sync.kv_meta import now_iso
    from desktop.data_access import get_kv_json, get_repo

    if not is_syncable_key(key):
        return
    repo = get_repo()
    pending = get_kv_json(_SYNC_PENDING_KEY, {}) or {}
    if not isinstance(pending, dict):
        pending = {}
    pending[key] = {"value": value, "updated_at": now_iso()}
    payload = json.dumps(pending, ensure_ascii=False, default=str)
    repo.execute(
        "INSERT OR REPLACE INTO kv_store VALUES (?,?,?)",
        (_SYNC_PENDING_KEY, payload, now_iso()),
    )


def install_sync_hooks() -> None:
    """Wrap set_kv_json so local edits queue for the next reconcile."""
    import desktop.data_access as da

    if getattr(da, "_sync_hook_installed", False):
        return
    original = da.set_kv_json

    def wrapped(key: str, value: Any) -> None:
        record_pending_key(key, value)
        return original(key, value)

    da.set_kv_json = wrapped
    da._sync_hook_installed = True


def _api_call(cfg: dict, method: str, path: str, payload: dict | None = None) -> dict:
    token = str(cfg.get("token", "") or "")
    if not token:
        login = _api_call(cfg, "POST", "/api/auth/login", {"username": cfg["username"], "password": cfg["password"]})
        if login.get("ok") and login.get("token"):
            cfg["token"] = login["token"]
            save_sync_config(cfg)
            token = cfg["token"]
        else:
            raise RuntimeError(login.get("message", "API login failed"))

    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(cfg["api_base"] + path, data=data, method=method.upper(), headers=headers)
    host = (urllib.parse.urlparse(cfg["api_base"]).hostname or "").lower()
    opener = (
        urllib.request.build_opener(urllib.request.ProxyHandler({}))
        if host in {"127.0.0.1", "localhost", "0.0.0.0"}
        else urllib.request.build_opener()
    )
    with opener.open(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _collect_client_payload() -> dict:
    from core.sync.kv_meta import list_syncable_kv
    from core.sync.positions_sync import export_positions_bundle
    from desktop.data_access import get_kv_json, get_repo

    repo = get_repo()
    kv = list_syncable_kv(repo)
    pending = get_kv_json(_SYNC_PENDING_KEY, {}) or {}
    if isinstance(pending, dict):
        for key, entry in pending.items():
            if isinstance(entry, dict) and "value" in entry:
                kv[key] = {
                    "value": entry["value"],
                    "updated_at": entry.get("updated_at", ""),
                }
    return {
        "device_id": _device_id(),
        "kv_changes": kv,
        "positions": export_positions_bundle(repo),
    }


def _apply_server_payload(data: dict) -> dict:
    global _APPLYING
    from core.sync.kv_meta import kv_set_with_timestamp
    from core.sync.positions_sync import apply_positions_bundle
    from desktop.data_access import get_repo

    _APPLYING = True
    try:
        repo = get_repo()
        applied_kv = 0
        for key, entry in (data.get("outbound_kv") or {}).items():
            if isinstance(entry, dict):
                kv_set_with_timestamp(repo, key, entry.get("value"))
                applied_kv += 1
        pos_stats = apply_positions_bundle(repo, data.get("positions") or [])
        return {"applied_kv": applied_kv, "positions": pos_stats}
    finally:
        _APPLYING = False


def _clear_synced_pending(server_keys: set[str]) -> None:
    from core.sync.kv_meta import now_iso
    from desktop.data_access import get_kv_json, get_repo

    pending = get_kv_json(_SYNC_PENDING_KEY, {}) or {}
    if not isinstance(pending, dict):
        return
    for key in list(pending.keys()):
        if key in server_keys:
            pending.pop(key, None)
    repo = get_repo()
    repo.execute(
        "INSERT OR REPLACE INTO kv_store VALUES (?,?,?)",
        (_SYNC_PENDING_KEY, json.dumps(pending, ensure_ascii=False), now_iso()),
    )


def run_sync() -> dict:
    """One reconcile round. Safe to call from QTimer."""
    cfg = load_sync_config()
    if not cfg.get("enabled"):
        return {"skipped": True, "reason": "sync disabled"}

    install_sync_hooks()
    try:
        payload = _collect_client_payload()
        resp = _api_call(
            cfg,
            "POST",
            "/api/sync/reconcile",
            {
                "device_id": payload["device_id"],
                "kv_changes": payload["kv_changes"],
                "positions": payload["positions"],
            },
        )
        if not resp.get("ok"):
            raise RuntimeError(resp.get("message", "sync failed"))
        data = resp.get("data", {})
        local_apply = _apply_server_payload(data)
        _clear_synced_pending(set(payload["kv_changes"].keys()))

        from core.sync.kv_meta import now_iso
        from desktop.data_access import set_kv_json

        state = {
            "last_ok": now_iso(),
            "device_id": payload["device_id"],
            "imported_kv_server": data.get("imported_kv", 0),
            "applied_kv_local": local_apply.get("applied_kv", 0),
            "message": resp.get("message", ""),
        }
        set_kv_json(_SYNC_STATE_KEY, state)
        return {"ok": True, **state}
    except urllib.error.URLError as exc:
        _log.warning("sync unreachable: %s", exc)
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        _log.warning("sync failed: %s", exc)
        return {"ok": False, "error": str(exc)}
