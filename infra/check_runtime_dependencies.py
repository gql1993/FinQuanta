from __future__ import annotations

import argparse
import importlib.util
import sys


REQUIRED_MODULES = [
    ("fastapi", "FastAPI API service"),
    ("uvicorn", "API ASGI server"),
    ("pandas", "dataframe processing"),
    ("numpy", "numeric processing"),
    ("streamlit", "web UI"),
    ("PyQt6", "desktop UI"),
    ("openai", "LLM client"),
]

OPTIONAL_MODULES = [
    ("akshare", "market data provider"),
    ("matplotlib", "charts"),
    ("mplfinance", "candlestick charts"),
    ("plotly", "web charts"),
    ("psycopg", "PostgreSQL backend"),
    ("redis", "Redis cache/client"),
    ("openclaw", "OpenClaw integration"),
    ("PyQt6.QtWebEngineWidgets", "desktop embedded browser"),
]


def _check_module(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Check FinQuanta runtime Python dependencies.")
    parser.add_argument("--strict", action="store_true", help="Treat optional dependency misses as failures.")
    args = parser.parse_args()

    required_missing = []
    optional_missing = []
    print(f"PYTHON={sys.version.split()[0]}")
    for module, purpose in REQUIRED_MODULES:
        ok = _check_module(module)
        print(f"[{'PASS' if ok else 'FAIL'}] required {module}: {purpose}")
        if not ok:
            required_missing.append(module)
    for module, purpose in OPTIONAL_MODULES:
        ok = _check_module(module)
        print(f"[{'PASS' if ok else 'WARN'}] optional {module}: {purpose}")
        if not ok:
            optional_missing.append(module)

    failed = bool(required_missing) or (args.strict and bool(optional_missing))
    if required_missing:
        print(f"REQUIRED_MISSING={','.join(required_missing)}")
    if optional_missing:
        print(f"OPTIONAL_MISSING={','.join(optional_missing)}")
    print("[RESULT] PASS" if not failed else "[RESULT] FAIL")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
