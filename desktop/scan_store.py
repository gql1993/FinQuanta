"""Canonical read/write for stock scan results (last_scan_results + metadata)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from core.config.scan import get_scan_consumer_settings
from desktop.data_access import get_kv_json, set_kv_json

_log = logging.getLogger("scan_store")

SCAN_RESULTS_KEY = "last_scan_results"
SCAN_META_KEY = "last_scan_results_meta"

_SOURCE_LABELS = {
    "daemon": "定时扫描",
    "ui": "手动扫描",
    "unknown": "未知",
}


def save_scan_results(
    rows: list[dict],
    *,
    source: str,
    strategy_id: str,
) -> None:
    """Persist scan rows and metadata sidecar (single write contract for all producers)."""
    payload = list(rows or [])
    set_kv_json(SCAN_RESULTS_KEY, payload)
    meta = {
        "source": str(source or "unknown"),
        "strategy_id": str(strategy_id or ""),
        "count": len(payload),
        "written_at": datetime.now().isoformat(timespec="seconds"),
    }
    set_kv_json(SCAN_META_KEY, meta)
    _log.info(
        "scan results saved: source=%s strategy=%s count=%s",
        meta["source"],
        meta["strategy_id"],
        meta["count"],
    )


def get_scan_results(default: list | None = None) -> list:
    rows = get_kv_json(SCAN_RESULTS_KEY, default)
    return rows if isinstance(rows, list) else (default or [])


def get_scan_results_meta(default: dict | None = None) -> dict[str, Any]:
    meta = get_kv_json(SCAN_META_KEY, default)
    return meta if isinstance(meta, dict) else (default or {})


def resolve_scan_results() -> tuple[list[dict], dict[str, Any], str | None]:
    """
    Return scan rows for AI / custom portfolio consumers, honoring FINQUANTA_AI_SCAN_SOURCE.

    Returns (rows, meta, warning). warning is set when configured source filter yields nothing.
    """
    rows = list(get_scan_results())
    meta = get_scan_results_meta()
    settings = get_scan_consumer_settings()
    warning: str | None = None

    if settings.source == "resonance":
        min_hits = max(2, settings.min_hits)
        filtered = [r for r in rows if int(r.get("命中数", 1) or 1) >= min_hits]
        if rows and not filtered:
            warning = f"共振筛选：无命中数≥{min_hits} 的候选（共 {len(rows)} 只原始结果）"
        rows = filtered
    elif settings.source in {"daemon", "ui"}:
        actual = str(meta.get("source", "") or "")
        if actual and actual != settings.source:
            warning = (
                f"扫描来源不匹配：配置要求 {settings.source}，"
                f"当前为 {actual or '未知'}（{meta.get('written_at', '-')})"
            )
            rows = []
        elif not rows:
            warning = f"无扫描结果（期望来源 {settings.source}）"
    elif settings.min_hits > 1:
        rows = [r for r in rows if int(r.get("命中数", 1) or 1) >= settings.min_hits]

    return rows, meta, warning


def format_scan_meta_summary(
    meta: dict[str, Any] | None = None,
    *,
    count: int | None = None,
    warning: str | None = None,
) -> str:
    """One-line label for AI panel / logs."""
    meta = meta or {}
    settings = get_scan_consumer_settings()
    src = str(meta.get("source", "") or "unknown")
    src_label = _SOURCE_LABELS.get(src, src)
    strategy = str(meta.get("strategy_id", "") or "-")
    written = str(meta.get("written_at", "") or "-")
    n = count if count is not None else int(meta.get("count", 0) or 0)
    parts = [
        f"选股池：{n} 只",
        f"来源 {src_label}",
        f"策略 {strategy}",
        f"更新 {written}",
    ]
    if settings.source != "latest":
        parts.append(f"消费规则 {settings.source}")
    if warning:
        parts.append(f"⚠ {warning}")
    return " | ".join(parts)
