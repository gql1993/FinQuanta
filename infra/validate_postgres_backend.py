from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _print_result(ok: bool, name: str, detail=""):
    prefix = "[PASS]" if ok else "[FAIL]"
    print(f"{prefix} {name}: {detail}")
    return ok


def main():
    from py_pglite import PGliteConfig, PGliteManager

    work_dir = Path(ROOT) / "data_cache" / "pglite_validation"
    config = PGliteConfig(
        use_tcp=True,
        tcp_host="127.0.0.1",
        tcp_port=55432,
        work_dir=work_dir,
        auto_install_deps=False,
        node_modules_check=True,
        cleanup_on_exit=True,
        timeout=45,
    )

    all_ok = True
    with PGliteManager(config=config) as db:
        os.environ["FINQUANTA_DB_BACKEND"] = "postgres"
        os.environ["FINQUANTA_POSTGRES_DSN"] = db.get_dsn()
        os.environ["FINQUANTA_PG_PERSISTENT"] = "1"
        os.environ["FINQUANTA_REDIS_URL"] = ""
        os.environ["FINQUANTA_ENV"] = "pg-validate"

        import api_server.storage as storage_module
        import api_server.auth as auth_module
        import api_server.settings_service as settings_module
        import api_server.assistant_service as assistant_module
        import api_server.main as main_module

        repo = storage_module.repo
        dsn_detail = db.get_dsn()
        all_ok &= _print_result(repo.ping().get("ok", False), "postgres_ping", dsn_detail)

        postgres_sql = Path(ROOT) / "infra" / "postgres_init.sql"
        repo.executescript(postgres_sql.read_text(encoding="utf-8"))
        auth_module.ensure_auth_tables()
        assistant_module.ensure_assistant_tables()

        repo.kv_set("ai_config", {"api_key": "demo-key", "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"})
        repo.kv_set("last_scan_results", [{"代码": "600519", "名称": "贵州茅台", "板块": "白酒", "评分": 95, "建议买入": "强烈买入"}])
        kv = repo.kv_get("last_scan_results", [])
        all_ok &= _print_result(isinstance(kv, list) and len(kv) == 1, "postgres_kv_rw", len(kv))

        from fastapi.testclient import TestClient

        client = TestClient(main_module.app)

        def request(method: str, path: str, token: str = "", payload: dict | None = None):
            headers = {}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            resp = client.request(method, path, headers=headers, json=payload)
            return resp.status_code, resp.json() if resp.content else {}

        code, body = request("GET", "/health")
        all_ok &= _print_result(code == 200 and body.get("db_backend") == "postgres", "health", body.get("db_backend"))

        code, body = request("GET", "/health/deps")
        all_ok &= _print_result(code == 200 and body.get("dependencies", {}).get("database", {}).get("backend") == "postgres", "health_deps", body.get("dependencies", {}))

        code, body = request("POST", "/api/auth/login", payload={"username": "admin", "password": "admin123"})
        token = body.get("token", "")
        all_ok &= _print_result(code == 200 and bool(token), "auth_login", body.get("role", ""))
        if not token:
            return 1

        code, body = request("GET", "/api/auth/profile", token=token)
        all_ok &= _print_result(code == 200 and body.get("data", {}).get("username") == "admin", "auth_profile", body.get("data", {}))

        code, body = request("GET", "/api/settings/ai", token=token)
        all_ok &= _print_result(code == 200 and body.get("data", {}).get("model") == "deepseek-chat", "settings_ai_get", body.get("data", {}))

        code, body = request("POST", "/api/settings/ai", token=token, payload={"api_key": "abc", "base_url": "https://api.test/v1", "model": "demo"})
        all_ok &= _print_result(code == 200 and body.get("data", {}).get("model") == "demo", "settings_ai_post", body.get("data", {}))

        code, body = request("GET", "/api/scan/latest", token=token)
        all_ok &= _print_result(code == 200 and body.get("data", {}).get("count") == 1, "scan_latest", body.get("data", {}))

        code, body = request("GET", "/api/assistant/sessions", token=token)
        all_ok &= _print_result(code == 200, "assistant_sessions", body.get("data", {}))

        code, body = request("POST", "/api/auth/logout", token=token)
        all_ok &= _print_result(code == 200 and body.get("data", {}).get("logout") is True, "auth_logout", body.get("data", {}))

    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
