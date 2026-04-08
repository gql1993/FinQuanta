from __future__ import annotations

import hashlib
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
    expires = (datetime.now() + timedelta(days=7)).isoformat()
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
