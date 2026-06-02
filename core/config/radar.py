from __future__ import annotations

from dataclasses import dataclass

from core.config.settings_center import settings_center


@dataclass(frozen=True)
class DaemonRadarSettings:
    """Unattended radar scan — off by default (no system-wide main strategy)."""

    enabled: bool = False


def get_daemon_radar_settings() -> DaemonRadarSettings:
    return DaemonRadarSettings(
        enabled=settings_center.get_bool("FINQUANTA_DAEMON_AUTO_SCAN", default=False),
    )
