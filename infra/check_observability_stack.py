from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

API_BASE = os.environ.get("FINQUANTA_API_BASE", "http://127.0.0.1:9000").rstrip("/")
GRAFANA_BASE = os.environ.get("FINQUANTA_GRAFANA_BASE", "http://127.0.0.1:3000").rstrip("/")
TEMPO_BASE = os.environ.get("FINQUANTA_TEMPO_BASE", "http://127.0.0.1:3200").rstrip("/")
LOKI_BASE = os.environ.get("FINQUANTA_LOKI_BASE", "http://127.0.0.1:3100").rstrip("/")
OBS_TOKEN = os.environ.get("FINQUANTA_OBSERVABILITY_READ_TOKEN", "")


def get_json(url: str) -> tuple[bool, dict]:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
        return True, json.loads(body) if body else {}


def get_text(url: str) -> tuple[bool, str]:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return True, resp.read().decode("utf-8", errors="ignore")


def check(name: str, fn):
    try:
        value = fn()
        print(f"[PASS] {name}: {value}")
        return True
    except urllib.error.HTTPError as exc:
        print(f"[FAIL] {name}: HTTP {exc.code}")
        return False
    except Exception as exc:
        print(f"[FAIL] {name}: {exc}")
        return False


def main() -> int:
    ok = True
    ok &= check("grafana_health", lambda: get_json(f"{GRAFANA_BASE}/api/health")[1].get("database", ""))
    ok &= check("tempo_ready", lambda: get_text(f"{TEMPO_BASE}/ready")[1][:20])
    ok &= check("loki_ready", lambda: get_text(f"{LOKI_BASE}/ready")[1][:20])
    panel_url = f"{API_BASE}/api/observability/dashboard/panel-input"
    if OBS_TOKEN:
        panel_url += f"?obs_token={OBS_TOKEN}"
    ok &= check("api_panel_input", lambda: get_json(panel_url)[1].get("data", {}).get("generated_at", ""))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
