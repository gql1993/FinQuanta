from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta

from api_server.storage import repo

ROLE_PERMISSIONS = {
    "admin": {
        "snapshot:read",
        "ops:read",
        "portfolio:read",
        "scan:read",
        "scan:run",
        "openclaw:run",
        "openclaw:admin",
        "openclaw:learn",
        "task:trigger",
        "settings:write",
    },
    "operator": {
        "snapshot:read",
        "ops:read",
        "portfolio:read",
        "scan:read",
        "scan:run",
        "openclaw:run",
        "openclaw:learn",
        "task:trigger",
    },
    "viewer": {
        "snapshot:read",
        "ops:read",
        "portfolio:read",
        "scan:read",
    },
}


def _safe_int(value, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _now() -> str:
    return datetime.now().isoformat()


def _hash_password(password: str, salt: str | None = None, rounds: int = 120000) -> str:
    salt = salt or secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), rounds)
    return f"pbkdf2_sha256${rounds}${salt}${derived.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    if not stored:
        return False
    if stored.startswith("pbkdf2_sha256$"):
        try:
            _, rounds_s, salt, digest = stored.split("$", 3)
            rounds = int(rounds_s)
            calc = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), rounds).hex()
            return secrets.compare_digest(calc, digest)
        except Exception:
            return False
    return secrets.compare_digest(password, stored)


def _password_needs_upgrade(stored: str) -> bool:
    return not (stored or "").startswith("pbkdf2_sha256$")


def log_auth_event(action: str, username: str, success: bool, detail: str = "", actor: str = ""):
    ensure_auth_tables()
    repo.execute(
        "INSERT INTO auth_audit_log(id, timestamp, actor, username, action, success, detail) VALUES (?,?,?,?,?,?,?)",
        (secrets.token_hex(8), _now(), actor or username, username, action, 1 if success else 0, detail),
    )


def ensure_auth_tables():
    repo.executescript(
        """
        CREATE TABLE IF NOT EXISTS api_users (
            username TEXT PRIMARY KEY,
            password TEXT,
            role TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS api_tokens (
            token TEXT PRIMARY KEY,
            username TEXT,
            role TEXT,
            expires_at TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS auth_audit_log (
            id TEXT PRIMARY KEY,
            timestamp TEXT,
            actor TEXT,
            username TEXT,
            action TEXT,
            success INTEGER,
            detail TEXT
        );
        """
    )
    row = repo.fetchone("SELECT username FROM api_users WHERE username=?", ("admin",))
    if not row:
        repo.execute(
            "INSERT INTO api_users(username, password, role, updated_at) VALUES (?,?,?,?)",
            ("admin", _hash_password("admin123"), "admin", _now()),
        )


def login(username: str, password: str) -> tuple[bool, str, str]:
    ensure_auth_tables()
    row = repo.fetchone(
        "SELECT password, role FROM api_users WHERE username=?",
        (username,),
    )
    if not row:
        log_auth_event("login", username, False, "user_not_found")
        return False, "", ""
    stored_password, role = row
    if not _verify_password(password, stored_password):
        log_auth_event("login", username, False, "bad_password")
        return False, "", ""
    if _password_needs_upgrade(stored_password):
        repo.execute(
            "UPDATE api_users SET password=?, updated_at=? WHERE username=?",
            (_hash_password(password), _now(), username),
        )
    token = secrets.token_hex(16)
    token_ttl_days = max(1, min(90, _safe_int(os.environ.get("FINQUANTA_API_TOKEN_TTL_DAYS"), 7)))
    expires = (datetime.now() + timedelta(days=token_ttl_days)).isoformat()
    repo.execute("DELETE FROM api_tokens WHERE token=?", (token,))
    repo.execute(
        "INSERT INTO api_tokens(token, username, role, expires_at, created_at) VALUES (?,?,?,?,?)",
        (token, username, role, expires, _now()),
    )
    log_auth_event("login", username, True, "ok")
    return True, token, role


def verify_token(token: str) -> dict | None:
    ensure_auth_tables()
    row = repo.fetchone(
        "SELECT username, role, expires_at FROM api_tokens WHERE token=?",
        (token,),
    )
    if not row:
        return None
    username, role, expires_at = row
    try:
        if datetime.fromisoformat(expires_at) < datetime.now():
            return None
    except Exception:
        return None
    return {"username": username, "role": role, "permissions": sorted(ROLE_PERMISSIONS.get(role, [])), "token": token}


def has_permission(user: dict | None, permission: str) -> bool:
    if not user:
        return False
    perms = set(user.get("permissions", []))
    return permission in perms


def get_auth_security_status() -> dict:
    ensure_auth_tables()
    users = list_users()
    max_active_tokens = max(1, _safe_int(os.environ.get("FINQUANTA_AUTH_MAX_ACTIVE_TOKENS"), 20))
    max_admin_tokens = max(0, _safe_int(os.environ.get("FINQUANTA_AUTH_MAX_ADMIN_TOKENS"), 2))
    max_token_age_days = max(1, _safe_int(os.environ.get("FINQUANTA_AUTH_MAX_TOKEN_AGE_DAYS"), 7))
    failed_auth_threshold = max(1, _safe_int(os.environ.get("FINQUANTA_AUTH_FAILED_AUTH_THRESHOLD"), 5))
    role_counts = {role: 0 for role in ROLE_PERMISSIONS}
    unknown_roles = []
    for item in users:
        role = str(item.get("role", "") or "")
        if role in role_counts:
            role_counts[role] += 1
        else:
            unknown_roles.append(role or "(empty)")

    admin_row = repo.fetchone("SELECT password FROM api_users WHERE username=?", ("admin",))
    default_admin_password = bool(admin_row and _verify_password("admin123", admin_row[0]))
    admin_count = role_counts.get("admin", 0)

    active_tokens = 0
    expired_tokens = 0
    invalid_tokens = 0
    active_admin_tokens = 0
    old_active_tokens = 0
    token_roles = {role: 0 for role in ROLE_PERMISSIONS}
    now = datetime.now()
    for row in repo.fetchall("SELECT username, role, expires_at, created_at FROM api_tokens"):
        username = row[0] if len(row) > 0 else ""
        role = str(row[1] if len(row) > 1 else "" or "")
        expires_at = row[2] if len(row) > 2 else ""
        created_at = row[3] if len(row) > 3 else ""
        try:
            expires_dt = datetime.fromisoformat(str(expires_at))
            if expires_dt >= now:
                active_tokens += 1
                if role in token_roles:
                    token_roles[role] += 1
                if role == "admin":
                    active_admin_tokens += 1
                try:
                    created_dt = datetime.fromisoformat(str(created_at))
                    if (now - created_dt).days > max_token_age_days:
                        old_active_tokens += 1
                except Exception:
                    invalid_tokens += 1
            else:
                expired_tokens += 1
        except Exception:
            invalid_tokens += 1

    audit_rows = get_recent_auth_audit(limit=100)
    failed_auth_actions = [
        item
        for item in audit_rows
        if not bool(item.get("success", True)) and str(item.get("action", "") or "").startswith(("login", "change_password"))
    ]

    findings = []
    if admin_count <= 0:
        findings.append({
            "level": "error",
            "code": "missing_admin",
            "message": "未发现 admin 角色账号，无法完成生产管理闭环。",
        })
    if default_admin_password:
        findings.append({
            "level": "warning",
            "code": "default_admin_password",
            "message": "默认 admin 密码仍为 admin123，上线前必须修改。",
        })
    if unknown_roles:
        findings.append({
            "level": "warning",
            "code": "unknown_roles",
            "message": f"发现未知角色: {', '.join(sorted(set(unknown_roles)))}",
        })
    if invalid_tokens:
        findings.append({
            "level": "warning",
            "code": "invalid_token_expiry",
            "message": f"发现 {invalid_tokens} 个过期时间格式异常的 token。",
        })
    if active_tokens > max_active_tokens:
        findings.append({
            "level": "warning",
            "code": "too_many_active_tokens",
            "message": f"活跃 token 数 {active_tokens} 超过阈值 {max_active_tokens}，建议清理过期 token 并撤销闲置会话。",
        })
    if active_admin_tokens > max_admin_tokens:
        findings.append({
            "level": "warning",
            "code": "too_many_admin_tokens",
            "message": f"活跃 admin token 数 {active_admin_tokens} 超过阈值 {max_admin_tokens}，建议仅在变更窗口使用 admin。",
        })
    if old_active_tokens:
        findings.append({
            "level": "warning",
            "code": "old_active_tokens",
            "message": f"发现 {old_active_tokens} 个活跃 token 创建时间超过 {max_token_age_days} 天。",
        })
    if len(failed_auth_actions) >= failed_auth_threshold:
        findings.append({
            "level": "warning",
            "code": "recent_auth_failures",
            "message": f"最近认证失败 {len(failed_auth_actions)} 次，达到阈值 {failed_auth_threshold}。",
        })

    status = "ready"
    if any(item["level"] == "error" for item in findings):
        status = "error"
    elif findings:
        status = "warning"

    return {
        "status": status,
        "summary": "认证配置可用于生产" if status == "ready" else "认证配置存在上线风险",
        "default_admin_password": default_admin_password,
        "user_count": len(users),
        "role_counts": role_counts,
        "unknown_roles": sorted(set(unknown_roles)),
        "tokens": {
            "active": active_tokens,
            "expired": expired_tokens,
            "invalid": invalid_tokens,
            "active_admin": active_admin_tokens,
            "old_active": old_active_tokens,
            "by_role": token_roles,
        },
        "policy": {
            "token_ttl_days": max(1, min(90, _safe_int(os.environ.get("FINQUANTA_API_TOKEN_TTL_DAYS"), 7))),
            "max_active_tokens": max_active_tokens,
            "max_admin_tokens": max_admin_tokens,
            "max_token_age_days": max_token_age_days,
            "failed_auth_threshold": failed_auth_threshold,
        },
        "audit_summary": {
            "recent_count": len(audit_rows),
            "failed_auth_count": len(failed_auth_actions),
        },
        "findings": findings,
    }


def build_production_security_report() -> dict:
    status = get_auth_security_status()
    findings = list(status.get("findings", []) or [])
    checklist = [
        {
            "name": "default_admin_password_changed",
            "ok": not bool(status.get("default_admin_password", False)),
            "detail": "默认 admin/admin123 已修改" if not status.get("default_admin_password") else "默认 admin/admin123 仍可登录",
        },
        {
            "name": "admin_exists",
            "ok": int(status.get("role_counts", {}).get("admin", 0) or 0) > 0,
            "detail": f"admin_count={status.get('role_counts', {}).get('admin', 0)}",
        },
        {
            "name": "token_hygiene",
            "ok": not any(item.get("code") in {"too_many_active_tokens", "too_many_admin_tokens", "old_active_tokens"} for item in findings),
            "detail": str(status.get("tokens", {})),
        },
        {
            "name": "auth_failures",
            "ok": not any(item.get("code") == "recent_auth_failures" for item in findings),
            "detail": str(status.get("audit_summary", {})),
        },
    ]
    report_status = "ready"
    if any(item.get("level") == "error" for item in findings) or not all(item["ok"] for item in checklist[:2]):
        report_status = "error"
    elif findings or not all(item["ok"] for item in checklist):
        report_status = "warning"
    return {
        "status": report_status,
        "ready": report_status == "ready",
        "summary": "生产权限与认证审计已就绪" if report_status == "ready" else "生产权限与认证审计存在需处理项",
        "checklist": checklist,
        "findings": findings,
        "recommended_actions": _build_production_security_actions(findings, checklist),
        "security": status,
    }


def _build_production_security_actions(findings: list[dict], checklist: list[dict]) -> list[str]:
    codes = {str(item.get("code", "")) for item in findings}
    failed = {str(item.get("name", "")) for item in checklist if not bool(item.get("ok", False))}
    actions: list[str] = []
    if "default_admin_password_changed" in failed:
        actions.append("立即调用 /api/auth/change-password 修改默认 admin 密码，修改后旧 token 会自动撤销。")
    if "too_many_active_tokens" in codes or "old_active_tokens" in codes:
        actions.append("调用 /api/admin/tokens/cleanup-expired 清理过期 token，并对闲置账号执行 /api/admin/tokens/revoke。")
    if "too_many_admin_tokens" in codes:
        actions.append("撤销多余 admin token，日常操作使用 operator，admin 只在变更窗口使用。")
    if "recent_auth_failures" in codes:
        actions.append("查看 /api/admin/auth-audit，确认是否存在错误脚本或异常登录尝试。")
    if not actions:
        actions.append("保持最小权限账号分工，定期导出 auth audit 和 OpenClaw config audit。")
    return actions


def list_users() -> list[dict]:
    ensure_auth_tables()
    rows = repo.fetchall(
        "SELECT username, role, updated_at FROM api_users ORDER BY updated_at DESC, username ASC"
    )
    return [{"username": r[0], "role": r[1], "updated_at": r[2]} for r in rows]


def upsert_user(username: str, password: str, role: str) -> dict:
    ensure_auth_tables()
    now = _now()
    row = repo.fetchone("SELECT username FROM api_users WHERE username=?", (username,))
    if row:
        repo.execute(
            "UPDATE api_users SET password=?, role=?, updated_at=? WHERE username=?",
            (_hash_password(password), role, now, username),
        )
        log_auth_event("user_update", username, True, f"role={role}", actor="admin")
        return {"username": username, "role": role, "updated_at": now, "created": False}
    repo.execute(
        "INSERT INTO api_users(username, password, role, updated_at) VALUES (?,?,?,?)",
        (username, _hash_password(password), role, now),
    )
    log_auth_event("user_create", username, True, f"role={role}", actor="admin")
    return {"username": username, "role": role, "updated_at": now, "created": True}


def delete_user(username: str) -> bool:
    ensure_auth_tables()
    if username == "admin":
        return False
    row = repo.fetchone("SELECT username FROM api_users WHERE username=?", (username,))
    if not row:
        return False
    repo.execute("DELETE FROM api_tokens WHERE username=?", (username,))
    repo.execute("DELETE FROM api_users WHERE username=?", (username,))
    log_auth_event("user_delete", username, True, "deleted", actor="admin")
    return True


def change_password(username: str, old_password: str, new_password: str) -> tuple[bool, str]:
    ensure_auth_tables()
    row = repo.fetchone("SELECT password FROM api_users WHERE username=?", (username,))
    if not row:
        log_auth_event("change_password", username, False, "user_not_found")
        return False, "用户不存在"
    if not _verify_password(old_password, row[0]):
        log_auth_event("change_password", username, False, "old_password_mismatch")
        return False, "旧密码错误"
    repo.execute(
        "UPDATE api_users SET password=?, updated_at=? WHERE username=?",
        (_hash_password(new_password), _now(), username),
    )
    repo.execute("DELETE FROM api_tokens WHERE username=?", (username,))
    log_auth_event("change_password", username, True, "password_changed_and_tokens_revoked")
    return True, "密码修改成功，请重新登录"


def logout(token: str, username: str) -> bool:
    ensure_auth_tables()
    row = repo.fetchone("SELECT token FROM api_tokens WHERE token=?", (token,))
    if not row:
        log_auth_event("logout", username, False, "token_not_found")
        return False
    repo.execute("DELETE FROM api_tokens WHERE token=?", (token,))
    log_auth_event("logout", username, True, "token_revoked")
    return True


def revoke_user_tokens(username: str, actor: str = "admin") -> int:
    ensure_auth_tables()
    rows = repo.fetchall("SELECT token FROM api_tokens WHERE username=?", (username,))
    count = len(rows)
    repo.execute("DELETE FROM api_tokens WHERE username=?", (username,))
    log_auth_event("revoke_tokens", username, True, f"revoked={count}", actor=actor)
    return count


def revoke_other_user_tokens(username: str, keep_token: str, actor: str = "admin") -> int:
    ensure_auth_tables()
    rows = repo.fetchall("SELECT token FROM api_tokens WHERE username=? AND token<>?", (username, keep_token))
    count = len(rows)
    repo.execute("DELETE FROM api_tokens WHERE username=? AND token<>?", (username, keep_token))
    log_auth_event("revoke_other_tokens", username, True, f"revoked={count},kept_current=1", actor=actor)
    return count


def cleanup_expired_tokens(actor: str = "admin") -> dict:
    ensure_auth_tables()
    rows = repo.fetchall("SELECT token, username, expires_at FROM api_tokens")
    now = datetime.now()
    expired_tokens = []
    invalid_tokens = []
    for row in rows:
        token, username, expires_at = row
        try:
            if datetime.fromisoformat(str(expires_at)) < now:
                expired_tokens.append((token, username))
        except Exception:
            invalid_tokens.append((token, username))

    for token, _username in expired_tokens + invalid_tokens:
        repo.execute("DELETE FROM api_tokens WHERE token=?", (token,))

    expired_count = len(expired_tokens)
    invalid_count = len(invalid_tokens)
    total = expired_count + invalid_count
    log_auth_event(
        "cleanup_tokens",
        "api_tokens",
        True,
        f"expired={expired_count},invalid={invalid_count},deleted={total}",
        actor=actor,
    )
    return {
        "deleted": total,
        "expired": expired_count,
        "invalid": invalid_count,
        "remaining_active": max(0, len(rows) - total),
    }


def get_recent_auth_audit(limit: int = 50) -> list[dict]:
    ensure_auth_tables()
    rows = repo.fetchall(
        "SELECT timestamp, actor, username, action, success, detail FROM auth_audit_log "
        "ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    )
    return [
        {
            "timestamp": r[0],
            "actor": r[1],
            "username": r[2],
            "action": r[3],
            "success": bool(r[4]),
            "detail": r[5] or "",
        }
        for r in rows
    ]
