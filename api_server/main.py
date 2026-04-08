from __future__ import annotations

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from api_server.auth import (
    change_password,
    delete_user,
    ensure_auth_tables,
    get_recent_auth_audit,
    has_permission,
    list_users,
    login,
    logout,
    revoke_user_tokens,
    upsert_user,
    verify_token,
)
from api_server.cache_provider import snapshot_cache
from api_server.config import settings
from api_server.schemas import (
    ApiResponse,
    ApprovalTradeRequest,
    AiConfigRequest,
    AssistantAskRequest,
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    PushConfigRequest,
    PushTestRequest,
    RevokeTokensRequest,
    TriggerRequest,
    UserUpsertRequest,
)
from api_server.assistant_service import (
    ask_assistant,
    build_assistant_context_payload,
    get_session_messages,
    get_sessions,
)
from api_server.settings_service import get_ai_config, save_ai_config
from api_server.storage import repo
from core.application.openclaw_service import (
    get_openclaw_data_sources,
    get_openclaw_strategy_weights,
    run_openclaw_learning,
    run_openclaw_pipeline,
)
from core.application.ops_service import (
    get_message_feed,
    get_ops_center_payload,
    get_recent_system_events,
    get_recent_task_runs,
)
from core.application.portfolio_service import (
    get_portfolio_positions,
    get_portfolio_summary,
)
from core.application.snapshot_service import get_system_snapshot
from core.application.task_service import run_scan_task, trigger_named_task
from core.application.trade_approval_service import approve_trade
from core.application.verify_service import (
    calibrate_verify,
    get_verify_accuracy_stats,
    get_verify_records,
)

app = FastAPI(
    title="FinQuanta API",
    version="0.1.0",
    description="FinQuanta 产品化 API 骨架，用于 Web 端 / 小程序端 / 远程运维接入。",
)

cors_origins = [x.strip() for x in settings.cors_origins.split(",")] if settings.cors_origins else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins if cors_origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ensure_auth_tables()
ROLE_NAMES = {"admin", "operator", "viewer"}


def _decode_json_field(value, default):
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return default


def require_user(authorization: str | None):
    if not authorization:
        raise HTTPException(status_code=401, detail="missing authorization")
    token = authorization.replace("Bearer ", "").strip()
    user = verify_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="invalid token")
    return user


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "finquanta-api",
        "env": settings.app_env,
        "db_backend": settings.db_backend,
        "redis_cache": snapshot_cache.enabled,
    }


@app.get("/health/deps")
def health_dependencies():
    db = repo.ping()
    cache = snapshot_cache.ping()
    return {
        "ok": bool(db.get("ok")) and bool(cache.get("ok")),
        "service": "finquanta-api",
        "dependencies": {
            "database": db,
            "cache": cache,
        },
    }


@app.post("/api/auth/login", response_model=LoginResponse)
def api_login(req: LoginRequest):
    ok, token, role = login(req.username, req.password)
    if not ok:
        return LoginResponse(ok=False, message="用户名或密码错误")
    return LoginResponse(ok=True, token=token, role=role, message="登录成功")


@app.get("/api/auth/profile", response_model=ApiResponse)
def api_auth_profile(authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    return ApiResponse(data=user)


@app.post("/api/auth/change-password", response_model=ApiResponse)
def api_auth_change_password(req: ChangePasswordRequest, authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    ok, msg = change_password(user["username"], req.old_password, req.new_password)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return ApiResponse(data={"changed": True}, message=msg)


@app.post("/api/auth/logout", response_model=ApiResponse)
def api_auth_logout(authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    ok = logout(user.get("token", ""), user["username"])
    if not ok:
        raise HTTPException(status_code=400, detail="logout failed")
    return ApiResponse(data={"logout": True}, message="已退出登录")


@app.get("/api/snapshot/system", response_model=ApiResponse)
def api_snapshot_system(authorization: str | None = Header(default=None)):
    require_user(authorization)
    cache_key = "api:snapshot:system"
    cached = snapshot_cache.get_json(cache_key)
    if cached:
        return ApiResponse(data=cached)
    data = get_system_snapshot()
    snapshot_cache.set_json(cache_key, data, ttl=settings.snapshot_cache_ttl)
    return ApiResponse(data=data)


@app.get("/api/ops/tasks", response_model=ApiResponse)
def api_ops_tasks(authorization: str | None = Header(default=None), limit: int = 30):
    require_user(authorization)
    return ApiResponse(data=get_recent_task_runs(limit))


@app.get("/api/ops/events", response_model=ApiResponse)
def api_ops_events(authorization: str | None = Header(default=None), limit: int = 30):
    require_user(authorization)
    return ApiResponse(data=get_recent_system_events(limit))


@app.get("/api/ops/center", response_model=ApiResponse)
def api_ops_center(authorization: str | None = Header(default=None), limit: int = 20):
    require_user(authorization)
    return ApiResponse(data=get_ops_center_payload(limit))


@app.get("/api/scan/latest", response_model=ApiResponse)
def api_scan_latest(authorization: str | None = Header(default=None)):
    require_user(authorization)
    row = repo.fetchone("SELECT value, updated_at FROM kv_store WHERE key=?", ("last_scan_results",))
    if not row:
        return ApiResponse(data={"items": [], "updated_at": "", "count": 0})
    items = _decode_json_field(row[0], [])
    return ApiResponse(data={"items": items, "updated_at": row[1] or "", "count": len(items)})


@app.post("/api/scan/run", response_model=ApiResponse)
def api_scan_run(req: TriggerRequest, authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    if not has_permission(user, "scan:run"):
        raise HTTPException(status_code=403, detail="permission denied")
    if req.dry_run:
        return ApiResponse(data={"dry_run": True, "task": "scan_stocks"})
    run_scan_task()
    return api_scan_latest(authorization)


@app.get("/api/portfolio/summary", response_model=ApiResponse)
def api_portfolio_summary(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(data=get_portfolio_summary())


@app.get("/api/portfolio/positions", response_model=ApiResponse)
def api_portfolio_positions(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(data=get_portfolio_positions())


@app.get("/api/portfolio/recommendations", response_model=ApiResponse)
def api_portfolio_recommendations(authorization: str | None = Header(default=None), limit: int = 20):
    require_user(authorization)
    row = repo.fetchone(
        "SELECT timestamp, decisions, analysis FROM ai_decision_memory "
        "WHERE mode='auto' ORDER BY id DESC LIMIT 1"
    )
    if not row:
        return ApiResponse(data={"timestamp": "", "analysis": "", "items": []})
    decisions = _decode_json_field(row[1], [])
    return ApiResponse(
        data={
            "timestamp": row[0],
            "analysis": row[2] or "",
            "items": decisions[:limit],
        }
    )


@app.get("/api/messages", response_model=ApiResponse)
def api_messages(authorization: str | None = Header(default=None), limit: int = 30):
    require_user(authorization)
    return ApiResponse(data=get_message_feed(limit))


@app.get("/api/assistant/context", response_model=ApiResponse)
def api_assistant_context(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(data=build_assistant_context_payload())


@app.get("/api/assistant/sessions", response_model=ApiResponse)
def api_assistant_sessions(authorization: str | None = Header(default=None), limit: int = 30):
    require_user(authorization)
    return ApiResponse(data={"items": get_sessions(limit)})


@app.get("/api/assistant/session/{session_id}", response_model=ApiResponse)
def api_assistant_session(session_id: str, authorization: str | None = Header(default=None), limit: int = 100):
    require_user(authorization)
    return ApiResponse(data={"session_id": session_id, "messages": get_session_messages(session_id, limit=limit)})


@app.post("/api/assistant/ask", response_model=ApiResponse)
def api_assistant_ask(req: AssistantAskRequest, authorization: str | None = Header(default=None)):
    require_user(authorization)
    session_id = req.session_id.strip() or datetime.now().strftime("%Y%m%d_%H%M%S")
    return ApiResponse(data=ask_assistant(req.prompt, session_id))


@app.get("/api/settings/ai", response_model=ApiResponse)
def api_settings_ai(authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    if not has_permission(user, "settings:write"):
        raise HTTPException(status_code=403, detail="permission denied")
    return ApiResponse(data=get_ai_config())


@app.post("/api/settings/ai", response_model=ApiResponse)
def api_settings_ai_save(req: AiConfigRequest, authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    if not has_permission(user, "settings:write"):
        raise HTTPException(status_code=403, detail="permission denied")
    cfg = save_ai_config(req.api_key, req.base_url, req.model)
    return ApiResponse(data=cfg, message="AI 配置已保存")


@app.get("/api/settings/push", response_model=ApiResponse)
def api_settings_push(authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    if not has_permission(user, "settings:write"):
        raise HTTPException(status_code=403, detail="permission denied")
    from signal_push import get_push_config
    return ApiResponse(data=get_push_config())


@app.post("/api/settings/push", response_model=ApiResponse)
def api_settings_push_save(req: PushConfigRequest, authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    if not has_permission(user, "settings:write"):
        raise HTTPException(status_code=403, detail="permission denied")
    from signal_push import get_push_config, save_push_config
    cfg = get_push_config()
    cfg["serverchan_key"] = req.serverchan_key
    cfg["wecom_webhook"] = req.wecom_webhook
    save_push_config(cfg)
    return ApiResponse(data=cfg, message="推送配置已保存")


@app.post("/api/settings/push/test", response_model=ApiResponse)
def api_settings_push_test(req: PushTestRequest, authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    if not has_permission(user, "settings:write"):
        raise HTTPException(status_code=403, detail="permission denied")
    from signal_push import push_signal
    result = push_signal(req.title, req.content)
    return ApiResponse(data=result, message="测试推送已执行")


@app.get("/api/stock/{code}", response_model=ApiResponse)
def api_stock_summary(code: str, authorization: str | None = Header(default=None)):
    require_user(authorization)
    name_row = repo.fetchone("SELECT name FROM stock_list WHERE code=?", (code,))
    rows = repo.fetchall(
        "SELECT date, open, high, low, close, volume FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 60",
        (code,),
    )
    if not rows:
        return ApiResponse(ok=False, message="no data", data={})
    rows = list(reversed(rows))
    closes = [r[4] for r in rows]
    latest = closes[-1]
    prev = closes[-2] if len(closes) >= 2 else latest
    pct = (latest / prev - 1) * 100 if prev > 0 else 0
    return ApiResponse(
        data={
            "code": code,
            "name": name_row[0] if name_row else code,
            "latest_price": round(latest, 2),
            "change_pct": round(pct, 2),
            "high_60d": round(max(r[2] for r in rows), 2),
            "low_60d": round(min(r[3] for r in rows), 2),
            "last_date": rows[-1][0],
        }
    )


@app.get("/api/stock/{code}/kline", response_model=ApiResponse)
def api_stock_kline(code: str, authorization: str | None = Header(default=None), limit: int = 120):
    require_user(authorization)
    rows = repo.fetchall(
        "SELECT date, open, high, low, close, volume FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT ?",
        (code, limit),
    )
    rows = list(reversed(rows))
    data = [
        {"date": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5]}
        for r in rows
    ]
    return ApiResponse(data={"code": code, "items": data, "count": len(data)})


@app.get("/api/stock/{code}/verify", response_model=ApiResponse)
def api_stock_verify(code: str, authorization: str | None = Header(default=None), limit: int = 30):
    require_user(authorization)
    rows = [r for r in get_verify_records(limit=500) if r.get("code") == code][:limit]
    return ApiResponse(data=rows)


@app.get("/api/verify/summary", response_model=ApiResponse)
def api_verify_summary(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(data=get_verify_accuracy_stats())


@app.get("/api/verify/records", response_model=ApiResponse)
def api_verify_records(
    authorization: str | None = Header(default=None),
    limit: int = 100,
    strategy: str = "",
):
    require_user(authorization)
    rows = get_verify_records(limit=limit)
    if strategy:
        rows = [r for r in rows if (r.get("strategy") or "").lower() == strategy.lower()]
    return ApiResponse(data=rows)


@app.post("/api/verify/calibrate", response_model=ApiResponse)
def api_verify_calibrate(authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    if not has_permission(user, "task:trigger"):
        raise HTTPException(status_code=403, detail="permission denied")
    return ApiResponse(data=calibrate_verify())


@app.get("/api/openclaw/weights", response_model=ApiResponse)
def api_openclaw_weights(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(data=get_openclaw_strategy_weights())


@app.get("/api/openclaw/sources", response_model=ApiResponse)
def api_openclaw_sources(authorization: str | None = Header(default=None)):
    require_user(authorization)
    return ApiResponse(data=get_openclaw_data_sources())


@app.post("/api/openclaw/pipeline/run", response_model=ApiResponse)
def api_openclaw_pipeline_run(req: TriggerRequest, authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    if not has_permission(user, "openclaw:run"):
        raise HTTPException(status_code=403, detail="permission denied")
    boards = req.boards or ["人工智能", "芯片", "量子科技"]
    if req.dry_run:
        return ApiResponse(data={"dry_run": True, "boards": boards})
    result = run_openclaw_pipeline(boards=boards)
    return ApiResponse(data=result)


@app.post("/api/openclaw/learn/run", response_model=ApiResponse)
def api_openclaw_learn_run(req: TriggerRequest, authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    if not has_permission(user, "openclaw:learn"):
        raise HTTPException(status_code=403, detail="permission denied")
    if req.dry_run:
        return ApiResponse(data={"dry_run": True})
    result = run_openclaw_learning()
    return ApiResponse(data=result)


@app.post("/api/task/trigger/{task_key}", response_model=ApiResponse)
def api_trigger_task(task_key: str, req: TriggerRequest, authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    if not has_permission(user, "task:trigger"):
        raise HTTPException(status_code=403, detail="permission denied")
    if req.dry_run:
        return ApiResponse(data={"dry_run": True, "task": task_key})
    try:
        result = trigger_named_task(task_key, boards=req.boards)
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown task")
    return ApiResponse(data={"task": task_key, "result": result})


@app.post("/api/approval/trade", response_model=ApiResponse)
def api_trade_approval(req: ApprovalTradeRequest, authorization: str | None = Header(default=None)):
    """
    小程序/网页审批接口（第一版）：
    - mode 默认为 auto（AI推荐仓）
    - 支持 BUY / SELL
    """
    user = require_user(authorization)
    if not has_permission(user, "task:trigger"):
        raise HTTPException(status_code=403, detail="permission denied")

    mode = req.mode or "auto"
    action = (req.action or "").upper()
    if action not in ("BUY", "SELL"):
        raise HTTPException(status_code=400, detail="action must be BUY or SELL")
    return ApiResponse(
        data=approve_trade(
            mode=mode,
            action=action,
            code=req.code,
            name=req.name,
            price=req.price,
            shares=req.shares,
            reason=req.reason,
        )
    )


@app.get("/api/admin/users", response_model=ApiResponse)
def api_admin_users(authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    if not has_permission(user, "settings:write"):
        raise HTTPException(status_code=403, detail="permission denied")
    return ApiResponse(data={"items": list_users(), "roles": sorted(ROLE_NAMES)})


@app.post("/api/admin/users", response_model=ApiResponse)
def api_admin_upsert_user(req: UserUpsertRequest, authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    if not has_permission(user, "settings:write"):
        raise HTTPException(status_code=403, detail="permission denied")
    role = (req.role or "viewer").strip().lower()
    if role not in ROLE_NAMES:
        raise HTTPException(status_code=400, detail="invalid role")
    result = upsert_user(req.username.strip(), req.password, role)
    return ApiResponse(data=result)


@app.delete("/api/admin/users/{username}", response_model=ApiResponse)
def api_admin_delete_user(username: str, authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    if not has_permission(user, "settings:write"):
        raise HTTPException(status_code=403, detail="permission denied")
    ok = delete_user(username)
    if not ok:
        raise HTTPException(status_code=400, detail="delete failed")
    return ApiResponse(data={"deleted": True, "username": username})


@app.post("/api/admin/tokens/revoke", response_model=ApiResponse)
def api_admin_revoke_tokens(req: RevokeTokensRequest, authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    if not has_permission(user, "settings:write"):
        raise HTTPException(status_code=403, detail="permission denied")
    count = revoke_user_tokens(req.username.strip(), actor=user["username"])
    return ApiResponse(data={"username": req.username.strip(), "revoked": count})


@app.get("/api/admin/auth-audit", response_model=ApiResponse)
def api_admin_auth_audit(authorization: str | None = Header(default=None), limit: int = 50):
    user = require_user(authorization)
    if not has_permission(user, "settings:write"):
        raise HTTPException(status_code=403, detail="permission denied")
    return ApiResponse(data={"items": get_recent_auth_audit(limit)})
