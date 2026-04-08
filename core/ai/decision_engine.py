"""
Shared AI decision engine.

This module owns the decision prompt assembly and response parsing logic so the
desktop layer can gradually become a thin adapter around AI execution.
"""

from __future__ import annotations

import json
from typing import Callable

from core.ai.context_builder import (
    build_ai_portfolio_context_text,
    build_candidates_context_text,
    build_decision_history_context_text,
    build_learning_feedback_context_text,
    build_market_context_text,
    build_rotation_context_text,
)
from core.ai.decision_models import (
    build_decision_result,
    build_error_result,
)
from core.ai.prompt_registry import get_ai_decision_system_prompt


def build_ai_decision_prompt(
    board: str = "人工智能",
    mode: str = "auto",
    extra_prompt: str = "",
) -> str:
    market = build_market_context_text()
    portfolio = build_ai_portfolio_context_text(mode)
    candidates = build_candidates_context_text(board=board)
    history = build_decision_history_context_text()
    evolution = build_learning_feedback_context_text()
    rotation = build_rotation_context_text()
    return f"""请基于以下数据做出交易决策：

{market}

{portfolio}

{candidates}

{history}

{evolution}

{rotation}

{extra_prompt}

请输出 JSON 格式的交易决策："""


def parse_ai_decision_response(response: str) -> dict:
    if response.startswith("ERROR:"):
        return build_error_result(response)

    try:
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            payload = json.loads(response[start:end])
            return build_decision_result(
                analysis=str(payload.get("analysis", "") or response),
                decisions=payload.get("decisions", []),
                raw_response=response,
                parse_status="json",
            )
        return build_decision_result(
            analysis=response,
            decisions=[],
            raw_response=response,
            parse_status="plain_text",
        )
    except json.JSONDecodeError:
        return build_decision_result(
            analysis=response,
            decisions=[],
            raw_response=response,
            parse_status="invalid_json",
        )


def run_ai_decision(
    llm_call: Callable[[str, str], str],
    board: str = "人工智能",
    mode: str = "auto",
    extra_prompt: str = "",
) -> dict:
    prompt = build_ai_decision_prompt(board=board, mode=mode, extra_prompt=extra_prompt)
    response = llm_call(prompt, system=get_ai_decision_system_prompt())
    return parse_ai_decision_response(response)
