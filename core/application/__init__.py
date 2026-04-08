"""
Application service layer for FinQuanta.

This package is the first extraction target in the refactor plan so new
cross-channel use cases can converge on stable service entry points.
"""

from core.application.snapshot_service import (
    build_system_snapshot,
    get_system_snapshot,
    get_system_snapshot_cached,
    save_system_snapshot,
)
from core.application.portfolio_service import (
    get_portfolio_positions,
    get_portfolio_recommendations,
    get_portfolio_summary,
)
from core.application.assistant_service import (
    ask_assistant,
    build_assistant_context_payload,
    get_session_messages,
    get_sessions,
)
from core.application.ops_service import (
    get_message_feed,
    get_operation_log,
    get_ops_center_payload,
    get_recent_system_events,
    get_recent_task_runs,
)
from core.application.openclaw_service import (
    get_openclaw_data_sources,
    get_openclaw_strategy_weights,
    run_openclaw_learning,
    run_openclaw_pipeline,
)
from core.application.task_service import run_scan_task, trigger_named_task
from core.application.trade_approval_service import approve_trade
from core.application.verify_service import (
    calibrate_verify,
    get_verify_accuracy_stats,
    get_verify_records,
)

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
    "run_scan_task",
    "trigger_named_task",
    "approve_trade",
]
