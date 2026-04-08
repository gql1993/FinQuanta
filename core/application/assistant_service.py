"""
Application-level assistant service.

The first extraction keeps the current data sources and LLM call path, but
moves the orchestration entry point out of `api_server` so other clients can
reuse it.
"""

from __future__ import annotations

import secrets
from datetime import datetime

from api_server.storage import repo
from core.ai.context_builder import build_assistant_context_payload
from core.ai.prompt_registry import build_assistant_system_prompt
from desktop.ai_trader import _call_llm


def ensure_assistant_tables():
    repo.executescript(
        """
        CREATE TABLE IF NOT EXISTS ai_chat_history (
            id TEXT PRIMARY KEY,
            session_id TEXT,
            role TEXT,
            content TEXT,
            created_at TEXT
        );
        """
    )


def save_chat_msg(session_id: str, role: str, content: str):
    ensure_assistant_tables()
    msg_id = secrets.token_hex(8)
    created_at = datetime.now().isoformat()
    try:
        repo.execute(
            "INSERT INTO ai_chat_history (id, session_id, role, content, created_at) VALUES (?,?,?,?,?)",
            (msg_id, session_id, role, content, created_at),
        )
    except Exception:
        # 兼容历史 SQLite 结构：旧表的 id 为 INTEGER AUTOINCREMENT
        repo.execute(
            "INSERT INTO ai_chat_history (session_id, role, content, created_at) VALUES (?,?,?,?)",
            (session_id, role, content, created_at),
        )


def get_sessions(limit: int = 30) -> list[dict]:
    ensure_assistant_tables()
    rows = repo.fetchall(
        """
        SELECT session_id, MIN(created_at), MAX(created_at), COUNT(*)
        FROM ai_chat_history
        GROUP BY session_id
        ORDER BY MAX(created_at) DESC
        LIMIT ?
        """,
        (limit,),
    )
    items = []
    for row in rows:
        first_user = repo.fetchone(
            "SELECT content FROM ai_chat_history WHERE session_id=? AND role='user' ORDER BY created_at, id LIMIT 1",
            (row[0],),
        )
        items.append(
            {
                "session_id": row[0],
                "first_time": row[1],
                "last_time": row[2],
                "msg_count": row[3],
                "first_question": ((first_user[0] if first_user else "") or "")[:40],
            }
        )
    return items


def get_session_messages(session_id: str, limit: int = 100) -> list[dict]:
    ensure_assistant_tables()
    rows = repo.fetchall(
        """
        SELECT role, content, created_at
        FROM ai_chat_history
        WHERE session_id=?
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (session_id, limit),
    )
    rows = list(reversed(rows))
    return [{"role": row[0], "content": row[1], "time": row[2]} for row in rows]


def ask_assistant(prompt: str, session_id: str) -> dict:
    ensure_assistant_tables()
    context = build_assistant_context_payload()
    system = build_assistant_system_prompt(context["context_text"])
    save_chat_msg(session_id, "user", prompt)
    answer = _call_llm(prompt, system=system)
    save_chat_msg(session_id, "assistant", answer)
    return {
        "session_id": session_id,
        "reply": answer,
        "context_excerpt": context["context_text"][:1200],
    }
