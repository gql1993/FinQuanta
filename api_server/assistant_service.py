"""
兼容层：保留 `api_server.assistant_service` 的旧导入路径。

真实实现已迁移到 `core.application.assistant_service`。
"""

from core.application.assistant_service import (
    ask_assistant,
    build_assistant_context_payload,
    ensure_assistant_tables,
    get_session_messages,
    get_sessions,
    save_chat_msg,
)

__all__ = [
    "ask_assistant",
    "build_assistant_context_payload",
    "ensure_assistant_tables",
    "get_session_messages",
    "get_sessions",
    "save_chat_msg",
]
