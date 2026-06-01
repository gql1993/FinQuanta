from __future__ import annotations

from dataclasses import dataclass

from core.config.settings_center import settings_center

_VALID_SOURCES = frozenset({"latest", "daemon", "ui", "resonance"})


@dataclass(frozen=True)
class ScanConsumerSettings:
    """How AI / custom portfolio consume last_scan_results."""

    source: str = "latest"
    min_hits: int = 1


def get_scan_consumer_settings() -> ScanConsumerSettings:
    raw = settings_center.get_str("FINQUANTA_AI_SCAN_SOURCE", "latest").strip().lower()
    source = raw if raw in _VALID_SOURCES else "latest"
    min_hits = max(1, settings_center.get_int("FINQUANTA_AI_SCAN_MIN_HITS", 1))
    return ScanConsumerSettings(source=source, min_hits=min_hits)
