"""
FinQuanta 后台守护调度器
替代 OpenClaw 的核心能力：7×24 定时调度 + 推送 + 主动预警。

运行方式：
  1. 命令行直接跑：python -m desktop.daemon_scheduler
  2. 注册为 Windows 服务/计划任务
  3. 客户端内嵌启动

功能：
  - 每天 9:50  拉取实时报价
  - 每天 10:00 刷新K线日线 + 三仓自动决策 + 推送
  - 每天 13:30 刷新K线日线（下午场前）
  - 每天 14:00 三仓自动决策（下午）+ 推送
  - 每天 15:30 走势验证校准 + 日报推送
  - 实时监控持仓止损线，触发预警
"""
import os
import sys
import time
import json
import re
import logging
import subprocess
import threading
from datetime import datetime, date, timedelta

from desktop.data_access import get_kv_json, get_repo, set_kv_json
from desktop.task_orchestrator import log_system_event, run_task

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_log = logging.getLogger("daemon")
_DAEMON_LEADER_KEY = "daemon_leader_lock_v1"
_LEADER_TTL_SECONDS = 180
_DAEMON_PUSH_STATUS_KEY = "daemon_push_status_v1"
_DAEMON_DUPLICATE_KEY = "daemon_duplicate_lock_v1"
_OPENCLAW_ALERT_STATE_KEY = "openclaw_daemon_alert_state"
_OPENCLAW_ALERT_POLICY_KEY = "openclaw_daemon_alert_policy"
_OPENCLAW_ALERT_POLICY_DEFAULTS = {
    "enabled": True,
    "suppress_seconds": 1800,
    "escalate_after": 3,
    "notify_on_success": False,
    "notify_on_warning": True,
    "notify_on_error": True,
    "success_summary_interval_seconds": 86400,
    "min_level": "warning",
    "default_channels": ["wechat_personal"],
    "escalation_channels": ["wechat_personal", "wecom_group_bot"],
}
_OPENCLAW_RUN_HISTORY_KEY = "openclaw_daemon_run_history"

# 全策略流水线调度表
SCHEDULE = [
    # ── 09:50 盘前准备 ──
    {"time": "09:50", "key": "fetch_data",    "name": "拉取实时行情(盘前)", "func": "_task_fetch_data"},
    {"time": "10:00", "key": "refresh_kline", "name": "刷新K线日线(上午)", "func": "_task_refresh_kline"},
    {"time": "10:02", "key": "refresh_boards","name": "补全板块成分股",    "func": "_task_refresh_boards"},
    # ── 10:05 选股+决策 ──
    {"time": "10:03", "key": "sector_rotate", "name": "板块轮动分析",     "func": "_task_sector_rotation"},
    {"time": "10:04", "key": "strat_rotate",  "name": "策略轮动评估",     "func": "_task_strategy_rotation"},
    {"time": "10:05", "key": "scan_stocks",   "name": "选股雷达扫描",     "func": "_task_scan_stocks"},
    {"time": "10:08", "key": "push_strong",   "name": "推送强烈买入信号",  "func": "_task_push_strong_buy"},
    {"time": "10:10", "key": "short_term",    "name": "短期选股+NLP",     "func": "_task_short_term"},
    {"time": "10:12", "key": "custom_top3",   "name": "自定义仓Top3买入", "func": "_task_custom_top3"},
    {"time": "10:15", "key": "ai_decision",   "name": "四仓决策(上午)",    "func": "_task_ai_decision"},
    {"time": "10:18", "key": "auto_sell",    "name": "自动卖出检查(上午)", "func": "_task_auto_sell"},
    {"time": "10:20", "key": "quantum_buy",   "name": "量子仓优化(周一)",  "func": "_task_quantum_buy"},
    {"time": "10:25", "key": "openclaw_pipeline", "name": "OpenClaw自主全流程", "func": "_task_openclaw_pipeline"},
    # ── 盘中监控（实时行情每小时刷新） ──
    {"time": "10:30", "key": "risk_calc",     "name": "风险计算(10:30)",   "func": "_task_risk_calc"},
    {"time": "11:00", "key": "fetch_data",    "name": "刷新实时行情(11:00)","func": "_task_fetch_data"},
    {"time": "11:00", "key": "watchlist_scan","name": "关注股异常(11:00)", "func": "_task_watchlist_scan"},
    {"time": "11:30", "key": "risk_calc",     "name": "风险计算(11:30)",   "func": "_task_risk_calc"},
    {"time": "12:00", "key": "fetch_data",    "name": "刷新实时行情(12:00)","func": "_task_fetch_data"},
    # ── 下午 ──
    {"time": "13:00", "key": "fetch_data",    "name": "刷新实时行情(13:00)","func": "_task_fetch_data"},
    {"time": "13:00", "key": "risk_calc",     "name": "风险计算(13:00)",   "func": "_task_risk_calc"},
    {"time": "13:30", "key": "refresh_kline", "name": "刷新K线日线(下午)", "func": "_task_refresh_kline"},
    {"time": "14:00", "key": "fetch_data",    "name": "刷新实时行情(14:00)","func": "_task_fetch_data"},
    {"time": "14:00", "key": "ai_decision",   "name": "四仓决策(下午)",    "func": "_task_ai_decision"},
    {"time": "14:05", "key": "auto_sell",    "name": "自动卖出检查(下午)", "func": "_task_auto_sell"},
    {"time": "14:00", "key": "watchlist_scan","name": "关注股异常(14:00)", "func": "_task_watchlist_scan"},
    {"time": "14:30", "key": "risk_calc",     "name": "风险计算(14:30)",   "func": "_task_risk_calc"},
    # ── 15:30 收盘复盘 ──
    {"time": "15:30", "key": "trend_verify",  "name": "走势验证校准",     "func": "_task_trend_verify"},
    {"time": "15:30", "key": "custom_cal",    "name": "自定义仓校准",     "func": "_task_custom_calibrate"},
    {"time": "15:30", "key": "daily_report",  "name": "日报推送",         "func": "_task_daily_report"},
    {"time": "15:32", "key": "record_nav",    "name": "记录每日净值",     "func": "_task_record_nav"},
    {"time": "15:35", "key": "auto_learn",    "name": "OpenClaw自主学习", "func": "_task_auto_learn"},
    {"time": "16:00", "key": "auto_backtest", "name": "周期性策略回测",   "func": "_task_auto_backtest"},
    {"time": "16:05", "key": "data_cleanup",  "name": "数据自动清理",     "func": "_task_data_cleanup"},
]

# 预警检查间隔（秒）
ALERT_INTERVAL = 300  # 每5分钟检查一次


class DaemonScheduler:
    def __init__(self, boards: list[str] = None, disabled_tasks: set = None):
        self.boards = boards or _load_openclaw_daemon_boards()
        self.disabled_tasks = disabled_tasks or set()
        self._running = True
        self._last_run = {}
        self._time_overrides = {}
        self._leader_token = ""
        self._load_last_run()
        self._load_time_overrides()

    @staticmethod
    def _now_ts() -> float:
        return time.time()

    @staticmethod
    def _is_pid_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        if pid == os.getpid():
            return True
        if os.name == "nt":
            try:
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                result = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="ignore",
                    timeout=3,
                    creationflags=flags,
                )
                return any(f'"{pid}"' in line for line in result.stdout.splitlines())
            except Exception:
                return False
        try:
            os.kill(pid, 0)
            return True
        except Exception:
            return False

    def _acquire_leader(self) -> bool:
        now_ts = self._now_ts()
        current = get_kv_json(_DAEMON_LEADER_KEY, {}) or {}
        if isinstance(current, str):
            try:
                current = json.loads(current)
            except Exception:
                current = {}
        if isinstance(current, dict):
            hb = float(current.get("heartbeat_ts", 0) or 0)
            pid = int(current.get("pid", 0) or 0)
            token = str(current.get("token", "") or "")
            if token and (now_ts - hb) < _LEADER_TTL_SECONDS and self._is_pid_alive(pid):
                set_kv_json(
                    _DAEMON_DUPLICATE_KEY,
                    {
                        "detected": True,
                        "detected_at": datetime.now().isoformat(timespec="seconds"),
                        "holder_pid": pid,
                        "holder_heartbeat_at": str(current.get("heartbeat_at", "")),
                        "candidate_pid": os.getpid(),
                    },
                )
                return False

        self._leader_token = f"{os.getpid()}-{int(now_ts)}"
        payload = {
            "token": self._leader_token,
            "pid": os.getpid(),
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "heartbeat_ts": now_ts,
            "heartbeat_at": datetime.now().isoformat(timespec="seconds"),
        }
        set_kv_json(_DAEMON_LEADER_KEY, payload)
        set_kv_json(
            _DAEMON_DUPLICATE_KEY,
            {
                "detected": False,
                "detected_at": "",
                "holder_pid": os.getpid(),
                "holder_heartbeat_at": payload.get("heartbeat_at", ""),
                "candidate_pid": 0,
            },
        )
        verify = get_kv_json(_DAEMON_LEADER_KEY, {}) or {}
        if isinstance(verify, str):
            try:
                verify = json.loads(verify)
            except Exception:
                verify = {}
        return isinstance(verify, dict) and str(verify.get("token", "")) == self._leader_token

    def _renew_leader(self):
        if not self._leader_token:
            return
        payload = {
            "token": self._leader_token,
            "pid": os.getpid(),
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "heartbeat_ts": self._now_ts(),
            "heartbeat_at": datetime.now().isoformat(timespec="seconds"),
        }
        set_kv_json(_DAEMON_LEADER_KEY, payload)

    def _release_leader(self):
        if not self._leader_token:
            return
        current = get_kv_json(_DAEMON_LEADER_KEY, {}) or {}
        if isinstance(current, str):
            try:
                current = json.loads(current)
            except Exception:
                current = {}
        if isinstance(current, dict) and str(current.get("token", "")) == self._leader_token:
            set_kv_json(_DAEMON_LEADER_KEY, {})
        self._leader_token = ""

    def _load_last_run(self):
        try:
            raw = get_kv_json("daemon_last_run", None)
            if raw is None:
                self._last_run = {}
            elif isinstance(raw, dict):
                self._last_run = raw
            elif isinstance(raw, str):
                self._last_run = json.loads(raw)
            else:
                self._last_run = {}
        except Exception:
            self._last_run = {}

    def _save_last_run(self):
        try:
            set_kv_json("daemon_last_run", self._last_run)
        except Exception:
            pass

    def _load_time_overrides(self):
        try:
            raw = get_kv_json("sched_time_overrides", None)
            self._time_overrides = raw if isinstance(raw, dict) else {}
        except Exception:
            self._time_overrides = {}

    def _get_task_time(self, task: dict) -> str:
        key = task.get("key", "")
        override = self._time_overrides.get(key)
        return override or task.get("time", "")

    def _is_trading_day(self) -> bool:
        d = date.today()
        if d.weekday() >= 5:
            return False
        try:
            from desktop.ai_portfolio import _CN_HOLIDAYS
            return d not in _CN_HOLIDAYS
        except Exception:
            return d.weekday() < 5

    def _push(self, title: str, content: str, channels: list[str] | None = None):
        """推送到微信（静默失败，限制频率避免耗尽免费额度）。"""
        today_key = date.today().isoformat()
        push_count_key = f"_push_count_{today_key}"
        count = self._last_run.get(push_count_key, 0)
        channel_map = {
            "wechat_personal": "serverchan",
            "serverchan": "serverchan",
            "wecom_group_bot": "wecom",
            "wecom": "wecom",
            "email": "email",
        }
        requested_channels = [str(item).strip() for item in channels or [] if str(item).strip()]
        push_channels = [channel_map[item] for item in requested_channels if item in channel_map]
        push_channels = list(dict.fromkeys(push_channels))
        push_status = {
            "last_title": title,
            "last_attempt_at": datetime.now().isoformat(timespec="seconds"),
            "count_today": count,
            "last_success_at": "",
            "last_result": "skipped",
            "last_error": "",
            "requested_channels": requested_channels,
            "push_channels": push_channels,
        }

        if count >= 4:
            _log.info(f"push skipped (daily limit {count}/4): {title}")
            push_status["last_result"] = "skipped_limit"
            push_status["count_today"] = count
            set_kv_json(_DAEMON_PUSH_STATUS_KEY, push_status)
            return

        try:
            from signal_push import push_signal
            result = {} if requested_channels and not push_channels else push_signal(title, content, channels=push_channels or None)
            external_ok = any(value is True for value in result.values())
            sc = result.get("serverchan")
            if external_ok:
                self._last_run[push_count_key] = count + 1
                _log.info(f"pushed ({count+1}/4): {title}")
                push_status["last_result"] = "success"
                push_status["count_today"] = count + 1
                push_status["last_success_at"] = datetime.now().isoformat(timespec="seconds")
            elif any(value is False for value in result.values()):
                _log.warning(f"push failed: {title}")
                push_status["last_result"] = "failed"
                push_status["last_error"] = "push channel returned false"
            else:
                _log.info(f"push: no channel configured")
                push_status["last_result"] = "skipped_no_channel"
            push_status["raw_result"] = result
            set_kv_json(_DAEMON_PUSH_STATUS_KEY, push_status)
        except Exception as e:
            _log.warning(f"push skipped: {e}")
            push_status["last_result"] = "error"
            push_status["last_error"] = str(e)
            set_kv_json(_DAEMON_PUSH_STATUS_KEY, push_status)

    def _push_openclaw_alert(self, status: str, title: str, content: str):
        """OpenClaw 专用告警：支持静默窗口和连续失败升级。"""
        now_ts = time.time()
        policy = get_openclaw_alert_policy_config()
        suppress_seconds = int(policy.get("suppress_seconds", 1800) or 1800)
        escalate_after = int(policy.get("escalate_after", 3) or 3)
        normalized_status = str(status or "").lower()
        level_order = {"success": 0, "info": 1, "warning": 2, "error": 3, "critical": 4}
        min_level = str(policy.get("min_level", "warning") or "warning").lower()
        status_level = level_order.get(normalized_status, 2)
        min_level_value = level_order.get(min_level, 2)
        state = get_kv_json(_OPENCLAW_ALERT_STATE_KEY, {}) or {}
        if isinstance(state, str):
            try:
                state = json.loads(state)
            except Exception:
                state = {}
        if not isinstance(state, dict):
            state = {}

        previous_status = str(state.get("last_status", "") or "")
        last_push_ts = float(state.get("last_push_ts", 0) or 0)
        last_success_push_ts = float(state.get("last_success_push_ts", 0) or 0)
        consecutive_errors = int(state.get("consecutive_errors", 0) or 0)
        if normalized_status == "error":
            consecutive_errors = consecutive_errors + 1 if previous_status == "error" else 1
        elif normalized_status == "success":
            consecutive_errors = 0

        if not bool(policy.get("enabled", True)):
            state.update(
                {
                    "last_status": normalized_status,
                    "last_seen_ts": now_ts,
                    "last_seen_at": datetime.now().isoformat(timespec="seconds"),
                    "consecutive_errors": consecutive_errors,
                    "last_result": "disabled_by_policy",
                    "policy": policy,
                }
            )
            set_kv_json(_OPENCLAW_ALERT_STATE_KEY, state)
            return

        notify_enabled = bool(policy.get(f"notify_on_{normalized_status}", True))
        if normalized_status == "success":
            notify_enabled = bool(policy.get("notify_on_success", False))
        success_interval = max(0, int(policy.get("success_summary_interval_seconds", 86400) or 86400))
        success_suppressed = (
            normalized_status == "success"
            and success_interval > 0
            and (now_ts - last_success_push_ts) < success_interval
        )
        filtered = status_level < min_level_value
        if filtered or not notify_enabled or success_suppressed:
            state.update(
                {
                    "last_status": normalized_status,
                    "last_seen_ts": now_ts,
                    "last_seen_at": datetime.now().isoformat(timespec="seconds"),
                    "consecutive_errors": consecutive_errors,
                    "last_result": "filtered_by_policy"
                    if filtered
                    else "disabled_for_status"
                    if not notify_enabled
                    else "success_suppressed",
                    "policy": policy,
                    "routing": {
                        "status": normalized_status,
                        "min_level": min_level,
                        "notify_enabled": notify_enabled,
                        "success_interval_seconds": success_interval,
                        "channels": [],
                    },
                }
            )
            set_kv_json(_OPENCLAW_ALERT_STATE_KEY, state)
            return

        escalated = normalized_status == "error" and consecutive_errors >= max(1, escalate_after)
        suppressed = (
            normalized_status == previous_status
            and (now_ts - last_push_ts) < max(0, suppress_seconds)
            and not escalated
        )
        channels = list(policy.get("escalation_channels" if escalated else "default_channels", []) or [])

        state.update(
            {
                "last_status": normalized_status,
                "last_seen_ts": now_ts,
                "last_seen_at": datetime.now().isoformat(timespec="seconds"),
                "consecutive_errors": consecutive_errors,
                "suppressed_count": int(state.get("suppressed_count", 0) or 0) + (1 if suppressed else 0),
                "escalated": escalated,
                "routing": {
                    "status": normalized_status,
                    "min_level": min_level,
                    "notify_enabled": notify_enabled,
                    "escalated": escalated,
                    "channels": channels,
                },
                "policy": policy,
            }
        )

        if suppressed:
            state["last_result"] = "suppressed"
            set_kv_json(_OPENCLAW_ALERT_STATE_KEY, state)
            _log.info(f"OpenClaw alert suppressed: status={normalized_status}, title={title}")
            return

        if escalated:
            title = f"🚨 OpenClaw连续失败{consecutive_errors}次"
            content = f"{content}\n\n连续失败次数: {consecutive_errors}"
        if channels:
            content = f"{content}\n\n通知通道: {', '.join(channels)}"
        self._push(title, content, channels=channels)
        state.update(
            {
                "last_push_ts": now_ts,
                "last_push_at": datetime.now().isoformat(timespec="seconds"),
                "last_title": title,
                "last_result": "pushed",
            }
        )
        if normalized_status == "success":
            state["last_success_push_ts"] = now_ts
            state["last_success_push_at"] = datetime.now().isoformat(timespec="seconds")
        set_kv_json(_OPENCLAW_ALERT_STATE_KEY, state)

    def _reset_openclaw_alert_state(self):
        state = get_kv_json(_OPENCLAW_ALERT_STATE_KEY, {}) or {}
        if isinstance(state, str):
            try:
                state = json.loads(state)
            except Exception:
                state = {}
        if not isinstance(state, dict):
            state = {}
        state.update(
            {
                "last_status": "success",
                "last_seen_ts": time.time(),
                "last_seen_at": datetime.now().isoformat(timespec="seconds"),
                "consecutive_errors": 0,
                "escalated": False,
                "last_result": "reset_on_success",
            }
        )
        set_kv_json(_OPENCLAW_ALERT_STATE_KEY, state)

    def _append_openclaw_run_history(self, payload: dict):
        history = get_kv_json(_OPENCLAW_RUN_HISTORY_KEY, []) or []
        if isinstance(history, str):
            try:
                history = json.loads(history)
            except Exception:
                history = []
        if not isinstance(history, list):
            history = []
        plan = payload.get("execution_plan", {}) if isinstance(payload, dict) else {}
        sim = payload.get("simulation", {}) if isinstance(payload, dict) else {}
        trace = payload.get("agent_trace", {}) if isinstance(payload, dict) else {}
        orchestration = payload.get("coordinator_orchestration", {}) if isinstance(payload, dict) else {}
        item = {
            "timestamp": payload.get("timestamp", datetime.now().isoformat(timespec="seconds")),
            "status": payload.get("status", "unknown"),
            "summary": payload.get("summary", ""),
            "boards": payload.get("boards", []),
            "decision_sample": payload.get("decision_sample", [])[:20] if isinstance(payload.get("decision_sample", []), list) else [],
            "executed_sample": payload.get("executed_sample", [])[:20] if isinstance(payload.get("executed_sample", []), list) else [],
            "mode": plan.get("mode", "") if isinstance(plan, dict) else "",
            "blocked_count": plan.get("blocked_count", 0) if isinstance(plan, dict) else 0,
            "simulation_passed": bool(sim.get("passed", False)) if isinstance(sim, dict) else False,
            "simulation_success_runs": int(sim.get("consecutive_success_runs", 0) or 0) if isinstance(sim, dict) else 0,
            "simulation": {
                "passed": bool(sim.get("passed", False)) if isinstance(sim, dict) else False,
                "consecutive_success_runs": int(sim.get("consecutive_success_runs", 0) or 0)
                if isinstance(sim, dict)
                else 0,
                "required_runs": int(sim.get("required_runs", 0) or 0) if isinstance(sim, dict) else 0,
            },
            "trace_span_count": int(trace.get("span_count", 0) or 0) if isinstance(trace, dict) else 0,
            "orchestration_stage_count": int(orchestration.get("stage_count", 0) or 0)
            if isinstance(orchestration, dict)
            else 0,
            "orchestration_action_count": int(orchestration.get("action_count", 0) or 0)
            if isinstance(orchestration, dict)
            else 0,
            "error_count": len(payload.get("errors", []) or []),
        }
        history.insert(0, item)
        set_kv_json(_OPENCLAW_RUN_HISTORY_KEY, history[:30])

    def _summarize_openclaw_observability(self, result: dict) -> dict:
        trace_items = list(result.get("agent_trace", []) or []) if isinstance(result, dict) else []
        trace_context = result.get("agent_trace_context", {}) if isinstance(result, dict) else {}
        spans = []
        for span in trace_items[:20]:
            if not isinstance(span, dict):
                continue
            spans.append(
                {
                    "agent_key": span.get("agent_key", ""),
                    "stage": span.get("stage", ""),
                    "status": span.get("status", ""),
                    "duration_ms": span.get("duration_ms", 0),
                    "span_id": span.get("span_id", ""),
                    "parent_span_id": span.get("parent_span_id", ""),
                    "input_summary": span.get("input_summary", {}),
                    "output_summary": span.get("output_summary", {}),
                    "error": span.get("error", ""),
                }
            )

        coordinator = result.get("coordinator", {}) if isinstance(result, dict) else {}
        orchestration_items = coordinator.get("orchestration", []) if isinstance(coordinator, dict) else []
        action_count = 0
        items = []
        for item in list(orchestration_items or [])[:20]:
            if not isinstance(item, dict):
                continue
            actions = item.get("actions_done", item.get("actions", [])) or []
            if isinstance(actions, list):
                action_count += len(actions)
            items.append(
                {
                    "stage": item.get("stage", ""),
                    "ready": bool(item.get("ready", True)),
                    "mode": item.get("mode", ""),
                    "reason": item.get("reason", ""),
                    "actions_done": actions[:5] if isinstance(actions, list) else [],
                    "timestamp": item.get("timestamp", ""),
                }
            )

        return {
            "agent_trace": {
                "context": trace_context if isinstance(trace_context, dict) else {},
                "span_count": len(trace_items),
                "spans": spans,
            },
            "coordinator_orchestration": {
                "stage_count": len(orchestration_items or []),
                "action_count": action_count,
                "items": items,
            },
        }

    # ===== 任务实现 =====

    def _task_refresh_boards(self):
        """自动刷新板块成分股 + 补全缺失日线数据。"""
        _log.info("refreshing board stocks...")
        try:
            from desktop.data_sync import sync_board_stocks
            result = sync_board_stocks(max_fetch=80)
            _log.info(
                f"board sync: fetched {result['fetched']}, "
                f"failed {result['failed']}, remaining {result['remaining']}"
            )
        except Exception as e:
            _log.error(f"board refresh error: {e}")

    def _task_fetch_data(self):
        """拉取最新实时报价（快速，仅抓当前价格快照）。"""
        _log.info("fetching latest realtime quotes...")
        try:
            from desktop.providers.realtime_quote import RealtimeQuoteProvider

            repo = get_repo()
            codes = [r[0] for r in repo.fetchall("SELECT DISTINCT code FROM board_stocks LIMIT 200", ())]
            if codes:
                quotes = RealtimeQuoteProvider().get_quotes(codes[:100], force=True)
                _log.info(f"fetched {len(quotes)} realtime quotes")
        except Exception as e:
            _log.error(f"fetch data error: {e}")

    def _task_refresh_kline(self):
        """刷新K线日线数据（写入最新 OHLCV，供K线图和策略使用）。"""
        _log.info("refreshing daily kline data...")
        try:
            from desktop.data_sync import refresh_latest_kline

            repo = get_repo()
            priority_codes = set()

            try:
                for r in repo.fetchall(
                    "SELECT DISTINCT code FROM ai_positions WHERE status='open'", ()
                ):
                    priority_codes.add(r[0])
            except Exception:
                pass
            try:
                mp = get_kv_json("manual_portfolio", {}) or {}
                for p in mp.get("positions", []):
                    c = p.get("code", "")
                    if c:
                        priority_codes.add(c)
            except Exception:
                pass

            board_codes = [
                r[0]
                for r in repo.fetchall(
                    "SELECT DISTINCT code FROM board_stocks LIMIT 500", ()
                )
            ]

            # 先刷新持仓，再刷其他
            all_codes = list(priority_codes) + [c for c in board_codes if c not in priority_codes]
            result = refresh_latest_kline(codes=all_codes, max_codes=800, threads=8)
            _log.info(
                f"kline refresh done: {result['fetched']} stocks updated, "
                f"{result['rows_updated']} rows, {result['failed']} failed"
            )
            self._push(
                "📊 K线数据已刷新",
                f"刷新 {result['fetched']} 只股票日线数据，共 {result['rows_updated']} 条记录"
            ) if result["fetched"] > 0 else None
        except Exception as e:
            _log.error(f"kline refresh error: {e}")

    def _task_scan_stocks(self):
        """自动执行选股雷达扫描（使用统一策略引擎 + 当前最强策略）。"""
        _log.info("running stock scan (strategy engine)...")
        try:
            import numpy as np
            from desktop.strategy_engine import build_context, score_candidate
            from desktop.strategy_rotator import get_current_best_strategy

            repo = get_repo()
            current_strategy = get_current_best_strategy()

            codes = [
                r[0]
                for r in repo.fetchall(
                    "SELECT code, COUNT(*) as cnt FROM daily_kline "
                    "GROUP BY code HAVING cnt >= 50 ORDER BY cnt DESC LIMIT 500",
                    (),
                )
            ]

            names = {}
            try:
                for r in repo.fetchall("SELECT code, name FROM stock_list", ()):
                    names[r[0]] = r[1]
            except Exception:
                pass

            board_map = {}
            try:
                for r in repo.fetchall("SELECT code, board FROM board_stocks", ()):
                    if r[0] not in board_map:
                        board_map[r[0]] = r[1]
            except Exception:
                pass

            results = []
            for code in codes:
                rows = repo.fetchall(
                    "SELECT close, high, low, volume FROM daily_kline "
                    "WHERE code=? ORDER BY date DESC LIMIT 260",
                    (code,),
                )
                if len(rows) < 50:
                    continue
                rows = rows[::-1]
                closes = np.array([r[0] for r in rows])
                highs = np.array([r[1] for r in rows])
                lows = np.array([r[2] for r in rows])
                vols = np.array([r[3] for r in rows])
                n = len(closes)
                price = float(closes[-1])
                if price <= 0:
                    continue

                ctx = build_context(code, closes, highs, lows, vols)
                scored = score_candidate(current_strategy, ctx)
                score = scored["score"]

                if score >= 40:
                    results.append({
                        "代码": code,
                        "名称": names.get(code, code),
                        "板块": board_map.get(code, ""),
                        "策略": scored["strategy"],
                        "评分": str(score),
                        "价格": f"{price:.2f}",
                        "建议买入": scored["buy_advice"],
                        "建议操作": scored["action_advice"],
                        "VCP": "✓" if scored["vcp"] else "",
                        "突破": "✓" if scored["breakout"] else "",
                        "收缩": f"{scored['contraction']:.2f}" if scored["contraction"] else "",
                        "量比": f"{scored['vol_ratio']:.1f}" if scored["vol_ratio"] else "",
                        "RS": str(scored["rs"]),
                        "离高点%": f"{scored['dist_high']:+.1f}%",
                    })

            results.sort(key=lambda x: int(x.get("评分", "0")), reverse=True)
            results = results[:50]

            set_kv_json("last_scan_results", results)

            n_r = len(results)
            top3 = ", ".join(f"{r['代码']}({r['评分']})" for r in results[:3])
            _log.info(f"scan done: {n_r} candidates, strategy={current_strategy}, top3: {top3}")
            if n_r > 0:
                self._push(
                    f"选股雷达 {n_r}只候选",
                    f"策略: {current_strategy}\\nTop3: {top3}"
                )

            try:
                from desktop.trend_verify import record_signals
                record_signals(results[:10])
            except Exception:
                pass

        except Exception as e:
            _log.error(f"scan error: {e}")

    def _task_push_strong_buy(self):
        """扫描后自动推送强烈买入信号到微信。"""
        _log.info("pushing strong buy signals...")
        try:
            candidates = get_kv_json("last_scan_results", None)
            if not candidates:
                return
            if not isinstance(candidates, list):
                return
            strong = [c for c in candidates if "强烈" in c.get("建议买入", "") or
                      int(c.get("评分", "0")) >= 60]
            if not strong:
                _log.info("no strong buy signals to push")
                return

            lines = [f"📡 选股雷达 — 强烈买入推荐", f"　　共 {len(strong)} 只候选", ""]
            for i, s in enumerate(strong[:15], 1):
                lines.append(f"　　({i}) {s.get('代码','')} {s.get('名称','')}  "
                             f"评分{s.get('评分','')}  [{s.get('板块','')}]")
            self._push(f"选股雷达 {len(strong)}只强烈买入", "\n".join(lines))
            _log.info(f"pushed {len(strong)} strong buy signals")
        except Exception as e:
            _log.error(f"push strong buy error: {e}")

    def _task_custom_top3(self):
        """扫描后自动执行自定义仓 Top3 买入。"""
        _log.info("auto buying custom portfolio Top3...")
        try:
            from desktop.custom_portfolio import auto_buy_top3_from_scan
            results = auto_buy_top3_from_scan()
            for r in results:
                _log.info(f"custom top3: {r}")
        except Exception as e:
            _log.error(f"custom top3 error: {e}")

    def _task_quantum_buy(self):
        """量子优化并买入（每周一执行，其他日跳过）。"""
        from datetime import date as _date
        if _date.today().weekday() != 0:
            _log.info("quantum buy: skipped (only runs on Monday)")
            return

        _log.info("running quantum optimization + buy...")
        try:
            from desktop.quantum.preprocessing import compute_stats
            from desktop.quantum.config import QOptConfig
            from desktop.quantum.evaluation import run_full_comparison
            repo = get_repo()
            scan = get_kv_json("last_scan_results", None)
            if not scan or not isinstance(scan, list):
                return
            codes = [s.get("代码", "") for s in scan[:40] if s.get("代码")]

            prices = {}
            names = {}
            for code in codes:
                r = repo.fetchall(
                    "SELECT close FROM daily_kline WHERE code=? ORDER BY date", (code,)
                )
                if len(r) >= 30:
                    prices[code] = [x[0] for x in r]
                nr = repo.fetchone("SELECT name FROM stock_list WHERE code=?", (code,))
                if nr:
                    names[code] = nr[0]

            if len(prices) < 5:
                _log.info("quantum: not enough stocks")
                return

            stats = compute_stats(prices, names)
            config = QOptConfig(max_holdings=5, risk_aversion=1.0, seed=42)
            comparison = run_full_comparison(stats, config)

            methods = comparison.get("methods", [])
            best = next((m for m in methods if m.get("is_best") and m.get("valid")), None)
            if best:
                buy_codes = best.get("selected_codes", [])
                from desktop.ai_portfolio import buy, get_state

                state = get_state("quantum")
                per_stock = state["cash"] / max(len(buy_codes), 1)
                for code in buy_codes:
                    px_r = repo.fetchone(
                        "SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 1",
                        (code,),
                    )
                    if px_r:
                        px = px_r[0]
                        shares = int(per_stock / px / 100) * 100
                        if shares >= 100:
                            name = names.get(code, code)
                            buy("quantum", code, name, px, shares, round(px * 0.92, 2), "量子优化自动买入")
                _log.info(f"quantum buy: {len(buy_codes)} stocks from {best.get('method','')}")
        except Exception as e:
            _log.error(f"quantum buy error: {e}")

    def _task_sector_rotation(self):
        """板块轮动：分析各板块近期表现，识别最强板块。"""
        _log.info("running sector rotation...")
        try:
            from desktop.strategy_rotator import evaluate_sector_rotation
            result = evaluate_sector_rotation()
            top3 = result.get("top3", [])
            _log.info(f"sector rotation: top3={top3}")
        except Exception as e:
            _log.error(f"sector rotation error: {e}")

    def _task_strategy_rotation(self):
        """策略轮动：跑全部8策略，选出最强策略。"""
        _log.info("running strategy rotation...")
        try:
            from desktop.strategy_rotator import evaluate_rotation
            result = evaluate_rotation()
            best = result.get("best_name", "SEPA")
            score = result.get("best_score", 0)
            _log.info(f"rotation: best={best}({score:.1f})")
            # 推送轮动结果
            rankings = result.get("rankings", [])
            if rankings:
                lines = ["📊 策略轮动评估结果", ""]
                for i, r in enumerate(rankings[:5], 1):
                    marker = "👑" if i == 1 else f"{i}."
                    lines.append(
                        f"　　{marker} {r['name']}: 综合{r['composite_score']:.0f}分  "
                        f"候选{r['candidates']}只  准确率{r['accuracy']:.0f}%"
                    )
                self._push(f"策略轮动: {best}最强", "\n".join(lines))
        except Exception as e:
            _log.error(f"strategy rotation error: {e}")

    def _task_auto_sell(self):
        """自动卖出检查：5种规则 + ATR更新 + 完全自主仓执行 + 其他仓推送。"""
        _log.info("running auto sell check...")
        try:
            from desktop.auto_sell import execute_auto_sell
            result = execute_auto_sell()
            n_exec = len(result.get("executed", []))
            n_suggest = len(result.get("suggested", []))
            n_atr = len(result.get("atr_updates", []))
            _log.info(f"auto sell: executed={n_exec}, suggested={n_suggest}, atr_updates={n_atr}")
        except Exception as e:
            _log.error(f"auto sell error: {e}")

    def _task_custom_calibrate(self):
        """自定义仓校准跟踪。"""
        _log.info("calibrating custom portfolio...")
        try:
            from desktop.custom_portfolio import calibrate_tracking
            result = calibrate_tracking()
            _log.info(f"custom calibrate: {result}")
        except Exception as e:
            _log.error(f"custom calibrate error: {e}")

    def _task_short_term(self):
        """短期选股分析：事件驱动 + NLP情绪 + 基金持仓。"""
        _log.info("running short-term analysis...")
        try:
            # 事件选股：抓取资讯
            try:
                from desktop.event_strategy import fetch_news_eastmoney
                news = fetch_news_eastmoney(limit=20)
                if news:
                    _log.info(f"fetched {len(news)} news items")
                    # NLP 情绪分析
                    try:
                        from desktop.news_nlp import batch_analyze
                        sentiments = batch_analyze([n.get("title", "") for n in news[:10]])
                        pos = sum(1 for s in sentiments if s.get("sentiment") == "positive")
                        neg = sum(1 for s in sentiments if s.get("sentiment") == "negative")
                        _log.info(f"NLP sentiment: positive={pos}, negative={neg}")

                        # 高影响事件自动推送
                        urgent = [s for s in sentiments if s.get("urgency") == "high"]
                        if urgent or neg >= 5:
                            alert_titles = [n.get("title", "")[:30] for n in news[:3]]
                            self._push(
                                f"📰 舆情预警(负面{neg}条)",
                                "\n".join(alert_titles)
                            )
                    except Exception as e:
                        _log.warning(f"NLP skipped: {e}")
            except Exception as e:
                _log.warning(f"news fetch skipped: {e}")

            # 基金持仓：加载明星基金经理
            try:
                from desktop.fund_strategy import get_star_managers
                managers = get_star_managers()
                if managers:
                    _log.info(f"star fund managers: {len(managers)}")
            except Exception as e:
                _log.warning(f"fund analysis skipped: {e}")

        except Exception as e:
            _log.error(f"short-term analysis error: {e}")

    def _task_ai_decision(self):
        """三仓决策 + 推送。"""
        _log.info("running AI decisions...")
        try:
            from desktop.auto_scheduler import run_scheduled_task
            result = run_scheduled_task(self.boards[0], boards=self.boards)

            n_full = len(result.get("full_auto_results", []))
            n_auto = len(result.get("auto_results", []))
            n_manual = len(result.get("manual_suggestions", []))
            _log.info(f"decisions done: full={n_full}, auto={n_auto}, manual={n_manual}")
            try:
                from desktop.snapshot_service import save_system_snapshot
                save_system_snapshot()
            except Exception as e:
                _log.warning(f"system snapshot skipped after ai decision: {e}")
        except Exception as e:
            _log.error(f"ai decision error: {e}")

    def _task_risk_calc(self):
        """计算全仓组合风险指标并保存到 kv_store，供总览页使用。"""
        _log.info("calculating portfolio risk...")
        try:
            try:
                from desktop.market_state import save_market_state_snapshot
                save_market_state_snapshot()
            except Exception as e:
                _log.warning(f"market state snapshot skipped: {e}")
            import numpy as np

            repo = get_repo()
            all_pos = []
            rows = repo.fetchall(
                "SELECT code, name, entry_price, shares FROM ai_positions WHERE status='open'"
            )
            for code, name, ep, sh in rows:
                r = repo.fetchone(
                    "SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 1",
                    (code,),
                )
                px = r[0] if r else ep
                mv = px * sh
                if mv > 0:
                    all_pos.append({"code": code, "name": name or code, "mv": mv})

            try:
                pf = get_kv_json("manual_portfolio", {}) or {}
                for p in pf.get("positions", []):
                    code = p.get("code", "")
                    ep = p.get("entry_price", 0)
                    sh = p.get("shares", 0)
                    r2 = repo.fetchone(
                        "SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 1",
                        (code,),
                    )
                    px = r2[0] if r2 else ep
                    mv = px * sh
                    if mv > 0:
                        all_pos.append({"code": code, "name": p.get("name", code), "mv": mv})
            except Exception:
                pass

            risk = {"var95": 0, "var99": 0, "max_exposure": 0, "max_name": "-",
                    "hhi": 0, "drawdown": 0, "n_positions": len(all_pos)}

            if all_pos:
                weights = [p["mv"] for p in all_pos]
                daily_returns = []
                for p in all_pos:
                    cur = repo.fetchall(
                        "SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 60",
                        (p["code"],),
                    )
                    cls = [r[0] for r in reversed(cur)]
                    if len(cls) >= 2:
                        rets = [(cls[i] / cls[i - 1] - 1) for i in range(1, len(cls))]
                        daily_returns.append(rets)
                    else:
                        daily_returns.append([0.0])

                total_mv = sum(weights)
                if total_mv > 0:
                    w_arr = np.array([w / total_mv for w in weights])
                    risk["hhi"] = round(float(np.sum(w_arr ** 2)), 4)
                    max_idx = int(np.argmax(w_arr))
                    risk["max_exposure"] = round(float(w_arr[max_idx]), 4)
                    risk["max_name"] = all_pos[max_idx]["name"]

                    min_len = min(len(r) for r in daily_returns)
                    if min_len >= 5:
                        port_rets = np.zeros(min_len)
                        for i, rets in enumerate(daily_returns):
                            port_rets += w_arr[i] * np.array(rets[-min_len:])
                        risk["var95"] = round(float(np.percentile(port_rets, 5) * total_mv), 2)
                        risk["var99"] = round(float(np.percentile(port_rets, 1) * total_mv), 2)
                        cum = np.cumprod(1 + port_rets)
                        peak = np.maximum.accumulate(cum)
                        dd = (cum - peak) / peak
                        risk["drawdown"] = round(float(dd[-1]), 4) if len(dd) > 0 else 0

            set_kv_json("portfolio_risk", risk)
            try:
                from desktop.snapshot_service import save_system_snapshot
                save_system_snapshot()
            except Exception as e:
                _log.warning(f"system snapshot skipped after risk calc: {e}")
            _log.info(f"risk calc done: {len(all_pos)} positions, VaR95={risk['var95']:.0f}")
        except Exception as e:
            _log.error(f"risk calc error: {e}")

    def _task_trend_verify(self):
        """走势验证校准（独立于日报）。"""
        _log.info("running trend verification...")
        try:
            from desktop.trend_verify import calibrate, get_accuracy_stats
            calibrate()
            stats = get_accuracy_stats()
            if stats.get("total", 0) > 0:
                _log.info(
                    f"trend verify: {stats['total']} signals, "
                    f"accuracy {stats['accuracy']:.1f}%, "
                    f"avg_pnl_5d {stats['avg_pnl_5d']:+.2f}%"
                )
        except Exception as e:
            _log.error(f"trend verify error: {e}")

    def _task_watchlist_scan(self):
        """扫描关注股（持仓+自选）的异常信号，有异常则推送预警。"""
        _log.info("scanning watchlist for anomalies...")
        try:
            import numpy as np

            repo = get_repo()
            watch_codes = set()
            for r in repo.fetchall(
                "SELECT DISTINCT code FROM ai_positions WHERE status='open'", ()
            ):
                watch_codes.add(r[0])
            try:
                mp = get_kv_json("manual_portfolio", {}) or {}
                for p in mp.get("positions", []):
                    watch_codes.add(p.get("code", ""))
            except Exception:
                pass

            if not watch_codes:
                _log.info("watchlist empty, skipping")
                return

            from desktop.providers.realtime_quote import RealtimeQuoteProvider

            quotes = RealtimeQuoteProvider().get_quotes(list(watch_codes), force=True)

            alerts = []
            for code in watch_codes:
                if not code:
                    continue
                q = quotes.get(code, {})
                price = q.get("price", 0)
                if price <= 0:
                    continue

                rows = repo.fetchall(
                    "SELECT close, volume FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 20",
                    (code,),
                )
                if len(rows) < 5:
                    continue

                closes = [r[0] for r in reversed(rows)]
                vols = [r[1] for r in reversed(rows)]
                prev_close = closes[-1]
                day_pct = (price / prev_close - 1) * 100 if prev_close > 0 else 0

                name_r = repo.fetchone("SELECT name FROM stock_list WHERE code=?", (code,))
                name = name_r[0] if name_r else code

                # 异常检测
                if day_pct >= 8:
                    alerts.append(f"🔥 {code}{name} 大涨{day_pct:.1f}%，关注止盈")
                elif day_pct <= -6:
                    alerts.append(f"🚨 {code}{name} 大跌{day_pct:.1f}%，关注止损")

                # 放量异动
                if len(vols) >= 5:
                    vol_avg = float(np.mean(vols[-5:]))
                    if vol_avg > 0:
                        cur_vol = q.get("volume", 0)
                        if cur_vol and cur_vol > vol_avg * 3:
                            alerts.append(f"📊 {code}{name} 异常放量(3倍均量)")

                # 突破20日高点
                if len(closes) >= 20:
                    h20 = max(closes[-20:])
                    if price > h20:
                        alerts.append(f"📈 {code}{name} 突破20日高点{h20:.2f}")

            if alerts:
                self._push(
                    f"📡 关注股异常({len(alerts)}条)",
                    "\n".join(alerts[:10])
                )
                _log.info(f"watchlist alerts: {len(alerts)}")
            else:
                _log.info("watchlist: no anomalies")

        except Exception as e:
            _log.error(f"watchlist scan error: {e}")

    def _task_auto_backtest(self):
        """周期性策略回测：每周五或每月验证各策略的历史表现。"""
        _log.info("running periodic backtest...")
        try:
            from desktop.backtest_service import run_strategy_backtest

            repo = get_repo()
            strategies = ["sepa", "canslim", "turtle", "graham", "buffett", "lynch", "domestic_trend", "domestic_value"]
            bt_results = {}
            for strat in strategies:
                try:
                    result = run_strategy_backtest(strategy_id=strat, sample_size=100, start_date="2022-06-01")
                    if result:
                        bt_results[strat] = {
                            "total_return": round(result.get("total_return", 0) * 100, 2),
                            "sharpe": round(result.get("sharpe_ratio", 0), 2),
                            "win_rate": round(result.get("win_rate", 0) * 100, 1),
                            "total_trades": result.get("total_trades", 0),
                            "max_drawdown": round(result.get("max_drawdown", 0) * 100, 2),
                        }
                except Exception as e:
                    _log.warning(f"backtest {strat} failed: {e}")

            if bt_results:
                set_kv_json("auto_backtest_results", bt_results)
                best = max(bt_results, key=lambda s: bt_results[s].get("sharpe", 0))
                _log.info(
                    f"backtest done: {len(bt_results)} strategies, "
                    f"best={best}(sharpe={bt_results[best]['sharpe']})"
                )

                try:
                    import json as _json

                    ts = datetime.now().isoformat()
                    repo.execute(
                        "INSERT INTO openclaw_learning (timestamp,module,metric,value,detail) "
                        "VALUES (?,?,?,?,?)",
                        (
                            ts,
                            "backtest",
                            f"best_strategy_{best}",
                            bt_results[best]["sharpe"],
                            _json.dumps(bt_results, ensure_ascii=False),
                        ),
                    )
                    _log.info("backtest results fed to OpenClaw learner")
                except Exception:
                    pass
        except Exception as e:
            _log.error(f"auto backtest error: {e}")

    def _task_record_nav(self):
        """记录每日各仓位净值。"""
        _log.info("recording daily NAV...")
        try:
            from desktop.portfolio_tracker import record_daily_nav
            record_daily_nav()
            try:
                from desktop.snapshot_service import save_system_snapshot
                save_system_snapshot()
            except Exception as e:
                _log.warning(f"system snapshot skipped after nav: {e}")
        except Exception as e:
            _log.error(f"record NAV error: {e}")

    def _task_data_cleanup(self):
        """自动清理过期数据（每月一次实际执行）。"""
        # 只在每月1号执行
        if date.today().day != 1:
            return
        _log.info("running data cleanup...")
        try:
            from desktop.portfolio_tracker import cleanup_old_data
            result = cleanup_old_data(keep_days=730)
            _log.info(f"cleanup: {result}")
        except Exception as e:
            _log.error(f"cleanup error: {e}")

    def _task_auto_learn(self):
        """OpenClaw 自主学习：采集各模块结果 → 评估 → 更新策略权重。"""
        _log.info("running OpenClaw auto-learn...")
        try:
            from desktop.openclaw_learner import evaluate_and_learn, get_enhanced_full_auto_prompt
            result = evaluate_and_learn()
            n_learnings = len(result.get("learnings", []))
            n_strategies = len(result.get("scan_perf", {}))
            _log.info(
                f"auto-learn done: {n_strategies} strategies evaluated, "
                f"{n_learnings} findings"
            )

            # 生成并保存增强的自主仓 prompt
            enhanced = get_enhanced_full_auto_prompt()
            if enhanced:
                set_kv_json("openclaw_evolution_prompt", enhanced)
                _log.info("evolution prompt updated for full_auto")

        except Exception as e:
            _log.error(f"auto-learn error: {e}")

    def _task_openclaw_pipeline(self):
        """OpenClaw 无人值守全流程：选股、研判、风控、审批、执行、归因、学习。"""
        _log.info("running headless OpenClaw pipeline...")
        from core.application.openclaw_service import run_openclaw_pipeline

        try:
            result = run_openclaw_pipeline(boards=self.boards)
        except Exception as e:
            payload = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "status": "error",
                "boards": list(self.boards),
                "summary": f"OpenClaw后台执行异常: {e}",
                "errors": [str(e)[:300]],
                "execution_plan": {"mode": "error", "blocked_count": 0},
            }
            set_kv_json("openclaw_last_daemon_run", payload)
            try:
                from desktop.agents import record_unattended_trade_guard_simulation

                record_unattended_trade_guard_simulation("error", payload["summary"])
            except Exception:
                pass
            self._append_openclaw_run_history(payload)
            log_system_event(
                "openclaw",
                "daemon",
                "OpenClaw后台执行失败",
                detail=payload["summary"],
                level="error",
            )
            self._push_openclaw_alert("error", "⚠️ OpenClaw后台执行失败", payload["summary"])
            raise
        if not isinstance(result, dict):
            payload = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "status": "error",
                "boards": list(self.boards),
                "summary": "OpenClaw后台执行返回无效结果",
                "errors": ["non-dict result"],
                "execution_plan": {"mode": "invalid_result", "blocked_count": 0},
            }
            set_kv_json("openclaw_last_daemon_run", payload)
            try:
                from desktop.agents import record_unattended_trade_guard_simulation

                record_unattended_trade_guard_simulation("error", payload["summary"])
            except Exception:
                pass
            self._append_openclaw_run_history(payload)
            log_system_event(
                "openclaw",
                "daemon",
                "OpenClaw后台执行返回无效结果",
                detail=payload["summary"],
                level="error",
            )
            self._push_openclaw_alert("error", "⚠️ OpenClaw后台执行异常", payload["summary"])
            return
        steps = result.get("steps", []) or []
        errors = result.get("errors", []) or []
        decisions = result.get("decisions", []) or []
        executed = result.get("executed_decisions", []) or []
        execution_plan = result.get("execution_plan", {}) or {}
        mode = execution_plan.get("mode", "normal") if isinstance(execution_plan, dict) else "normal"
        failed_steps = [step for step in steps if isinstance(step, dict) and step.get("status") == "error"]
        blocked_count = execution_plan.get("blocked_count", 0) if isinstance(execution_plan, dict) else 0
        if errors or failed_steps:
            status = "error"
        elif decisions and not executed:
            status = "warning"
        else:
            status = "success"
        summary = (
            f"steps={len(steps)}, decisions={len(decisions)}, executed={len(executed)}, "
            f"errors={len(errors)}, failed_steps={len(failed_steps)}, mode={mode}"
        )
        def _decision_sample(rows):
            items = []
            for row in list(rows or [])[:20]:
                if not isinstance(row, dict):
                    continue
                items.append(
                    {
                        "action": row.get("action", ""),
                        "code": row.get("code", ""),
                        "name": row.get("name", ""),
                        "price": row.get("price", 0),
                        "shares": row.get("shares", 0),
                        "sector": row.get("sector") or row.get("industry") or row.get("board") or "",
                        "reason": str(row.get("reason", "") or "")[:160],
                    }
                )
            return items

        payload = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "status": status,
            "boards": list(self.boards),
            "summary": summary,
            "errors": errors[:5],
            "decision_sample": _decision_sample(decisions),
            "executed_sample": _decision_sample(executed),
            "failed_steps": [
                {
                    "name": step.get("name", ""),
                    "error": step.get("error", ""),
                }
                for step in failed_steps[:5]
            ],
            "execution_plan": {
                "mode": mode,
                "blocked_count": blocked_count,
            },
        }
        payload.update(self._summarize_openclaw_observability(result))
        set_kv_json("openclaw_last_daemon_run", payload)
        try:
            from desktop.agents import record_unattended_trade_guard_simulation

            payload["simulation"] = record_unattended_trade_guard_simulation(status, summary)
            set_kv_json("openclaw_last_daemon_run", payload)
        except Exception:
            pass
        self._append_openclaw_run_history(payload)
        level = "error" if status == "error" else "warning" if status == "warning" else "info"
        log_system_event(
            "openclaw",
            "daemon",
            f"OpenClaw后台执行{status}",
            detail=summary,
            level=level,
        )
        if status == "error":
            detail = "\n".join([summary] + [str(item)[:120] for item in errors[:3]])
            self._push_openclaw_alert("error", "⚠️ OpenClaw后台执行失败", detail)
        elif status == "warning":
            self._push_openclaw_alert("warning", "⚠️ OpenClaw后台执行未产生交易", summary)
        else:
            self._reset_openclaw_alert_state()
        _log.info(f"headless OpenClaw pipeline done: {summary}")

    def _task_daily_report(self):
        """走势校准 + 日报推送。"""
        _log.info("running daily report...")
        try:
            def _num(x, default=0.0) -> float:
                if x is None:
                    return default
                try:
                    v = float(x)
                    return default if v != v else v
                except (TypeError, ValueError):
                    return default

            # 校准走势验证
            from desktop.trend_verify import calibrate, get_accuracy_stats
            cal_result = calibrate()
            stats = get_accuracy_stats()

            # 校准 AI 决策记忆
            from desktop.agents import calibrate_decisions, get_decision_accuracy
            calibrate_decisions(5)
            ai_acc = get_decision_accuracy()

            # 构建日报
            lines = [
                f"📊 FinQuanta 每日报告",
                f"　　日期: {date.today().isoformat()}",
                "",
            ]

            section = 1
            # 走势验证
            if stats.get("total", 0) > 0:
                lines.append(f"{section}. 📈 走势验证")
                lines.append(f"　　总信号: {stats['total']} 个")
                lines.append(f"　　准确率: {_num(stats.get('accuracy')):.1f}%")
                lines.append(f"　　1日均涨: {_num(stats.get('avg_pnl_1d')):+.2f}%")
                lines.append(f"　　5日均涨: {_num(stats.get('avg_pnl_5d')):+.2f}%")
                lines.append("")
                section += 1

            # AI 决策准确率
            if ai_acc.get("total_decisions", 0) > 0:
                lines.append(f"{section}. 🤖 AI决策绩效")
                lines.append(f"　　总决策: {ai_acc['total_decisions']} 次")
                lines.append(f"　　准确率: {_num(ai_acc.get('accuracy')):.1f}%")
                lines.append(f"　　均收益: {_num(ai_acc.get('avg_pnl')):+.2f}%")
                lines.append("")
                section += 1

            # 仓位对比
            try:
                from desktop.ai_portfolio import get_comparison
                comp = get_comparison()
                lines.append(f"{section}. 💰 六仓对比")
                for i, (key, label) in enumerate([
                    ("full_auto", "完全自主"), ("auto", "AI推荐"),
                    ("custom", "自定义"),
                    ("quantum", "量子仓"),
                ], 1):
                    c = comp.get(key, {})
                    if c:
                        lines.append(
                            f"　　({i}) {label}: 收益{_num(c.get('return_pct')):+.2f}%  "
                            f"胜率{_num(c.get('win_rate')):.0f}%  "
                            f"交易{int(_num(c.get('total_trades'), 0))}笔"
                        )
                lines.append("")
            except Exception:
                pass

            msg = "\n".join(lines)
            self._push(f"FinQuanta 日报 {date.today()}", msg)
            _log.info("daily report sent")

        except Exception as e:
            _log.error(f"daily report error: {e}")

    def _check_alerts(self):
        """检查持仓止损预警（同一条预警每天只推送一次）。"""
        try:
            from desktop.ai_portfolio import get_state
            from desktop.providers.realtime_quote import RealtimeQuoteProvider

            today = date.today().isoformat()
            alerted_key = f"_alerted_{today}"
            alerted_today = set(self._last_run.get(alerted_key, []))

            alerts = []
            for mode, label in [("full_auto", "完全自主"), ("auto", "AI推荐"), ("custom", "自定义")]:
                state = get_state(mode)
                codes = [p["code"] for p in state["positions"]]
                if not codes:
                    continue

                quotes = RealtimeQuoteProvider().get_quotes(codes)
                for p in state["positions"]:
                    code = p["code"]
                    q = quotes.get(code, {})
                    price = q.get("price", 0)
                    stop = p.get("stop_loss", 0)

                    # 止损预警
                    alert_id = f"stop_{mode}_{code}"
                    if price > 0 and stop > 0 and price <= stop and alert_id not in alerted_today:
                        alerts.append(
                            f"🚨 {label} {code} {p.get('name','')}: "
                            f"现价{price:.2f} ≤ 止损{stop:.2f}!"
                        )
                        alerted_today.add(alert_id)

                    # 盈利超20%提醒
                    entry = p.get("entry_price", 0)
                    profit_id = f"profit_{mode}_{code}"
                    if entry > 0 and price > 0 and profit_id not in alerted_today:
                        pnl = (price / entry - 1) * 100
                        if pnl >= 20:
                            alerts.append(
                                f"🎉 {label} {code}: 盈利{pnl:.1f}%，考虑止盈"
                            )
                            alerted_today.add(profit_id)

            if alerts:
                self._push("⚠️ FinQuanta 预警", "\n".join(alerts))
                _log.info(f"alerts sent: {len(alerts)}")

            # 保存今日已预警记录
            self._last_run[alerted_key] = list(alerted_today)

        except Exception as e:
            _log.error(f"alert check error: {e}")

    # ===== 主循环 =====

    def run(self):
        """主循环：每分钟检查调度表 + 定期检查预警。"""
        if not self._acquire_leader():
            _log.warning("daemon skipped: another scheduler instance is active")
            return
        _log.info(f"FinQuanta Daemon started, boards: {self.boards}")
        last_alert = 0

        try:
            while self._running:
                now = datetime.now()
                today = now.strftime("%Y-%m-%d")
                current_time = now.strftime("%H:%M")

                self._renew_leader()
                if self._is_trading_day():
                    self._load_time_overrides()
                    # 检查定时任务
                    for task in SCHEDULE:
                        task_key = task.get("key", "")
                        if task_key in self.disabled_tasks:
                            continue
                        task_time = self._get_task_time(task)
                        run_key = f"{today}_{task_time}_{task['name']}"
                        if current_time >= task_time and run_key not in self._last_run:
                            _log.info(f"executing: {task['name']} ({task_time})")
                            try:
                                func = getattr(self, task["func"])
                                run_task(task["name"], "daemon", func)
                                log_system_event(
                                    "daemon",
                                    "task",
                                    f"任务完成: {task['name']}",
                                    detail=f"time={task_time}",
                                )
                            except Exception as e:
                                _log.error(f"task {task['name']} failed: {e}")
                            self._last_run[run_key] = now.isoformat()
                            self._save_last_run()

                    # 预警检查（交易时间内每5分钟）
                    if "alert_check" not in self.disabled_tasks:
                        t = now.hour * 100 + now.minute
                        if (915 <= t <= 1130 or 1300 <= t <= 1500):
                            if time.time() - last_alert > ALERT_INTERVAL:
                                self._check_alerts()
                                last_alert = time.time()

                time.sleep(30)
        finally:
            self._release_leader()

    def stop(self):
        self._running = False

    def run_full_pipeline(self) -> list[str]:
        """立即执行全策略流水线（不受时间限制），返回执行结果。"""
        results = []
        pipeline = [
            ("fetch_data",    self._task_fetch_data,     "拉取实时行情"),
            ("refresh_kline", self._task_refresh_kline,  "刷新K线日线"),
            ("scan_stocks",   self._task_scan_stocks,    "选股雷达扫描"),
            ("short_term",    self._task_short_term,     "短期选股分析"),
            ("openclaw_pipeline", self._task_openclaw_pipeline, "OpenClaw自主全流程"),
            ("ai_decision",   self._task_ai_decision,    "AI 三仓决策"),
            ("trend_verify",  self._task_trend_verify,   "走势验证校准"),
            ("daily_report",  self._task_daily_report,   "日报推送"),
        ]
        for key, func, name in pipeline:
            if key in self.disabled_tasks:
                results.append(f"⏭ {name}: 已禁用，跳过")
                continue
            try:
                _log.info(f"pipeline: {name}...")
                func()
                results.append(f"✅ {name}: 完成")
            except Exception as e:
                results.append(f"❌ {name}: {e}")
                _log.error(f"pipeline {name} failed: {e}")
        return results


def start_daemon(boards: list[str] = None, disabled_tasks: set = None):
    """启动后台守护线程（供客户端调用）。"""
    daemon = DaemonScheduler(boards, disabled_tasks=disabled_tasks)
    thread = threading.Thread(target=daemon.run, daemon=True, name="FinQuanta-Daemon")
    thread.start()
    return daemon


def _load_openclaw_daemon_boards(default: list[str] | None = None) -> list[str]:
    fallback = default or ["人工智能", "芯片", "量子科技"]
    raw = get_kv_json("openclaw_daemon_boards", None)
    if isinstance(raw, list):
        boards = [str(item).strip() for item in raw if str(item).strip()]
        return boards or fallback
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                boards = [str(item).strip() for item in parsed if str(item).strip()]
                return boards or fallback
        except Exception:
            boards = [item.strip() for item in re.split(r"[,，\s]+", raw) if item.strip()]
            return boards or fallback
    return fallback


def _safe_int(value, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _normalize_channels(value, default: list[str]) -> list[str]:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                value = parsed
            else:
                value = re.split(r"[,，\s]+", value)
        except Exception:
            value = re.split(r"[,，\s]+", value)
    if isinstance(value, list):
        channels = [str(item).strip() for item in value if str(item).strip()]
        return channels or list(default)
    return list(default)


def get_openclaw_alert_policy_config() -> dict:
    cfg = dict(_OPENCLAW_ALERT_POLICY_DEFAULTS)
    cfg["suppress_seconds"] = _safe_int(
        os.environ.get("FINQUANTA_OPENCLAW_ALERT_SUPPRESS_SECONDS"),
        cfg["suppress_seconds"],
    )
    cfg["escalate_after"] = _safe_int(
        os.environ.get("FINQUANTA_OPENCLAW_ALERT_ESCALATE_AFTER"),
        cfg["escalate_after"],
    )
    stored = get_kv_json(_OPENCLAW_ALERT_POLICY_KEY, {}) or {}
    if isinstance(stored, str):
        try:
            stored = json.loads(stored)
        except Exception:
            stored = {}
    if isinstance(stored, dict):
        cfg.update({k: v for k, v in stored.items() if v is not None})
    cfg["enabled"] = bool(cfg.get("enabled", True))
    cfg["notify_on_success"] = bool(cfg.get("notify_on_success", False))
    cfg["notify_on_warning"] = bool(cfg.get("notify_on_warning", True))
    cfg["notify_on_error"] = bool(cfg.get("notify_on_error", True))
    cfg["suppress_seconds"] = max(0, min(86400, _safe_int(cfg.get("suppress_seconds"), 1800)))
    cfg["escalate_after"] = max(1, min(100, _safe_int(cfg.get("escalate_after"), 3)))
    cfg["success_summary_interval_seconds"] = max(
        0,
        min(604800, _safe_int(cfg.get("success_summary_interval_seconds"), 86400)),
    )
    min_level = str(cfg.get("min_level", "warning") or "warning").lower()
    cfg["min_level"] = min_level if min_level in {"success", "info", "warning", "error", "critical"} else "warning"
    cfg["default_channels"] = _normalize_channels(
        cfg.get("default_channels"),
        _OPENCLAW_ALERT_POLICY_DEFAULTS["default_channels"],
    )
    cfg["escalation_channels"] = _normalize_channels(
        cfg.get("escalation_channels"),
        _OPENCLAW_ALERT_POLICY_DEFAULTS["escalation_channels"],
    )
    return cfg


def set_openclaw_alert_policy_config(payload: dict) -> dict:
    current = get_openclaw_alert_policy_config()
    incoming = payload or {}
    if "enabled" in incoming:
        current["enabled"] = bool(incoming.get("enabled"))
    for key in ("notify_on_success", "notify_on_warning", "notify_on_error"):
        if key in incoming:
            current[key] = bool(incoming.get(key))
    if "suppress_seconds" in incoming:
        current["suppress_seconds"] = max(0, min(86400, _safe_int(incoming.get("suppress_seconds"), 1800)))
    if "escalate_after" in incoming:
        current["escalate_after"] = max(1, min(100, _safe_int(incoming.get("escalate_after"), 3)))
    if "success_summary_interval_seconds" in incoming:
        current["success_summary_interval_seconds"] = max(
            0,
            min(604800, _safe_int(incoming.get("success_summary_interval_seconds"), 86400)),
        )
    if "min_level" in incoming:
        min_level = str(incoming.get("min_level", "warning") or "warning").lower()
        current["min_level"] = min_level if min_level in {"success", "info", "warning", "error", "critical"} else "warning"
    if "default_channels" in incoming:
        current["default_channels"] = _normalize_channels(
            incoming.get("default_channels"),
            _OPENCLAW_ALERT_POLICY_DEFAULTS["default_channels"],
        )
    if "escalation_channels" in incoming:
        current["escalation_channels"] = _normalize_channels(
            incoming.get("escalation_channels"),
            _OPENCLAW_ALERT_POLICY_DEFAULTS["escalation_channels"],
        )
    set_kv_json(_OPENCLAW_ALERT_POLICY_KEY, current)
    return get_openclaw_alert_policy_config()


def _extract_schedule_times(raw: str) -> list[str]:
    text = str(raw or "")
    # Supports entries like "09:50", "10:00,11:00", "10:30~14:30(5次)".
    return re.findall(r"\b([01]\d|2[0-3]):[0-5]\d\b", text)


def _is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if os.name == "nt":
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=3,
                creationflags=flags,
            )
            return any(f'"{pid}"' in line for line in result.stdout.splitlines())
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _build_next_task_snapshot(now: datetime, disabled_tasks: set[str], overrides: dict) -> dict:
    best_dt = None
    best_task = None
    for day_offset in range(0, 7):
        day = now.date() + timedelta(days=day_offset)
        for task in SCHEDULE:
            task_key = str(task.get("key", "")).strip()
            if task_key in disabled_tasks:
                continue
            raw_time = overrides.get(task_key) or task.get("time", "")
            for hhmm in _extract_schedule_times(raw_time):
                try:
                    run_dt = datetime.combine(day, datetime.strptime(hhmm, "%H:%M").time())
                except Exception:
                    continue
                if run_dt <= now:
                    continue
                if best_dt is None or run_dt < best_dt:
                    best_dt = run_dt
                    best_task = {
                        "task_key": task_key,
                        "task_name": task.get("name", task_key),
                        "time": hhmm,
                        "scheduled_at": run_dt.isoformat(timespec="seconds"),
                    }
    return best_task or {"task_key": "", "task_name": "", "time": "", "scheduled_at": ""}


def get_daemon_runtime_status() -> dict:
    now = datetime.now()
    leader = get_kv_json(_DAEMON_LEADER_KEY, {}) or {}
    if isinstance(leader, str):
        try:
            leader = json.loads(leader)
        except Exception:
            leader = {}
    raw_disabled = get_kv_json("sched_disabled_tasks", []) or []
    if isinstance(raw_disabled, str):
        try:
            raw_disabled = json.loads(raw_disabled)
        except Exception:
            raw_disabled = []
    disabled = {str(item) for item in raw_disabled} if isinstance(raw_disabled, list) else set()
    overrides = get_kv_json("sched_time_overrides", {}) or {}
    if isinstance(overrides, str):
        try:
            overrides = json.loads(overrides)
        except Exception:
            overrides = {}
    if not isinstance(overrides, dict):
        overrides = {}

    heartbeat_ts = float(leader.get("heartbeat_ts", 0) or 0) if isinstance(leader, dict) else 0
    leader_pid = int(leader.get("pid", 0) or 0) if isinstance(leader, dict) else 0
    active = bool(leader.get("token")) and (time.time() - heartbeat_ts) < _LEADER_TTL_SECONDS and _is_pid_alive(leader_pid)
    push_status = get_kv_json(_DAEMON_PUSH_STATUS_KEY, {}) or {}
    if isinstance(push_status, str):
        try:
            push_status = json.loads(push_status)
        except Exception:
            push_status = {}
    duplicate_lock = get_kv_json(_DAEMON_DUPLICATE_KEY, {}) or {}
    if isinstance(duplicate_lock, str):
        try:
            duplicate_lock = json.loads(duplicate_lock)
        except Exception:
            duplicate_lock = {}

    return {
        "active": active,
        "leader_pid": leader_pid,
        "leader_token": str(leader.get("token", "")) if isinstance(leader, dict) else "",
        "heartbeat_at": str(leader.get("heartbeat_at", "")) if isinstance(leader, dict) else "",
        "heartbeat_age_seconds": int(max(0.0, time.time() - heartbeat_ts)) if heartbeat_ts else -1,
        "disabled_tasks": sorted(disabled),
        "next_task": _build_next_task_snapshot(now, disabled, overrides),
        "push_status": push_status if isinstance(push_status, dict) else {},
        "duplicate_lock": duplicate_lock if isinstance(duplicate_lock, dict) else {},
    }


# 独立运行入口
if __name__ == "__main__":
    os.makedirs("data_cache", exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        handlers=[
            logging.FileHandler(os.path.join("data_cache", "daemon.log"), encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    print("=" * 50)
    print("  FinQuanta Daemon Scheduler")
    print("  7x24 自动化调度 + 预警 + 推送")
    print("=" * 50)

    boards = sys.argv[1:] if len(sys.argv) > 1 else ["人工智能", "芯片", "量子科技", "军工"]
    print(f"  板块: {', '.join(boards)}")
    print(f"  任务: {', '.join(t['name'] for t in SCHEDULE)}")
    print(f"  预警: 每{ALERT_INTERVAL}秒检查止损/止盈")
    print("=" * 50)

    daemon = DaemonScheduler(boards)
    try:
        daemon.run()
    except KeyboardInterrupt:
        print("\nDaemon stopped.")
        daemon.stop()
