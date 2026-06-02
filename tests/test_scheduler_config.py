from core.config.scheduler import get_ai_scheduler_settings, get_arena_scheduler_settings
from core.config.scan import get_scan_consumer_settings


def test_ai_scheduler_settings_defaults(monkeypatch):
    monkeypatch.delenv("FINQUANTA_AI_SCHEDULER_MORNING_TIME", raising=False)
    monkeypatch.delenv("FINQUANTA_AI_SCHEDULER_AFTERNOON_TIME", raising=False)

    settings = get_ai_scheduler_settings()

    assert settings.times == ["10:15", "14:00"]


def test_ai_scheduler_settings_env_override(monkeypatch):
    monkeypatch.setenv("FINQUANTA_AI_SCHEDULER_MORNING_TIME", "10:30")
    monkeypatch.setenv("FINQUANTA_AI_SCHEDULER_AFTERNOON_TIME", "14:30")

    settings = get_ai_scheduler_settings()

    assert settings.times == ["10:30", "14:30"]


def test_arena_scheduler_settings_defaults(monkeypatch):
    monkeypatch.delenv("FINQUANTA_ARENA_SCHEDULER_ENABLED", raising=False)
    monkeypatch.delenv("FINQUANTA_ARENA_SCHEDULER_MORNING_TIME", raising=False)
    monkeypatch.delenv("FINQUANTA_ARENA_SCHEDULER_AFTERNOON_TIME", raising=False)
    monkeypatch.delenv("FINQUANTA_ARENA_SCHEDULER_PUSH", raising=False)

    settings = get_arena_scheduler_settings()

    assert settings.enabled is True
    assert settings.times == ["10:04", "14:03"]
    assert settings.push_summary is False


def test_arena_scheduler_settings_env_override(monkeypatch):
    monkeypatch.setenv("FINQUANTA_ARENA_SCHEDULER_ENABLED", "0")
    monkeypatch.setenv("FINQUANTA_ARENA_SCHEDULER_MORNING_TIME", "10:20")
    monkeypatch.setenv("FINQUANTA_ARENA_SCHEDULER_AFTERNOON_TIME", "14:10")
    monkeypatch.setenv("FINQUANTA_ARENA_SCHEDULER_PUSH", "true")

    settings = get_arena_scheduler_settings()

    assert settings.enabled is False
    assert settings.times == ["10:20", "14:10"]
    assert settings.push_summary is True


def test_scan_consumer_settings_defaults(monkeypatch):
    monkeypatch.delenv("FINQUANTA_AI_SCAN_SOURCE", raising=False)
    monkeypatch.delenv("FINQUANTA_AI_SCAN_MIN_HITS", raising=False)

    settings = get_scan_consumer_settings()

    assert settings.source == "latest"
    assert settings.min_hits == 1


def test_scan_consumer_settings_env_override(monkeypatch):
    monkeypatch.setenv("FINQUANTA_AI_SCAN_SOURCE", "daemon")
    monkeypatch.setenv("FINQUANTA_AI_SCAN_MIN_HITS", "2")

    settings = get_scan_consumer_settings()

    assert settings.source == "daemon"
    assert settings.min_hits == 2
