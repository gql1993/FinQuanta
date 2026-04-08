from __future__ import annotations

import secrets
from datetime import datetime

from api_server.storage import repo
from desktop.ai_trader import _call_llm
from desktop.openclaw_learner import get_strategy_weights
from desktop.snapshot_service import get_system_snapshot
from desktop.task_orchestrator import get_recent_system_events, get_recent_task_runs
from desktop.trend_verify import get_accuracy_stats, get_records


def ensure_assistant_tables():
    repo.executescript(
        """
        CREATE TABLE IF NOT EXISTS ai_chat_history (
            id TEXT PRIMARY KEY,
            session_id TEXT,
            role TEXT,
            content TEXT,
            created_at TEXT
        );
        """
    )


def save_chat_msg(session_id: str, role: str, content: str):
    ensure_assistant_tables()
    msg_id = secrets.token_hex(8)
    created_at = datetime.now().isoformat()
    try:
        repo.execute(
            "INSERT INTO ai_chat_history (id, session_id, role, content, created_at) VALUES (?,?,?,?,?)",
            (msg_id, session_id, role, content, created_at),
        )
    except Exception:
        # 兼容历史 SQLite 结构：旧表的 id 为 INTEGER AUTOINCREMENT
        repo.execute(
            "INSERT INTO ai_chat_history (session_id, role, content, created_at) VALUES (?,?,?,?)",
            (session_id, role, content, created_at),
        )


def get_sessions(limit: int = 30) -> list[dict]:
    ensure_assistant_tables()
    rows = repo.fetchall(
        """
        SELECT session_id, MIN(created_at), MAX(created_at), COUNT(*)
        FROM ai_chat_history
        GROUP BY session_id
        ORDER BY MAX(created_at) DESC
        LIMIT ?
        """,
        (limit,),
    )
    items = []
    for r in rows:
        first_user = repo.fetchone(
            "SELECT content FROM ai_chat_history WHERE session_id=? AND role='user' ORDER BY created_at, id LIMIT 1",
            (r[0],),
        )
        items.append(
            {
                "session_id": r[0],
                "first_time": r[1],
                "last_time": r[2],
                "msg_count": r[3],
                "first_question": ((first_user[0] if first_user else "") or "")[:40],
            }
        )
    return items


def get_session_messages(session_id: str, limit: int = 100) -> list[dict]:
    ensure_assistant_tables()
    rows = repo.fetchall(
        """
        SELECT role, content, created_at
        FROM ai_chat_history
        WHERE session_id=?
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (session_id, limit),
    )
    rows = list(reversed(rows))
    return [{"role": r[0], "content": r[1], "time": r[2]} for r in rows]


def build_assistant_context_payload() -> dict:
    snap = get_system_snapshot()
    last_scan = repo.kv_get("last_scan_results", []) or []
    manual = snap.get("manual_portfolio", {})
    totals = snap.get("totals", {})
    ai_portfolios = snap.get("ai_portfolios", {})
    risk = snap.get("risk", {})
    market = snap.get("market_state", {})
    verify = get_accuracy_stats()
    recent_verify = get_records(limit=8)
    weights = get_strategy_weights()
    events = get_recent_system_events(8)
    tasks = get_recent_task_runs(8)

    top_scan = []
    for item in last_scan[:10]:
        top_scan.append(
            {
                "code": item.get("代码", ""),
                "name": item.get("名称", ""),
                "board": item.get("板块", ""),
                "score": item.get("评分", ""),
                "advice": item.get("建议买入", ""),
            }
        )

    concise_weights = {
        k: {
            "weight": round(v.get("weight", 0), 3),
            "accuracy": round(v.get("accuracy", 0), 2),
            "avg_pnl_5d": round(v.get("avg_pnl_5d", 0), 2),
        }
        for k, v in weights.items()
    }

    text_parts = [
        "【系统总览】",
        f"总资产: {totals.get('equity', 0):,.0f}",
        f"总现金: {totals.get('cash', 0):,.0f}",
        f"总持仓数: {totals.get('positions', 0)}",
        f"手动仓收益率: {manual.get('return_pct', 0):+.2f}%",
        f"市场状态: {market.get('state', 'neutral')} {market.get('reason', '')}",
        f"风险VaR95: {risk.get('var95', 0)}",
        "",
        "【AI仓概况】",
    ]
    for mode in ["full_auto", "auto", "custom", "quantum"]:
        c = ai_portfolios.get(mode, {})
        text_parts.append(
            f"{mode}: equity={c.get('equity', 0):,.0f}, return={c.get('return_pct', 0):+.2f}%, trades={c.get('total_trades', 0)}"
        )
    text_parts.extend(
        [
            "",
            "【最近扫描Top10】",
        ]
    )
    for item in top_scan:
        text_parts.append(
            f"{item['code']} {item['name']} 板块={item['board']} 评分={item['score']} 建议={item['advice']}"
        )
    text_parts.extend(
        [
            "",
            "【走势验证概况】",
            f"总信号={verify.get('total', 0)} 准确率={verify.get('accuracy', 0):.1f}% 1日均涨={verify.get('avg_pnl_1d', 0):+.2f}% 5日均涨={verify.get('avg_pnl_5d', 0):+.2f}%",
            "",
            "【最近任务】",
        ]
    )
    for task in tasks[:5]:
        text_parts.append(
            f"{task.get('timestamp', '')[:16]} {task.get('task_name', '')} {task.get('status', '')} {task.get('summary', '')}"
        )
    text_parts.extend(
        [
            "",
            "【最近系统事件】",
        ]
    )
    for event in events[:5]:
        text_parts.append(
            f"{event.get('timestamp', '')[:16]} {event.get('title', '')} {event.get('detail', '')[:80]}"
        )

    return {
        "snapshot": {
            "totals": totals,
            "manual": manual,
            "market_state": market,
            "risk": risk,
            "ai_portfolios": ai_portfolios,
        },
        "scan_top10": top_scan,
        "verify_summary": verify,
        "verify_recent": recent_verify,
        "strategy_weights": concise_weights,
        "tasks": tasks,
        "events": events,
        "context_text": "\n".join(text_parts),
    }


def ask_assistant(prompt: str, session_id: str) -> dict:
    ensure_assistant_tables()
    context = build_assistant_context_payload()
    system = (
        "你是 FinQuanta 量化交易平台的 AI 助手。"
        "你必须优先基于系统上下文回答，结合市场状态、持仓、选股、走势验证、策略权重做辅助分析。"
        "如果数据不足，要明确指出，不要编造。"
        "\n\n"
        f"{context['context_text']}"
    )
    save_chat_msg(session_id, "user", prompt)
    answer = _call_llm(prompt, system=system)
    save_chat_msg(session_id, "assistant", answer)
    return {
        "session_id": session_id,
        "reply": answer,
        "context_excerpt": context["context_text"][:1200],
    }
