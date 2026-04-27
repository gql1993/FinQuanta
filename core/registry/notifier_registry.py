"""
Notifier registry skeleton.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NotifierDefinition:
    key: str
    display_name: str
    module_path: str
    channels: tuple[str, ...]


def get_notifier_registry() -> dict[str, NotifierDefinition]:
    return {
        "serverchan": NotifierDefinition(
            key="serverchan",
            display_name="ServerChan Notifier",
            module_path="signal_push",
            channels=("wechat_personal",),
        ),
        "wecom": NotifierDefinition(
            key="wecom",
            display_name="WeCom Bot Notifier",
            module_path="signal_push",
            channels=("wecom_group_bot",),
        ),
        "app_message_feed": NotifierDefinition(
            key="app_message_feed",
            display_name="App Message Feed Notifier",
            module_path="core.application.ops_service",
            channels=("in_app_feed",),
        ),
    }


def list_registered_notifiers() -> list[dict]:
    return [
        {
            "key": definition.key,
            "display_name": definition.display_name,
            "module_path": definition.module_path,
            "channels": list(definition.channels),
        }
        for definition in get_notifier_registry().values()
    ]
