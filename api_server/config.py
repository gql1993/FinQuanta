from __future__ import annotations

import os
from dataclasses import dataclass

from api_server.env_loader import load_env_files

load_env_files()


@dataclass
class ApiSettings:
    app_env: str = os.environ.get("FINQUANTA_ENV", "dev")
    api_base: str = os.environ.get("FINQUANTA_API_BASE", "http://127.0.0.1:9000")
    api_host: str = os.environ.get("FINQUANTA_API_HOST", "0.0.0.0")
    api_port: int = int(os.environ.get("FINQUANTA_API_PORT", "9000"))
    db_backend: str = os.environ.get("FINQUANTA_DB_BACKEND", "sqlite")  # sqlite / postgres
    sqlite_path: str = os.environ.get("FINQUANTA_SQLITE_PATH", os.path.join("data_cache", "quant.db"))
    postgres_dsn: str = os.environ.get("FINQUANTA_POSTGRES_DSN", "")
    redis_url: str = os.environ.get("FINQUANTA_REDIS_URL", "")
    cors_origins: str = os.environ.get("FINQUANTA_CORS_ORIGINS", "*")
    snapshot_cache_ttl: int = int(os.environ.get("FINQUANTA_SNAPSHOT_CACHE_TTL", "120"))


settings = ApiSettings()
