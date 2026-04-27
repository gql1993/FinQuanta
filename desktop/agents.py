"""
多智能体协同决策系统
四个智能体各司其职，协同完成交易决策：

1. 情报智能体 (Intelligence Agent) — 负责数据采集和整理
2. 分析智能体 (Analysis Agent) — 负责策略分析和评分
3. 验证智能体 (Verification Agent) — 校验候选股是否存在历史失效与高风险模式
4. 决策智能体 (Decision Agent) — 综合前三者的输出做最终交易决策

工作流: 情报 → 分析 → 验证 → 决策 → 执行
"""
import os
import json
import numpy as np
import logging
from datetime import datetime, date
from typing import Callable

from core.ai.decision_memory import (
    calibrate_decisions as calibrate_decisions_core,
    ensure_decision_memory_table,
    get_decision_accuracy as get_decision_accuracy_core,
    save_decision_memory as save_decision_memory_core,
)
from desktop.data_access import RepoCompatConnection, get_kv_json, set_kv_json
from core.observability.tracing import create_trace_id, finish_span, start_span

_log = logging.getLogger("agents")

_COORDINATOR_POLICY_KEY = "openclaw_coordinator_policy"
_COORDINATOR_POLICY_DEFAULTS = {
    "observe_blocked_ratio": 0.7,
    "sell_only_sentiment_ratio": 0.25,
    "limit_buy_sentiment_ratio": 0.35,
    "limit_buy_max_count": 1,
    "learning_min_samples": 3,
}
_UNATTENDED_TRADE_GUARD_KEY = "openclaw_unattended_trade_guard"
_UNATTENDED_TRADE_USAGE_KEY = "openclaw_unattended_trade_usage"
_UNATTENDED_SIMULATION_STATE_KEY = "openclaw_unattended_simulation_state"
_UNATTENDED_TRADE_GUARD_DEFAULTS = {
    "enabled": True,
    "unattended_buy_enabled": False,
    "allow_sell_when_buy_disabled": True,
    "max_daily_buy_amount": 50000.0,
    "max_single_buy_amount": 20000.0,
    "max_daily_buy_count": 3,
    "max_batch_buy_amount": 30000.0,
    "max_batch_buy_count": 2,
    "max_symbol_daily_buy_count": 1,
    "max_sector_daily_buy_amount": 30000.0,
    "max_sector_daily_buy_count": 2,
    "buy_cooldown_minutes": 30,
    "require_simulation_pass": True,
    "simulation_min_success_runs": 3,
    "blacklist": [],
    "whitelist": [],
}


def _clamp_float(value, low: float, high: float, default: float) -> float:
    try:
        return round(max(low, min(high, float(value))), 3)
    except Exception:
        return default


def _clamp_int(value, low: int, high: int, default: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except Exception:
        return default


def reset_unattended_trade_guard_simulation_state(reason: str = "") -> dict:
    payload = {
        "passed": False,
        "consecutive_success_runs": 0,
        "last_status": "reset",
        "last_summary": str(reason or "策略或安全参数变更，需重新完成仿真门禁")[:300],
        "reset_reason": str(reason or "policy_changed")[:300],
        "updated_at": datetime.now().isoformat(),
    }
    set_kv_json(_UNATTENDED_SIMULATION_STATE_KEY, payload)
    return payload


def get_coordinator_policy_config() -> dict:
    """读取协调者策略参数；缺省值保持首版硬编码行为。"""
    raw = get_kv_json(_COORDINATOR_POLICY_KEY, {}) or {}
    if not isinstance(raw, dict):
        raw = {}
    cfg = {**_COORDINATOR_POLICY_DEFAULTS, **raw}
    return {
        "observe_blocked_ratio": _clamp_float(
            cfg.get("observe_blocked_ratio"),
            0.3,
            1.0,
            _COORDINATOR_POLICY_DEFAULTS["observe_blocked_ratio"],
        ),
        "sell_only_sentiment_ratio": _clamp_float(
            cfg.get("sell_only_sentiment_ratio"),
            0.05,
            0.6,
            _COORDINATOR_POLICY_DEFAULTS["sell_only_sentiment_ratio"],
        ),
        "limit_buy_sentiment_ratio": _clamp_float(
            cfg.get("limit_buy_sentiment_ratio"),
            0.1,
            0.8,
            _COORDINATOR_POLICY_DEFAULTS["limit_buy_sentiment_ratio"],
        ),
        "limit_buy_max_count": _clamp_int(
            cfg.get("limit_buy_max_count"),
            1,
            5,
            _COORDINATOR_POLICY_DEFAULTS["limit_buy_max_count"],
        ),
        "learning_min_samples": _clamp_int(
            cfg.get("learning_min_samples"),
            1,
            30,
            _COORDINATOR_POLICY_DEFAULTS["learning_min_samples"],
        ),
        "updated_at": str(cfg.get("updated_at", "") or ""),
        "last_learning_note": str(cfg.get("last_learning_note", "") or ""),
    }


def set_coordinator_policy_config(config: dict) -> dict:
    previous = get_coordinator_policy_config()
    payload = {**previous, **(config or {})}
    payload = {
        **payload,
        "observe_blocked_ratio": _clamp_float(payload.get("observe_blocked_ratio"), 0.3, 1.0, 0.7),
        "sell_only_sentiment_ratio": _clamp_float(payload.get("sell_only_sentiment_ratio"), 0.05, 0.6, 0.25),
        "limit_buy_sentiment_ratio": _clamp_float(payload.get("limit_buy_sentiment_ratio"), 0.1, 0.8, 0.35),
        "limit_buy_max_count": _clamp_int(payload.get("limit_buy_max_count"), 1, 5, 1),
        "learning_min_samples": _clamp_int(payload.get("learning_min_samples"), 1, 30, 3),
        "updated_at": datetime.now().isoformat(),
    }
    set_kv_json(_COORDINATOR_POLICY_KEY, payload)
    watched_keys = {
        "observe_blocked_ratio",
        "sell_only_sentiment_ratio",
        "limit_buy_sentiment_ratio",
        "limit_buy_max_count",
    }
    if any(previous.get(key) != payload.get(key) for key in watched_keys):
        reset_unattended_trade_guard_simulation_state("Coordinator策略变更，需重新完成无人值守买入仿真")
    return payload


def adapt_coordinator_policy_from_learning(ai_perf: dict) -> dict:
    """根据协调者分流后验表现小幅调参，避免一次学习过度摆动。"""
    eff = (ai_perf or {}).get("coordinator_effectiveness", {}) or {}
    cfg = get_coordinator_policy_config()
    routed = int(eff.get("routed_blocked_count", 0) or 0)
    min_samples = int(cfg.get("learning_min_samples", 3) or 3)
    if routed < min_samples:
        return {
            "changed": False,
            "reason": f"分流样本不足({routed}/{min_samples})，暂不调参",
            "config": cfg,
        }

    avoided = int(eff.get("avoided_losses", 0) or 0)
    missed = int(eff.get("missed_gains", 0) or 0)
    avoided_rate = float(eff.get("avoided_loss_rate", 0) or 0)
    next_cfg = dict(cfg)

    if avoided_rate >= 70 and avoided > missed:
        next_cfg["sell_only_sentiment_ratio"] = cfg["sell_only_sentiment_ratio"] + 0.03
        next_cfg["limit_buy_sentiment_ratio"] = cfg["limit_buy_sentiment_ratio"] + 0.03
        next_cfg["limit_buy_max_count"] = max(1, int(cfg["limit_buy_max_count"]) - 1)
        note = "分流避免亏损率较高，略微收紧弱势环境买入"
    elif missed >= avoided or avoided_rate < 40:
        next_cfg["sell_only_sentiment_ratio"] = cfg["sell_only_sentiment_ratio"] - 0.03
        next_cfg["limit_buy_sentiment_ratio"] = cfg["limit_buy_sentiment_ratio"] - 0.03
        next_cfg["limit_buy_max_count"] = min(5, int(cfg["limit_buy_max_count"]) + 1)
        note = "分流错过收益偏多，略微放宽弱势环境买入"
    else:
        return {
            "changed": False,
            "reason": "分流效果中性，暂不调参",
            "config": cfg,
        }

    next_cfg["last_learning_note"] = note
    saved = set_coordinator_policy_config(next_cfg)
    return {"changed": True, "reason": note, "config": saved}


def _normalize_code_list(value) -> list[str]:
    if isinstance(value, str):
        items = value.replace("，", ",").replace(" ", ",").split(",")
    elif isinstance(value, (list, tuple, set)):
        items = value
    else:
        items = []
    return sorted({str(item).strip() for item in items if str(item).strip()})


def _normalize_sector(value) -> str:
    return str(value or "").strip() or "未分组"


def get_unattended_trade_guard_config() -> dict:
    raw = get_kv_json(_UNATTENDED_TRADE_GUARD_KEY, {}) or {}
    if not isinstance(raw, dict):
        raw = {}
    cfg = {**_UNATTENDED_TRADE_GUARD_DEFAULTS, **raw}
    return {
        "enabled": bool(cfg.get("enabled", True)),
        "unattended_buy_enabled": bool(cfg.get("unattended_buy_enabled", False)),
        "allow_sell_when_buy_disabled": bool(cfg.get("allow_sell_when_buy_disabled", True)),
        "max_daily_buy_amount": _clamp_float(cfg.get("max_daily_buy_amount"), 0.0, 10_000_000.0, 50000.0),
        "max_single_buy_amount": _clamp_float(cfg.get("max_single_buy_amount"), 0.0, 10_000_000.0, 20000.0),
        "max_daily_buy_count": _clamp_int(cfg.get("max_daily_buy_count"), 0, 1000, 3),
        "max_batch_buy_amount": _clamp_float(cfg.get("max_batch_buy_amount"), 0.0, 10_000_000.0, 30000.0),
        "max_batch_buy_count": _clamp_int(cfg.get("max_batch_buy_count"), 0, 100, 2),
        "max_symbol_daily_buy_count": _clamp_int(cfg.get("max_symbol_daily_buy_count"), 0, 100, 1),
        "max_sector_daily_buy_amount": _clamp_float(
            cfg.get("max_sector_daily_buy_amount"),
            0.0,
            10_000_000.0,
            30000.0,
        ),
        "max_sector_daily_buy_count": _clamp_int(cfg.get("max_sector_daily_buy_count"), 0, 100, 2),
        "buy_cooldown_minutes": _clamp_int(cfg.get("buy_cooldown_minutes"), 0, 1440, 30),
        "require_simulation_pass": bool(cfg.get("require_simulation_pass", True)),
        "simulation_min_success_runs": _clamp_int(cfg.get("simulation_min_success_runs"), 1, 100, 3),
        "blacklist": _normalize_code_list(cfg.get("blacklist", [])),
        "whitelist": _normalize_code_list(cfg.get("whitelist", [])),
        "updated_at": str(cfg.get("updated_at", "") or ""),
    }


def set_unattended_trade_guard_config(config: dict) -> dict:
    previous = get_unattended_trade_guard_config()
    payload = {**previous, **(config or {})}
    payload = {
        **payload,
        "enabled": bool(payload.get("enabled", True)),
        "unattended_buy_enabled": bool(payload.get("unattended_buy_enabled", False)),
        "allow_sell_when_buy_disabled": bool(payload.get("allow_sell_when_buy_disabled", True)),
        "max_daily_buy_amount": _clamp_float(payload.get("max_daily_buy_amount"), 0.0, 10_000_000.0, 50000.0),
        "max_single_buy_amount": _clamp_float(payload.get("max_single_buy_amount"), 0.0, 10_000_000.0, 20000.0),
        "max_daily_buy_count": _clamp_int(payload.get("max_daily_buy_count"), 0, 1000, 3),
        "max_batch_buy_amount": _clamp_float(payload.get("max_batch_buy_amount"), 0.0, 10_000_000.0, 30000.0),
        "max_batch_buy_count": _clamp_int(payload.get("max_batch_buy_count"), 0, 100, 2),
        "max_symbol_daily_buy_count": _clamp_int(payload.get("max_symbol_daily_buy_count"), 0, 100, 1),
        "max_sector_daily_buy_amount": _clamp_float(
            payload.get("max_sector_daily_buy_amount"),
            0.0,
            10_000_000.0,
            30000.0,
        ),
        "max_sector_daily_buy_count": _clamp_int(payload.get("max_sector_daily_buy_count"), 0, 100, 2),
        "buy_cooldown_minutes": _clamp_int(payload.get("buy_cooldown_minutes"), 0, 1440, 30),
        "require_simulation_pass": bool(payload.get("require_simulation_pass", True)),
        "simulation_min_success_runs": _clamp_int(payload.get("simulation_min_success_runs"), 1, 100, 3),
        "blacklist": _normalize_code_list(payload.get("blacklist", [])),
        "whitelist": _normalize_code_list(payload.get("whitelist", [])),
        "updated_at": datetime.now().isoformat(),
    }
    set_kv_json(_UNATTENDED_TRADE_GUARD_KEY, payload)
    watched_keys = {
        "enabled",
        "unattended_buy_enabled",
        "max_daily_buy_amount",
        "max_single_buy_amount",
        "max_daily_buy_count",
        "max_batch_buy_amount",
        "max_batch_buy_count",
        "max_symbol_daily_buy_count",
        "max_sector_daily_buy_amount",
        "max_sector_daily_buy_count",
        "buy_cooldown_minutes",
        "require_simulation_pass",
        "simulation_min_success_runs",
        "blacklist",
        "whitelist",
    }
    if any(previous.get(key) != payload.get(key) for key in watched_keys):
        reset_unattended_trade_guard_simulation_state("无人值守交易安全闸变更，需重新完成仿真")
    return payload


def _get_unattended_trade_usage() -> dict:
    today = date.today().isoformat()
    raw = get_kv_json(_UNATTENDED_TRADE_USAGE_KEY, {}) or {}
    if not isinstance(raw, dict) or raw.get("date") != today:
        return {
            "date": today,
            "buy_count": 0,
            "buy_amount": 0.0,
            "symbols": {},
            "sectors": {},
            "last_buy_at": "",
        }
    return {
        "date": today,
        "buy_count": int(raw.get("buy_count", 0) or 0),
        "buy_amount": float(raw.get("buy_amount", 0.0) or 0.0),
        "symbols": raw.get("symbols", {}) if isinstance(raw.get("symbols", {}), dict) else {},
        "sectors": raw.get("sectors", {}) if isinstance(raw.get("sectors", {}), dict) else {},
        "last_buy_at": str(raw.get("last_buy_at", "") or ""),
    }


def get_unattended_trade_guard_usage() -> dict:
    return _get_unattended_trade_usage()


def get_unattended_trade_guard_simulation_state() -> dict:
    raw = get_kv_json(_UNATTENDED_SIMULATION_STATE_KEY, {}) or {}
    if not isinstance(raw, dict):
        raw = {}
    cfg = get_unattended_trade_guard_config()
    required = int(cfg.get("simulation_min_success_runs", 3) or 3)
    consecutive = int(raw.get("consecutive_success_runs", 0) or 0)
    return {
        "passed": bool(raw.get("passed", False)) and consecutive >= required,
        "consecutive_success_runs": consecutive,
        "required_success_runs": required,
        "last_status": str(raw.get("last_status", "") or ""),
        "last_summary": str(raw.get("last_summary", "") or ""),
        "reset_reason": str(raw.get("reset_reason", "") or ""),
        "updated_at": str(raw.get("updated_at", "") or ""),
    }


def record_unattended_trade_guard_simulation(status: str, summary: str = "") -> dict:
    normalized = str(status or "").lower()
    summary_text = str(summary or "")
    transient_error = normalized == "error" and any(
        marker in summary_text.lower()
        for marker in [
            "gateway down",
            "connection refused",
            "timed out",
            "timeout",
            "temporarily unavailable",
        ]
    )
    current = get_unattended_trade_guard_simulation_state()
    consecutive = int(current.get("consecutive_success_runs", 0) or 0)
    if normalized in {"success", "warning"}:
        consecutive += 1
    elif normalized == "error" and not transient_error:
        consecutive = 0
    required = int(current.get("required_success_runs", 3) or 3)
    payload = {
        "passed": consecutive >= required,
        "consecutive_success_runs": consecutive,
        "required_success_runs": required,
        "last_status": "transient_error" if transient_error else normalized,
        "last_summary": summary_text[:300],
        "transient_error": transient_error,
        "updated_at": datetime.now().isoformat(),
    }
    set_kv_json(_UNATTENDED_SIMULATION_STATE_KEY, payload)
    return payload


def _record_unattended_trade_usage(approved_buys: list[dict]):
    if not approved_buys:
        return
    usage = _get_unattended_trade_usage()
    for item in approved_buys:
        code = str(item.get("code", "") or "")
        sector = _normalize_sector(item.get("sector") or item.get("industry") or item.get("board"))
        amount = float(item.get("price", 0) or 0) * int(item.get("shares", 0) or 0)
        usage["buy_count"] += 1
        usage["buy_amount"] += amount
        if code:
            symbol_usage = usage["symbols"].setdefault(code, {"count": 0, "amount": 0.0})
            symbol_usage["count"] = int(symbol_usage.get("count", 0) or 0) + 1
            symbol_usage["amount"] = round(float(symbol_usage.get("amount", 0.0) or 0.0) + amount, 2)
        sector_usage = usage["sectors"].setdefault(sector, {"count": 0, "amount": 0.0})
        sector_usage["count"] = int(sector_usage.get("count", 0) or 0) + 1
        sector_usage["amount"] = round(float(sector_usage.get("amount", 0.0) or 0.0) + amount, 2)
        usage["last_buy_at"] = datetime.now().isoformat()
    usage["buy_amount"] = round(float(usage["buy_amount"]), 2)
    set_kv_json(_UNATTENDED_TRADE_USAGE_KEY, usage)


def _evaluate_unattended_trade_guard(
    *,
    action: str,
    code: str,
    sector: str = "",
    price: float,
    shares: int,
    approved_buys_in_batch: list[dict],
    mode: str,
) -> dict:
    cfg = get_unattended_trade_guard_config()
    if not cfg.get("enabled", True):
        return {"approved": True, "message": "guard disabled", "policy": cfg}

    normalized_action = str(action or "").lower()
    normalized_mode = str(mode or "").lower()
    if normalized_action == "sell":
        if cfg.get("unattended_buy_enabled", False) or cfg.get("allow_sell_when_buy_disabled", True):
            return {"approved": True, "message": "sell allowed", "policy": cfg}
        return {"approved": False, "message": "无人值守实盘未开启，卖出也被禁止", "policy": cfg}
    if normalized_action != "buy":
        return {"approved": True, "message": "non-buy action", "policy": cfg}

    errors: list[str] = []
    if normalized_mode in {"auto", "full_auto"} and not cfg.get("unattended_buy_enabled", False):
        errors.append("无人值守买入未开启")
    if normalized_mode in {"auto", "full_auto"} and cfg.get("require_simulation_pass", True):
        sim = get_unattended_trade_guard_simulation_state()
        if not sim.get("passed", False):
            errors.append(
                "无人值守仿真门禁未通过"
                f"({sim.get('consecutive_success_runs', 0)}/{sim.get('required_success_runs', 3)})"
            )
    blacklist = set(cfg.get("blacklist", []) or [])
    whitelist = set(cfg.get("whitelist", []) or [])
    if code in blacklist:
        errors.append("股票在无人值守黑名单中")
    if whitelist and code not in whitelist:
        errors.append("股票不在无人值守白名单中")

    amount = float(price or 0) * int(shares or 0)
    if amount > float(cfg.get("max_single_buy_amount", 0) or 0):
        errors.append(f"单票买入金额 {amount:.2f} 超过上限 {cfg['max_single_buy_amount']:.2f}")
    usage = _get_unattended_trade_usage()
    batch_count = len(approved_buys_in_batch)
    batch_amount = sum(float(item.get("price", 0) or 0) * int(item.get("shares", 0) or 0) for item in approved_buys_in_batch)
    if batch_count + 1 > int(cfg.get("max_batch_buy_count", 0) or 0):
        errors.append("单批无人值守买入次数超过上限")
    if batch_amount + amount > float(cfg.get("max_batch_buy_amount", 0) or 0):
        errors.append("单批无人值守买入金额超过上限")
    if usage["buy_count"] + batch_count + 1 > int(cfg.get("max_daily_buy_count", 0) or 0):
        errors.append("无人值守每日买入次数超过上限")
    if usage["buy_amount"] + batch_amount + amount > float(cfg.get("max_daily_buy_amount", 0) or 0):
        errors.append("无人值守每日买入金额超过上限")
    symbol_usage = (usage.get("symbols", {}) or {}).get(code, {}) if code else {}
    batch_symbol_count = sum(1 for item in approved_buys_in_batch if str(item.get("code", "") or "") == code)
    if (
        int(symbol_usage.get("count", 0) or 0) + batch_symbol_count + 1
        > int(cfg.get("max_symbol_daily_buy_count", 0) or 0)
    ):
        errors.append("单票每日无人值守买入次数超过上限")
    normalized_sector = _normalize_sector(sector)
    sector_usage = (usage.get("sectors", {}) or {}).get(normalized_sector, {})
    batch_sector_items = [
        item for item in approved_buys_in_batch
        if _normalize_sector(item.get("sector") or item.get("industry") or item.get("board")) == normalized_sector
    ]
    batch_sector_count = len(batch_sector_items)
    batch_sector_amount = sum(
        float(item.get("price", 0) or 0) * int(item.get("shares", 0) or 0)
        for item in batch_sector_items
    )
    if (
        int(sector_usage.get("count", 0) or 0) + batch_sector_count + 1
        > int(cfg.get("max_sector_daily_buy_count", 0) or 0)
    ):
        errors.append("板块每日无人值守买入次数超过上限")
    if (
        float(sector_usage.get("amount", 0.0) or 0.0) + batch_sector_amount + amount
        > float(cfg.get("max_sector_daily_buy_amount", 0) or 0)
    ):
        errors.append("板块每日无人值守买入金额超过上限")
    cooldown_minutes = int(cfg.get("buy_cooldown_minutes", 0) or 0)
    last_buy_at = str(usage.get("last_buy_at", "") or "")
    if cooldown_minutes > 0 and last_buy_at:
        try:
            elapsed = (datetime.now() - datetime.fromisoformat(last_buy_at)).total_seconds() / 60
            if elapsed < cooldown_minutes:
                errors.append(f"无人值守买入冷却中({elapsed:.0f}/{cooldown_minutes}分钟)")
        except Exception:
            pass

    return {
        "approved": not errors,
        "message": "approved" if not errors else "; ".join(errors),
        "policy": cfg,
    }


def _summarize_for_trace(payload) -> dict:
    if isinstance(payload, dict):
        summary = {}
        for key, value in payload.items():
            if key in {"steps", "agent_trace"}:
                continue
            if isinstance(value, list):
                summary[key] = {"type": "list", "count": len(value)}
            elif isinstance(value, dict):
                summary[key] = {"type": "dict", "keys": list(value.keys())[:8]}
            else:
                text = str(value)
                summary[key] = text[:120]
        return summary
    if isinstance(payload, list):
        return {"type": "list", "count": len(payload)}
    return {"value": str(payload)[:160]}


def _agent_trace_step(
    trace_items: list[dict],
    parent_traceparent: str,
    agent_key: str,
    stage: str,
    fn: Callable,
    *,
    inputs=None,
    metadata: dict | None = None,
):
    span = start_span(
        f"agent.{agent_key}",
        traceparent=parent_traceparent,
        metadata={
            "kind": "agent",
            "agent_key": agent_key,
            "stage": stage,
            "input_summary": _summarize_for_trace(inputs),
            **(metadata or {}),
        },
    )
    try:
        output = fn()
        span.setdefault("metadata", {})["output_summary"] = _summarize_for_trace(output)
        finished = finish_span(span, status="ok")
        trace_items.append(_compact_agent_span(finished))
        return output
    except Exception as exc:
        span.setdefault("metadata", {})["error"] = str(exc)[:240]
        finished = finish_span(span, status="error")
        trace_items.append(_compact_agent_span(finished))
        raise


def _compact_agent_span(span: dict) -> dict:
    metadata = span.get("metadata", {}) or {}
    return {
        "name": span.get("name", ""),
        "agent_key": metadata.get("agent_key", ""),
        "stage": metadata.get("stage", ""),
        "status": span.get("status", ""),
        "duration_ms": round(float(span.get("duration_ms", 0.0) or 0.0), 3),
        "trace_id_hex": span.get("trace_id_hex", ""),
        "span_id": span.get("span_id", ""),
        "parent_span_id": span.get("parent_span_id", ""),
        "input_summary": metadata.get("input_summary", {}),
        "output_summary": metadata.get("output_summary", {}),
        "error": metadata.get("error", ""),
    }


class IntelligenceAgent:
    """
    情报智能体：采集市场数据、新闻事件、基金动向，输出结构化情报摘要。
    不做判断，只做事实陈述。
    """
    NAME = "📡 情报智能体"

    SYSTEM_PROMPT = (
        "你是一个专业的金融情报分析员。你的职责是：\n"
        "1. 整理市场数据，客观陈述事实\n"
        "2. 提取关键信号（涨跌异动、资金流向、板块轮动）\n"
        "3. 汇总新闻事件和基金动向\n"
        "4. 不做主观判断，不给买卖建议\n"
        "输出格式：分为【市场概况】【板块动态】【资金信号】【事件要闻】【基金动向】五个模块。"
    )

    @staticmethod
    def gather(boards: list[str] = None) -> dict:
        """采集全方位情报数据。"""
        if not boards:
            return {"agent": "intelligence", "error": "未指定板块", "market": {}, "boards": [], "events": [], "fund_top": []}
        report = {"agent": "intelligence", "timestamp": datetime.now().isoformat()}

        conn = RepoCompatConnection()
        conn.execute("PRAGMA journal_mode=WAL")

        # 市场概况：取有数据的前50只股票的涨跌统计
        try:
            cur = conn.execute("""
                SELECT d1.code,
                    (SELECT close FROM daily_kline d2 WHERE d2.code=d1.code ORDER BY date DESC LIMIT 1) as last_c,
                    (SELECT close FROM daily_kline d3 WHERE d3.code=d1.code ORDER BY date DESC LIMIT 1 OFFSET 1) as prev_c
                FROM (SELECT DISTINCT code FROM daily_kline) d1 LIMIT 200
            """)
            stocks = []
            up, down, flat = 0, 0, 0
            for r in cur.fetchall():
                if r[1] and r[2] and r[2] > 0:
                    pct = (r[1] - r[2]) / r[2] * 100
                    stocks.append({"code": r[0], "price": r[1], "pct": round(pct, 2)})
                    if pct > 0.5:
                        up += 1
                    elif pct < -0.5:
                        down += 1
                    else:
                        flat += 1
            report["market"] = {
                "total": len(stocks), "up": up, "down": down, "flat": flat,
                "top_gainers": sorted(stocks, key=lambda x: x["pct"], reverse=True)[:5],
                "top_losers": sorted(stocks, key=lambda x: x["pct"])[:5],
            }
        except Exception:
            report["market"] = {"error": "市场数据读取失败"}

        # 板块动态
        try:
            board_stats = []
            for board in boards:
                cur_b = conn.execute("SELECT code FROM board_stocks WHERE board=?", (board,))
                codes = [r[0] for r in cur_b.fetchall()]
                pcts = []
                for code in codes[:30]:
                    cur2 = conn.execute(
                        "SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 2", (code,)
                    )
                    rows = cur2.fetchall()
                    if len(rows) == 2 and rows[1][0] > 0:
                        pcts.append((rows[0][0] / rows[1][0] - 1) * 100)
                avg = float(np.mean(pcts)) if pcts else 0
                board_stats.append({"board": board, "stocks": len(codes), "avg_pct": round(avg, 2)})
            report["boards"] = board_stats
        except Exception:
            report["boards"] = []

        # 事件要闻
        try:
            cur_e = conn.execute(
                "SELECT event_text, matched_boards, event_date FROM events ORDER BY id DESC LIMIT 5"
            )
            report["events"] = [
                {"text": r[0], "boards": r[1], "date": r[2]} for r in cur_e.fetchall()
            ]
        except Exception:
            report["events"] = []

        # 基金动向
        try:
            cur_f = conn.execute(
                "SELECT code, name, holding_funds, change_type FROM fund_holdings "
                "ORDER BY holding_funds DESC LIMIT 10"
            )
            report["fund_top"] = [
                {"code": r[0], "name": r[1], "funds": r[2], "change": r[3]}
                for r in cur_f.fetchall()
            ]
        except Exception:
            report["fund_top"] = []

        conn.close()
        return report

    @staticmethod
    def to_prompt(report: dict) -> str:
        """将情报数据转为自然语言摘要。"""
        lines = ["===== 情报智能体报告 ====="]

        m = report.get("market", {})
        if "error" not in m:
            lines.append(f"\n【市场概况】{m.get('total', 0)}只股票: 上涨{m.get('up', 0)} 下跌{m.get('down', 0)} 持平{m.get('flat', 0)}")
            for s in m.get("top_gainers", [])[:3]:
                lines.append(f"  涨幅前列: {s['code']} {s['pct']:+.2f}%")
            for s in m.get("top_losers", [])[:3]:
                lines.append(f"  跌幅前列: {s['code']} {s['pct']:+.2f}%")

        for b in report.get("boards", []):
            lines.append(f"\n【板块】{b['board']}: {b['stocks']}只, 均涨跌 {b['avg_pct']:+.2f}%")

        events = report.get("events", [])
        if events:
            lines.append("\n【事件要闻】")
            for e in events[:3]:
                lines.append(f"  {e.get('date', '')} {e.get('text', '')}")

        fund = report.get("fund_top", [])
        if fund:
            lines.append("\n【基金动向】")
            for f in fund[:5]:
                lines.append(f"  {f['code']} {f['name']}: {f['funds']}只基金, {f.get('change', '-')}")

        return "\n".join(lines)


class AnalysisAgent:
    """
    分析智能体：基于情报数据做多维度策略分析，输出评分和信号。
    只做分析判断，不做执行决策。
    """
    NAME = "🔬 分析智能体"

    SYSTEM_PROMPT = (
        "你是一个专业的量化策略分析师。你的职责是：\n"
        "1. 基于情报数据，分析市场趋势和板块轮动\n"
        "2. 对候选股票做多策略评分（趋势/动量/价值/情绪/事件/基金持仓）\n"
        "3. 识别潜在的风险和机会\n"
        "4. 输出结构化的分析报告，不做最终买卖决策\n"
        "输出格式：分为【趋势判断】【板块评级】【个股评分】【风险提示】四个模块。\n"
        "个股评分请用表格，包含代码、名称、趋势分、动量分、综合评分、信号。"
    )

    @staticmethod
    def analyze(intel_report: dict, boards: list[str] = None) -> dict:
        """基于情报做策略分析。"""
        if not boards:
            return {"agent": "analysis", "candidates": [], "market_regime": "未指定板块"}

        conn = RepoCompatConnection()
        conn.execute("PRAGMA journal_mode=WAL")

        candidates = []
        for board in boards[:5]:
            cur = conn.execute("SELECT code FROM board_stocks WHERE board=?", (board,))
            codes = [r[0] for r in cur.fetchall()]

            names = {}
            try:
                cur_n = conn.execute("SELECT code, name FROM stock_list")
                names = {r[0]: r[1] for r in cur_n.fetchall()}
            except Exception:
                pass

            for code in codes[:20]:
                cur2 = conn.execute(
                    "SELECT close, high, low, volume FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 60",
                    (code,),
                )
                rows = cur2.fetchall()
                if len(rows) < 20:
                    continue
                rows = rows[::-1]
                closes = np.array([r[0] for r in rows])
                vols = np.array([r[3] for r in rows])
                n = len(closes)
                price = float(closes[-1])
                if price <= 0:
                    continue

                # 趋势分
                ma20 = float(np.mean(closes[-20:]))
                ma50 = float(np.mean(closes[-50:])) if n >= 50 else ma20
                trend_score = 0
                if price > ma20 > ma50:
                    trend_score = 80
                elif price > ma20:
                    trend_score = 60
                elif price < ma20 < ma50:
                    trend_score = 20
                else:
                    trend_score = 40

                # 动量分
                mom5 = (closes[-1] / closes[-6] - 1) * 100 if n >= 6 else 0
                mom20 = (closes[-1] / closes[-21] - 1) * 100 if n >= 21 else 0
                momentum_score = min(100, max(0, 50 + mom5 * 3 + mom20))

                # 量能分
                vol_avg = float(np.mean(vols[-20:])) if n >= 20 and np.mean(vols[-20:]) > 0 else 1
                vol_ratio = float(vols[-1]) / vol_avg
                volume_score = min(100, int(vol_ratio * 40))

                # 综合
                total = int(trend_score * 0.4 + momentum_score * 0.3 + volume_score * 0.3)

                signals = []
                if trend_score >= 70:
                    signals.append("多头趋势")
                if mom5 > 3:
                    signals.append(f"5日强势{mom5:+.1f}%")
                if vol_ratio > 1.5:
                    signals.append("放量")

                # 基金持仓加分
                try:
                    cur_f = conn.execute(
                        "SELECT holding_funds, change_type FROM fund_holdings WHERE code=? LIMIT 1", (code,)
                    )
                    fr = cur_f.fetchone()
                    if fr and fr[0] and fr[0] >= 100:
                        total += 5
                        signals.append(f"基金{fr[0]}只")
                    if fr and fr[1] and "增持" in str(fr[1]):
                        total += 5
                        signals.append("基金增持")
                except Exception:
                    pass

                candidates.append({
                    "code": code, "name": names.get(code, ""),
                    "board": board, "price": round(price, 2),
                    "trend": trend_score, "momentum": round(momentum_score),
                    "volume": volume_score, "total": min(100, total),
                    "signals": signals,
                })

        conn.close()
        candidates.sort(key=lambda x: x["total"], reverse=True)

        return {
            "agent": "analysis",
            "timestamp": datetime.now().isoformat(),
            "candidates": candidates[:30],
            "market_regime": _detect_regime(intel_report),
        }

    @staticmethod
    def to_prompt(analysis: dict) -> str:
        """将分析结果转为自然语言。"""
        lines = ["===== 分析智能体报告 ====="]

        regime = analysis.get("market_regime", "中性")
        lines.append(f"\n【市场环境判断】{regime}")

        candidates = analysis.get("candidates", [])
        if candidates:
            lines.append("\n【个股评分 Top15】")
            lines.append("| 代码 | 名称 | 板块 | 趋势 | 动量 | 综合 | 信号 |")
            lines.append("|------|------|------|------|------|------|------|")
            for c in candidates[:15]:
                sig = ", ".join(c["signals"][:3]) if c["signals"] else "-"
                lines.append(
                    f"| {c['code']} | {c['name']} | {c['board']} | "
                    f"{c['trend']} | {c['momentum']} | {c['total']} | {sig} |"
                )

        return "\n".join(lines)


class VerificationAgent:
    """
    验证智能体：基于走势验证历史与失败归因，对候选股做只读验收。
    第一版不直接拦截交易，只输出 verified/questionable/rejected 和风险说明。
    """
    NAME = "✅ 验证智能体"

    @staticmethod
    def _build_candidate_assessment(
        candidate: dict,
        *,
        market_regime: str,
        failed_by_code: dict[str, int],
        failed_by_board: dict[str, int],
    ) -> dict:
        code = str(candidate.get("code", "") or "")
        board = str(candidate.get("board", "") or "")
        score = int(candidate.get("total", 0) or 0)
        notes: list[str] = []
        tags: list[str] = []
        verification_score = score

        code_failures = failed_by_code.get(code, 0)
        board_failures = failed_by_board.get(board, 0)

        if code_failures >= 1:
            notes.append(f"该股近120天失败信号 {code_failures} 次")
            tags.append("history_fail")
            verification_score -= min(18, code_failures * 8)
        if board_failures >= 4:
            notes.append(f"{board} 板块近期失败样本偏多({board_failures}次)")
            tags.append("board_risk")
            verification_score -= min(12, board_failures)
        if "弱势" in market_regime and score < 70:
            notes.append("当前市场偏弱，需更高确认度")
            tags.append("weak_market")
            verification_score -= 10
        if score < 55:
            notes.append("综合评分偏低")
            tags.append("low_score")
            verification_score -= 12
        elif score < 70:
            notes.append("综合评分中等，建议二次确认")
            tags.append("mid_score")
            verification_score -= 5

        verification_score = max(0, min(100, verification_score))
        if board_failures >= 6 or code_failures >= 2:
            board_risk_level = "high"
        elif board_failures >= 3 or code_failures >= 1:
            board_risk_level = "medium"
        else:
            board_risk_level = "low"

        if verification_score >= 75 and code_failures == 0:
            verdict = "verified"
        elif verification_score < 45 or code_failures >= 2 or ("弱势" in market_regime and score < 55):
            verdict = "rejected"
        elif notes:
            verdict = "questionable"
        else:
            verdict = "verified"

        return {
            **candidate,
            "verification": verdict,
            "verification_notes": notes,
            "verification_score": verification_score,
            "verification_reason_tags": list(dict.fromkeys(tags)),
            "board_risk_level": board_risk_level,
            "recent_failure_count": code_failures,
            "recent_board_failure_count": board_failures,
        }

    @staticmethod
    def verify(analysis: dict) -> dict:
        from desktop.trend_verify import get_accuracy_stats, get_failure_summary, get_records

        candidates = list(analysis.get("candidates", []) or [])
        market_regime = str(analysis.get("market_regime", "") or "")
        failed_records = get_records(limit=300, failed_only=True, since_days=120)
        accuracy_stats = get_accuracy_stats()
        failure_summary = get_failure_summary(limit=120, since_days=180)

        failed_by_code: dict[str, int] = {}
        failed_by_board: dict[str, int] = {}
        for record in failed_records:
            code = str(record.get("code", "") or "")
            board = str(record.get("board", "") or "")
            if code:
                failed_by_code[code] = failed_by_code.get(code, 0) + 1
            if board:
                failed_by_board[board] = failed_by_board.get(board, 0) + 1

        top_roots = [item.get("label", "") for item in failure_summary.get("top_root_causes", [])[:3] if item.get("label")]

        verified = []
        questionable = []
        rejected = []
        risk_flags = []

        for candidate in candidates:
            payload = VerificationAgent._build_candidate_assessment(
                candidate,
                market_regime=market_regime,
                failed_by_code=failed_by_code,
                failed_by_board=failed_by_board,
            )
            code = str(payload.get("code", "") or "")
            board = str(payload.get("board", "") or "")
            notes = payload.get("verification_notes", [])
            verdict = payload.get("verification", "questionable")
            if verdict == "verified":
                verified.append(payload)
            elif verdict == "questionable":
                questionable.append(payload)
            else:
                rejected.append(payload)

            if notes:
                risk_flags.append(
                    {
                        "code": code,
                        "name": payload.get("name", ""),
                        "board": board,
                        "notes": notes,
                        "verification_score": payload.get("verification_score", 0),
                        "board_risk_level": payload.get("board_risk_level", "low"),
                    }
                )

        return {
            "agent": "verification",
            "timestamp": datetime.now().isoformat(),
            "verified_candidates": verified,
            "questionable_candidates": questionable,
            "rejected_candidates": rejected,
            "all_candidates": verified + questionable + rejected,
            "risk_flags": risk_flags[:20],
            "market_regime": market_regime,
            "accuracy": accuracy_stats.get("accuracy", 0),
            "top_failure_roots": top_roots,
        }

    @staticmethod
    def to_prompt(verification: dict) -> str:
        lines = ["===== 验证智能体报告 ====="]
        lines.append(
            f"\n【验证概况】通过{len(verification.get('verified_candidates', []))} "
            f"存疑{len(verification.get('questionable_candidates', []))} "
            f"拒绝{len(verification.get('rejected_candidates', []))} "
            f"| 历史准确率 {verification.get('accuracy', 0):.1f}%"
        )
        roots = verification.get("top_failure_roots", [])
        if roots:
            lines.append(f"【近期高频失败根因】{' / '.join(roots)}")

        if verification.get("verified_candidates"):
            lines.append("\n【优先候选】")
            for item in verification["verified_candidates"][:8]:
                lines.append(
                    f"  {item.get('code','')} {item.get('name','')}: "
                    f"验证分{item.get('verification_score', 0)}"
                )

        if verification.get("questionable_candidates"):
            lines.append("\n【存疑候选】")
            for item in verification["questionable_candidates"][:10]:
                note = "；".join(item.get("verification_notes", [])[:2]) or "-"
                lines.append(
                    f"  {item.get('code','')} {item.get('name','')}: "
                    f"验证分{item.get('verification_score', 0)} {note}"
                )

        if verification.get("rejected_candidates"):
            lines.append("\n【高风险候选】")
            for item in verification["rejected_candidates"][:10]:
                note = "；".join(item.get("verification_notes", [])[:2]) or "-"
                lines.append(
                    f"  {item.get('code','')} {item.get('name','')}: "
                    f"验证分{item.get('verification_score', 0)} {note}"
                )

        return "\n".join(lines)


def _build_verified_candidate_context(verification: dict) -> str:
    lines = ["===== 验证后候选清单 ====="]
    verified = verification.get("verified_candidates", []) or []
    questionable = verification.get("questionable_candidates", []) or []
    rejected = verification.get("rejected_candidates", []) or []

    if verified:
        lines.append("\n【优先参考候选（已通过验证）】")
        for item in verified[:12]:
            lines.append(
                f"- {item.get('code','')} {item.get('name','')} "
                f"综合{item.get('total', 0)} 验证{item.get('verification_score', 0)} "
                f"板块风险={item.get('board_risk_level', 'low')}"
            )
    else:
        lines.append("\n【优先参考候选（已通过验证）】无")

    if questionable:
        lines.append("\n【谨慎参考候选（需二次确认）】")
        for item in questionable[:12]:
            note = "；".join(item.get("verification_notes", [])[:2]) or "-"
            lines.append(
                f"- {item.get('code','')} {item.get('name','')} "
                f"综合{item.get('total', 0)} 验证{item.get('verification_score', 0)} "
                f"{note}"
            )

    if rejected:
        lines.append("\n【原则上不新开仓候选】")
        for item in rejected[:12]:
            note = "；".join(item.get("verification_notes", [])[:2]) or "-"
            lines.append(
                f"- {item.get('code','')} {item.get('name','')} "
                f"综合{item.get('total', 0)} 验证{item.get('verification_score', 0)} "
                f"{note}"
            )

    return "\n".join(lines)


def _apply_verification_guardrails(decisions: list[dict], verification: dict) -> dict:
    """对决策结果施加半硬约束：拒绝高风险新开仓，存疑候选保留但追加提示。"""
    verified_map = {
        str(item.get("code", "") or ""): item
        for item in verification.get("verified_candidates", []) or []
    }
    questionable_map = {
        str(item.get("code", "") or ""): item
        for item in verification.get("questionable_candidates", []) or []
    }
    rejected_map = {
        str(item.get("code", "") or ""): item
        for item in verification.get("rejected_candidates", []) or []
    }

    filtered: list[dict] = []
    blocked: list[dict] = []
    annotated: list[dict] = []

    for decision in decisions or []:
        action = str(decision.get("action", "") or "").lower()
        code = str(decision.get("code", "") or "")

        if action != "buy" or not code:
            filtered.append(decision)
            continue

        if code in rejected_map:
            item = rejected_map[code]
            blocked.append(
                {
                    "code": code,
                    "name": decision.get("name", item.get("name", "")),
                    "reason": "；".join(item.get("verification_notes", [])[:2]) or "验证智能体判定为高风险候选",
                    "verification_score": item.get("verification_score", 0),
                }
            )
            continue

        if code in questionable_map:
            item = questionable_map[code]
            updated = dict(decision)
            note = "；".join(item.get("verification_notes", [])[:2])
            suffix = f" [验证存疑: {note}]" if note else " [验证存疑]"
            updated["reason"] = f"{decision.get('reason', '')}{suffix}".strip()
            updated["verification_score"] = item.get("verification_score", 0)
            updated["verification"] = "questionable"
            filtered.append(updated)
            annotated.append(
                {
                    "code": code,
                    "name": decision.get("name", item.get("name", "")),
                    "reason": note or "验证智能体标记为存疑",
                    "verification_score": item.get("verification_score", 0),
                }
            )
            continue

        if code in verified_map:
            item = verified_map[code]
            updated = dict(decision)
            updated["verification_score"] = item.get("verification_score", 0)
            updated["verification"] = "verified"
            filtered.append(updated)
            continue

        filtered.append(decision)

    summary_bits = []
    if blocked:
        summary_bits.append(f"拦截高风险买入 {len(blocked)} 条")
    if annotated:
        summary_bits.append(f"标记存疑买入 {len(annotated)} 条")
    summary = "，".join(summary_bits) if summary_bits else "未触发额外约束"

    return {
        "filtered_decisions": filtered,
        "blocked_buys": blocked,
        "annotated_buys": annotated,
        "summary": summary,
    }


class CoordinatorAgent:
    """
    协调者智能体：负责任务编排、阶段总结和下一步建议。
    第一版不直接派发并行 worker，只输出清晰的 orchestration plan。
    """
    NAME = "🧭 协调者智能体"

    @staticmethod
    def plan_pipeline(boards: list[str] | None = None) -> dict:
        boards = boards or []
        focus = boards[:3]
        stages = [
            "感知采集",
            "因子筛选",
            "多智能体研判",
            "仓位优化",
            "风控检查",
            "执行与归因",
            "自主学习",
        ]
        return {
            "agent": "coordinator",
            "timestamp": datetime.now().isoformat(),
            "focus_boards": focus,
            "objective": "围绕核心板块完成从候选生成到学习反馈的全流程编排",
            "risk_policy": "先验证后决策，高风险候选不新开仓，非交易时间只生成建议不执行",
            "stage_plan": stages,
            "summary": f"聚焦板块: {', '.join(focus) if focus else '默认市场篮子'}",
            "next_action": "启动流程",
        }

    @staticmethod
    def inspect_stage_readiness(stage_key: str, results: dict) -> dict:
        """
        阶段前置编排检查：只产出诊断和建议动作，具体执行由流水线引擎完成。
        """
        stage = str(stage_key or "").lower()
        candidates = list(results.get("candidates", []) or [])
        decisions = list(results.get("decisions", []) or [])
        errors = list(results.get("errors", []) or [])
        actions: list[dict] = []
        ready = True
        mode = "normal"
        reason = "前置条件满足"

        if stage == "s3" and not candidates:
            mode = "hydrate_candidates"
            reason = "候选池为空，尝试从最近扫描结果补充上下文"
            actions.append(
                {
                    "type": "hydrate_last_scan_results",
                    "target": "candidates",
                    "reason": reason,
                    "limit": 30,
                }
            )

        if stage == "s4" and not decisions:
            ready = False
            mode = "wait_decisions"
            reason = "缺少 AI 决策，仓位优化无法产生有效权重"
            if candidates:
                actions.append(
                    {
                        "type": "recommend_rerun",
                        "target": "s3",
                        "reason": "已有候选但无决策，建议重跑多智能体研判",
                    }
                )

        if stage == "s6":
            if not decisions:
                ready = False
                mode = "wait_decisions"
                reason = "缺少交易决策，执行阶段应跳过"
            elif not results.get("risk_report"):
                mode = "require_risk_check"
                reason = "执行前缺少结构化风控报告，建议先完成风控阶段"
                actions.append(
                    {
                        "type": "require_prerequisite",
                        "target": "s5",
                        "reason": reason,
                    }
                )

        if stage == "s9" and len(errors) >= 2:
            mode = "degraded_learning"
            reason = "上游存在多处错误，学习阶段应降低置信度或暂停"
            actions.append(
                {
                    "type": "mark_degraded",
                    "target": "learning",
                    "reason": reason,
                }
            )

        return {
            "stage": stage,
            "ready": ready,
            "mode": mode,
            "reason": reason,
            "actions": actions,
            "timestamp": datetime.now().isoformat(),
        }

    @staticmethod
    def summarize_pipeline(results: dict) -> dict:
        steps = results.get("steps", []) or []
        ok_count = sum(1 for step in steps if step.get("status") == "ok")
        error_count = sum(1 for step in steps if step.get("status") == "error")
        candidate_count = len(results.get("candidates", []) or [])
        decision_count = len(results.get("decisions", []) or [])
        executed_count = len(results.get("executed_decisions", []) or [])
        guardrails = results.get("decision_guardrails", {}) or {}
        exec_plan = results.get("execution_plan", {}) or {}
        blocked = len(guardrails.get("blocked_buys", []) or [])
        annotated = len(guardrails.get("annotated_buys", []) or [])
        routed_blocked = len(exec_plan.get("blocked", []) or [])

        if error_count > 0:
            next_action = "优先处理失败步骤并复跑相关阶段"
        elif blocked > 0:
            next_action = "复盘被拦截买入样本，评估守门阈值是否需要调优"
        elif routed_blocked > 0:
            next_action = "复盘协调者分流拦截策略，确认降速与风险偏好是否匹配"
        elif decision_count == 0:
            next_action = "暂无决策输出，建议检查候选质量和市场环境"
        else:
            next_action = "继续执行学习闭环，观察验证通过候选的后验表现"

        summary = (
            f"完成步骤 {ok_count}/{len(steps)}，候选 {candidate_count} 只，"
            f"决策 {decision_count} 条(执行 {executed_count} 条)，"
            f"守门拦截 {blocked} 条，分流拦截 {routed_blocked} 条，存疑放行 {annotated} 条"
        )
        return {
            "ok_steps": ok_count,
            "error_steps": error_count,
            "candidate_count": candidate_count,
            "decision_count": decision_count,
            "executed_decision_count": executed_count,
            "blocked_buy_count": blocked,
            "routed_blocked_count": routed_blocked,
            "annotated_buy_count": annotated,
            "summary": summary,
            "next_action": next_action,
        }

    @staticmethod
    def route_stage(stage_key: str, results: dict) -> dict:
        """
        根据当前上下文决定阶段是否执行，实现轻量分流。
        返回: {"run": bool, "mode": str, "reason": str}
        """
        stage = str(stage_key or "").lower()
        decisions = list(results.get("decisions", []) or [])
        candidates = list(results.get("candidates", []) or [])
        errors = list(results.get("errors", []) or [])
        guardrails = results.get("decision_guardrails", {}) or {}
        blocked = len(guardrails.get("blocked_buys", []) or [])
        buy_count = sum(1 for item in decisions if str(item.get("action", "")).lower() == "buy")
        sell_count = sum(1 for item in decisions if str(item.get("action", "")).lower() == "sell")
        sentiment = results.get("news_sentiment", {}) or {}
        positive_ratio = float(sentiment.get("ratio", 0.5) or 0.5)
        risk_summary = str(results.get("risk_summary", "") or "")
        policy_cfg = get_coordinator_policy_config()

        if stage == "s4":
            if not decisions:
                return {"run": False, "mode": "skip", "reason": "无决策输出，跳过仓位优化"}
            return {"run": True, "mode": "normal", "reason": "存在决策指令，执行仓位优化"}

        if stage == "s6":
            if not decisions:
                return {"run": False, "mode": "skip", "reason": "无可执行决策，跳过交易执行"}
            blocked_ratio = (blocked / max(buy_count, 1)) if buy_count > 0 else 0.0
            if buy_count > 0 and blocked_ratio >= policy_cfg["observe_blocked_ratio"] and sell_count == 0:
                return {"run": False, "mode": "observe_only", "reason": "买入信号大多被守门拦截，进入观察模式"}
            if ("⚠" in risk_summary or "回撤" in risk_summary) and buy_count > 0:
                return {
                    "run": True,
                    "mode": "sell_only",
                    "reason": "风控预警阶段，仅执行减仓/持有类指令",
                    "execution_policy": {
                        "allow_buy": False,
                        "allow_sell": True,
                        "allow_hold": True,
                        "max_buy_count": 0,
                    },
                }
            if positive_ratio < policy_cfg["sell_only_sentiment_ratio"] and buy_count > sell_count:
                return {
                    "run": True,
                    "mode": "sell_only",
                    "reason": "舆情偏弱，仅执行卖出以降低风险暴露",
                    "execution_policy": {
                        "allow_buy": False,
                        "allow_sell": True,
                        "allow_hold": True,
                        "max_buy_count": 0,
                    },
                }
            if positive_ratio < policy_cfg["limit_buy_sentiment_ratio"] and buy_count > 0:
                return {
                    "run": True,
                    "mode": "limit_buy",
                    "reason": "舆情偏谨慎，买入指令降速并限制数量",
                    "execution_policy": {
                        "allow_buy": True,
                        "allow_sell": True,
                        "allow_hold": True,
                        "max_buy_count": policy_cfg["limit_buy_max_count"],
                    },
                }
            return {"run": True, "mode": "normal", "reason": "通过执行门控，允许执行交易"}

        if stage == "s7":
            if not candidates and not decisions:
                return {"run": False, "mode": "skip", "reason": "无候选且无决策，跳过推送"}
            return {"run": True, "mode": "normal", "reason": "存在可汇报内容，执行推送"}

        if stage == "s8":
            if not candidates and not decisions:
                return {"run": False, "mode": "skip", "reason": "缺少归因样本，跳过归因记录"}
            return {"run": True, "mode": "normal", "reason": "具备候选或决策样本，执行归因记录"}

        if stage == "s9":
            if len(errors) >= 3:
                return {"run": False, "mode": "skip", "reason": "上游失败过多，暂停自主学习避免污染样本"}
            return {"run": True, "mode": "normal", "reason": "流程质量可接受，执行学习进化"}

        return {"run": True, "mode": "normal", "reason": "默认执行"}

    @staticmethod
    def recover_stage_failure(stage_key: str, stage_name: str, error: str, results: dict) -> dict:
        """
        首版失败恢复策略：对易受临时数据/API波动影响的阶段允许自动重试一次。
        更复杂的补数据/重排任务后续可挂在这里。
        """
        stage = str(stage_key or "").lower()
        tried = results.setdefault("_recovery_tried", {})
        retryable = {"s1", "s2", "s3", "s5"}
        if stage in retryable and not tried.get(stage):
            tried[stage] = True
            return {
                "retry": True,
                "mode": "retry_once",
                "reason": f"{stage_name} 失败，协调者触发一次自动重试",
            }
        if stage == "s6":
            return {
                "retry": False,
                "mode": "manual_review",
                "reason": "执行阶段失败需人工复核，避免重复下单",
            }
        if len(results.get("errors", []) or []) >= 2:
            return {
                "retry": False,
                "mode": "halt_downstream",
                "reason": "连续失败较多，建议暂停后续高风险阶段",
            }
        return {
            "retry": False,
            "mode": "no_recovery",
            "reason": f"{stage_name} 暂无自动恢复策略: {str(error)[:80]}",
        }


class RiskAgent:
    """风险智能体：统一评估持仓、组合风险和市场情绪风险。"""
    NAME = "🛡️ 风险智能体"

    @staticmethod
    def _safe_float(value, default: float = 0.0) -> float:
        try:
            return float(value)
        except Exception:
            return default

    @staticmethod
    def _safe_int(value, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return default

    @staticmethod
    def _position_value(position: dict) -> float:
        price = RiskAgent._safe_float(
            position.get("current_price")
            or position.get("price")
            or position.get("entry_price")
        )
        shares = RiskAgent._safe_int(position.get("shares"))
        return max(0.0, price * shares)

    @staticmethod
    def _buy_amount(decision: dict) -> float:
        if str(decision.get("action", "") or "").lower() != "buy":
            return 0.0
        return max(
            0.0,
            RiskAgent._safe_float(decision.get("price")) * RiskAgent._safe_int(decision.get("shares")),
        )

    @staticmethod
    def assess_openclaw(results: dict | None = None) -> dict:
        from desktop.ai_portfolio import get_state

        payload = results or {}
        warnings: list[str] = []
        checks: list[dict] = []
        metrics: dict[str, dict] = {}
        decisions = [item for item in (payload.get("decisions", []) or []) if isinstance(item, dict)]
        pending_buy_amount = sum(RiskAgent._buy_amount(item) for item in decisions)
        pending_buy_codes = {
            str(item.get("code", "") or "")
            for item in decisions
            if str(item.get("action", "") or "").lower() == "buy" and str(item.get("code", "") or "")
        }

        for mode, label in [("auto", "半自主"), ("full_auto", "完全自主")]:
            state = get_state(mode)
            raw_positions = state.get("positions", []) if isinstance(state, dict) else []
            positions = [item for item in raw_positions if isinstance(item, dict)]
            n_pos = len(raw_positions)
            cash = RiskAgent._safe_float(state.get("cash", 0) if isinstance(state, dict) else 0)
            initial_capital = max(RiskAgent._safe_float(state.get("initial_capital", 0) if isinstance(state, dict) else 0), 1)
            position_values = [RiskAgent._position_value(item) for item in positions]
            position_value = sum(position_values)
            equity = max(cash + position_value, initial_capital, 1)
            cash_ratio = cash / max(equity, 1) * 100
            exposure_ratio = position_value / max(equity, 1) * 100
            max_position_ratio = (max(position_values) / max(equity, 1) * 100) if position_values else 0.0
            stop_loss_missing = sum(
                1 for item in positions if RiskAgent._safe_float(item.get("stop_loss")) <= 0
            )
            stop_loss_risk_amount = 0.0
            for item in positions:
                entry = RiskAgent._safe_float(item.get("entry_price"))
                stop_loss = RiskAgent._safe_float(item.get("stop_loss"))
                shares = RiskAgent._safe_int(item.get("shares"))
                if entry > 0 and stop_loss > 0 and stop_loss < entry and shares > 0:
                    stop_loss_risk_amount += (entry - stop_loss) * shares
            stop_loss_risk_ratio = stop_loss_risk_amount / max(equity, 1) * 100
            duplicate_buy_codes = sorted(
                {
                    str(item.get("code", "") or "")
                    for item in positions
                    if str(item.get("code", "") or "") in pending_buy_codes
                }
            )
            post_trade_cash_ratio = (cash - pending_buy_amount) / max(equity, 1) * 100

            metrics[mode] = {
                "position_count": n_pos,
                "cash_ratio": round(cash_ratio, 2),
                "exposure_ratio": round(exposure_ratio, 2),
                "max_position_ratio": round(max_position_ratio, 2),
                "stop_loss_missing": stop_loss_missing,
                "stop_loss_risk_ratio": round(stop_loss_risk_ratio, 2),
                "pending_buy_amount": round(pending_buy_amount, 2),
                "post_trade_cash_ratio": round(post_trade_cash_ratio, 2),
                "duplicate_buy_codes": duplicate_buy_codes,
            }

            checks.append({"name": f"{label}持仓数", "value": n_pos, "ok": n_pos < 10})
            checks.append({"name": f"{label}现金比例", "value": round(cash_ratio, 1), "ok": cash_ratio >= 10})
            checks.append({"name": f"{label}仓位暴露", "value": round(exposure_ratio, 1), "ok": exposure_ratio <= 90})
            checks.append({"name": f"{label}单票集中度", "value": round(max_position_ratio, 1), "ok": max_position_ratio <= 35})
            checks.append({"name": f"{label}止损缺失", "value": stop_loss_missing, "ok": stop_loss_missing == 0})
            checks.append({"name": f"{label}止损风险", "value": round(stop_loss_risk_ratio, 1), "ok": stop_loss_risk_ratio <= 8})
            if pending_buy_amount > 0:
                checks.append({
                    "name": f"{label}执行后现金比例",
                    "value": round(post_trade_cash_ratio, 1),
                    "ok": post_trade_cash_ratio >= 10,
                })
            if n_pos >= 10:
                warnings.append(f"{label}持仓{n_pos}≥10")
            if cash_ratio < 10:
                warnings.append(f"{label}现金{cash_ratio:.0f}%<10%")
            if exposure_ratio > 90:
                warnings.append(f"{label}仓位暴露{exposure_ratio:.0f}%>90%")
            if max_position_ratio > 35:
                warnings.append(f"{label}单票集中度{max_position_ratio:.0f}%>35%")
            if stop_loss_missing:
                warnings.append(f"{label}{stop_loss_missing}个持仓缺少止损")
            if stop_loss_risk_ratio > 8:
                warnings.append(f"{label}止损风险{stop_loss_risk_ratio:.1f}%>8%")
            if pending_buy_amount > 0 and post_trade_cash_ratio < 10:
                warnings.append(f"{label}执行后现金{post_trade_cash_ratio:.0f}%<10%")
            if duplicate_buy_codes:
                warnings.append(f"{label}重复加仓: {','.join(duplicate_buy_codes[:5])}")

        try:
            risk = get_kv_json("portfolio_risk")
            if isinstance(risk, dict):
                var95 = abs(float(risk.get("var95", 0) or 0))
                drawdown = abs(float(risk.get("drawdown", 0) or 0))
                checks.append({"name": "VaR95", "value": var95, "ok": var95 <= 100000})
                checks.append({"name": "回撤", "value": round(drawdown, 4), "ok": drawdown <= 0.1})
                if var95 > 100000:
                    warnings.append(f"VaR95=¥{var95:,.0f}过高")
                if drawdown > 0.1:
                    warnings.append(f"回撤{drawdown:.1%}超10%")
        except Exception:
            pass

        sentiment = payload.get("news_sentiment", {}) or {}
        if sentiment.get("ratio", 0.5) < 0.3:
            warnings.append(f"舆情偏空(正面率{sentiment['ratio']:.0%})")
            checks.append({"name": "新闻正面率", "value": sentiment.get("ratio", 0), "ok": False})

        summary = f"⚠ {'; '.join(warnings)}" if warnings else "✅ 全部通过"
        return {
            "agent": "risk",
            "timestamp": datetime.now().isoformat(),
            "ok": not warnings,
            "warnings": warnings,
            "checks": checks,
            "metrics": metrics,
            "summary": summary,
        }


class ApprovalAgent:
    """审批智能体：在执行前逐条评估交易请求，不直接下单。"""
    NAME = "✅ 审批智能体"

    @staticmethod
    def review_decisions(decisions: list[dict], *, mode: str = "auto") -> dict:
        from core.risk.approval_service import evaluate_trade_request
        from desktop.ai_trader import _get_real_price

        approved: list[dict] = []
        rejected: list[dict] = []
        skipped: list[dict] = []
        approved_buys_for_usage: list[dict] = []

        for decision in decisions or []:
            action = str(decision.get("action", "") or "").lower()
            code = str(decision.get("code", "") or "")
            if action == "hold":
                approved.append(decision)
                continue
            if action not in {"buy", "sell"}:
                skipped.append({"decision": decision, "message": "unsupported action"})
                continue

            price = float(decision.get("price", 0) or 0)
            real_price = _get_real_price(code) if code else 0
            if real_price > 0:
                price = real_price
            shares = int(decision.get("shares", 0) or 0)
            guard = _evaluate_unattended_trade_guard(
                action=action,
                code=code,
                sector=decision.get("sector") or decision.get("industry") or decision.get("board") or "",
                price=price,
                shares=shares,
                approved_buys_in_batch=approved_buys_for_usage,
                mode=mode,
            )
            if not guard.get("approved"):
                rejected.append(
                    {
                        "action": action,
                        "code": code,
                        "name": decision.get("name", ""),
                        "message": guard.get("message", "unattended trade guard rejected"),
                        "policy": {
                            "stage": "unattended_trade_guard",
                            "guard": guard.get("policy", {}),
                        },
                    }
                )
                continue
            evaluation = evaluate_trade_request(
                mode=mode,
                action=action,
                code=code,
                name=decision.get("name", ""),
                price=price,
                shares=shares,
                reason=decision.get("reason", ""),
            )
            if evaluation.get("approved"):
                updated = dict(decision)
                updated["price"] = price
                approved.append(updated)
                if action == "buy":
                    approved_buys_for_usage.append(updated)
            else:
                rejected.append(
                    {
                        "action": action,
                        "code": code,
                        "name": decision.get("name", ""),
                        "message": evaluation.get("message", "approval rejected"),
                        "policy": evaluation.get("policy", {}),
                    }
                )

        _record_unattended_trade_usage(approved_buys_for_usage)
        bits = []
        if rejected:
            bits.append(f"拒绝 {len(rejected)} 条")
        if skipped:
            bits.append(f"跳过 {len(skipped)} 条")
        summary = f"审批通过 {len(approved)} 条" + (f"，{', '.join(bits)}" if bits else "")
        return {
            "agent": "approval",
            "timestamp": datetime.now().isoformat(),
            "approved_decisions": approved,
            "rejected_decisions": rejected,
            "skipped_decisions": skipped,
            "summary": summary,
        }


class DecisionAgent:
    """
    决策智能体：综合情报和分析结果，做最终买卖决策。
    """
    NAME = "🎯 决策智能体"

    SYSTEM_PROMPT = (
        "你是最终决策者。你的职责是：\n"
        "1. 综合情报智能体、分析智能体、验证智能体的输出\n"
        "2. 结合当前持仓情况，做出最终的买卖决策\n"
        "3. 优先采用已通过验证的候选，对存疑候选谨慎处理，对高风险候选原则上不新开仓\n"
        "4. 控制风险：单只股票不超过总资金10%，总持仓不超过10只\n"
        "5. 明确给出操作指令和理由\n\n"
        "输出严格的 JSON 格式：\n"
        '{"analysis": "一句话总结", "decisions": [\n'
        '  {"action": "buy", "code": "300502", "name": "新易盛", "price": 380, "shares": 500, "reason": "趋势强+放量突破"},\n'
        '  {"action": "sell", "code": "002049", "name": "紫光国微", "reason": "跌破止损线"},\n'
        '  {"action": "hold", "code": "688981", "name": "中芯国际", "reason": "趋势良好继续持有"}\n'
        "]}"
    )

    @staticmethod
    def decide(
        intel_prompt: str,
        analysis_prompt: str,
        verification_prompt: str,
        candidate_context: str,
        portfolio_context: str,
    ) -> str:
        """调用 LLM 做最终决策。"""
        from desktop.ai_trader import _call_llm

        prompt = (
            f"以下是情报智能体、分析智能体、验证智能体的报告，请做出最终交易决策。\n\n"
            f"{intel_prompt}\n\n"
            f"{analysis_prompt}\n\n"
            f"{verification_prompt}\n\n"
            f"{candidate_context}\n\n"
            f"{portfolio_context}\n\n"
            f"请输出 JSON 格式的交易决策："
        )
        return _call_llm(prompt, system=DecisionAgent.SYSTEM_PROMPT)


def _detect_regime(intel: dict) -> str:
    """基于情报判断市场环境。"""
    m = intel.get("market", {})
    up = m.get("up", 0)
    down = m.get("down", 0)
    total = m.get("total", 1)
    if total == 0:
        return "数据不足"
    ratio = up / max(total, 1)
    if ratio > 0.65:
        return "🟢 强势（多数上涨，可积极操作）"
    elif ratio > 0.45:
        return "🟡 震荡（涨跌参半，精选个股）"
    else:
        return "🔴 弱势（多数下跌，控制仓位）"


def _init_memory_table():
    ensure_decision_memory_table()


_init_memory_table()


def _save_decision_memory(result: dict):
    """保存完整决策上下文到数据库，供后续校准。"""
    save_decision_memory_core(result)


def calibrate_decisions(days_after: int = 5) -> list[dict]:
    """
    校准历史决策：检查 N 天前的买入决策，实际收益是多少。
    更新 actual_results 和 calibrated 字段。
    """
    return calibrate_decisions_core(days_after=days_after)


def get_decision_accuracy(limit: int = 50) -> dict:
    """统计 AI 决策的历史准确率。"""
    return get_decision_accuracy_core(limit=limit)


def run_multi_agent_cycle(boards: list[str] = None, mode: str = "full_auto",
                          execute: bool = True, persist_memory: bool = True,
                          traceparent: str = "") -> dict:
    """
    多智能体协同决策：情报 → 分析 → 验证 → 决策 → 执行。
    execute=False 时只做分析不执行（非交易时间）。
    """
    if not boards:
        return {"error": "未指定板块", "timestamp": "", "steps": [], "decisions": [], "exec_results": ["未指定板块"]}

    agent_trace: list[dict] = []
    root_span = start_span(
        "agent.multi_agent_cycle",
        trace_id=create_trace_id("agent-cycle"),
        traceparent=traceparent,
        metadata={
            "kind": "agent_pipeline",
            "mode": mode,
            "boards": list(boards),
            "execute": bool(execute),
        },
    )
    root_traceparent = root_span.get("traceparent", "")

    result = {
        "timestamp": datetime.now().isoformat(),
        "mode": mode,
        "steps": [],
        "agent_trace": agent_trace,
        "trace": {
            "trace_id": root_span.get("trace_id", ""),
            "trace_id_hex": root_span.get("trace_id_hex", ""),
            "traceparent": root_traceparent,
            "root_span_id": root_span.get("span_id", ""),
        },
    }

    # Step 1: 情报智能体
    _log.info("Step 1: Intelligence Agent gathering...")
    intel = _agent_trace_step(
        agent_trace,
        root_traceparent,
        "intelligence",
        "sense",
        lambda: IntelligenceAgent.gather(boards),
        inputs={"boards": boards},
    )
    intel_prompt = IntelligenceAgent.to_prompt(intel)
    result["steps"].append({
        "agent": IntelligenceAgent.NAME,
        "status": "✅ 完成",
        "summary": f"采集 {intel.get('market', {}).get('total', 0)} 只股票, {len(intel.get('events', []))} 条事件",
        "output": intel_prompt,
    })

    # Step 2: 分析智能体
    _log.info("Step 2: Analysis Agent analyzing...")
    analysis = _agent_trace_step(
        agent_trace,
        root_traceparent,
        "analysis",
        "analyze",
        lambda: AnalysisAgent.analyze(intel, boards),
        inputs={"intel": intel, "boards": boards},
    )
    analysis_prompt = AnalysisAgent.to_prompt(analysis)
    result["steps"].append({
        "agent": AnalysisAgent.NAME,
        "status": "✅ 完成",
        "summary": f"评分 {len(analysis.get('candidates', []))} 只候选, 环境: {analysis.get('market_regime', '-')}",
        "output": analysis_prompt,
    })

    # Step 3: 验证智能体
    _log.info("Step 3: Verification Agent verifying...")
    verification = _agent_trace_step(
        agent_trace,
        root_traceparent,
        "verification",
        "verify",
        lambda: VerificationAgent.verify(analysis),
        inputs={"analysis": analysis},
    )
    verification_prompt = VerificationAgent.to_prompt(verification)
    candidate_context = _build_verified_candidate_context(verification)
    verified_count = len(verification.get("verified_candidates", []))
    questionable_count = len(verification.get("questionable_candidates", []))
    rejected_count = len(verification.get("rejected_candidates", []))
    result["verification"] = verification
    result["steps"].append({
        "agent": VerificationAgent.NAME,
        "status": "✅ 完成",
        "summary": f"通过 {verified_count} 只, 存疑 {questionable_count} 只, 高风险 {rejected_count} 只",
        "output": verification_prompt,
    })

    # Step 4: 构建持仓上下文
    from desktop.ai_trader import _build_portfolio_context
    portfolio = _agent_trace_step(
        agent_trace,
        root_traceparent,
        "portfolio_context",
        "context",
        lambda: _build_portfolio_context(mode),
        inputs={"mode": mode},
    )

    # Step 5: 决策智能体
    _log.info("Step 4: Decision Agent deciding...")
    response = _agent_trace_step(
        agent_trace,
        root_traceparent,
        "decision",
        "decide",
        lambda: DecisionAgent.decide(
            intel_prompt,
            analysis_prompt,
            verification_prompt,
            candidate_context,
            portfolio,
        ),
        inputs={
            "intel_prompt_len": len(intel_prompt),
            "analysis_prompt_len": len(analysis_prompt),
            "verification_prompt_len": len(verification_prompt),
            "candidate_context_len": len(candidate_context),
        },
    )
    result["steps"].append({
        "agent": DecisionAgent.NAME,
        "status": "✅ 完成",
        "summary": "已输出决策",
        "output": response,
    })

    # 解析决策
    import json as _json
    try:
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            parsed = _json.loads(response[start:end])
        else:
            parsed = {"analysis": response, "decisions": []}
    except Exception:
        parsed = {"analysis": response, "decisions": []}

    raw_decisions = parsed.get("decisions", [])
    guardrails = _agent_trace_step(
        agent_trace,
        root_traceparent,
        "verification_guardrail",
        "guardrail",
        lambda: _apply_verification_guardrails(raw_decisions, verification),
        inputs={"raw_decisions": raw_decisions, "verification": verification},
    )
    result["raw_decisions"] = raw_decisions
    result["decision_guardrails"] = guardrails
    result["decisions"] = guardrails.get("filtered_decisions", raw_decisions)
    result["analysis"] = parsed.get("analysis", "")
    result["steps"].append({
        "agent": "🛂 验证守门",
        "status": "✅ 完成",
        "summary": guardrails.get("summary", "未触发额外约束"),
        "output": json.dumps(
            {
                "blocked_buys": guardrails.get("blocked_buys", []),
                "annotated_buys": guardrails.get("annotated_buys", []),
            },
            ensure_ascii=False,
        ),
    })

    # Step 6: 执行（仅在交易时间）
    if result["decisions"] and execute:
        from desktop.ai_trader import execute_ai_decisions
        exec_results = _agent_trace_step(
            agent_trace,
            root_traceparent,
            "execution_engine",
            "execute",
            lambda: execute_ai_decisions(result["decisions"], mode=mode),
            inputs={"decisions": result["decisions"], "mode": mode},
        )
        result["steps"].append({
            "agent": "⚡ 执行引擎",
            "status": "✅ 完成",
            "summary": f"执行 {len(exec_results)} 条",
            "output": "\n".join(exec_results),
        })
        result["exec_results"] = exec_results
    elif result["decisions"] and not execute:
        n = len(result["decisions"])
        result["steps"].append({
            "agent": "⏳ 执行引擎",
            "status": "⏸️ 等待开盘",
            "summary": f"{n} 条决策待执行（非交易时间）",
            "output": "",
        })
        result["exec_results"] = [f"⏳ {n} 条决策已生成，等待交易时间执行"]
    else:
        result["exec_results"] = ["暂无操作"]

    # Step 7: 保存决策记忆（供后续学习和校准）
    if persist_memory:
        _agent_trace_step(
            agent_trace,
            root_traceparent,
            "decision_memory",
            "memory",
            lambda: _save_decision_memory(result),
            inputs={
                "decisions": result.get("decisions", []),
                "raw_decisions": result.get("raw_decisions", []),
                "guardrails": result.get("decision_guardrails", {}),
            },
        )

    # Step 8: 更新跟踪止损
    if mode == "full_auto":
        try:
            from desktop.ai_trader import update_trailing_stops
            stop_updates = _agent_trace_step(
                agent_trace,
                root_traceparent,
                "risk_engine",
                "risk",
                lambda: update_trailing_stops(mode),
                inputs={"mode": mode},
            )
            if stop_updates:
                result["steps"].append({
                    "agent": "🛡️ 风控引擎",
                    "status": "✅ 完成",
                    "summary": f"ATR跟踪止损更新 {len(stop_updates)} 只",
                    "output": "\n".join(stop_updates),
                })
                result["exec_results"].extend(stop_updates)
        except Exception:
            pass

    root_span.setdefault("metadata", {})["output_summary"] = {
        "steps": len(result.get("steps", []) or []),
        "decisions": len(result.get("decisions", []) or []),
        "trace_spans": len(agent_trace),
    }
    root_finished = finish_span(root_span, status="ok")
    result["trace"]["duration_ms"] = round(float(root_finished.get("duration_ms", 0.0) or 0.0), 3)
    result["trace"]["status"] = root_finished.get("status", "ok")
    return result
