"""
OpenClaw 集成 - AI 自主交易代理
兼容不同 OpenClaw SDK 版本，支持自动决策与执行。
"""
import os
import json
import logging
from typing import Any

from desktop.data_access import get_kv_json, set_kv_json

_log = logging.getLogger("openclaw_agent")

OPENCLAW_CONFIG_KEY = "openclaw_config"
DEFAULT_OPENCLAW_MODEL = "claude-3-5-sonnet"


def save_openclaw_config(api_key: str, model: str = ""):
    """保存 OpenClaw API 配置。"""
    payload = {"api_key": api_key}
    if model:
        payload["model"] = model
    set_kv_json(OPENCLAW_CONFIG_KEY, payload)


def get_openclaw_config() -> dict:
    api_key = os.environ.get("OPENCLAW_API_KEY", "").strip()
    model = os.environ.get("OPENCLAW_MODEL", DEFAULT_OPENCLAW_MODEL).strip() or DEFAULT_OPENCLAW_MODEL
    try:
        cfg = get_kv_json(OPENCLAW_CONFIG_KEY)
        if isinstance(cfg, str):
            cfg = json.loads(cfg)
        if isinstance(cfg, dict):
            if not api_key:
                api_key = str(cfg.get("api_key", "")).strip()
            if "model" in cfg and str(cfg.get("model", "")).strip():
                model = str(cfg.get("model")).strip()
    except Exception:
        pass
    return {"api_key": api_key, "model": model}


def _build_trading_prompt(board: str = "人工智能") -> str:
    """构建交易决策 prompt（复用 ai_trader 的上下文）。"""
    from desktop.ai_trader import (
        _build_market_context,
        _build_portfolio_context,
        _build_candidates_context,
        SYSTEM_PROMPT,
    )
    market = _build_market_context()
    portfolio = _build_portfolio_context("auto")
    candidates = _build_candidates_context(board)

    return f"""{SYSTEM_PROMPT}

请基于以下数据做出交易决策：

{market}

{portfolio}

{candidates}

请输出 JSON 格式的交易决策："""


def run_openclaw_decision(board: str = "人工智能") -> dict:
    """通过 OpenClaw Agent 做自主决策。"""
    cfg = get_openclaw_config()
    if not cfg["api_key"]:
        return {"error": "未配置 OpenClaw API Key", "decisions": []}

    try:
        client = _create_openclaw_client(cfg["api_key"])

        prompt = _build_trading_prompt(board)
        reply = _run_openclaw_prompt(client, prompt, model=cfg["model"])

        _log.info(f"openclaw response: {str(reply)[:200]}")

        # 解析 JSON
        result = _parse_openclaw_reply(reply)

        result["source"] = "openclaw"
        result["model"] = cfg["model"]
        return result

    except ImportError:
        return {"error": "OpenClaw SDK 未安装 (pip install openclaw)", "decisions": []}
    except Exception as e:
        _log.error(f"openclaw error: {e}")
        return {"error": f"OpenClaw 调用失败: {e}", "decisions": []}


def run_openclaw_auto_cycle(board: str = "人工智能") -> list[str]:
    """OpenClaw 自主仓自动决策+执行。"""
    from desktop.ai_trader import execute_ai_decisions

    result = run_openclaw_decision(board)
    decisions = result.get("decisions", [])

    if result.get("error"):
        return [f"OpenClaw 错误: {result['error']}"]

    if decisions:
        results = execute_ai_decisions(decisions, mode="auto")
        results.insert(0, f"[OpenClaw] {result.get('analysis', '')}")
        return results

    return [f"[OpenClaw] AI 分析完毕，暂无操作。{result.get('analysis', '')}"]


def _create_openclaw_client(api_key: str):
    """
    兼容不同版本 SDK 的客户端创建入口。
    """
    try:
        import openclaw

        client_cls = (
            getattr(openclaw, "OpenClawClient", None)
            or getattr(openclaw, "Client", None)
            or getattr(openclaw, "OpenClaw", None)
        )
        if client_cls is not None:
            remote_factory = getattr(client_cls, "remote", None)
            if callable(remote_factory):
                return remote_factory(api_key=api_key)
            return client_cls(api_key=api_key)
    except Exception as exc:
        _log.warning("openclaw import fallback to cmdop: %s", exc)

    try:
        from cmdop import CMDOPClient

        return CMDOPClient.remote(api_key=api_key)
    except Exception as exc:
        raise RuntimeError(f"openclaw/cmdop client init failed: {exc}") from exc


def _run_openclaw_prompt(client: Any, prompt: str, *, model: str) -> str:
    """
    同时兼容 agent 风格与 responses 风格 API。
    """
    agents = getattr(client, "agents", None)
    if agents and hasattr(agents, "create"):
        agent = agents.create(
            name="QuantTrader_Auto",
            model=model or DEFAULT_OPENCLAW_MODEL,
            tools=["calculator", "python_interpreter"],
        )
        for call_name in ("message", "run", "chat"):
            call = getattr(agent, call_name, None)
            if callable(call):
                return _extract_response_text(call(prompt))

    responses = getattr(client, "responses", None)
    if responses and hasattr(responses, "create"):
        response = responses.create(model=model or DEFAULT_OPENCLAW_MODEL, input=prompt)
        return _extract_response_text(response)

    for call_name in ("message", "run", "chat"):
        call = getattr(client, call_name, None)
        if callable(call):
            return _extract_response_text(call(prompt))

    raise RuntimeError("未识别到可用的 OpenClaw 调用方法")


def _extract_response_text(response: Any) -> str:
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        if isinstance(response.get("content"), str):
            return response["content"]
        if isinstance(response.get("output_text"), str):
            return response["output_text"]
    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str):
        return output_text
    return str(response)


def _parse_openclaw_reply(reply: str) -> dict:
    try:
        parsed = json.loads(reply)
        if isinstance(parsed, dict):
            parsed.setdefault("decisions", [])
            parsed.setdefault("analysis", "")
            return parsed
    except Exception:
        pass

    start = reply.find("{")
    end = reply.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            parsed = json.loads(reply[start:end])
            if isinstance(parsed, dict):
                parsed.setdefault("decisions", [])
                parsed.setdefault("analysis", "")
                return parsed
        except Exception:
            pass
    return {"analysis": reply, "decisions": []}
