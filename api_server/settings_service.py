from __future__ import annotations

from api_server.storage import repo


def get_ai_config() -> dict:
    cfg = repo.kv_get("ai_config", {}) or {}
    return cfg if isinstance(cfg, dict) else {}


def save_ai_config(api_key: str, base_url: str = "", model: str = "deepseek-chat") -> dict:
    cfg = {
        "api_key": api_key or "",
        "base_url": base_url or "https://api.deepseek.com/v1",
        "model": model or "deepseek-chat",
    }
    repo.kv_set("ai_config", cfg)
    return cfg
