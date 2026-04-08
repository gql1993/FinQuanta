from __future__ import annotations

import os


def _parse_env_line(line: str):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        return None, None
    key, value = line.split("=", 1)
    key = key.strip()
    value = value.strip().strip('"').strip("'")
    return key, value


def load_env_files(paths: list[str] | None = None):
    paths = paths or [".env.api.local", ".env.api", ".env"]
    loaded: list[str] = []
    for path in paths:
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                for raw in f:
                    key, value = _parse_env_line(raw)
                    if key:
                        os.environ.setdefault(key, value)
            loaded.append(path)
        except Exception:
            continue
    return loaded
