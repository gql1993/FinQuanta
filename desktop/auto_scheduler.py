"""
定时自动决策 + 微信推送
每天 10:00 和 14:00 自动运行 AI 决策，结果推送到微信。

两种运行方式:
  1. 客户端内置定时器（客户端开着就行）
  2. Windows 计划任务（独立运行，不需要客户端）
     python -m desktop.auto_scheduler
"""
import os
import sys
import json
import logging
from datetime import datetime, date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from desktop.data_access import get_kv_json, set_kv_json

_log = logging.getLogger("auto_scheduler")

SCHEDULE_TIMES = ["10:00", "14:00"]


def _should_run_today() -> bool:
    """检查今天是否为交易日（简单判断：周一到周五）。"""
    today = date.today()
    if today.weekday() >= 5:
        return False
    # 检查节假日
    holidays_path = os.path.join("data_cache", "cn_holidays.json")
    if os.path.exists(holidays_path):
        try:
            with open(holidays_path, "r", encoding="utf-8") as f:
                holidays = json.load(f)
            if today.isoformat() in holidays:
                return False
        except Exception:
            pass
    return True


def _get_last_run() -> str:
    """获取上次运行时间。"""
    try:
        v = get_kv_json("auto_last_run")
        if v is None:
            return ""
        if isinstance(v, str):
            return v
        return json.dumps(v)
    except Exception:
        return ""


def _set_last_run(ts: str):
    try:
        set_kv_json("auto_last_run", ts)
    except Exception:
        pass


def run_scheduled_task(board: str = "人工智能", boards: list = None) -> dict:
    """执行一次定时任务：四仓决策 + 推送。"""
    from desktop.ai_trader import run_ai_decision, run_auto_cycle, run_full_auto_cycle

    if not boards:
        boards = [board]

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _log.info(f"scheduled task start: {ts}")

    results = {
        "time": ts,
        "full_auto_results": [],
        "auto_results": [],
        "manual_suggestions": [],
        "pushed": False,
    }

    # 1) 完全自主仓：AI全权决策+自动执行
    try:
        full_auto_results = run_full_auto_cycle(boards)
        results["full_auto_results"] = full_auto_results
        _log.info(f"full_auto_cycle: {len(full_auto_results)} results")
    except Exception as e:
        results["full_auto_results"] = [f"完全自主仓失败: {e}"]
        _log.error(f"full_auto_cycle error: {e}")

    # 2) AI推荐仓：AI决策+自动执行
    try:
        auto_results = run_auto_cycle(boards[0])
        results["auto_results"] = auto_results
        _log.info(f"auto_cycle: {len(auto_results)} results")
    except Exception as e:
        results["auto_results"] = [f"AI推荐仓失败: {e}"]
        _log.error(f"auto_cycle error: {e}")

    # 3) 构建推送消息
    msg = _build_push_message(results)

    # 4) 推送到微信
    try:
        from signal_push import push_signal
        push_result = push_signal(f"📊 AI 量化日报 {ts[:10]}", msg)
        results["pushed"] = any(push_result.values()) if push_result else False
        _log.info(f"push result: {push_result}")
    except Exception as e:
        _log.error(f"push error: {e}")

    _set_last_run(ts)

    # 5) 保存日报到 SQLite
    try:
        set_kv_json(f"daily_report_{ts[:10]}", results)
    except Exception:
        pass

    return results


def _build_push_message(results: dict) -> str:
    """构建微信推送消息（三仓，格式化版）。"""
    lines = []
    ts = results.get("time", "")
    lines.append(f"📊 AI量化日报")
    lines.append(f"　　时间: {ts}")
    lines.append("")

    # 1. 完全自主仓
    lines.append("1. 🟣 完全自主仓（AI全权决策）")
    for i, r in enumerate(results.get("full_auto_results", []), 1):
        lines.append(f"　　({i}) {r}")
    if not results.get("full_auto_results"):
        lines.append("　　暂无操作")
    lines.append("")

    # 2. AI推荐仓
    lines.append("2. 🔵 AI推荐仓（定时自动触发）")
    for i, r in enumerate(results.get("auto_results", []), 1):
        lines.append(f"　　({i}) {r}")
    if not results.get("auto_results"):
        lines.append("　　暂无操作")
    lines.append("")

    # 3. 仓位对比
    try:
        from desktop.ai_portfolio import get_comparison
        comp = get_comparison()
        lines.append("3. 📊 仓位对比")
        for i, (key, label) in enumerate([
            ("full_auto", "完全自主"), ("auto", "AI推荐"),
            ("custom", "自定义"), ("quantum", "量子仓"),
        ], 1):
            c = comp.get(key, {})
            lines.append(
                f"　　({i}) {label}: 收益{c.get('return_pct', 0):+.2f}%  "
                f"胜率{c.get('win_rate', 0):.0f}%  "
                f"交易{c.get('total_trades', 0)}笔"
            )
    except Exception:
        pass

    return "\n".join(lines)


def check_and_run(board: str = "人工智能", boards: list = None) -> dict | None:
    """检查是否到了定时任务时间，如果到了就执行。"""
    if not _should_run_today():
        return None

    now = datetime.now()
    current_time = now.strftime("%H:%M")
    last_run = _get_last_run()
    today_str = now.strftime("%Y-%m-%d")

    for schedule_time in SCHEDULE_TIMES:
        run_key = f"{today_str} {schedule_time}"
        if current_time >= schedule_time and last_run < run_key:
            _log.info(f"triggered: {run_key}")
            return run_scheduled_task(board, boards=boards)

    return None


# 独立运行入口（Windows 计划任务用）
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(message)s",
        handlers=[
            logging.FileHandler(os.path.join("data_cache", "scheduler.log"), encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

    board = sys.argv[1] if len(sys.argv) > 1 else "人工智能"
    print(f"手动执行定时任务（板块: {board}）...")
    result = run_scheduled_task(board)
    print(f"完成: 自主仓 {len(result['auto_results'])} 条, 推荐 {len(result['manual_suggestions'])} 条, 推送 {'成功' if result['pushed'] else '未推送'}")
