from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api_server.env_loader import load_env_files

load_env_files()


API_BASE = os.environ.get("FINQUANTA_API_BASE", "http://127.0.0.1:9000").rstrip("/")
API_USER = os.environ.get("FINQUANTA_SMOKE_USER", "admin")
API_PASSWORD = os.environ.get("FINQUANTA_SMOKE_PASSWORD", "admin123")
TRACEPARENT_SAMPLE = "00-11111111111111111111111111111111-2222222222222222-01"


def api_call(
    method: str,
    path: str,
    payload: dict | None = None,
    token: str = "",
    headers: dict | None = None,
):
    merged_headers = {"Content-Type": "application/json"}
    if isinstance(headers, dict):
        merged_headers.update(headers)
    if token:
        merged_headers["Authorization"] = f"Bearer {token}"
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"{API_BASE}{path}", method=method.upper(), headers=merged_headers, data=data)
    parsed = urllib.parse.urlparse(API_BASE)
    host = (parsed.hostname or "").lower()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({})) if host in {"127.0.0.1", "localhost", "0.0.0.0"} else urllib.request.build_opener()
    with opener.open(req, timeout=20) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
        return json.loads(body) if body else {}


def api_call_text(method: str, path: str, token: str = "") -> str:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{API_BASE}{path}", method=method.upper(), headers=headers)
    parsed = urllib.parse.urlparse(API_BASE)
    host = (parsed.hostname or "").lower()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({})) if host in {"127.0.0.1", "localhost", "0.0.0.0"} else urllib.request.build_opener()
    with opener.open(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def check(name: str, fn):
    try:
        result = fn()
        print(f"[PASS] {name}: {result}")
        return True
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        print(f"[FAIL] {name}: HTTP {exc.code} {detail}")
        return False
    except Exception as exc:
        print(f"[FAIL] {name}: {exc}")
        return False


def _print_api_startup_hint(exc: Exception):
    parsed = urllib.parse.urlparse(API_BASE)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 9000
    print(f"[ERROR] API unreachable at {API_BASE}: {exc}")
    print("[HINT] Start API server then rerun smoke:")
    print(f"       python -m uvicorn api_server.main:app --host 0.0.0.0 --port {port}")
    if host not in {"127.0.0.1", "localhost", "0.0.0.0"}:
        print(f"[HINT] If API runs elsewhere, set FINQUANTA_API_BASE (current host: {host})")


def main():
    print(f"API_BASE={API_BASE}")
    try:
        api_call("GET", "/health")
    except Exception as exc:
        _print_api_startup_hint(exc)
        return 1

    ok = True

    ok &= check("health", lambda: api_call("GET", "/health").get("service"))
    ok &= check("health_runtime_mode", lambda: api_call("GET", "/health").get("runtime_mode"))
    ok &= check("health_deps", lambda: api_call("GET", "/health/deps").get("dependencies", {}).get("database", {}))

    login_resp = {}

    def do_login():
        nonlocal login_resp
        login_resp = api_call("POST", "/api/auth/login", {"username": API_USER, "password": API_PASSWORD})
        if not login_resp.get("ok"):
            raise RuntimeError(login_resp.get("message", "login failed"))
        return login_resp.get("role", "")

    ok &= check("auth_login", do_login)
    token = login_resp.get("token", "")
    if not token:
        return 1

    ok &= check("auth_profile", lambda: api_call("GET", "/api/auth/profile", token=token).get("data", {}).get("username"))
    ok &= check(
        "snapshot_system",
        lambda: (
            api_call("GET", "/api/snapshot/system", token=token)
            .get("data", {})
            .get("totals", {})
        ),
    )
    ok &= check("scan_latest", lambda: api_call("GET", "/api/scan/latest", token=token).get("data", {}).get("count", 0))
    ok &= check("portfolio_summary", lambda: api_call("GET", "/api/portfolio/summary", token=token).get("data", {}).keys())
    ok &= check("portfolio_positions", lambda: api_call("GET", "/api/portfolio/positions", token=token).get("data", {}).keys())
    ok &= check(
        "portfolio_recommendations",
        lambda: api_call("GET", "/api/portfolio/recommendations", token=token).get("data", {}).keys(),
    )
    ok &= check("ops_tasks", lambda: len(api_call("GET", "/api/ops/tasks", token=token).get("data", [])))
    ok &= check("ops_events", lambda: len(api_call("GET", "/api/ops/events", token=token).get("data", [])))
    def read_ops_center_registry_counts():
        payload = api_call("GET", "/api/ops/center", token=token).get("data", {})
        registry = payload.get("registry", {})
        provider_count = int(registry.get("provider_count", 0) or 0)
        strategy_count = int(registry.get("strategy_count", 0) or 0)
        notifier_count = int(registry.get("notifier_count", 0) or 0)
        workflow_count = int(registry.get("workflow_count", 0) or 0)
        if provider_count <= 0 or strategy_count <= 0 or notifier_count <= 0 or workflow_count <= 0:
            raise RuntimeError(
                f"invalid registry counts: providers={provider_count}, strategies={strategy_count}, "
                f"notifiers={notifier_count}, workflows={workflow_count}"
            )
        return provider_count, strategy_count, notifier_count, workflow_count

    def read_ops_center_registry_meta():
        payload = api_call("GET", "/api/ops/center", token=token).get("data", {})
        registry = payload.get("registry", {})
        meta = registry.get("meta", {})
        refreshed_at = str(meta.get("refreshed_at", "") or "")
        expires_at = str(meta.get("expires_at", "") or "")
        source = str(meta.get("source", "") or "")
        change_token = str(meta.get("change_token", "") or "")
        cached = meta.get("cached")
        if not refreshed_at or "T" not in refreshed_at:
            raise RuntimeError(f"invalid refreshed_at: {refreshed_at}")
        if not expires_at or "T" not in expires_at:
            raise RuntimeError(f"invalid expires_at: {expires_at}")
        if source != "core.registry":
            raise RuntimeError(f"invalid source: {source}")
        if len(change_token) < 20:
            raise RuntimeError(f"invalid change_token: {change_token}")
        if not isinstance(cached, bool):
            raise RuntimeError(f"invalid cached flag: {cached}")
        return {"refreshed_at": refreshed_at, "source": source, "change_token": change_token[:12], "cached": cached}

    def read_ops_center_registry_incremental():
        first = api_call("GET", "/api/ops/center", token=token).get("data", {})
        first_registry = first.get("registry", {})
        first_token = str(first_registry.get("meta", {}).get("change_token", "") or "")
        if not first_token:
            raise RuntimeError("missing initial registry change_token")
        second = api_call("GET", f"/api/ops/center?registry_token={first_token}", token=token).get("data", {})
        if second.get("registry_changed") is not False:
            raise RuntimeError(f"expected registry_changed=False, got {second.get('registry_changed')}")
        second_registry = second.get("registry", {})
        providers = second_registry.get("providers", [])
        strategies = second_registry.get("strategies", [])
        if providers or strategies:
            raise RuntimeError("expected compact registry payload when unchanged")
        second_cached = second_registry.get("meta", {}).get("cached")
        if not isinstance(second_cached, bool):
            raise RuntimeError(f"invalid cached flag in second payload: {second_cached}")
        return {"registry_changed": second.get("registry_changed"), "token": first_token[:12], "cached": second_cached}

    def read_ops_center_registry_sync():
        payload = api_call("GET", "/api/ops/center", token=token).get("data", {})
        sync = payload.get("registry_sync", {})
        payload_mode = str(sync.get("payload_mode", "") or "")
        cached = sync.get("cached")
        if payload_mode not in {"full", "compact"}:
            raise RuntimeError(f"invalid payload_mode: {payload_mode}")
        if not isinstance(cached, bool):
            raise RuntimeError(f"invalid cached value: {cached}")
        return {"payload_mode": payload_mode, "cached": cached}

    ok &= check(
        "ops_center",
        lambda: sorted(
            key
            for key in api_call("GET", "/api/ops/center", token=token).get("data", {}).keys()
            if key in {"snapshot", "tasks", "events", "operations", "registry", "registry_sync"}
        ),
    )
    ok &= check("ops_center_registry_counts", read_ops_center_registry_counts)
    ok &= check("ops_center_registry_meta", read_ops_center_registry_meta)
    ok &= check("ops_center_registry_sync", read_ops_center_registry_sync)
    ok &= check("ops_center_registry_incremental", read_ops_center_registry_incremental)
    ok &= check("messages", lambda: len(api_call("GET", "/api/messages", token=token).get("data", [])))
    ok &= check(
        "observability_metrics",
        lambda: sorted(
            api_call("GET", "/api/observability/metrics", token=token).get("data", {}).keys()
        ),
    )
    ok &= check(
        "observability_metrics_prometheus",
        lambda: "finquanta observability metrics"
        in api_call_text("GET", "/api/observability/metrics/prometheus", token=token),
    )
    ok &= check(
        "observability_metrics_otel",
        lambda: len(
            api_call("GET", "/api/observability/metrics/otel", token=token)
            .get("data", {})
            .get("resource_metrics", [])
        ),
    )
    ok &= check(
        "observability_traces",
        lambda: api_call("GET", "/api/observability/traces", token=token).get("data", {}).get("count", -1),
    )
    ok &= check(
        "observability_traces_index",
        lambda: api_call("GET", "/api/observability/traces/index", token=token).get("data", {}).get("count", -1),
    )
    ok &= check(
        "observability_traces_otel",
        lambda: api_call("GET", "/api/observability/traces/otel", token=token).get("data", {}).get("count", -1),
    )
    ok &= check(
        "observability_traces_otel_by_trace_id",
        lambda: (
            lambda traceparent: api_call(
                "GET",
                f"/api/observability/traces/otel?trace_id={traceparent.split('-')[1]}&limit=20",
                token=token,
            )
            .get("data", {})
            .get("summary", {})
            .get("span_count", -1)
        )(
            api_call("GET", "/api/observability/trace/context", token=token)
            .get("data", {})
            .get("outgoing", {})
            .get("traceparent", "00-0-0-00")
        ),
    )
    ok &= check(
        "observability_trace_detail_by_context",
        lambda: (
            lambda traceparent: api_call(
                "GET",
                f"/api/observability/traces/trace/{traceparent.split('-')[1]}?limit=20",
                token=token,
            )
            .get("data", {})
            .get("summary", {})
            .get("span_count", -1)
        )(
            api_call("GET", "/api/observability/trace/context", token=token)
            .get("data", {})
            .get("outgoing", {})
            .get("traceparent", "00-0-0-00")
        ),
    )
    ok &= check(
        "observability_traces_config",
        lambda: api_call("GET", "/api/observability/traces/config", token=token)
        .get("data", {})
        .get("sample_ratio", ""),
    )
    ok &= check(
        "observability_traces_backend_presets",
        lambda: api_call("GET", "/api/observability/traces/backends/presets", token=token)
        .get("data", {})
        .get("default_backend", ""),
    )
    ok &= check(
        "observability_dashboard_template",
        lambda: api_call("GET", "/api/observability/dashboard/template", token=token)
        .get("data", {})
        .get("template_name", ""),
    )
    ok &= check(
        "observability_dashboard_panel_input",
        lambda: sorted(
            api_call("GET", "/api/observability/dashboard/panel-input", token=token)
            .get("data", {})
            .keys()
        ),
    )
    ok &= check(
        "observability_collector_state",
        lambda: api_call("GET", "/api/observability/collector/state", token=token)
        .get("data", {})
        .get("circuit_open", None),
    )
    ok &= check(
        "observability_collector_push_dry_run",
        lambda: api_call(
            "POST",
            "/api/observability/collector/push?signal=both&dry_run=true",
            token=token,
        )
        .get("data", {})
        .get("status", ""),
    )
    ok &= check(
        "observability_collector_push_trace_id_dry_run",
        lambda: (
            lambda traceparent: api_call(
                "POST",
                f"/api/observability/collector/push?signal=traces&dry_run=true&trace_id={traceparent.split('-')[1]}&trace_backend=tempo",
                token=token,
            )
            .get("data", {})
            .get("trace_id", "")
        )(
            api_call("GET", "/api/observability/trace/context", token=token)
            .get("data", {})
            .get("outgoing", {})
            .get("traceparent", "00-0-0-00")
        ),
    )
    ok &= check(
        "observability_trace_context",
        lambda: api_call(
            "GET",
            "/api/observability/trace/context",
            token=token,
        )
        .get("data", {})
        .get("outgoing", {})
        .get("traceparent", ""),
    )
    ok &= check(
        "observability_trends",
        lambda: api_call("GET", "/api/observability/trends", token=token).get("data", {}).get("window_days"),
    )
    ok &= check(
        "observability_alerts_policy",
        lambda: api_call("GET", "/api/observability/alerts/policy", token=token)
        .get("data", {})
        .get("name", ""),
    )
    ok &= check(
        "observability_alerts_routing_policy",
        lambda: api_call("GET", "/api/observability/alerts/routing", token=token)
        .get("data", {})
        .get("name", ""),
    )
    ok &= check(
        "observability_alerts_route",
        lambda: api_call("POST", "/api/observability/alerts/route?dry_run=true", token=token)
        .get("data", {})
        .get("routing", {})
        .get("decision_count", -1),
    )
    ok &= check(
        "observability_alerts_routing_state",
        lambda: sorted(
            api_call("GET", "/api/observability/alerts/routing/state", token=token)
            .get("data", {})
            .keys()
        ),
    )
    ok &= check(
        "observability_alerts_dispatch_dry_run",
        lambda: api_call("POST", "/api/observability/alerts/dispatch?dry_run=true", token=token)
        .get("data", {})
        .get("dispatch", {})
        .get("dispatch_count", -1),
    )
    ok &= check(
        "observability_alerts_dispatch_receipts",
        lambda: api_call("GET", "/api/observability/alerts/dispatch/receipts?limit=10", token=token)
        .get("data", {})
        .get("count", -1),
    )
    ok &= check(
        "observability_alerts",
        lambda: (
            api_call("GET", "/api/observability/alerts", token=token).get("data", {}).get("status", ""),
            api_call("GET", "/api/observability/alerts", token=token).get("data", {}).get("policy", {}).get("name", ""),
        ),
    )
    ok &= check("registry_overview", lambda: api_call("GET", "/api/registry", token=token).get("data", {}).get("provider_count", 0))
    ok &= check("registry_providers", lambda: len(api_call("GET", "/api/registry/providers", token=token).get("data", [])))
    ok &= check("registry_strategies", lambda: len(api_call("GET", "/api/registry/strategies", token=token).get("data", [])))
    ok &= check("registry_notifiers", lambda: len(api_call("GET", "/api/registry/notifiers", token=token).get("data", [])))
    ok &= check("registry_workflows", lambda: len(api_call("GET", "/api/registry/workflows", token=token).get("data", [])))
    ok &= check("openclaw_weights", lambda: api_call("GET", "/api/openclaw/weights", token=token).get("data", {}).keys())
    ok &= check("openclaw_sources", lambda: len(api_call("GET", "/api/openclaw/sources", token=token).get("data", [])))
    ok &= check(
        "openclaw_daemon_status",
        lambda: sorted(
            api_call("GET", "/api/openclaw/daemon/status", token=token).get("data", {}).keys()
        ),
    )
    ok &= check(
        "openclaw_guard_replay",
        lambda: (
            lambda data: {
                "ok": data.get("ok"),
                "source": data.get("source", ""),
                "input_count": data.get("input_count", 0),
                "message": data.get("message", ""),
            }
        )(
            api_call(
                "POST",
                "/api/openclaw/unattended-trade-guard/replay",
                {"limit": 3, "shares": 100, "mode": "auto", "use_real_price": False},
                token=token,
            ).get("data", {})
        ),
    )
    ok &= check(
        "openclaw_pipeline_dry_run_trace",
        lambda: api_call(
            "POST",
            "/api/openclaw/pipeline/run",
            {"dry_run": True},
            token=token,
            headers={"traceparent": TRACEPARENT_SAMPLE},
        )
        .get("data", {})
        .get("traceparent", ""),
    )
    ok &= check(
        "task_trigger_dry_run_trace",
        lambda: api_call(
            "POST",
            "/api/task/trigger/pipeline",
            {"dry_run": True},
            token=token,
            headers={"traceparent": TRACEPARENT_SAMPLE},
        )
        .get("data", {})
        .get("traceparent", ""),
    )
    ok &= check("verify_summary", lambda: api_call("GET", "/api/verify/summary", token=token).get("data", {}).get("total", 0))
    ok &= check("settings_ai", lambda: api_call("GET", "/api/settings/ai", token=token).get("data", {}).keys())
    ok &= check(
        "assistant_context",
        lambda: sorted(
            key
            for key in api_call("GET", "/api/assistant/context", token=token)
            .get("data", {})
            .keys()
            if key
            in {
                "snapshot_context",
                "market_context",
                "scan_context",
                "verify_context",
                "strategy_weights_context",
                "ops_context",
                "context_text",
            }
        ),
    )
    ok &= check(
        "assistant_ask",
        lambda: api_call(
            "POST",
            "/api/assistant/ask",
            {"prompt": "请用一句话总结当前系统状态", "session_id": "smoke_test"},
            token=token,
        ).get("data", {}).get("session_id", ""),
    )
    ok &= check("assistant_sessions", lambda: len(api_call("GET", "/api/assistant/sessions", token=token).get("data", {}).get("items", [])))
    ok &= check("auth_logout", lambda: api_call("POST", "/api/auth/logout", token=token).get("data", {}).get("logout"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
