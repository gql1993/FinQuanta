"""
OpenClaw 集成 - AI 自主交易代理
使用 OpenClaw SDK 创建一个自主量化交易 Agent，定时跑策略并自动执行买卖。
"""
import os
import json
import sqlite3
import logging
from datetime import datetime

_log = logging.getLogger("openclaw_agent")

DB_PATH = os.path.join("data_cache", "quant.db")
OPENCLAW_CONFIG_KEY = "openclaw_config"


def save_openclaw_config(api_key: str):
    """保存 OpenClaw API Key。"""
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.execute(
        "INSERT OR REPLACE INTO kv_store VALUES (?,?,?)",
        (OPENCLAW_CONFIG_KEY, json.dumps({"api_key": api_key}), datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_openclaw_config() -> dict:
    api_key = os.environ.get("OPENCLAW_API_KEY", "").strip()
    if not api_key:
        try:
            conn = sqlite3.connect(DB_PATH, timeout=5)
            cur = conn.execute("SELECT value FROM kv_store WHERE key=?", (OPENCLAW_CONFIG_KEY,))
            row = cur.fetchone()
            conn.close()
            if row:
                cfg = json.loads(row[0])
                api_key = cfg.get("api_key", "")
        except Exception:
            pass
    return {"api_key": api_key}


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
        from openclaw import OpenClawClient

        client = OpenClawClient(api_key=cfg["api_key"])

        # 创建量化交易 Agent
        agent = client.agents.create(
            name="QuantTrader_Auto",
            model="claude-3-5-sonnet",
            tools=["calculator", "python_interpreter"],
        )

        prompt = _build_trading_prompt(board)

        # 发送消息并获取回复
        response = agent.message(prompt)
        reply = response.content if hasattr(response, "content") else str(response)

        _log.info(f"openclaw response: {reply[:200]}")

        # 解析 JSON
        try:
            start = reply.find("{")
            end = reply.rfind("}") + 1
            if start >= 0 and end > start:
                result = json.loads(reply[start:end])
            else:
                result = {"analysis": reply, "decisions": []}
        except json.JSONDecodeError:
            result = {"analysis": reply, "decisions": []}

        result["source"] = "openclaw"
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
