"""
Application service layer for FinQuanta.

Exports are resolved lazily so higher-level packages can depend on application
symbols without forcing every service module to import at package load time.
"""

from __future__ import annotations

from importlib import import_module

_EXPORTS = {
    "build_system_snapshot": "core.application.snapshot_service",
    "get_system_snapshot": "core.application.snapshot_service",
    "get_system_snapshot_cached": "core.application.snapshot_service",
    "save_system_snapshot": "core.application.snapshot_service",
    "get_portfolio_positions": "core.application.portfolio_service",
    "get_portfolio_recommendations": "core.application.portfolio_service",
    "get_portfolio_summary": "core.application.portfolio_service",
    "ask_assistant": "core.application.assistant_service",
    "build_assistant_context_payload": "core.application.assistant_service",
    "get_session_messages": "core.application.assistant_service",
    "get_sessions": "core.application.assistant_service",
    "get_recent_task_runs": "core.application.ops_service",
    "get_recent_system_events": "core.application.ops_service",
    "get_operation_log": "core.application.ops_service",
    "get_ops_center_payload": "core.application.ops_service",
    "get_message_feed": "core.application.ops_service",
    "get_openclaw_strategy_weights": "core.application.openclaw_service",
    "get_openclaw_data_sources": "core.application.openclaw_service",
    "run_openclaw_pipeline": "core.application.openclaw_service",
    "run_openclaw_learning": "core.application.openclaw_service",
    "get_verify_records": "core.application.verify_service",
    "get_verify_accuracy_stats": "core.application.verify_service",
    "calibrate_verify": "core.application.verify_service",
    "get_trend_verify_records": "core.application.trend_verify_service",
    "get_trend_verify_stats": "core.application.trend_verify_service",
    "get_trend_failure_summary": "core.application.trend_verify_service",
    "run_batch_failure_analysis": "core.application.trend_verify_service",
    "run_scan_task": "core.application.task_service",
    "trigger_named_task": "core.application.task_service",
    "approve_trade": "core.application.trade_approval_service",
    "get_registry_overview": "core.application.registry_service",
    "get_registered_providers": "core.application.registry_service",
    "get_registered_strategies": "core.application.registry_service",
    "get_registered_notifiers": "core.application.registry_service",
    "get_registered_workflows": "core.application.registry_service",
    "export_runtime_state": "core.application.sync_service",
    "export_runtime_state_to_file": "core.application.sync_service",
    "import_runtime_state_from_file": "core.application.sync_service",
}


def __getattr__(name: str):
    module_name = _EXPORTS.get(name)
    if not module_name:
        raise AttributeError(name)
    module = import_module(module_name)
    return getattr(module, name)

__all__ = [
    "build_system_snapshot",
    "get_system_snapshot",
    "get_system_snapshot_cached",
    "save_system_snapshot",
    "get_portfolio_positions",
    "get_portfolio_recommendations",
    "get_portfolio_summary",
    "ask_assistant",
    "build_assistant_context_payload",
    "get_session_messages",
    "get_sessions",
    "get_recent_task_runs",
    "get_recent_system_events",
    "get_operation_log",
    "get_ops_center_payload",
    "get_message_feed",
    "get_openclaw_strategy_weights",
    "get_openclaw_data_sources",
    "run_openclaw_pipeline",
    "run_openclaw_learning",
    "get_verify_records",
    "get_verify_accuracy_stats",
    "calibrate_verify",
    "get_trend_verify_records",
    "get_trend_verify_stats",
    "get_trend_failure_summary",
    "run_batch_failure_analysis",
    "run_scan_task",
    "trigger_named_task",
    "approve_trade",
    "get_registry_overview",
    "get_registered_providers",
    "get_registered_strategies",
    "get_registered_notifiers",
    "get_registered_workflows",
    "export_runtime_state",
    "export_runtime_state_to_file",
    "import_runtime_state_from_file",
]
