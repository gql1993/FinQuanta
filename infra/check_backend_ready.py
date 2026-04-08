from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api_server.cache_provider import snapshot_cache
from api_server.config import settings
from api_server.storage import repo


def main():
    result = {
        "env": settings.app_env,
        "api_base": settings.api_base,
        "api_host": settings.api_host,
        "api_port": settings.api_port,
        "db_backend": settings.db_backend,
        "db": repo.ping(),
        "cache": snapshot_cache.ping(),
        "cors_origins": settings.cors_origins,
    }
    result["ok"] = bool(result["db"].get("ok")) and bool(result["cache"].get("ok"))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
