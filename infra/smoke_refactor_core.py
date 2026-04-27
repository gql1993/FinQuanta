from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def check(name: str, fn):
    try:
        result = fn()
        print(f"[PASS] {name}: {result}")
        return True
    except Exception as exc:
        print(f"[FAIL] {name}: {exc}")
        return False


def main():
    ok = True

    from core.runtime.mode import resolve_runtime_mode_context
    from core.config.feature_flags import is_feature_enabled
    from core.audit.event_models import create_system_event
    from core.observability.alert_policy import build_alert_policy
    from core.observability.alert_dispatcher import dispatch_routed_alerts, get_dispatch_receipts
    from core.observability.alert_router import build_alert_routing_policy, route_alerts
    from core.observability.alerts import evaluate_metrics_alerts
    from core.observability.dashboard_templates import build_trace_dashboard_template
    from core.observability.exporters import export_otel_metrics, export_prometheus_text
    from core.observability.metrics import get_metrics_snapshot, inc_counter
    from core.observability.otel_collector import get_collector_state, push_otel_collector
    from core.observability.structured_logging import build_structured_record
    from core.observability.trace_backend_presets import build_trace_backend_preset, resolve_trace_route
    from core.observability.panel_input import build_observability_panel_input
    from core.observability.tracing import (
        build_trace_graph,
        build_traceparent,
        create_trace_id,
        export_otel_traces,
        finish_span,
        get_recent_trace_spans,
        parse_traceparent,
        start_span,
    )
    from core.observability.trends import build_event_trend_report
    from core.ai.decision_engine import parse_ai_decision_response
    from core.application.registry_service import get_registry_overview
    from core.registry import (
        list_registered_notifiers,
        list_registered_providers,
        list_registered_strategies,
        list_registered_workflows,
    )
    from core.risk.approval_service import evaluate_trade_request
    from infra.setup_grafana_provisioning import setup_grafana_provisioning

    ok &= check(
        "runtime_mode_sqlite",
        lambda: resolve_runtime_mode_context(
            runtime_mode=None,
            db_backend="sqlite",
            api_base="http://127.0.0.1:9000",
        ).runtime_mode,
    )
    ok &= check(
        "runtime_mode_postgres",
        lambda: resolve_runtime_mode_context(
            runtime_mode=None,
            db_backend="postgres",
            api_base="http://127.0.0.1:9000",
        ).runtime_mode,
    )

    original_flag = os.environ.get("FINQUANTA_FEATURE_OPENCLAW_PIPELINE")
    try:
        os.environ["FINQUANTA_FEATURE_OPENCLAW_PIPELINE"] = "0"
        ok &= check("feature_flag_override", lambda: is_feature_enabled("openclaw_pipeline"))
    finally:
        if original_flag is None:
            os.environ.pop("FINQUANTA_FEATURE_OPENCLAW_PIPELINE", None)
        else:
            os.environ["FINQUANTA_FEATURE_OPENCLAW_PIPELINE"] = original_flag

    ok &= check(
        "decision_parse",
        lambda: parse_ai_decision_response(
            '{"analysis":"ok","decisions":[{"action":"BUY","code":"600519","price":123.4,"shares":300,"reason":"test"}]}'
        ).get("parse_status"),
    )
    ok &= check(
        "audit_event_model",
        lambda: create_system_event(
            source="smoke",
            category="refactor",
            title="event-model-ready",
            trace_id="trace-smoke",
            metadata={"phase": "m4-05"},
        ).to_dict().get("event_type"),
    )
    ok &= check(
        "structured_logging_model",
        lambda: build_structured_record(
            "smoke.observability",
            trace_id="trace-smoke",
            decision_id="decision-smoke",
            source="smoke",
            category="observability",
        ).get("event"),
    )
    ok &= check("tracing_create_trace_id", lambda: create_trace_id("smoke")[:6])
    ok &= check(
        "tracing_span_finish",
        lambda: finish_span(start_span("smoke.span", trace_id="trace-smoke"), status="ok").get("status"),
    )
    ok &= check(
        "tracing_traceparent_model",
        lambda: parse_traceparent(build_traceparent("a" * 32, "b" * 16, sampled=True)).get("sampled"),
    )
    ok &= check(
        "tracing_otel_export",
        lambda: (
            finish_span(start_span("smoke.trace.export"), status="ok"),
            len(export_otel_traces(limit=10).get("resource_spans", [])),
            len(get_recent_trace_spans(limit=10)),
        )[1],
    )
    ok &= check(
        "tracing_graph_model",
        lambda: build_trace_graph(get_recent_trace_spans(limit=10)).get("node_count"),
    )
    ok &= check(
        "tracing_otel_export_filtered",
        lambda: (
            lambda span: export_otel_traces(
                limit=10,
                trace_id=parse_traceparent(span.get("traceparent", "")).get("trace_id_hex", ""),
            )
            .get("summary", {})
            .get("span_count")
        )(finish_span(start_span("smoke.trace.filtered"), status="ok")),
    )
    ok &= check("tracing_backend_preset_model", lambda: build_trace_backend_preset(backend="tempo").get("backend"))
    ok &= check(
        "tracing_backend_route_model",
        lambda: resolve_trace_route(signal="traces", backend="jaeger", base_url="http://127.0.0.1:4318").get("endpoint"),
    )
    ok &= check(
        "dashboard_trace_template_model",
        lambda: build_trace_dashboard_template().get("template_name"),
    )
    ok &= check(
        "dashboard_panel_input_model",
        lambda: build_observability_panel_input(
            active_trace_id="demo",
            trace_index=[],
            trace_items=[],
            trace_summary={},
            trace_graph={},
            trace_otel_export={},
            alerts_payload={},
            routing_state={},
            dispatch_receipts=[],
            collector_state={},
            backend_presets={},
            dashboard_template={},
        )
        .get("trace", {})
        .get("active_trace_id"),
    )
    ok &= check(
        "metrics_counter_snapshot",
        lambda: (
            inc_counter("smoke_metric_total", labels={"phase": "m4_07"}),
            get_metrics_snapshot().get("counters", {}).get("smoke_metric_total|phase=m4_07"),
        )[-1],
    )
    ok &= check(
        "metrics_alerts_model",
        lambda: evaluate_metrics_alerts(get_metrics_snapshot()).get("status"),
    )
    ok &= check(
        "metrics_export_prometheus",
        lambda: "finquanta observability metrics" in export_prometheus_text(get_metrics_snapshot()),
    )
    ok &= check(
        "metrics_export_otel",
        lambda: len(export_otel_metrics(get_metrics_snapshot()).get("resource_metrics", [])),
    )
    ok &= check(
        "alert_policy_model",
        lambda: build_alert_policy().get("name"),
    )
    ok &= check(
        "event_trend_report_model",
        lambda: build_event_trend_report([], window_days=3).get("window_days"),
    )
    ok &= check("alert_routing_policy_model", lambda: build_alert_routing_policy().get("name"))
    ok &= check(
        "alert_routing_model",
        lambda: route_alerts(
            [{"code": "smoke.alert", "severity": "warning"}],
            routing_policy=build_alert_routing_policy(),
            notifiers=[{"channels": ["in_app_feed"]}],
            dry_run=True,
        ).get("decision_count"),
    )
    ok &= check(
        "alert_dispatch_model",
        lambda: dispatch_routed_alerts(
            [{"code": "smoke.alert", "message": "smoke alert"}],
            route_alerts(
                [{"code": "smoke.alert", "severity": "warning"}],
                routing_policy=build_alert_routing_policy(),
                notifiers=[{"channels": ["in_app_feed"]}],
                dry_run=True,
            ),
            dry_run=True,
        ).get("dispatch_count"),
    )
    ok &= check("alert_dispatch_receipts_model", lambda: len(get_dispatch_receipts(limit=5)))
    ok &= check(
        "otel_collector_state_model",
        lambda: sorted(get_collector_state().keys()),
    )
    ok &= check(
        "otel_collector_push_dry_run",
        lambda: push_otel_collector(
            endpoint="",
            metrics_snapshot=get_metrics_snapshot(),
            signals=("metrics",),
            dry_run=True,
        ).get("status"),
    )
    ok &= check(
        "otel_collector_push_trace_filtered_dry_run",
        lambda: (
            lambda span: push_otel_collector(
                endpoint="",
                trace_limit=20,
                signals=("traces",),
                trace_id=parse_traceparent(span.get("traceparent", "")).get("trace_id_hex", ""),
                dry_run=True,
            ).get("trace_id")
        )(finish_span(start_span("smoke.collector.filtered"), status="ok")),
    )

    ok &= check(
        "trade_approval_skeleton",
        lambda: evaluate_trade_request(
            mode="auto",
            action="SELL",
            code="600519",
            name="贵州茅台",
            price=123.4,
            shares=0,
            reason="smoke",
        ).get("approved"),
    )
    ok &= check("registry_provider_count", lambda: len(list_registered_providers()))
    ok &= check("registry_strategy_count", lambda: len(list_registered_strategies()))
    ok &= check("registry_notifier_count", lambda: len(list_registered_notifiers()))
    ok &= check("registry_workflow_count", lambda: len(list_registered_workflows()))
    ok &= check(
        "registry_meta_source",
        lambda: get_registry_overview().get("meta", {}).get("source", ""),
    )
    ok &= check(
        "registry_meta_change_token",
        lambda: get_registry_overview().get("meta", {}).get("change_token", "")[:12],
    )
    ok &= check(
        "registry_meta_expires_at",
        lambda: get_registry_overview().get("meta", {}).get("expires_at", ""),
    )
    ok &= check(
        "registry_meta_cached_flag",
        lambda: get_registry_overview().get("meta", {}).get("cached", None),
    )
    ok &= check(
        "grafana_provisioning_model",
        lambda: setup_grafana_provisioning(
            output_dir=Path(ROOT) / "infra" / "grafana" / "provisioning",
            api_base="http://127.0.0.1:9000",
            overwrite=False,
        ).get("provider_dashboards_path"),
    )
    ok &= check(
        "grafana_datasource_model",
        lambda: (
            lambda text: "FinQuanta Loki" in text
            or (_ for _ in ()).throw(RuntimeError("FinQuanta Loki datasource missing"))
        )(
            setup_grafana_provisioning(
                output_dir=Path(ROOT) / "infra" / "grafana" / "provisioning",
                api_base="http://127.0.0.1:9000",
                overwrite=True,
            )
            and (Path(ROOT) / "infra" / "grafana" / "provisioning" / "datasources" / "finquanta-infinity.yaml")
            .read_text(encoding="utf-8")
        ),
    )

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
