from __future__ import annotations

import os
from dataclasses import dataclass

from api_server.env_loader import load_env_files
from core.config.settings_center import settings_center
from core.runtime.mode import resolve_runtime_mode_context

load_env_files()

_runtime_context = resolve_runtime_mode_context()


@dataclass
class ApiSettings:
    app_env: str = settings_center.get_str("FINQUANTA_ENV", "dev")
    runtime_mode: str = _runtime_context.runtime_mode
    api_base: str = _runtime_context.api_base
    api_host: str = settings_center.get_str("FINQUANTA_API_HOST", "0.0.0.0")
    api_port: int = settings_center.get_int("FINQUANTA_API_PORT", 9000)
    db_backend: str = _runtime_context.db_backend  # sqlite / postgres
    sqlite_path: str = settings_center.get_str(
        "FINQUANTA_SQLITE_PATH", os.path.join("data_cache", "quant.db")
    )
    postgres_dsn: str = settings_center.get_str("FINQUANTA_POSTGRES_DSN", "")
    redis_url: str = settings_center.get_str("FINQUANTA_REDIS_URL", "")
    cors_origins: str = settings_center.get_str("FINQUANTA_CORS_ORIGINS", "*")
    snapshot_cache_ttl: int = settings_center.get_int(
        "FINQUANTA_SNAPSHOT_CACHE_TTL", 120
    )

    @property
    def is_local_mode(self) -> bool:
        return self.runtime_mode == "local"

    @property
    def is_platform_mode(self) -> bool:
        return self.runtime_mode == "platform"


settings = ApiSettings()
