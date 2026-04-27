"""
Unified event models for audit/ops pipelines.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


_DETAIL_WRAPPER_VERSION = 1


@dataclass
class SystemEvent:
    timestamp: str
    source: str
    category: str
    level: str
    title: str
    detail: str = ""
    event_type: str = "system"
    trace_id: str = ""
    decision_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_log_row(self) -> tuple[str, str, str, str, str, str]:
        return (
            self.timestamp,
            self.source,
            self.category,
            self.level,
            self.title,
            _encode_detail_payload(
                detail=self.detail,
                trace_id=self.trace_id,
                decision_id=self.decision_id,
                metadata=self.metadata,
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "source": self.source,
            "category": self.category,
            "level": self.level,
            "title": self.title,
            "detail": self.detail,
            "event_type": self.event_type,
            "trace_id": self.trace_id,
            "decision_id": self.decision_id,
            "metadata": dict(self.metadata),
        }


def create_system_event(
    source: str,
    category: str,
    title: str,
    detail: str = "",
    level: str = "info",
    *,
    trace_id: str = "",
    decision_id: str = "",
    metadata: dict[str, Any] | None = None,
    timestamp: str | None = None,
) -> SystemEvent:
    return SystemEvent(
        timestamp=timestamp or datetime.now().isoformat(),
        source=source,
        category=category,
        level=level,
        title=title,
        detail=detail,
        trace_id=trace_id,
        decision_id=decision_id,
        metadata=dict(metadata or {}),
    )


def event_from_log_row(row: tuple[Any, Any, Any, Any, Any, Any]) -> dict[str, Any]:
    raw_detail = row[5] if len(row) > 5 else ""
    parsed = _decode_detail_payload(raw_detail)
    return SystemEvent(
        timestamp=str(row[0] or ""),
        source=str(row[1] or ""),
        category=str(row[2] or ""),
        level=str(row[3] or "info"),
        title=str(row[4] or ""),
        detail=parsed["detail"],
        trace_id=parsed["trace_id"],
        decision_id=parsed["decision_id"],
        metadata=parsed["metadata"],
    ).to_dict()


def _encode_detail_payload(
    *,
    detail: str,
    trace_id: str = "",
    decision_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> str:
    metadata = dict(metadata or {})
    if not trace_id and not decision_id and not metadata:
        return detail
    payload = {
        "__event_detail__": _DETAIL_WRAPPER_VERSION,
        "detail": detail,
        "trace_id": trace_id,
        "decision_id": decision_id,
        "metadata": metadata,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _decode_detail_payload(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, str):
        return {"detail": str(raw or ""), "trace_id": "", "decision_id": "", "metadata": {}}
    text = raw.strip()
    if not text:
        return {"detail": "", "trace_id": "", "decision_id": "", "metadata": {}}
    if not (text.startswith("{") and text.endswith("}")):
        return {"detail": raw, "trace_id": "", "decision_id": "", "metadata": {}}
    try:
        data = json.loads(text)
    except Exception:
        return {"detail": raw, "trace_id": "", "decision_id": "", "metadata": {}}
    if not isinstance(data, dict) or "__event_detail__" not in data:
        return {"detail": raw, "trace_id": "", "decision_id": "", "metadata": {}}
    return {
        "detail": str(data.get("detail", "") or ""),
        "trace_id": str(data.get("trace_id", "") or ""),
        "decision_id": str(data.get("decision_id", "") or ""),
        "metadata": data.get("metadata", {}) if isinstance(data.get("metadata"), dict) else {},
    }
