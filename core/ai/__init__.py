"""
Shared AI runtime helpers.
"""

from core.ai.context_builder import (
    build_ai_portfolio_context_text,
    build_assistant_context_payload,
    build_candidates_context,
    build_candidates_context_text,
    build_decision_history_context,
    build_decision_history_context_text,
    build_learning_feedback_context,
    build_learning_feedback_context_text,
    build_market_context,
    build_market_context_text,
    build_openclaw_context,
    build_openclaw_context_text,
    build_ops_context,
    build_portfolio_context,
    build_rotation_context,
    build_rotation_context_text,
    build_scan_context,
    build_snapshot_context,
    build_strategy_weights_context,
    build_verify_context,
)
from core.ai.decision_engine import (
    build_ai_decision_prompt,
    parse_ai_decision_response,
    run_ai_decision,
)
from core.ai.prompt_registry import (
    build_assistant_system_prompt,
    get_ai_decision_system_prompt,
)

__all__ = [
    "build_snapshot_context",
    "build_market_context",
    "build_portfolio_context",
    "build_candidates_context",
    "build_decision_history_context",
    "build_rotation_context",
    "build_learning_feedback_context",
    "build_scan_context",
    "build_ops_context",
    "build_verify_context",
    "build_strategy_weights_context",
    "build_openclaw_context",
    "build_ai_portfolio_context_text",
    "build_candidates_context_text",
    "build_assistant_context_payload",
    "build_decision_history_context_text",
    "build_rotation_context_text",
    "build_learning_feedback_context_text",
    "build_market_context_text",
    "build_openclaw_context_text",
    "build_ai_decision_prompt",
    "parse_ai_decision_response",
    "run_ai_decision",
    "get_ai_decision_system_prompt",
    "build_assistant_system_prompt",
]
