from __future__ import annotations

import json
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any

from desktop.data_access import get_repo


def _schema_sql() -> str:
    sql_path = Path(__file__).resolve().parent.parent / "infra" / "assistant_actions_init.sql"
    return sql_path.read_text(encoding="utf-8")


def ensure_assistant_tables():
    get_repo().executescript(_schema_sql())


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _json_loads(value: Any, default=None):
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def create_action(
    session_id: str,
    user_text: str,
    intent: str,
    target: str = "",
    action: str = "",
    action_key: str = "",
    arguments: dict[str, Any] | None = None,
    preview: dict[str, Any] | None = None,
    risk_level: str = "low",
    requires_confirmation: bool = False,
    status: str = "pending",
) -> dict[str, Any]:
    ensure_assistant_tables()
    action_id = secrets.token_hex(12)
    now = datetime.now().isoformat()
    payload = {
        "id": action_id,
        "session_id": session_id,
        "user_text": user_text,
        "intent": intent,
        "target": target,
        "action": action,
        "action_key": action_key,
        "arguments_json": _json_dumps(arguments or {}),
        "preview_json": _json_dumps(preview or {}),
        "risk_level": risk_level,
        "requires_confirmation": 1 if requires_confirmation else 0,
        "status": status,
        "created_at": now,
        "confirmed_at": None,
        "executed_at": None,
        "error_text": "",
    }
    get_repo().execute(
        """
        INSERT INTO assistant_actions (
            id, session_id, user_text, intent, target, action, action_key,
            arguments_json, preview_json, risk_level, requires_confirmation,
            status, created_at, confirmed_at, executed_at, error_text
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            payload["id"],
            payload["session_id"],
            payload["user_text"],
            payload["intent"],
            payload["target"],
            payload["action"],
            payload["action_key"],
            payload["arguments_json"],
            payload["preview_json"],
            payload["risk_level"],
            payload["requires_confirmation"],
            payload["status"],
            payload["created_at"],
            payload["confirmed_at"],
            payload["executed_at"],
            payload["error_text"],
        ),
    )
    return get_action(action_id) or payload


def append_action_log(
    action_id: str,
    step: str,
    message: str,
    *,
    level: str = "info",
    detail: dict[str, Any] | None = None,
):
    ensure_assistant_tables()
    get_repo().execute(
        """
        INSERT INTO assistant_action_logs (action_id, step, level, message, detail_json, created_at)
        VALUES (?,?,?,?,?,?)
        """,
        (
            action_id,
            step,
            level,
            message,
            _json_dumps(detail or {}),
            datetime.now().isoformat(),
        ),
    )


def update_action_status(
    action_id: str,
    status: str,
    *,
    preview: dict[str, Any] | None = None,
    error_text: str = "",
    mark_confirmed: bool = False,
    mark_executed: bool = False,
):
    ensure_assistant_tables()
    now = datetime.now().isoformat()
    updates = ["status=?", "error_text=?"]
    params: list[Any] = [status, error_text]
    if preview is not None:
        updates.append("preview_json=?")
        params.append(_json_dumps(preview))
    if mark_confirmed:
        updates.append("confirmed_at=?")
        params.append(now)
    if mark_executed:
        updates.append("executed_at=?")
        params.append(now)
    params.append(action_id)
    get_repo().execute(
        f"UPDATE assistant_actions SET {', '.join(updates)} WHERE id=?",
        tuple(params),
    )


def get_action(action_id: str) -> dict[str, Any] | None:
    ensure_assistant_tables()
    row = get_repo().fetchone(
        """
        SELECT id, session_id, user_text, intent, target, action, action_key,
               arguments_json, preview_json, risk_level, requires_confirmation,
               status, created_at, confirmed_at, executed_at, error_text
        FROM assistant_actions
        WHERE id=?
        """,
        (action_id,),
    )
    if not row:
        return None
    return {
        "id": row[0],
        "session_id": row[1],
        "user_text": row[2],
        "intent": row[3],
        "target": row[4],
        "action": row[5],
        "action_key": row[6],
        "arguments": _json_loads(row[7], {}),
        "preview": _json_loads(row[8], {}),
        "risk_level": row[9],
        "requires_confirmation": bool(row[10]),
        "status": row[11],
        "created_at": row[12],
        "confirmed_at": row[13],
        "executed_at": row[14],
        "error_text": row[15] or "",
    }


def list_recent_actions(limit: int = 50) -> list[dict[str, Any]]:
    ensure_assistant_tables()
    rows = get_repo().fetchall(
        """
        SELECT id, session_id, user_text, intent, target, action, action_key,
               risk_level, requires_confirmation, status, created_at, error_text
        FROM assistant_actions
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    )
    return [
        {
            "id": row[0],
            "session_id": row[1],
            "user_text": row[2],
            "intent": row[3],
            "target": row[4],
            "action": row[5],
            "action_key": row[6],
            "risk_level": row[7],
            "requires_confirmation": bool(row[8]),
            "status": row[9],
            "created_at": row[10],
            "error_text": row[11] or "",
        }
        for row in rows
    ]


def list_action_logs(action_id: str) -> list[dict[str, Any]]:
    ensure_assistant_tables()
    rows = get_repo().fetchall(
        """
        SELECT step, level, message, detail_json, created_at
        FROM assistant_action_logs
        WHERE action_id=?
        ORDER BY id
        """,
        (action_id,),
    )
    return [
        {
            "step": row[0],
            "level": row[1],
            "message": row[2],
            "detail": _json_loads(row[3], {}),
            "created_at": row[4],
        }
        for row in rows
    ]
