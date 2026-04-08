from __future__ import annotations

import re
from typing import Any


_TIME_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
_NUMBER_RE = re.compile(r"(\d+(?:\.\d+)?)")
_CODE_RE = re.compile(r"\b(\d{6})\b")
_SHARES_RE = re.compile(r"(\d+)\s*股")
_PRICE_RE = re.compile(r"(?:(?:成本|价格|买入价|持仓价|现价)(?:改成|调整为|设为|为|到)?|按|@)\s*([0-9]+(?:\.[0-9]+)?)")
_STOP_RE = re.compile(r"(?:止损|止损价)(?:改成|调整为|设为|为|到)?\s*([0-9]+(?:\.[0-9]+)?)")

_TASK_ALIASES = {
    "刷新实时行情": "fetch_data",
    "实时行情": "fetch_data",
    "刷新k线日线": "refresh_kline",
    "刷新k线": "refresh_kline",
    "k线日线": "refresh_kline",
    "补全板块成分股": "refresh_boards",
    "板块成分股": "refresh_boards",
    "选股雷达扫描": "scan_stocks",
    "选股扫描": "scan_stocks",
    "推送强烈买入": "push_strong",
    "强烈买入": "push_strong",
    "短期选股": "short_term",
    "自定义仓top3": "custom_top3",
    "ai四仓决策": "ai_decision",
    "四仓决策": "ai_decision",
    "自动卖出检查": "auto_sell",
    "量子仓优化": "quantum_buy",
    "风险计算": "risk_calc",
    "关注股异常扫描": "watchlist_scan",
    "走势验证校准": "trend_verify",
    "走势验证": "trend_verify",
    "自定义仓校准": "custom_cal",
    "日报推送": "daily_report",
    "自主学习进化": "auto_learn",
    "自主学习": "auto_learn",
    "周期性回测": "auto_backtest",
    "策略回测": "auto_backtest",
    "止损止盈预警": "alert_check",
}


def _normalize_text(text: str) -> str:
    return (text or "").strip().replace("：", ":").replace("，", ",")


def _extract_time(text: str) -> str | None:
    m = _TIME_RE.search(text)
    if not m:
        return None
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def _extract_number(text: str) -> float | None:
    m = _NUMBER_RE.search(text)
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def _money_to_amount(text: str) -> float | None:
    number = _extract_number(text)
    if number is None:
        return None
    if "亿" in text:
        return number * 100000000
    if "万" in text:
        return number * 10000
    return number


def _extract_code(text: str) -> str | None:
    m = _CODE_RE.search(text)
    return m.group(1) if m else None


def _extract_shares(text: str) -> int | None:
    m = _SHARES_RE.search(text)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def _extract_price(text: str) -> float | None:
    m = _PRICE_RE.search(text)
    if m:
        try:
            return float(m.group(1))
        except Exception:
            return None
    return None


def _extract_stop(text: str) -> float | None:
    m = _STOP_RE.search(text)
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def _match_task_key(text: str) -> str | None:
    lowered = text.lower()
    for phrase, task_key in sorted(_TASK_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if phrase in text or phrase.lower() in lowered:
            return task_key
    return None


def parse_intent(text: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    第一版使用规则解析，后续可替换为 LLM + 规则混合解析。
    返回结果必须保持结构化，便于 UI 和执行器消费。
    """
    normalized = _normalize_text(text)
    lower = normalized.lower()
    intent = {
        "intent": "",
        "target": "",
        "action": "",
        "action_key": "",
        "arguments": {},
        "matched": False,
    }

    if any(key in normalized for key in ["总资产", "系统总览", "系统状态", "市场状态", "持仓数", "可用现金"]):
        intent.update(
            {
                "intent": "query",
                "target": "system",
                "action": "system_snapshot",
                "action_key": "query.system_snapshot",
                "matched": True,
            }
        )
        return intent

    task_key = _match_task_key(normalized)
    if task_key and ("改" in normalized or "调整" in normalized) and ("时间" in normalized or _extract_time(normalized)):
        schedule_time = _extract_time(normalized)
        intent.update(
            {
                "intent": "update",
                "target": "scheduler",
                "action": "scheduler_time",
                "action_key": "update.scheduler_time",
                "arguments": {"task_key": task_key, "schedule_time": schedule_time},
                "matched": True,
            }
        )
        return intent

    if "走势验证" in normalized and ("为什么" in normalized or "为空" in normalized or "空的" in normalized):
        intent.update(
            {
                "intent": "explain",
                "target": "trend_verify",
                "action": "trend_verify_empty",
                "action_key": "explain.trend_verify_empty",
                "matched": True,
            }
        )
        return intent

    if "走势验证" in normalized and ("校准" in normalized or "重新跑" in normalized or "重跑" in normalized):
        intent.update(
            {
                "intent": "run",
                "target": "trend_verify",
                "action": "calibrate_trend_verify",
                "action_key": "run.calibrate_trend_verify",
                "matched": True,
            }
        )
        return intent

    if ("同步" in normalized or "补日线" in normalized or "刷新日线" in normalized) and "走势验证" not in normalized:
        intent.update(
            {
                "intent": "run",
                "target": "daily_kline",
                "action": "refresh_latest_kline",
                "action_key": "run.refresh_latest_kline",
                "arguments": {"max_codes": 500, "threads": 8},
                "matched": True,
            }
        )
        return intent

    if "刷新" in normalized and ("快照" in normalized or "运行中心" in normalized):
        intent.update(
            {
                "intent": "run",
                "target": "system_snapshot",
                "action": "refresh_snapshot",
                "action_key": "run.refresh_snapshot",
                "matched": True,
            }
        )
        return intent

    if ("任务" in normalized and ("失败" in normalized or "最近" in normalized)) or "task" in lower:
        intent.update(
            {
                "intent": "query",
                "target": "task_runs",
                "action": "task_runs",
                "action_key": "query.task_runs",
                "arguments": {"limit": 10},
                "matched": True,
            }
        )
        return intent

    if "系统事件" in normalized or ("最近" in normalized and "事件" in normalized):
        intent.update(
            {
                "intent": "query",
                "target": "system_events",
                "action": "system_events",
                "action_key": "query.system_events",
                "arguments": {"limit": 10},
                "matched": True,
            }
        )
        return intent

    if "走势验证" in normalized and ("概况" in normalized or "统计" in normalized or "准确率" in normalized):
        intent.update(
            {
                "intent": "query",
                "target": "trend_verify",
                "action": "trend_verify_summary",
                "action_key": "query.trend_verify_summary",
                "matched": True,
            }
        )
        return intent

    if ("现金" in normalized and "改" in normalized) or ("手动仓" in normalized and "现金" in normalized):
        amount = _money_to_amount(normalized)
        intent.update(
            {
                "intent": "update",
                "target": "manual_portfolio",
                "action": "manual_portfolio_cash",
                "action_key": "update.manual_portfolio_cash",
                "arguments": {"cash": amount},
                "matched": True,
            }
        )
        return intent

    if "手动仓" in normalized and any(key in normalized for key in ["新增", "添加", "加入"]) and _extract_code(normalized):
        intent.update(
            {
                "intent": "update",
                "target": "manual_portfolio",
                "action": "manual_portfolio_position_add",
                "action_key": "update.manual_portfolio_position_add",
                "arguments": {
                    "code": _extract_code(normalized),
                    "shares": _extract_shares(normalized),
                    "entry_price": _extract_price(normalized),
                    "stop_loss": _extract_stop(normalized),
                },
                "matched": True,
            }
        )
        return intent

    if "手动仓" in normalized and any(key in normalized for key in ["删除", "移除", "去掉"]) and _extract_code(normalized):
        intent.update(
            {
                "intent": "update",
                "target": "manual_portfolio",
                "action": "manual_portfolio_position_remove",
                "action_key": "update.manual_portfolio_position_remove",
                "arguments": {
                    "code": _extract_code(normalized),
                    "sell_price": _extract_price(normalized),
                },
                "matched": True,
            }
        )
        return intent

    if "手动仓" in normalized and any(key in normalized for key in ["修改", "改成", "调整"]) and _extract_code(normalized):
        entry_price = _extract_price(normalized)
        shares = _extract_shares(normalized)
        stop_loss = _extract_stop(normalized)
        if any(v is not None for v in [entry_price, shares, stop_loss]):
            intent.update(
                {
                    "intent": "update",
                    "target": "manual_portfolio",
                    "action": "manual_portfolio_position_edit",
                    "action_key": "update.manual_portfolio_position_edit",
                    "arguments": {
                        "code": _extract_code(normalized),
                        "shares": shares,
                        "entry_price": entry_price,
                        "stop_loss": stop_loss,
                    },
                    "matched": True,
                }
            )
            return intent

    return intent
