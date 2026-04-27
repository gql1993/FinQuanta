from __future__ import annotations

import argparse
import os
import socket
import sys
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api_server.env_loader import load_env_files


def _is_enabled() -> bool:
    raw = str(os.environ.get("FINQUANTA_OPENCLAW_GATEWAY_ENABLED", "1")).strip().lower()
    return raw not in {"0", "false", "off", "no"}


def _resolve_host_port() -> tuple[str, int, str]:
    base = str(os.environ.get("FINQUANTA_OPENCLAW_GATEWAY_BASE", "http://127.0.0.1:18789")).strip()
    if not base:
        base = "http://127.0.0.1:18789"
    parsed = urllib.parse.urlparse(base if "://" in base else f"http://{base}")
    host = parsed.hostname or "127.0.0.1"
    if host == "0.0.0.0":
        host = "127.0.0.1"
    port = parsed.port or 18789
    return host, port, base


def _tcp_probe(host: str, port: int, timeout_s: float) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(max(0.2, timeout_s))
        try:
            s.connect((host, port))
            return True
        except Exception:
            return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Check OpenClaw gateway reachability.")
    parser.add_argument("--strict", action="store_true", help="Return non-zero when gateway is unreachable.")
    args = parser.parse_args()

    load_env_files()

    enabled = _is_enabled()
    timeout = float(os.environ.get("FINQUANTA_OPENCLAW_GATEWAY_TIMEOUT_SECONDS", "1.0") or "1.0")
    host, port, base = _resolve_host_port()

    print(f"OPENCLAW_GATEWAY_ENABLED={1 if enabled else 0}")
    print(f"OPENCLAW_GATEWAY_BASE={base}")
    print(f"OPENCLAW_GATEWAY_PROBE={host}:{port}")

    if not enabled:
        print("[SKIP] Gateway disabled by FINQUANTA_OPENCLAW_GATEWAY_ENABLED.")
        return 0

    if _tcp_probe(host, port, timeout):
        print("[PASS] OpenClaw gateway is reachable.")
        return 0

    print("[FAIL] OpenClaw gateway is unreachable.")
    print("[HINT] Run: start_openclaw.bat")
    return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
