"""
Application-level OpenClaw service.
"""

from __future__ import annotations


DEFAULT_OPENCLAW_BOARDS = ["人工智能", "芯片", "量子科技"]


def get_openclaw_strategy_weights() -> dict:
    from desktop.openclaw_learner import get_strategy_weights

    return get_strategy_weights()


def get_openclaw_data_sources() -> list[dict]:
    from desktop.openclaw_engine import get_data_sources_status

    return get_data_sources_status()


def run_openclaw_pipeline(boards: list[str] | None = None) -> dict:
    from desktop.openclaw_engine import run_full_pipeline

    return run_full_pipeline(boards=boards or DEFAULT_OPENCLAW_BOARDS)


def run_openclaw_learning() -> dict:
    from desktop.openclaw_learner import evaluate_and_learn

    return evaluate_and_learn()
