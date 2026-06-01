from __future__ import annotations

from dataclasses import dataclass

from core.config.settings_center import settings_center


@dataclass(frozen=True)
class AiSchedulerSettings:
    morning_time: str = "10:15"
    afternoon_time: str = "14:00"

    @property
    def times(self) -> list[str]:
        return [self.morning_time, self.afternoon_time]


@dataclass(frozen=True)
class ArenaSchedulerSettings:
    enabled: bool = True
    morning_time: str = "10:17"
    afternoon_time: str = "14:03"
    push_summary: bool = False

    @property
    def times(self) -> list[str]:
        return [self.morning_time, self.afternoon_time]


def get_ai_scheduler_settings() -> AiSchedulerSettings:
    return AiSchedulerSettings(
        morning_time=settings_center.get_str("FINQUANTA_AI_SCHEDULER_MORNING_TIME", "10:15"),
        afternoon_time=settings_center.get_str("FINQUANTA_AI_SCHEDULER_AFTERNOON_TIME", "14:00"),
    )


def get_arena_scheduler_settings() -> ArenaSchedulerSettings:
    return ArenaSchedulerSettings(
        enabled=settings_center.get_bool("FINQUANTA_ARENA_SCHEDULER_ENABLED", default=True),
        morning_time=settings_center.get_str("FINQUANTA_ARENA_SCHEDULER_MORNING_TIME", "10:17"),
        afternoon_time=settings_center.get_str("FINQUANTA_ARENA_SCHEDULER_AFTERNOON_TIME", "14:03"),
        push_summary=settings_center.get_bool("FINQUANTA_ARENA_SCHEDULER_PUSH", default=False),
    )
