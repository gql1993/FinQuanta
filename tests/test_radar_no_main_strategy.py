"""No system-wide main strategy — radar and arena are separate."""

from __future__ import annotations

from core.config.radar import get_daemon_radar_settings


def test_daemon_radar_scan_disabled_by_default(monkeypatch):
    monkeypatch.delenv("FINQUANTA_DAEMON_AUTO_SCAN", raising=False)
    assert get_daemon_radar_settings().enabled is False


def test_daemon_radar_scan_opt_in(monkeypatch):
    monkeypatch.setenv("FINQUANTA_DAEMON_AUTO_SCAN", "1")
    assert get_daemon_radar_settings().enabled is True
