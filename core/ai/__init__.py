"""
Shared AI runtime helpers.

Exports are resolved lazily to avoid circular imports between AI/application
packages while keeping a convenient package-level API.
"""

from __future__ import annotations

from importlib import import_module

_EXPORTS = {
    "build_snapshot_context": "core.ai.context_builder",
    "build_market_context": "core.ai.context_builder",
    "build_portfolio_context": "core.ai.context_builder",
    "build_candidates_context": "core.ai.context_builder",
    "build_decision_history_context": "core.ai.context_builder",
    "build_decision_reflection_context": "core.ai.context_builder",
    "build_decision_memory_context": "core.ai.context_builder",
    "parse_board_tokens": "core.ai.context_builder",
    "build_rotation_context": "core.ai.context_builder",
    "build_learning_feedback_context": "core.ai.context_builder",
    "build_scan_context": "core.ai.context_builder",
    "build_ops_context": "core.ai.context_builder",
    "build_verify_context": "core.ai.context_builder",
    "build_strategy_weights_context": "core.ai.context_builder",
    "build_openclaw_context": "core.ai.context_builder",
    "build_ai_portfolio_context_text": "core.ai.context_builder",
    "build_candidates_context_text": "core.ai.context_builder",
    "build_assistant_context_payload": "core.ai.context_builder",
    "build_decision_history_context_text": "core.ai.context_builder",
    "build_decision_reflection_context_text": "core.ai.context_builder",
    "build_decision_memory_context_text": "core.ai.context_builder",
    "build_rotation_context_text": "core.ai.context_builder",
    "build_learning_feedback_context_text": "core.ai.context_builder",
    "build_market_context_text": "core.ai.context_builder",
    "build_openclaw_context_text": "core.ai.context_builder",
    "TradingDecision": "core.ai.decision_models",
    "DecisionEngineResult": "core.ai.decision_models",
    "normalize_decision_payload": "core.ai.decision_models",
    "build_decision_result": "core.ai.decision_models",
    "build_error_result": "core.ai.decision_models",
    "ensure_decision_memory_table": "core.ai.decision_memory",
    "save_decision_memory": "core.ai.decision_memory",
    "calibrate_decisions": "core.ai.decision_memory",
    "get_decision_accuracy": "core.ai.decision_memory",
    "build_ai_decision_prompt": "core.ai.decision_engine",
    "parse_ai_decision_response": "core.ai.decision_engine",
    "apply_decision_price_grounding": "core.ai.decision_engine",
    "run_ai_decision": "core.ai.decision_engine",
    "build_grounded_price_map": "core.ai.decision_grounding",
    "build_grounded_price_map_from_verification": "core.ai.decision_grounding",
    "normalize_buy_decisions": "core.ai.decision_grounding",
    "get_ai_decision_system_prompt": "core.ai.prompt_registry",
    "get_decision_agent_system_prompt": "core.ai.prompt_registry",
    "get_decision_grounding_rules": "core.ai.prompt_registry",
    "append_decision_grounding_rules": "core.ai.prompt_registry",
    "build_assistant_system_prompt": "core.ai.prompt_registry",
}


def __getattr__(name: str):
    module_name = _EXPORTS.get(name)
    if not module_name:
        raise AttributeError(name)
    module = import_module(module_name)
    return getattr(module, name)

__all__ = [
    "build_snapshot_context",
    "build_market_context",
    "build_portfolio_context",
    "build_candidates_context",
    "build_decision_history_context",
    "build_decision_reflection_context",
    "build_decision_memory_context",
    "parse_board_tokens",
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
    "build_decision_reflection_context_text",
    "build_decision_memory_context_text",
    "build_rotation_context_text",
    "build_learning_feedback_context_text",
    "build_market_context_text",
    "build_openclaw_context_text",
    "build_ai_decision_prompt",
    "parse_ai_decision_response",
    "apply_decision_price_grounding",
    "run_ai_decision",
    "build_grounded_price_map",
    "build_grounded_price_map_from_verification",
    "normalize_buy_decisions",
    "TradingDecision",
    "DecisionEngineResult",
    "normalize_decision_payload",
    "build_decision_result",
    "build_error_result",
    "ensure_decision_memory_table",
    "save_decision_memory",
    "calibrate_decisions",
    "get_decision_accuracy",
    "get_ai_decision_system_prompt",
    "get_decision_agent_system_prompt",
    "get_decision_grounding_rules",
    "append_decision_grounding_rules",
    "build_assistant_system_prompt",
]
