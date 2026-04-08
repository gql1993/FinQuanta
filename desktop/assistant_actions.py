from __future__ import annotations

from datetime import date, datetime
from typing import Any

from desktop.data_access import get_repo
from desktop.platform_store import get_kv_json, set_kv_json
from desktop.snapshot_service import get_system_snapshot, save_system_snapshot
from desktop.task_orchestrator import get_recent_system_events, get_recent_task_runs
from desktop.trend_verify import calibrate, get_accuracy_stats
from desktop.data_sync import refresh_latest_kline
from desktop.daemon_scheduler import SCHEDULE


def _get_schedule_overrides() -> dict[str, str]:
    return get_kv_json("sched_time_overrides", {}) or {}


def _get_schedule_time(task_key: str) -> str | None:
    overrides = _get_schedule_overrides()
    if task_key in overrides:
        return overrides[task_key]
    for item in SCHEDULE:
        if item.get("key") == task_key:
            return item.get("time")
    return None


def _get_schedule_name(task_key: str) -> str:
    for item in SCHEDULE:
        if item.get("key") == task_key:
            return item.get("name", task_key)
    return task_key


def _get_manual_portfolio() -> dict[str, Any]:
    return get_kv_json(
        "manual_portfolio",
        {"positions": [], "cash": 1000000, "initial_capital": 1000000, "history": []},
    ) or {"positions": [], "cash": 1000000, "initial_capital": 1000000, "history": []}


def _save_manual_portfolio(pf: dict[str, Any]):
    set_kv_json("manual_portfolio", pf)
    try:
        save_system_snapshot()
    except Exception:
        pass


def _find_position(pf: dict[str, Any], code: str) -> tuple[int, dict[str, Any] | None]:
    for idx, pos in enumerate(pf.get("positions", [])):
        if pos.get("code") == code:
            return idx, pos
    return -1, None


def _lookup_stock_name(code: str) -> str:
    row = get_repo().fetchone("SELECT name FROM stock_list WHERE code=?", (code,))
    return row[0] if row and row[0] else code


def _get_latest_close(code: str) -> float | None:
    row = get_repo().fetchone(
        "SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 1",
        (code,),
    )
    if not row or row[0] is None:
        return None
    return float(row[0])


def _append_pf_history(pf: dict[str, Any], payload: dict[str, Any]):
    pf.setdefault("history", []).append(payload)


def _position_preview(pos: dict[str, Any] | None) -> dict[str, Any]:
    if not pos:
        return {}
    return {
        "code": pos.get("code"),
        "name": pos.get("name"),
        "shares": pos.get("shares"),
        "entry_price": pos.get("entry_price"),
        "stop_loss": pos.get("stop_loss"),
        "entry_date": pos.get("entry_date"),
    }


def preview_intent(intent: dict[str, Any]) -> dict[str, Any]:
    action_key = intent.get("action_key", "")
    args = dict(intent.get("arguments") or {})
    if action_key == "update.scheduler_time":
        task_key = args.get("task_key", "")
        new_time = args.get("schedule_time")
        return {
            "title": "修改调度时间",
            "before": {"task_key": task_key, "task_name": _get_schedule_name(task_key), "schedule_time": _get_schedule_time(task_key)},
            "after": {"task_key": task_key, "task_name": _get_schedule_name(task_key), "schedule_time": new_time},
        }
    if action_key == "update.manual_portfolio_cash":
        pf = get_kv_json("manual_portfolio", {"positions": [], "cash": 1000000, "initial_capital": 1000000}) or {}
        return {
            "title": "修改手动仓现金",
            "before": {"cash": pf.get("cash", 0)},
            "after": {"cash": args.get("cash")},
        }
    if action_key == "update.manual_portfolio_position_add":
        pf = _get_manual_portfolio()
        entry_price = args.get("entry_price") or 0
        shares = args.get("shares") or 0
        est_cost = round(float(entry_price) * int(shares) * 1.0003, 2) if entry_price and shares else None
        return {
            "title": "新增手动仓持仓",
            "before": {"cash": pf.get("cash", 0), "position_count": len(pf.get("positions", []))},
            "after": {
                "code": args.get("code"),
                "shares": shares,
                "entry_price": entry_price,
                "stop_loss": args.get("stop_loss"),
                "estimated_cash_after": round(pf.get("cash", 0) - est_cost, 2) if est_cost is not None else None,
            },
        }
    if action_key == "update.manual_portfolio_position_remove":
        pf = _get_manual_portfolio()
        _, pos = _find_position(pf, args.get("code", ""))
        settle = args.get("sell_price") or (pos.get("entry_price") if pos else None)
        estimated_revenue = round(float(settle) * int(pos.get("shares", 0)) * (1 - 0.0013), 2) if pos and settle else None
        return {
            "title": "删除手动仓持仓",
            "before": {"cash": pf.get("cash", 0), "position": _position_preview(pos)},
            "after": {
                "remove_code": args.get("code"),
                "settle_price": settle,
                "estimated_cash_after": round(pf.get("cash", 0) + estimated_revenue, 2) if estimated_revenue is not None else None,
            },
        }
    if action_key == "update.manual_portfolio_position_edit":
        pf = _get_manual_portfolio()
        _, pos = _find_position(pf, args.get("code", ""))
        return {
            "title": "修改手动仓持仓",
            "before": {"cash": pf.get("cash", 0), "position": _position_preview(pos)},
            "after": {
                "code": args.get("code"),
                "shares": args.get("shares"),
                "entry_price": args.get("entry_price"),
                "stop_loss": args.get("stop_loss"),
            },
        }
    if action_key == "run.calibrate_trend_verify":
        stats = get_accuracy_stats()
        return {
            "title": "执行走势验证校准",
            "before": {"total_signals": stats.get("total", 0), "accuracy": stats.get("accuracy", 0)},
            "after": {"action": "calibrate"},
        }
    if action_key == "run.refresh_latest_kline":
        return {
            "title": "补同步最新日线",
            "before": {"scope": "selected_codes_or_default"},
            "after": {"arguments": args},
        }
    return {"title": action_key or "unknown_action", "before": {}, "after": args}


def dispatch_intent(intent: dict[str, Any]) -> dict[str, Any]:
    kind = intent.get("intent")
    if kind == "query":
        return run_query(intent)
    if kind == "explain":
        return run_explain(intent)
    if kind == "run":
        return run_task_action(intent)
    if kind == "update":
        return run_update_action(intent)
    raise ValueError(f"Unsupported intent: {kind}")


def run_query(intent: dict[str, Any]) -> dict[str, Any]:
    action_key = intent.get("action_key", "")
    if action_key == "query.system_snapshot":
        snap = get_system_snapshot()
        return {
            "type": "query_result",
            "title": "系统总览",
            "summary": f"总资产 ¥{snap.get('totals', {}).get('equity', 0):,.0f}",
            "data": snap,
        }
    if action_key == "query.trend_verify_summary":
        stats = get_accuracy_stats()
        return {
            "type": "query_result",
            "title": "走势验证概况",
            "summary": f"总信号 {stats.get('total', 0)} 个，准确率 {stats.get('accuracy', 0):.1f}%",
            "data": stats,
        }
    if action_key == "query.task_runs":
        rows = get_recent_task_runs(int(intent.get("arguments", {}).get("limit", 10)))
        return {"type": "query_result", "title": "最近任务", "summary": f"{len(rows)} 条", "data": rows}
    if action_key == "query.system_events":
        rows = get_recent_system_events(int(intent.get("arguments", {}).get("limit", 10)))
        return {"type": "query_result", "title": "最近系统事件", "summary": f"{len(rows)} 条", "data": rows}
    raise ValueError(f"Unsupported query action: {action_key}")


def run_explain(intent: dict[str, Any]) -> dict[str, Any]:
    action_key = intent.get("action_key", "")
    if action_key != "explain.trend_verify_empty":
        raise ValueError(f"Unsupported explain action: {action_key}")
    stats = get_accuracy_stats()
    repo = get_repo()
    daily_latest = (repo.fetchone("SELECT MAX(date) FROM daily_kline", ()) or [""])[0] or ""
    total = (repo.fetchone("SELECT COUNT(*) FROM trend_verify", ()) or (0,))[0]
    missing_1d = (repo.fetchone("SELECT COUNT(*) FROM trend_verify WHERE pnl_1d IS NULL", ()) or (0,))[0]
    missing_5d = (repo.fetchone("SELECT COUNT(*) FROM trend_verify WHERE pnl_5d IS NULL", ()) or (0,))[0]
    reasons = [
        "右侧周期收益是按信号日后的交易日数量逐步填充，不够天数时会留空。",
        "若 daily_kline 最新日期落后于 trend_verify 的 signal_date，新信号也会暂时为空。",
    ]
    return {
        "type": "explain_result",
        "title": "走势验证为空原因",
        "summary": f"总记录 {total}，1日空值 {missing_1d}，5日空值 {missing_5d}",
        "data": {
            "daily_kline_latest": daily_latest,
            "verify_stats": stats,
            "reasons": reasons,
            "suggested_actions": [
                "run.refresh_latest_kline",
                "run.calibrate_trend_verify",
            ],
        },
    }


def run_task_action(intent: dict[str, Any]) -> dict[str, Any]:
    action_key = intent.get("action_key", "")
    args = dict(intent.get("arguments") or {})
    if action_key == "run.refresh_snapshot":
        snap = save_system_snapshot()
        return {"type": "task_result", "title": "刷新系统快照", "summary": "已刷新", "data": snap}
    if action_key == "run.calibrate_trend_verify":
        result = calibrate()
        stats = get_accuracy_stats()
        return {
            "type": "task_result",
            "title": "走势验证校准",
            "summary": f"更新 {result.get('updated', 0)} 条",
            "data": {"result": result, "stats": stats},
        }
    if action_key == "run.refresh_latest_kline":
        result = refresh_latest_kline(
            codes=args.get("codes"),
            max_codes=int(args.get("max_codes", 500)),
            threads=int(args.get("threads", 8)),
            stale_after_days=int(args.get("stale_after_days", 1)),
        )
        return {"type": "task_result", "title": "补同步最新日线", "summary": str(result), "data": result}
    raise ValueError(f"Unsupported run action: {action_key}")


def run_update_action(intent: dict[str, Any]) -> dict[str, Any]:
    action_key = intent.get("action_key", "")
    args = dict(intent.get("arguments") or {})
    if action_key == "update.scheduler_time":
        task_key = args.get("task_key", "")
        schedule_time = args.get("schedule_time")
        if not task_key or not schedule_time:
            raise ValueError("缺少 task_key 或 schedule_time")
        overrides = _get_schedule_overrides()
        overrides[task_key] = schedule_time
        set_kv_json("sched_time_overrides", overrides)
        return {
            "type": "update_result",
            "title": "调度时间已更新",
            "summary": f"{_get_schedule_name(task_key)} -> {schedule_time}",
            "data": {"task_key": task_key, "task_name": _get_schedule_name(task_key), "schedule_time": schedule_time, "overrides": overrides},
        }
    if action_key == "update.manual_portfolio_cash":
        cash = args.get("cash")
        if cash is None or float(cash) < 0:
            raise ValueError("现金金额无效")
        pf = _get_manual_portfolio()
        pf["cash"] = round(float(cash), 2)
        _append_pf_history(
            pf,
            {
                "time": datetime.now().isoformat(),
                "action": "ADJUST_CASH",
                "cash": pf["cash"],
            },
        )
        _save_manual_portfolio(pf)
        return {
            "type": "update_result",
            "title": "手动仓现金已更新",
            "summary": f"cash={pf['cash']:.2f}",
            "data": pf,
        }
    if action_key == "update.manual_portfolio_position_add":
        code = str(args.get("code") or "")
        shares = int(args.get("shares") or 0)
        entry_price = float(args.get("entry_price") or 0)
        stop_loss = args.get("stop_loss")
        if not code or len(code) != 6 or not code.isdigit():
            raise ValueError("缺少有效股票代码")
        if shares <= 0 or shares % 100 != 0:
            raise ValueError("股数必须为正整数且为 100 的倍数")
        if entry_price <= 0:
            raise ValueError("新增持仓需要提供有效成本价")
        pf = _get_manual_portfolio()
        _, existing = _find_position(pf, code)
        if existing:
            raise ValueError(f"{code} 已存在，请使用修改持仓")
        cost = round(entry_price * shares * 1.0003, 2)
        if cost > float(pf.get("cash", 0)):
            raise ValueError(f"现金不足，需 {cost:.2f}，当前仅有 {pf.get('cash', 0):.2f}")
        name = _lookup_stock_name(code)
        if stop_loss is None:
            stop_loss = round(entry_price * 0.92, 2)
        new_pos = {
            "code": code,
            "name": name,
            "entry_price": round(entry_price, 2),
            "shares": shares,
            "entry_date": date.today().isoformat(),
            "stop_loss": round(float(stop_loss), 2),
        }
        pf.setdefault("positions", []).append(new_pos)
        pf["cash"] = round(float(pf.get("cash", 0)) - cost, 2)
        _append_pf_history(
            pf,
            {
                "time": datetime.now().isoformat(),
                "action": "BUY",
                "code": code,
                "name": name,
                "price": round(entry_price, 2),
                "shares": shares,
                "source": "assistant",
            },
        )
        _save_manual_portfolio(pf)
        return {
            "type": "update_result",
            "title": "手动仓持仓已新增",
            "summary": f"{code} {name} {shares}股 @ {entry_price:.2f}",
            "data": {"position": new_pos, "cash": pf["cash"]},
        }
    if action_key == "update.manual_portfolio_position_remove":
        code = str(args.get("code") or "")
        pf = _get_manual_portfolio()
        idx, pos = _find_position(pf, code)
        if idx < 0 or not pos:
            raise ValueError(f"未找到持仓 {code}")
        settle_price = float(args.get("sell_price") or _get_latest_close(code) or pos.get("entry_price") or 0)
        if settle_price <= 0:
            raise ValueError("无法获取删除持仓的结算价格")
        shares = int(pos.get("shares", 0) or 0)
        revenue = round(settle_price * shares * (1 - 0.0013), 2)
        pnl = round(revenue - float(pos.get("entry_price", 0) or 0) * shares, 2)
        pf["cash"] = round(float(pf.get("cash", 0)) + revenue, 2)
        removed = pf["positions"].pop(idx)
        _append_pf_history(
            pf,
            {
                "time": datetime.now().isoformat(),
                "action": "SELL",
                "code": code,
                "name": removed.get("name", ""),
                "price": round(settle_price, 2),
                "shares": shares,
                "pnl": pnl,
                "entry_price": removed.get("entry_price", 0),
                "entry_date": removed.get("entry_date", ""),
                "source": "assistant",
            },
        )
        _save_manual_portfolio(pf)
        return {
            "type": "update_result",
            "title": "手动仓持仓已删除",
            "summary": f"{code} {shares}股 已按 {settle_price:.2f} 移除",
            "data": {"removed": removed, "settle_price": settle_price, "pnl": pnl, "cash": pf["cash"]},
        }
    if action_key == "update.manual_portfolio_position_edit":
        code = str(args.get("code") or "")
        pf = _get_manual_portfolio()
        idx, pos = _find_position(pf, code)
        if idx < 0 or not pos:
            raise ValueError(f"未找到持仓 {code}")
        new_shares = args.get("shares")
        new_entry_price = args.get("entry_price")
        new_stop_loss = args.get("stop_loss")
        old_entry_price = float(pos.get("entry_price", 0) or 0)
        old_shares = int(pos.get("shares", 0) or 0)
        cash_delta = 0.0
        if new_shares is not None:
            new_shares = int(new_shares)
            if new_shares <= 0 or new_shares % 100 != 0:
                raise ValueError("修改后的股数必须为正整数且为 100 的倍数")
            delta_shares = new_shares - old_shares
            if delta_shares > 0:
                cash_delta = round(-delta_shares * old_entry_price * 1.0003, 2)
            elif delta_shares < 0:
                cash_delta = round((-delta_shares) * old_entry_price * (1 - 0.0013), 2)
            if float(pf.get("cash", 0)) + cash_delta < 0:
                raise ValueError("现金不足，无法增加到该持仓股数")
            pf["cash"] = round(float(pf.get("cash", 0)) + cash_delta, 2)
            pos["shares"] = new_shares
        if new_entry_price is not None:
            new_entry_price = float(new_entry_price)
            if new_entry_price <= 0:
                raise ValueError("修改后的成本价无效")
            pos["entry_price"] = round(new_entry_price, 2)
        if new_stop_loss is not None:
            pos["stop_loss"] = round(float(new_stop_loss), 2)
        pf["positions"][idx] = pos
        _append_pf_history(
            pf,
            {
                "time": datetime.now().isoformat(),
                "action": "EDIT_POSITION",
                "code": code,
                "shares": pos.get("shares"),
                "entry_price": pos.get("entry_price"),
                "stop_loss": pos.get("stop_loss"),
                "cash_delta": cash_delta,
                "source": "assistant",
            },
        )
        _save_manual_portfolio(pf)
        return {
            "type": "update_result",
            "title": "手动仓持仓已修改",
            "summary": f"{code} 已更新",
            "data": {"position": pos, "cash": pf["cash"], "cash_delta": cash_delta},
        }
    raise ValueError(f"Unsupported update action: {action_key}")
