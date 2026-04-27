"""
Structured logging helpers.

M4-06: provide a lightweight, dependency-free JSON logging utility with
standard trace fields for cross-module observability.
"""

from __future__ import annotations

import json
import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone
from typing import Any

_LOGGER_CACHE: dict[str, logging.Logger] = {}


def get_structured_logger(name: str = "finquanta.observability") -> logging.Logger:
    logger = _LOGGER_CACHE.get(name)
    if logger:
        return logger
    logger = logging.getLogger(name)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        _attach_file_handler(logger)
    if logger.level == logging.NOTSET:
        logger.setLevel(logging.INFO)
    _LOGGER_CACHE[name] = logger
    return logger


def build_structured_record(
    event: str,
    *,
    level: str = "INFO",
    trace_id: str = "",
    decision_id: str = "",
    source: str = "",
    category: str = "",
    metadata: dict[str, Any] | None = None,
    **fields: Any,
) -> dict[str, Any]:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "level": level.upper(),
        "trace_id": trace_id,
        "decision_id": decision_id,
        "source": source,
        "category": category,
        "metadata": dict(metadata or {}),
    }
    record.update(fields)
    return record


def emit_structured_log(
    event: str,
    *,
    level: str = "INFO",
    logger_name: str = "finquanta.observability",
    **fields: Any,
) -> dict[str, Any]:
    record = build_structured_record(event, level=level, **fields)
    logger = get_structured_logger(logger_name)
    body = json.dumps(record, ensure_ascii=False, default=str, separators=(",", ":"))
    logger.log(_to_logging_level(level), body)
    return record


def _to_logging_level(level: str) -> int:
    normalized = (level or "INFO").upper()
    return {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }.get(normalized, logging.INFO)


def _attach_file_handler(logger: logging.Logger) -> None:
    path = os.environ.get("FINQUANTA_STRUCTURED_LOG_PATH", os.path.join("logs", "observability", "structured.log"))
    text = str(path or "").strip()
    if not text:
        return
    try:
        os.makedirs(os.path.dirname(text) or ".", exist_ok=True)
        max_bytes = _safe_int(os.environ.get("FINQUANTA_STRUCTURED_LOG_MAX_BYTES"), 10 * 1024 * 1024)
        backup_count = _safe_int(os.environ.get("FINQUANTA_STRUCTURED_LOG_BACKUP_COUNT"), 5)
        file_handler = RotatingFileHandler(
            text,
            maxBytes=max(1024, max_bytes),
            backupCount=max(1, backup_count),
            encoding="utf-8",
        )
        file_handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(file_handler)
    except Exception:
        # File sink is best-effort; keep stdout logging functional.
        pass


def _safe_int(value: str | None, default: int) -> int:
    try:
        return int(str(value or "").strip())
    except (TypeError, ValueError):
        return int(default)
