"""
Shared AI context builder.

This module centralizes the common context assembly used by assistant,
AI portfolio decisions, and OpenClaw fallback decisions.

The public API is intentionally split into:
1. structured builders returning dict/list payloads
2. text renderers built on top of those payloads
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np

from core.application.openclaw_service import get_openclaw_strategy_weights
from core.application.ops_service import (
    get_recent_system_events,
    get_recent_task_runs,
)
from core.application.snapshot_service import get_system_snapshot
from core.application.verify_service import (
    get_verify_accuracy_stats,
    get_verify_records,
)
from desktop.ai_portfolio import get_state
from desktop.data_access import RepoCompatConnection, get_kv_json


def build_snapshot_context(refresh: bool = False) -> dict[str, Any]:
    """Return the shared system snapshot context."""
    snapshot = get_system_snapshot(refresh=refresh)
    return {
        "snapshot": snapshot,
        "totals": snapshot.get("totals", {}),
        "manual": snapshot.get("manual_portfolio", {}),
        "manual_raw": snapshot.get("manual_portfolio_raw", {}),
        "market_state": snapshot.get("market_state", {}),
        "risk": snapshot.get("risk", {}),
        "ai_portfolios": snapshot.get("ai_portfolios", {}),
        "ai_states": snapshot.get("ai_states", {}),
    }


def build_market_context(
    universe_limit: int = 100,
    top_gainers_limit: int = 10,
    top_losers_limit: int = 5,
) -> dict[str, Any]:
    """Return structured market context for AI features."""
    conn = RepoCompatConnection()

    try:
        from desktop.market_state import get_market_state_snapshot

        market_state = get_market_state_snapshot()
    except Exception:
        market_state = {}

    cursor = conn.execute(
        """
        SELECT code,
               (SELECT close FROM daily_kline d2 WHERE d2.code=d1.code ORDER BY date DESC LIMIT 1) as last_close,
               (SELECT close FROM daily_kline d3 WHERE d3.code=d1.code ORDER BY date DESC LIMIT 1 OFFSET 1) as prev_close
        FROM (SELECT DISTINCT code FROM daily_kline) d1
        LIMIT ?
        """,
        (universe_limit,),
    )
    movers = []
    for row in cursor.fetchall():
        code, last, prev = row
        if last and prev and prev > 0:
            movers.append(
                {
                    "code": code,
                    "price": float(last),
                    "pct": (last - prev) / prev * 100,
                }
            )

    conn.close()
    movers.sort(key=lambda item: item["pct"], reverse=True)

    return {
        "market_state": market_state,
        "top_gainers": movers[:top_gainers_limit],
        "top_losers": movers[-top_losers_limit:],
    }


def _compute_strategy_scores_for_context(code: str, closes, highs, lows, volumes) -> dict:
    """Context-friendly copy of the local strategy scoring logic."""
    n = len(closes)
    if n < 50:
        return {"score": 0, "signals": [], "strategies": {}}

    price = float(closes[-1])
    ma50 = float(np.mean(closes[-50:]))
    ma150 = float(np.mean(closes[-150:])) if n >= 150 else ma50
    ma200 = float(np.mean(closes[-200:])) if n >= 200 else ma150

    results = {}

    sepa_score = 0
    sepa_signals = []
    if price > ma50:
        sepa_score += 15
    if n >= 200 and ma50 > ma150 > ma200:
        sepa_score += 20
        sepa_signals.append("多头排列")
    if n >= 200:
        ma200_prev = float(np.mean(closes[-222:-22])) if n >= 222 else ma200
        if ma200 > ma200_prev:
            sepa_score += 10
    high_52w = float(np.max(highs[-250:])) if n >= 250 else float(np.max(highs))
    if high_52w > 0 and price >= high_52w * 0.75:
        sepa_score += 10
    results["SEPA趋势"] = {
        "score": sepa_score,
        "signals": sepa_signals,
        "view": "看多" if sepa_score >= 40 else "中性" if sepa_score >= 20 else "看空",
    }

    vcp_score = 0
    vcp_signals = []
    if n >= 40:
        vol_early = float(
            np.std(closes[-40:-20]) / max(np.mean(closes[-40:-20]), 1e-6)
        )
        vol_recent = float(np.std(closes[-20:]) / max(np.mean(closes[-20:]), 1e-6))
        if vol_recent < vol_early * 0.8:
            vcp_score += 25
            vcp_signals.append("波动收缩")
    if n >= 20:
        high20 = float(np.max(closes[-21:-1]))
        if price >= high20:
            vcp_score += 30
            vcp_signals.append("突破20日高点")
        elif price >= high20 * 0.98:
            vcp_score += 15
            vcp_signals.append("接近突破")
    results["VCP形态"] = {
        "score": vcp_score,
        "signals": vcp_signals,
        "view": "突破" if vcp_score >= 40 else "收缩" if vcp_score >= 20 else "无形态",
    }

    value_score = 0
    value_signals = []
    if price < ma200 * 0.9:
        value_score += 30
        value_signals.append("低于MA200的90%")
    momentum60 = (price / float(closes[-61]) - 1) if n >= 61 and closes[-61] > 0 else 0
    if momentum60 < -0.15:
        value_score += 20
        value_signals.append(f"60日跌{momentum60*100:.0f}%超跌")
    results["价值评估"] = {
        "score": value_score,
        "signals": value_signals,
        "view": "低估" if value_score >= 30 else "合理",
    }

    momentum_score = 0
    momentum_signals = []
    momentum5 = (price / float(closes[-6]) - 1) * 100 if n >= 6 and closes[-6] > 0 else 0
    momentum20 = (
        (price / float(closes[-21]) - 1) * 100 if n >= 21 and closes[-21] > 0 else 0
    )
    if momentum5 > 5:
        momentum_score += 20
        momentum_signals.append(f"5日涨{momentum5:.1f}%")
    if momentum20 > 10:
        momentum_score += 20
        momentum_signals.append(f"20日涨{momentum20:.1f}%")
    results["动量"] = {
        "score": momentum_score,
        "signals": momentum_signals,
        "view": "强势" if momentum_score >= 30 else "中性" if momentum_score >= 10 else "弱势",
    }

    emotion_score = 0
    emotion_signals = []
    if n >= 20:
        vol_ma20 = float(np.mean(volumes[-20:])) if np.mean(volumes[-20:]) > 0 else 1
        vol_ratio = float(volumes[-1]) / vol_ma20
        if vol_ratio > 1.5 and momentum5 > 3:
            emotion_score += 25
            emotion_signals.append(f"放量{vol_ratio:.1f}倍+短期强势")
        elif vol_ratio > 1.2:
            emotion_score += 10
            emotion_signals.append(f"量比{vol_ratio:.1f}")
        if n >= 2 and closes[-2] > 0:
            day_pct = (closes[-1] - closes[-2]) / closes[-2] * 100
            if day_pct >= 9.5:
                emotion_score += 20
                emotion_signals.append("涨停")
    results["情绪博弈"] = {
        "score": emotion_score,
        "signals": emotion_signals,
        "view": "高潮" if emotion_score >= 30 else "活跃" if emotion_score >= 10 else "平淡",
    }

    event_score = 0
    event_signals = []
    if n >= 2:
        day_pct = (closes[-1] - closes[-2]) / closes[-2] * 100 if closes[-2] > 0 else 0
        vol_ma20 = (
            float(np.mean(volumes[-20:])) if n >= 20 and np.mean(volumes[-20:]) > 0 else 1
        )
        vol_ratio = float(volumes[-1]) / vol_ma20 if vol_ma20 > 0 else 1
        if abs(day_pct) > 5 and vol_ratio > 2:
            event_score += 30
            event_signals.append(f"异动{day_pct:+.1f}%+放量{vol_ratio:.1f}倍")
        elif abs(day_pct) > 3 and vol_ratio > 1.5:
            event_score += 15
            event_signals.append(f"小异动{day_pct:+.1f}%")
    results["事件驱动"] = {
        "score": event_score,
        "signals": event_signals,
        "view": "有事件" if event_score >= 15 else "无事件",
    }

    fund_score = 0
    fund_signals = []
    try:
        conn = RepoCompatConnection()
        row = conn.execute(
            "SELECT holding_funds, change_type FROM fund_holdings WHERE code=? ORDER BY updated_at DESC LIMIT 1",
            (code,),
        ).fetchone()
        conn.close()
        if row:
            holding_funds, change_type = row
            if holding_funds and int(holding_funds) >= 100:
                fund_score += 15
                fund_signals.append(f"{holding_funds}只基金持有")
            if holding_funds and int(holding_funds) >= 500:
                fund_score += 15
                fund_signals.append("超500只基金重仓")
            if change_type == "增持":
                fund_score += 20
                fund_signals.append("基金增持")
            elif change_type == "新进":
                fund_score += 25
                fund_signals.append("基金新进")
            elif change_type == "减持":
                fund_score -= 10
                fund_signals.append("基金减持")
    except Exception:
        pass
    results["基金持仓"] = {
        "score": max(fund_score, 0),
        "signals": fund_signals,
        "view": "重仓" if fund_score >= 30 else "持有" if fund_score > 0 else "无持仓",
    }

    total_score = sum(result["score"] for result in results.values())
    all_signals = []
    for result in results.values():
        all_signals.extend(result["signals"])

    return {"score": total_score, "signals": all_signals, "strategies": results}


def build_portfolio_context(mode: str = "auto") -> dict[str, Any]:
    """Return structured portfolio context for a given AI mode."""
    state = get_state(mode)
    label_map = {
        "auto": "AI自主仓",
        "full_auto": "完全自主仓",
        "manual": "AI推荐仓",
        "custom": "自定义仓",
        "quantum": "量子仓",
    }
    positions = []
    conn = RepoCompatConnection()
    for position in state["positions"]:
        code = position["code"]
        rows_db = conn.execute(
            "SELECT close, high, low, volume FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 260",
            (code,),
        ).fetchall()
        if rows_db:
            rows_db = rows_db[::-1]
            closes = np.array([row[0] for row in rows_db])
            highs = np.array([row[1] for row in rows_db])
            lows = np.array([row[2] for row in rows_db])
            volumes = np.array([row[3] for row in rows_db])
            current_price = float(closes[-1])
            scores = _compute_strategy_scores_for_context(
                code, closes, highs, lows, volumes
            )
            strategy_views = " ".join(
                f"{name}:{strategy['view']}"
                for name, strategy in scores["strategies"].items()
                if strategy["score"] > 0
            )
        else:
            current_price = position["entry_price"]
            scores = {"score": 0, "strategies": {}}
            strategy_views = "无数据"

        pnl_pct = (
            (current_price - position["entry_price"]) / position["entry_price"] * 100
            if position["entry_price"]
            else 0
        )
        positions.append(
            {
                "code": code,
                "name": position["name"],
                "entry_price": position["entry_price"],
                "current_price": current_price,
                "pnl_pct": pnl_pct,
                "shares": position["shares"],
                "entry_date": position["entry_date"],
                "strategy_score": scores["score"],
                "strategy_views": strategy_views,
                "strategies": scores.get("strategies", {}),
            }
        )

    conn.close()

    return {
        "mode": mode,
        "label": label_map.get(mode, mode),
        "cash": state["cash"],
        "initial_capital": state["initial_capital"],
        "position_count": len(state["positions"]),
        "positions": positions,
        "recent_trades": state["closed_trades"][:5],
    }


def build_decision_history_context(limit: int = 5) -> dict[str, Any]:
    """Return structured calibrated AI decision history feedback."""
    try:
        conn = RepoCompatConnection()
        rows = conn.execute(
            "SELECT timestamp, decisions, actual_results, verification_summary, guardrail_summary "
            "FROM ai_decision_memory WHERE calibrated=1 "
            "ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        if not rows:
            return {"items": [], "summary_text": ""}

        items = []
        for ts, decisions_json, results_json, verification_json, guardrail_json in rows:
            try:
                decisions = json.loads(decisions_json) if decisions_json else []
                results = json.loads(results_json) if results_json else {}
                verification = json.loads(verification_json) if verification_json else {}
                guardrails = json.loads(guardrail_json) if guardrail_json else {}
                pnl = results.get("avg_pnl", 0)
                correct = results.get("correct_ratio", 0)
                count = len(decisions) if isinstance(decisions, list) else 0
                items.append(
                    {
                        "timestamp": ts,
                        "decision_count": count,
                        "correct_ratio": correct,
                        "avg_pnl": pnl,
                        "verified_count": verification.get("verified_count", 0),
                        "blocked_buy_count": guardrails.get("blocked_buy_count", 0),
                    }
                )
            except Exception:
                pass
        return {
            "items": items,
            "summary_text": (
                "请参考历史表现，避免重复犯错，强化有效模式。" if items else ""
            ),
        }
    except Exception:
        return {"items": [], "summary_text": ""}


def build_scan_context(limit: int = 10) -> dict[str, Any]:
    """Return structured latest scan context."""
    last_scan = get_kv_json("last_scan_results", []) or []
    top_scan = []
    for item in last_scan[:limit]:
        top_scan.append(
            {
                "code": item.get("代码", ""),
                "name": item.get("名称", ""),
                "board": item.get("板块", ""),
                "score": item.get("评分", ""),
                "advice": item.get("建议买入", ""),
            }
        )
    return {"items": top_scan}


def build_ops_context(
    task_limit: int = 8,
    event_limit: int = 8,
) -> dict[str, Any]:
    """Return structured task/event context."""
    return {
        "tasks": get_recent_task_runs(task_limit),
        "events": get_recent_system_events(event_limit),
    }


def build_verify_context(limit: int = 8) -> dict[str, Any]:
    """Return structured verification context."""
    return {
        "summary": get_verify_accuracy_stats(),
        "recent": get_verify_records(limit=limit),
    }


def build_strategy_weights_context(top_limit: int | None = None) -> dict[str, Any]:
    """Return structured strategy weight context."""
    weights = get_openclaw_strategy_weights()
    concise_weights = {
        key: {
            "weight": round(value.get("weight", 0), 3),
            "accuracy": round(value.get("accuracy", 0), 2),
            "avg_pnl_5d": round(value.get("avg_pnl_5d", 0), 2),
        }
        for key, value in weights.items()
    }
    top_items = sorted(
        concise_weights.items(),
        key=lambda item: item[1].get("weight", 0),
        reverse=True,
    )
    if top_limit is not None:
        top_items = top_items[:top_limit]
    return {
        "items": concise_weights,
        "top_items": [
            {"name": name, **meta}
            for name, meta in top_items
        ],
    }


def build_rotation_context() -> dict[str, Any]:
    """Return structured strategy/sector rotation context."""
    context = {
        "strategy_rotation": {},
        "sector_rotation": {},
    }
    try:
        conn = RepoCompatConnection()
        strategy_row = conn.execute(
            "SELECT value FROM kv_store WHERE key='strategy_rotation'"
        ).fetchone()
        if strategy_row:
            context["strategy_rotation"] = json.loads(strategy_row[0])
        sector_row = conn.execute(
            "SELECT value FROM kv_store WHERE key='sector_rotation'"
        ).fetchone()
        if sector_row:
            context["sector_rotation"] = json.loads(sector_row[0])
        conn.close()
    except Exception:
        pass
    return context


def build_learning_feedback_context() -> dict[str, Any]:
    """Return structured learning/evolution feedback context."""
    enhanced_prompt = ""
    try:
        from desktop.openclaw_learner import get_enhanced_full_auto_prompt

        enhanced_prompt = get_enhanced_full_auto_prompt()
    except Exception:
        enhanced_prompt = ""
    return {"enhanced_prompt": enhanced_prompt}


def build_candidates_context(board: str = "人工智能", limit: int = 30) -> dict[str, Any]:
    """Return structured candidate-stock context for AI decisions."""
    conn = RepoCompatConnection()
    conn.execute("PRAGMA journal_mode=WAL")

    boards = [item.strip() for item in board.split(",") if item.strip()]
    if not boards:
        conn.close()
        return {
            "boards": [],
            "board_summary": "",
            "candidate_count": 0,
            "strong_candidate_count": 0,
            "scan_candidate_count": 0,
            "items": [],
            "warning": "未指定有效板块，无法生成候选列表",
        }

    names = {}
    try:
        cursor = conn.execute("SELECT code, name FROM stock_list")
        names = {row[0]: row[1] for row in cursor.fetchall()}
    except Exception:
        pass

    scan_candidates = []
    try:
        row_scan = conn.execute(
            "SELECT value, updated_at FROM kv_store WHERE key='last_scan_results'"
        ).fetchone()
        if row_scan:
            scan_items = json.loads(row_scan[0])
            for item in scan_items[:50]:
                code = item.get("代码", "")
                if not code:
                    continue
                score = int(item.get("评分", 0))
                signals = []
                if item.get("VCP") == "✓":
                    signals.append("VCP收缩")
                if item.get("突破") == "✓":
                    signals.append("突破")
                if item.get("建议买入", ""):
                    signals.append(item["建议买入"])
                scan_candidates.append(
                    {
                        "code": code,
                        "name": item.get("名称", names.get(code, "")),
                        "price": float(item.get("价格", "0").replace(",", "") or 0),
                        "pct": 0,
                        "scores": {"score": score, "signals": signals, "strategies": {}},
                        "board": item.get("板块", "雷达精选"),
                    }
                )
    except Exception:
        pass

    seen = set()
    candidates = []
    board_tops = {}

    for board_name in boards:
        codes_in_board = [
            row[0]
            for row in conn.execute(
                "SELECT code FROM board_stocks WHERE board=?", (board_name,)
            ).fetchall()
        ]
        board_candidates = []

        for code in codes_in_board[:80]:
            if code in seen:
                continue
            rows = conn.execute(
                "SELECT close, high, low, volume FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 260",
                (code,),
            ).fetchall()
            if len(rows) < 50:
                continue
            rows = rows[::-1]
            closes = np.array([row[0] for row in rows])
            highs = np.array([row[1] for row in rows])
            lows = np.array([row[2] for row in rows])
            volumes = np.array([row[3] for row in rows])
            scores = _compute_strategy_scores_for_context(
                code, closes, highs, lows, volumes
            )
            price = float(closes[-1])
            prev = float(closes[-2]) if len(closes) >= 2 else price
            pct = (price - prev) / prev * 100 if prev > 0 else 0
            board_candidates.append(
                {
                    "code": code,
                    "name": names.get(code, ""),
                    "price": price,
                    "pct": pct,
                    "scores": scores,
                    "board": board_name,
                }
            )

        board_candidates.sort(key=lambda item: item["scores"]["score"], reverse=True)
        top_items = board_candidates[:10]
        board_tops[board_name] = len(top_items)
        for item in top_items:
            seen.add(item["code"])
            candidates.append(item)

    conn.close()

    for item in scan_candidates:
        if item["code"] not in seen:
            seen.add(item["code"])
            candidates.append(item)

    candidates.sort(key=lambda item: item["scores"]["score"], reverse=True)
    visible_items = []
    for item in candidates[:limit]:
        score = item["scores"]["score"]
        if score >= 80:
            advice = "★★★ 强烈买入"
        elif score >= 60:
            advice = "★★ 建议买入"
        elif score >= 40:
            advice = "★ 观望"
        else:
            advice = "- 不买"
        visible_items.append(
            {
                **item,
                "strategy_views": " ".join(
                    f"{name}:{strategy['view']}"
                    for name, strategy in item["scores"]["strategies"].items()
                    if strategy["score"] > 0
                ),
                "signal_text": ",".join(item["scores"]["signals"][:5])
                if item["scores"]["signals"]
                else "无",
                "advice": advice,
            }
        )

    board_summary = ", ".join(
        f"{board_name}({count}只)" for board_name, count in board_tops.items()
    )
    if scan_candidates:
        board_summary += f", 雷达精选({len(scan_candidates)}只)"

    return {
        "boards": boards,
        "board_summary": board_summary,
        "candidate_count": len(candidates),
        "strong_candidate_count": sum(
            1 for item in candidates if item["scores"]["score"] >= 60
        ),
        "scan_candidate_count": len(scan_candidates),
        "items": visible_items,
        "warning": "",
    }


def build_market_context_text() -> str:
    """Render a shared market snapshot text block."""
    context = build_market_context()
    market_state = context.get("market_state", {})
    lines = ["== 市场状态机 =="]
    lines.append(f"状态: {market_state.get('state', 'neutral')}")
    lines.append(f"原因: {market_state.get('reason', '')}")
    if market_state.get("sector_top3"):
        lines.append(f"强势板块: {', '.join(market_state['sector_top3'][:3])}")
    if market_state.get("sector_bottom3"):
        lines.append(f"弱势板块: {', '.join(market_state['sector_bottom3'][:3])}")
    lines.append("")
    lines.append("== 市场快照 ==")
    lines.append("涨幅前10:")
    for item in context.get("top_gainers", []):
        lines.append(f"  {item['code']} ¥{item['price']:.2f} {item['pct']:+.2f}%")
    lines.append("跌幅前5:")
    for item in context.get("top_losers", []):
        lines.append(f"  {item['code']} ¥{item['price']:.2f} {item['pct']:+.2f}%")
    return "\n".join(lines)


def build_ai_portfolio_context_text(mode: str = "auto") -> str:
    """Render the detailed AI portfolio decision context."""
    context = build_portfolio_context(mode)
    lines = [
        f"== {context['label']} ==",
        f"现金: ¥{context['cash']:,.2f}",
        f"初始资金: ¥{context['initial_capital']:,.0f}",
        f"持仓数: {context['position_count']}",
    ]
    for position in context.get("positions", []):
        lines.append(
            f"  {position['code']} {position['name']} 买{position['entry_price']:.2f} "
            f"现{position['current_price']:.2f} 盈亏{position['pnl_pct']:+.2f}% "
            f"{position['shares']}股 {position['entry_date']} | "
            f"策略评分{position['strategy_score']} {position['strategy_views']}"
        )
    if context.get("recent_trades"):
        lines.append("最近交易:")
        for trade in context["recent_trades"]:
            lines.append(
                f"  {trade['code']} {trade['entry_date']}→{trade['exit_date']} "
                f"盈亏¥{trade['pnl']:+,.0f} {trade['reason']}"
            )
    return "\n".join(lines)


def build_candidates_context_text(board: str = "人工智能", limit: int = 30) -> str:
    """Render candidate-stock context text for AI decisions."""
    context = build_candidates_context(board=board, limit=limit)
    if context.get("warning"):
        return f"== 候选股票 ==\n⚠️ {context['warning']}"

    lines = [
        f"== 候选股票（各板块Top10精选，共{context['candidate_count']}只，≥60分:{context['strong_candidate_count']}只）==",
        f"板块来源: {context['board_summary']}",
        "格式: 代码 名称 [板块] 现价 日涨跌% | 综合评分 | 策略判定 | 信号 | 建议",
    ]
    for item in context.get("items", []):
        lines.append(
            f"  {item['code']} {item['name']} [{item['board']}] ¥{item['price']:.2f} {item['pct']:+.2f}% | "
            f"综合{item['scores']['score']}分 | {item['strategy_views']} | {item['signal_text']} | {item['advice']}"
        )

    if context["strong_candidate_count"] > 3:
        lines.append(
            f"\n⚠️ 当前有 {context['strong_candidate_count']} 只达到买入标准（≥60分），建议积极布局多只，分散在不同板块。"
        )
    elif context["strong_candidate_count"] > 0:
        lines.append(
            f"\n📌 {context['strong_candidate_count']} 只达到买入标准，可精选买入。"
        )

    return "\n".join(lines)


def build_decision_history_context_text(limit: int = 5) -> str:
    """Render calibrated AI decision history feedback."""
    context = build_decision_history_context(limit)
    items = context.get("items", [])
    if not items:
        return ""
    lines = ["== 历史决策回顾（近5次已校准） =="]
    for item in items:
        lines.append(
            f"  {item['timestamp'][:10]}: {item['decision_count']}条决策, "
            f"准确率{item['correct_ratio']:.0%}, 均收益{item['avg_pnl']:+.1f}%"
        )
    if context.get("summary_text"):
        lines.append(context["summary_text"])
    return "\n".join(lines)


def build_rotation_context_text() -> str:
    """Render strategy/sector rotation context."""
    context = build_rotation_context()
    rotation_text = ""
    strategy_rotation = context.get("strategy_rotation", {})
    if strategy_rotation:
        rotation_text += (
            "\n== 策略轮动 ==\n"
            f"当前最强策略: {strategy_rotation.get('best_name', 'SEPA')}"
            f"(综合分{strategy_rotation.get('best_score', 0):.0f})\n"
        )
    sector_rotation = context.get("sector_rotation", {})
    top3 = sector_rotation.get("top3", [])
    if top3:
        rotation_text += f"最强板块: {', '.join(top3[:3])}，建议重点关注\n"
        bottom3 = sector_rotation.get("bottom3", [])
        if bottom3:
            rotation_text += f"最弱板块: {', '.join(bottom3[:3])}，建议回避\n"
    return rotation_text


def build_learning_feedback_context_text() -> str:
    """Render learning/evolution feedback context."""
    return build_learning_feedback_context().get("enhanced_prompt", "")


def build_assistant_context_payload(
    scan_limit: int = 10,
    task_limit: int = 8,
    event_limit: int = 8,
    verify_limit: int = 8,
) -> dict:
    """Build the normalized assistant context payload."""
    snapshot_context = build_snapshot_context()
    scan_context = build_scan_context(scan_limit)
    verify_context = build_verify_context(verify_limit)
    ops_context = build_ops_context(task_limit=task_limit, event_limit=event_limit)
    weights_context = build_strategy_weights_context()

    totals = snapshot_context["totals"]
    manual = snapshot_context["manual"]
    market = snapshot_context["market_state"]
    risk = snapshot_context["risk"]
    ai_portfolios = snapshot_context["ai_portfolios"]
    top_scan = scan_context["items"]
    verify = verify_context["summary"]
    recent_verify = verify_context["recent"]
    tasks = ops_context["tasks"]
    events = ops_context["events"]

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
        portfolio = ai_portfolios.get(mode, {})
        text_parts.append(
            f"{mode}: equity={portfolio.get('equity', 0):,.0f}, return={portfolio.get('return_pct', 0):+.2f}%, trades={portfolio.get('total_trades', 0)}"
        )
    text_parts.extend(["", "【最近扫描Top10】"])
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
    text_parts.extend(["", "【最近系统事件】"])
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
        "snapshot_context": snapshot_context,
        "market_context": build_market_context(),
        "scan_top10": top_scan,
        "scan_context": scan_context,
        "verify_summary": verify,
        "verify_recent": recent_verify,
        "verify_context": verify_context,
        "strategy_weights": weights_context["items"],
        "strategy_weights_context": weights_context,
        "tasks": tasks,
        "events": events,
        "ops_context": ops_context,
        "context_text": "\n".join(text_parts),
    }


def build_openclaw_context(
    boards: list[str] | None = None,
    candidate_count: int = 0,
    news_sentiment: dict | None = None,
    factor_coverage: int = 0,
) -> dict[str, Any]:
    """Return structured OpenClaw fallback context."""
    snapshot_context = build_snapshot_context()
    weights_context = build_strategy_weights_context(top_limit=3)
    return {
        "boards": boards or [],
        "candidate_count": candidate_count,
        "factor_coverage": factor_coverage,
        "news_sentiment": news_sentiment or {},
        "market_state": snapshot_context["market_state"],
        "risk": snapshot_context["risk"],
        "strategy_weights": weights_context["top_items"],
    }


def build_openclaw_context_text(
    boards: list[str] | None = None,
    candidate_count: int = 0,
    news_sentiment: dict | None = None,
    factor_coverage: int = 0,
) -> str:
    """Build a concise OpenClaw-specific context block for fallback decisions."""
    context = build_openclaw_context(
        boards=boards,
        candidate_count=candidate_count,
        news_sentiment=news_sentiment,
        factor_coverage=factor_coverage,
    )
    market = context["market_state"]
    risk = context["risk"]
    sentiment = context["news_sentiment"]
    board_text = ", ".join(context["boards"])
    top_weights = ", ".join(
        f"{item['name']}:{item['weight']:.2f}"
        for item in context["strategy_weights"]
    )
    lines = [
        "== OpenClaw补充上下文 ==",
        f"聚焦板块: {board_text or '未指定'}",
        f"市场状态: {market.get('state', 'neutral')} {market.get('reason', '')}",
        f"候选股票数: {context['candidate_count']}",
        f"因子覆盖数: {context['factor_coverage']}",
        f"风险VaR95: {risk.get('var95', 0)}",
    ]
    if sentiment:
        lines.append(
            f"舆情摘要: 总数{sentiment.get('total', 0)} 正面{sentiment.get('positive', 0)} 负面{sentiment.get('negative', 0)} 正面率{sentiment.get('ratio', 0):.0%}"
        )
    if top_weights:
        lines.append(f"策略权重Top: {top_weights}")
    lines.append("请优先结合以上 OpenClaw 流水线结果做更稳健的交易判断。")
    return "\n".join(lines)
