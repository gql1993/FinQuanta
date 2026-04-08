from __future__ import annotations

from typing import Any

from desktop.assistant_actions import dispatch_intent, preview_intent
from desktop.assistant_audit import (
    append_action_log,
    create_action,
    get_action,
    update_action_status,
)
from desktop.assistant_intents import parse_intent
from desktop.assistant_permissions import apply_policy, validate_intent
from desktop.snapshot_service import get_system_snapshot


def handle_user_message(text: str, session_id: str) -> dict[str, Any]:
    """
    统一入口：
    1. 解析自然语言
    2. 校验权限
    3. 创建审计动作
    4. 对查询类直接执行，对修改/任务类返回待确认卡片
    """
    context = {"snapshot": get_system_snapshot()}
    raw_intent = parse_intent(text, context=context)
    if not raw_intent.get("matched"):
        return {
            "ok": True,
            "type": "fallback_chat",
            "message": "该输入未匹配系统动作，回退到通用 AI 问答。",
            "intent": raw_intent,
        }
    intent = apply_policy(raw_intent)
    errors = validate_intent(intent)
    preview = preview_intent(intent)

    action = create_action(
        session_id=session_id,
        user_text=text,
        intent=intent["intent"],
        target=intent.get("target", ""),
        action=intent.get("action", ""),
        action_key=intent.get("action_key", ""),
        arguments=intent.get("arguments", {}),
        preview=preview,
        risk_level=intent.get("risk_level", "low"),
        requires_confirmation=bool(intent.get("requires_confirmation")),
        status="pending" if not errors else "failed",
    )
    append_action_log(action["id"], "intent_parsed", "已解析用户意图", detail=intent)

    if errors:
        update_action_status(action["id"], "failed", error_text="; ".join(errors))
        append_action_log(action["id"], "intent_rejected", "意图校验失败", level="error", detail={"errors": errors})
        return {
            "ok": False,
            "type": "error",
            "action_id": action["id"],
            "message": "; ".join(errors),
            "intent": intent,
        }

    if intent.get("requires_confirmation"):
        append_action_log(action["id"], "awaiting_confirmation", "等待用户确认执行", detail=preview)
        return {
            "ok": True,
            "type": "action_required",
            "action_id": action["id"],
            "intent": intent,
            "preview": preview,
            "message": "该操作需要确认后执行",
        }

    return confirm_action(action["id"], auto_confirm=True)


def confirm_action(action_id: str, auto_confirm: bool = False) -> dict[str, Any]:
    action = get_action(action_id)
    if not action:
        return {"ok": False, "type": "error", "message": f"未找到动作: {action_id}"}
    if action["status"] == "cancelled":
        return {"ok": False, "type": "error", "message": "该动作已取消", "action_id": action_id}
    update_action_status(action_id, "confirmed", mark_confirmed=not auto_confirm)
    append_action_log(action_id, "confirmed", "动作已确认，开始执行")
    try:
        result = dispatch_intent(action)
        update_action_status(action_id, "executed", mark_executed=True)
        append_action_log(action_id, "executed", "动作执行成功", detail=result)
        return {
            "ok": True,
            "type": result.get("type", "result"),
            "action_id": action_id,
            "result": result,
        }
    except Exception as exc:
        update_action_status(action_id, "failed", error_text=str(exc), mark_executed=True)
        append_action_log(action_id, "failed", "动作执行失败", level="error", detail={"error": str(exc)})
        return {
            "ok": False,
            "type": "error",
            "action_id": action_id,
            "message": str(exc),
        }


def cancel_action(action_id: str) -> dict[str, Any]:
    action = get_action(action_id)
    if not action:
        return {"ok": False, "type": "error", "message": f"未找到动作: {action_id}"}
    update_action_status(action_id, "cancelled")
    append_action_log(action_id, "cancelled", "用户取消执行")
    return {"ok": True, "type": "cancelled", "action_id": action_id}
