from __future__ import annotations

from api_server.storage import repo


def get_ai_config() -> dict:
    cfg = repo.kv_get("ai_config", {}) or {}
    if not isinstance(cfg, dict):
        return {}
    provider = cfg.get("provider", "")
    if not provider:
        base_url = str(cfg.get("base_url", "")).lower()
        if "openai" in base_url:
            provider = "OpenAI"
        elif "anthropic" in base_url:
            provider = "Claude"
        elif "googleapis" in base_url or "gemini" in base_url:
            provider = "Gemini"
        elif "deepseek" in base_url:
            provider = "DeepSeek"
        else:
            provider = "自定义"
        cfg["provider"] = provider
    if not cfg.get("model"):
        cfg["model"] = "deepseek-chat"
    return cfg


def save_ai_config(
    api_key: str,
    base_url: str = "",
    model: str = "deepseek-chat",
    provider: str = "DeepSeek",
) -> dict:
    cfg = {
        "api_key": api_key or "",
        "base_url": base_url or "https://api.deepseek.com/v1",
        "model": model or "deepseek-chat",
        "provider": provider or "DeepSeek",
    }
    repo.kv_set("ai_config", cfg)
    return cfg
