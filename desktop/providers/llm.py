"""LLM：统一走 ai_trader 配置。"""
from __future__ import annotations


class LLMProvider:
    def complete(self, prompt: str, system: str = "") -> str:
        from desktop.ai_trader import _call_llm

        return _call_llm(prompt, system=system)
