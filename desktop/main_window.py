"""
AI 驱动量化客户端 - 主窗口
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QStatusBar,
    QMenu, QMessageBox, QApplication, QTableWidgetItem,
)
from PyQt6.QtGui import QAction, QFont, QColor
from PyQt6.QtCore import Qt, QTimer

from desktop.theme import DARK_STYLE, LIGHT_STYLE
from desktop.db import init_db
from desktop.task_orchestrator import (
    get_recent_system_events,
    get_recent_task_runs,
    log_system_event,
    run_task,
)
from desktop.data_access import RepoCompatConnection, upsert_daily_kline_rows
import logging

_log = logging.getLogger("desktop")
_log_handler = logging.FileHandler(os.path.join("data_cache", "desktop_ops.log"), encoding="utf-8")
_log_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
_log.addHandler(_log_handler)
_log.setLevel(logging.DEBUG)

from desktop.panels.dashboard import DashboardPanel
from desktop.panels.screening import ScreeningPanel
from desktop.panels.portfolio import PortfolioPanel
from desktop.panels.backtest import BacktestPanel
from desktop.panels.stock_analysis import StockAnalysisPanel
from desktop.panels.ai_chat import AIChatPanel
from desktop.panels.ai_portfolio_panel import AIPortfolioPanel
from desktop.panels.short_term_panel import ShortTermPanel
from desktop.panels.trend_verify_panel import TrendVerifyPanel
from desktop.panels.settings import SettingsPanel
from desktop.panels.openclaw_panel import OpenClawPanel
from desktop.panels.ops_center import OpsCenterPanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FinQuanta — AI 量化交易平台")
        self.setMinimumSize(1280, 800)
        self.resize(1440, 900)

        init_db()
        # 启动时同步 CSV/JSON 缓存到 SQLite（首次运行或有新文件时）
        try:
            from desktop.data_sync import sync_csv_to_db
            sync_csv_to_db()
        except Exception:
            pass
        self._current_theme = "dark"
        self.setStyleSheet(DARK_STYLE)

        self._build_menubar()
        self._build_tabs()
        self._build_statusbar()
        self._build_tray()
        self._connect_signals()

        self._auto_refresh_timer = QTimer(self)
        self._auto_refresh_timer.timeout.connect(self._on_auto_refresh)
        self._auto_refresh_timer.start(60_000)

        # 后台守护调度器（替代旧的 QTimer 调度）
        self._daemon = None
        self._start_daemon()

        QTimer.singleShot(500, self._safe_initial_load)
        # 启动后延迟8秒开始后台刷新K线数据
        QTimer.singleShot(8000, self._startup_kline_refresh)

    def _startup_kline_refresh(self):
        """应用启动后，后台静默刷新所有持仓和关注股票的K线数据。"""
        from desktop.workers import Worker

        def _do():
            try:
                conn = RepoCompatConnection()
                codes = set()
                # AI 各仓持仓股
                try:
                    for r in conn.execute(
                        "SELECT DISTINCT code FROM ai_positions WHERE status='open'"
                    ):
                        codes.add(r[0])
                except Exception:
                    pass
                # 手动仓持仓股
                try:
                    import json as _json
                    row = conn.execute(
                        "SELECT value FROM kv_store WHERE key='manual_portfolio'"
                    ).fetchone()
                    if row:
                        for p in _json.loads(row[0]).get("positions", []):
                            codes.add(p.get("code", ""))
                except Exception:
                    pass
                # 所有板块成分股
                for r in conn.execute("SELECT DISTINCT code FROM board_stocks LIMIT 800"):
                    codes.add(r[0])
                conn.close()

                if not codes:
                    return {"fetched": 0, "failed": 0, "rows_updated": 0}

                from desktop.data_sync import refresh_latest_kline
                result = refresh_latest_kline(
                    codes=list(codes), max_codes=800, threads=8
                )
                return result
            except Exception as e:
                return {"error": str(e)}

        def _done(result):
            if result.get("fetched", 0) > 0:
                self.status.showMessage(
                    f"✅ 已更新 {result['fetched']} 只股票K线数据"
                    f"（{result['rows_updated']} 条）"
                )
                _log.info(f"startup kline refresh done: {result}")
            elif "error" in result:
                _log.warning(f"startup kline refresh error: {result['error']}")

        w = Worker(_do)
        w.finished.connect(_done)
        w.error.connect(lambda e: _log.warning(f"startup refresh error: {e}"))
        w.start()
        self._startup_refresh_worker = w

    def _start_daemon(self):
        """启动后台守护调度器（延迟启动，不阻塞 UI 初始化）。"""
        def _delayed_start():
            try:
                import json
                from desktop.daemon_scheduler import start_daemon
                boards = ["人工智能", "芯片", "量子科技", "军工", "新能源汽车"]
                # 读取已保存的禁用任务
                disabled = set()
                try:
                    conn = self._get_db()
                    row = conn.execute(
                        "SELECT value FROM kv_store WHERE key='sched_disabled_tasks'"
                    ).fetchone()
                    row_time = conn.execute(
                        "SELECT value FROM kv_store WHERE key='sched_time_overrides'"
                    ).fetchone()
                    conn.close()
                    if row:
                        disabled = set(json.loads(row[0]))
                        # 同步到设置面板 UI
                        for key, cb in self.settings.sched_checks.items():
                            cb.setChecked(key not in disabled)
                    if row_time:
                        overrides = json.loads(row_time[0])
                        for key, time_text in overrides.items():
                            self.settings.set_schedule_time(key, time_text)
                except Exception:
                    pass

                self._daemon = start_daemon(boards, disabled_tasks=disabled)
                self.settings.sched_status.setText("🟢 调度引擎: 运行中")
                self.settings.sched_status.setStyleSheet("color:#66bb6a; font-size:12px;")
                _log.info("daemon scheduler started")
            except Exception as e:
                _log.error(f"daemon start error: {e}")
        QTimer.singleShot(5000, _delayed_start)

    def _safe_initial_load(self):
        try:
            _log.info("initial_load start")
            self._initial_load()
            _log.info("initial_load done")
        except Exception as e:
            import traceback
            msg = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
            _log.error(f"initial_load error: {msg}")
            self.status.showMessage(f"加载异常: {e}")

    def _build_menubar(self):
        mb = self.menuBar()
        file_menu = mb.addMenu("文件")
        act_exit = QAction("退出", self)
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        view_menu = mb.addMenu("视图")
        act_dark = QAction("深色主题", self)
        act_dark.triggered.connect(lambda: self._set_theme("dark"))
        act_light = QAction("浅色主题", self)
        act_light.triggered.connect(lambda: self._set_theme("light"))
        view_menu.addAction(act_dark)
        view_menu.addAction(act_light)

        help_menu = mb.addMenu("帮助")
        act_about = QAction("关于", self)
        act_about.triggered.connect(self._show_about)
        help_menu.addAction(act_about)

    def _build_tabs(self):
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.West)
        self.tabs.setFont(QFont("", 11))

        self.dashboard = DashboardPanel()
        self.screening = ScreeningPanel()
        self.portfolio = PortfolioPanel()
        self.backtest = BacktestPanel()
        self.stock_analysis = StockAnalysisPanel()
        self.ai_chat = AIChatPanel()
        self.ai_portfolio = AIPortfolioPanel()
        self.short_term = ShortTermPanel()
        self.event_panel = self.short_term.event_panel
        self.fund_panel = self.short_term.fund_panel
        self.trend_verify = TrendVerifyPanel()
        self.openclaw = OpenClawPanel()
        self.ops_center = OpsCenterPanel()
        self.settings = SettingsPanel()

        # 走势验证 + 回测 嵌入选股模块
        self.screening.add_verify_tab(self.trend_verify)
        self.screening.add_backtest_tab(self.backtest)

        # 顶级 tab
        self.tabs.addTab(self.dashboard, "📈 总览")
        self.tabs.addTab(self.screening, "📡 选股")
        self.tabs.addTab(self.short_term, "⚡ 短期选股")
        self.tabs.addTab(self.portfolio, "💼 手动仓")
        self.tabs.addTab(self.ai_portfolio, "🤖 AI仓")
        self.tabs.addTab(self.ai_chat, "💬 AI助手")
        self.tabs.addTab(self.openclaw, "🦀 OpenClaw")
        self.tabs.addTab(self.ops_center, "🛰 运行中心")
        self.tabs.addTab(self.stock_analysis, "📉 个股")
        self.tabs.addTab(self.settings, "⚙️ 设置")

        self.setCentralWidget(self.tabs)

    def _build_statusbar(self):
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("就绪")

    def _build_tray(self):
        # 系统托盘在某些 Windows 版本会导致 C++ 层崩溃，暂时禁用
        self.tray = None

    def _navigate_to_stock(self, code: str):
        """跳转到个股分析页并自动开始分析（防抖 + 延迟）。"""
        if not code or len(code) != 6:
            return
        now = __import__("time").time()
        if hasattr(self, "_last_nav_time") and now - self._last_nav_time < 1.0:
            return
        self._last_nav_time = now
        try:
            _log.info(f"navigate_to_stock: {code}")
            self.stock_analysis.code_input.setText(code)
            self.tabs.setCurrentWidget(self.stock_analysis)
            QTimer.singleShot(200, self._on_stock_analyze)
        except Exception as e:
            _log.error(f"navigate_to_stock error: {e}")
            self.status.showMessage(f"跳转失败: {e}")

    def _connect_signals(self):
        self.screening.btn_scan.clicked.connect(self._on_scan)
        self.screening.btn_quantum_run.clicked.connect(self._on_quantum_optimize)
        self.screening.btn_pure_q_run.clicked.connect(self._on_pure_quantum_optimize)
        self.screening.btn_commodity_load.clicked.connect(self._on_commodity_load)
        self.screening.quantum_table.cellDoubleClicked.connect(self._on_quantum_dblclick)
        self.screening.pure_q_table.cellDoubleClicked.connect(self._on_pure_quantum_dblclick)
        self.screening.commodity_table.cellDoubleClicked.connect(self._on_commodity_dblclick)
        self.portfolio.btn_refresh.clicked.connect(self._on_portfolio_refresh)
        self.portfolio.btn_buy.clicked.connect(self._on_manual_buy)
        self.portfolio.btn_sell.clicked.connect(self._on_manual_sell)
        self.backtest.btn_run.clicked.connect(self._on_backtest_run)
        self.backtest.btn_monte_carlo.clicked.connect(self._on_monte_carlo)
        self.backtest.btn_walkforward.clicked.connect(self._on_walk_forward)
        self.backtest.btn_multi_compare.clicked.connect(self._on_multi_compare)
        self.stock_analysis.btn_analyze.clicked.connect(self._on_stock_analyze)
        self.stock_analysis.code_input.returnPressed.connect(self._on_stock_analyze)
        self.ai_chat.btn_send.clicked.connect(self._on_ai_send)
        self.ai_chat.msg_input.returnPressed.connect(self._on_ai_send)
        self.ai_chat.btn_confirm_action.clicked.connect(self._on_ai_confirm_action)
        self.ai_chat.btn_cancel_action.clicked.connect(self._on_ai_cancel_action)
        self.event_panel.btn_analyze.clicked.connect(self._on_event_analyze)
        self.event_panel.btn_save.clicked.connect(self._on_event_save)
        self.event_panel.btn_fetch_news.clicked.connect(self._on_fetch_news)
        self.event_panel.btn_fetch_broker.clicked.connect(self._on_fetch_broker)
        self.event_panel.backtest_table.cellClicked.connect(self._on_bt_board_click)
        self.event_panel.recommend_table.cellDoubleClicked.connect(self._on_event_stock_dblclick)
        self.event_panel.bt_detail_table.cellDoubleClicked.connect(self._on_event_stock_dblclick_bt)
        self.fund_panel.btn_load.clicked.connect(self._on_fund_load)
        self.fund_panel.btn_analyze.clicked.connect(self._on_fund_analyze)
        self.fund_panel.btn_compare.clicked.connect(self._on_fund_compare)
        self.fund_panel.holdings_table.cellDoubleClicked.connect(self._on_fund_stock_dblclick_holdings)
        self.fund_panel.perf_table.cellDoubleClicked.connect(self._on_fund_stock_dblclick)
        self.fund_panel.changes_table.cellDoubleClicked.connect(self._on_fund_stock_dblclick_changes)
        self.fund_panel.btn_load_mgr.clicked.connect(self._on_star_mgr_load)
        self.fund_panel.mgr_holdings_table.cellDoubleClicked.connect(self._on_star_stock_dblclick)
        self.trend_verify.btn_calibrate.clicked.connect(self._on_trend_calibrate)
        self.trend_verify.btn_ai_analyze.clicked.connect(self._on_trend_ai_analyze)
        self.trend_verify.table.cellDoubleClicked.connect(self._on_trend_verify_dblclick)
        self.ai_portfolio.btn_save_config.clicked.connect(self._on_ai_save_config)
        self.ai_portfolio.btn_run_ai.clicked.connect(self._on_ai_run_decision)
        self.ai_portfolio.btn_execute.clicked.connect(self._on_ai_execute_decisions)
        self.ai_portfolio.btn_auto_run.clicked.connect(self._on_ai_auto_cycle)
        self.ai_portfolio.btn_full_auto.clicked.connect(self._on_full_auto_cycle)
        self.ai_portfolio.btn_custom_scan.clicked.connect(self._on_custom_buy_top3)
        self.ai_portfolio.btn_custom_calibrate.clicked.connect(self._on_custom_calibrate)
        self.ai_portfolio.btn_quantum_buy.clicked.connect(self._on_quantum_buy)
        self.ai_portfolio.decisions_table.cellDoubleClicked.connect(self._on_ai_decision_dblclick)
        self.ai_portfolio.pos_table.cellDoubleClicked.connect(self._on_ai_pos_dblclick)
        self.ai_portfolio.pos_table.cellClicked.connect(self._on_ai_pos_click)
        self.ai_portfolio.btn_action_chart.clicked.connect(lambda: self._action_goto_chart("ai"))
        self.ai_portfolio.btn_action_buy.clicked.connect(lambda: self._action_buy("ai"))
        self.ai_portfolio.btn_action_sell.clicked.connect(lambda: self._action_sell("ai"))
        self.ai_portfolio.btn_action_detail.clicked.connect(lambda: self._action_detail("ai"))
        self.ai_portfolio.btn_action_condition.clicked.connect(lambda: self._action_condition("ai"))
        self.ai_portfolio.btn_action_ai_suggest.clicked.connect(lambda: self._action_ai_suggest("ai"))
        self.ai_portfolio.tracking_table.cellDoubleClicked.connect(self._on_tracking_dblclick)
        self.settings.combo_theme.currentTextChanged.connect(
            lambda t: self._set_theme("dark" if t == "深色" else "light")
        )
        # OpenClaw 面板
        self.openclaw.btn_save_cfg.clicked.connect(self._on_openclaw_save_cfg)
        self.openclaw.btn_connect.clicked.connect(self._on_openclaw_connect)
        self.openclaw.btn_run_pipeline.clicked.connect(self._on_openclaw_pipeline)
        self.openclaw.btn_fetch_all.clicked.connect(self._on_openclaw_fetch_all)
        self.openclaw.btn_fetch_news.clicked.connect(
            lambda: self.openclaw.monitor_log.append("📰 资讯抓取中...") or self._on_openclaw_fetch_all()
        )
        self.openclaw.btn_fetch_realtime.clicked.connect(
            lambda: self.openclaw.monitor_log.append("⚡ 实时行情刷新中...") or self._on_openclaw_fetch_all()
        )
        self.openclaw.btn_fetch_fund.clicked.connect(
            lambda: self.openclaw.monitor_log.append("📋 基金持仓更新中...") or self._on_openclaw_connect()
        )
        self.openclaw.btn_refresh_ops.clicked.connect(self._on_openclaw_refresh_ops)
        self.ops_center.btn_refresh.clicked.connect(self._on_ops_center_refresh)
        self.openclaw.btn_nl_run.clicked.connect(self._on_openclaw_nl_strategy)
        self.openclaw.btn_generate_report.clicked.connect(self._on_openclaw_report)
        self.openclaw.btn_suggest_optimize.clicked.connect(self._on_openclaw_optimize)
        self.openclaw.btn_learn_now.clicked.connect(self._on_openclaw_learn)
        self.openclaw.btn_evolve_advice.clicked.connect(self._on_openclaw_evolve_advice)
        self.openclaw.btn_apply_weights.clicked.connect(self._on_openclaw_apply_weights)
        self.openclaw.decision_result_table.cellDoubleClicked.connect(self._on_openclaw_stock_dblclick)

        self.settings.btn_save_push.clicked.connect(self._on_save_push)
        self.settings.btn_test_push.clicked.connect(self._on_test_push)
        self.settings.btn_save_ai.clicked.connect(self._on_settings_save_ai)
        self.settings.btn_save_sched.clicked.connect(self._on_save_sched_config)
        self.settings.btn_run_pipeline_now.clicked.connect(self._on_run_pipeline_now)
        self.settings.btn_view_sched_log.clicked.connect(self._on_view_sched_log)
        self.dashboard.pos_table.cellDoubleClicked.connect(self._on_dashboard_stock_dblclick)
        self.portfolio.pos_table.cellDoubleClicked.connect(self._on_portfolio_stock_dblclick)
        self.portfolio.pos_table.cellClicked.connect(self._on_portfolio_stock_click)
        self.portfolio.btn_action_chart.clicked.connect(lambda: self._action_goto_chart("manual"))
        self.portfolio.btn_action_buy.clicked.connect(lambda: self._action_buy("manual"))
        self.portfolio.btn_action_sell.clicked.connect(lambda: self._action_sell("manual"))
        self.portfolio.btn_action_detail.clicked.connect(lambda: self._action_detail("manual"))
        self.portfolio.btn_action_condition.clicked.connect(lambda: self._action_condition("manual"))
        self.portfolio.btn_action_ai_suggest.clicked.connect(lambda: self._action_ai_suggest("manual"))
        self.screening.result_table.cellDoubleClicked.connect(self._on_screening_stock_dblclick)

    def _on_dashboard_stock_dblclick(self, row, col):
        item = self.dashboard.pos_table.item(row, 0)
        if item:
            self._navigate_to_stock(item.text().strip())

    def _on_portfolio_stock_click(self, row, col):
        """手动仓：单击显示操作栏。"""
        code_item = self.portfolio.pos_table.item(row, 0)
        name_item = self.portfolio.pos_table.item(row, 1)
        if not code_item:
            return
        code = code_item.text().strip()
        name = name_item.text().strip() if name_item else code
        if not code or len(code) != 6:
            return
        self._active_action_code = code
        self._active_action_source = "manual"
        self.portfolio.action_stock_label.setText(f"{code} {name}")
        self.portfolio.action_bar.setVisible(True)

    def _on_portfolio_stock_dblclick(self, row, col):
        """手动仓：双击跳转个股行情。"""
        item = self.portfolio.pos_table.item(row, 0)
        if item:
            self._navigate_to_stock(item.text().strip())

    # ═══════ 操作栏统一处理 ═══════

    def _action_goto_chart(self, source: str):
        """看行情：跳转个股分析。"""
        code = getattr(self, "_active_action_code", "")
        if code:
            self._navigate_to_stock(code)

    def _action_buy(self, source: str):
        """买入：自动填充代码和最新价，跳转到买入表单。"""
        code = getattr(self, "_active_action_code", "")
        if not code:
            return
        try:
            from desktop.ai_trader import _get_real_price
            price = _get_real_price(code)
        except Exception:
            price = 0

        if source == "manual":
            self.portfolio.buy_code.setText(code)
            if price > 0:
                self.portfolio.buy_price.setValue(price)
            self.portfolio.inner_tabs.setCurrentIndex(1)  # 切换到「买入」tab
            self.status.showMessage(f"买入 {code}，最新价 ¥{price:.2f}" if price > 0 else f"买入 {code}")
        else:
            # AI 仓：跳转到手动仓买入界面（AI 仓买入由 AI 决策驱动）
            self.portfolio.buy_code.setText(code)
            if price > 0:
                self.portfolio.buy_price.setValue(price)
            self.portfolio.inner_tabs.setCurrentIndex(1)
            self.tabs.setCurrentWidget(self.portfolio)
            self.status.showMessage(f"已跳转到买入界面，{code} 最新价 ¥{price:.2f}")

    def _action_sell(self, source: str):
        """卖出：自动填充代码和最新价，跳转到卖出表单。"""
        code = getattr(self, "_active_action_code", "")
        if not code:
            return
        try:
            from desktop.ai_trader import _get_real_price
            price = _get_real_price(code)
        except Exception:
            price = 0

        if source == "manual":
            self.portfolio.sell_code.setText(code)
            if price > 0:
                self.portfolio.sell_price.setValue(price)
            self.portfolio.inner_tabs.setCurrentIndex(2)
            self.status.showMessage(f"卖出 {code}，最新价 ¥{price:.2f}" if price > 0 else f"卖出 {code}")
        else:
            # AI 仓：直接执行卖出（查找该股票所在的仓位模式）
            if price <= 0:
                self.status.showMessage(f"⚠ 无法获取 {code} 价格")
                return
            from desktop.workers import Worker

            def _do_sell():
                conn = RepoCompatConnection()
                row = conn.execute(
                    "SELECT mode FROM ai_positions WHERE code=? AND status='open' LIMIT 1",
                    (code,),
                ).fetchone()
                conn.close()
                if not row:
                    return f"⚠ AI 仓未持有 {code}"
                mode = row[0]
                from desktop.ai_portfolio import sell
                return sell(mode, code, price, "操作栏手动卖出")

            def _done(msg):
                self.status.showMessage(msg)
                self._refresh_ai_portfolio()

            w = Worker(_do_sell)
            w.finished.connect(_done)
            w.error.connect(lambda e: self.status.showMessage(f"卖出失败: {e}"))
            w.start()
            self._action_sell_worker = w

    def _action_detail(self, source: str):
        """明细：跳转到个股分析。"""
        self._action_goto_chart(source)

    def _action_ai_suggest(self, source: str):
        """OpenClaw AI 研判：分析个股并给出买入/持有/卖出建议。"""
        code = getattr(self, "_active_action_code", "")
        if not code:
            return

        panel = self.portfolio if source == "manual" else self.ai_portfolio
        panel.ai_suggest_label.setVisible(True)
        panel.ai_suggest_label.setText(f"🦀 OpenClaw 正在分析 {code}...")
        panel.ai_suggest_label.setStyleSheet("color:#ffb74d; font-size:12px; padding:4px;")
        self.status.showMessage(f"🦀 OpenClaw 研判 {code}...")

        from desktop.workers import Worker

        def _do():
            from desktop.ai_trader import _call_llm, _get_real_price

            price = _get_real_price(code)
            conn = RepoCompatConnection()

            # 读取K线数据
            rows = conn.execute(
                "SELECT date, close, high, low, volume FROM daily_kline "
                "WHERE code=? ORDER BY date DESC LIMIT 60", (code,)
            ).fetchall()
            name_r = conn.execute("SELECT name FROM stock_list WHERE code=?", (code,)).fetchone()
            name = name_r[0] if name_r else code

            # 读取学习权重
            weights_ctx = ""
            try:
                from desktop.openclaw_learner import get_strategy_weights
                w = get_strategy_weights()
                if w:
                    best = max(w.items(), key=lambda x: x[1].get("weight", 0))
                    weights_ctx = f"\n策略学习反馈: 最优策略{best[0]}(准确率{best[1]['accuracy']:.0f}%)"
            except Exception:
                pass

            # 构建上下文
            import numpy as np
            ctx_lines = [f"股票: {code} {name}，最新价: {price:.2f}"]
            if rows:
                closes = [r[1] for r in reversed(rows)]
                n = len(closes)
                if n >= 5:
                    ma5 = np.mean(closes[-5:])
                    ma20 = np.mean(closes[-20:]) if n >= 20 else ma5
                    ma50 = np.mean(closes[-50:]) if n >= 50 else ma20
                    pct5 = (closes[-1] / closes[-6] - 1) * 100 if n >= 6 else 0
                    pct20 = (closes[-1] / closes[-21] - 1) * 100 if n >= 21 else 0
                    ctx_lines.append(f"MA5={ma5:.2f} MA20={ma20:.2f} MA50={ma50:.2f}")
                    ctx_lines.append(f"5日涨跌={pct5:+.1f}% 20日涨跌={pct20:+.1f}%")
                    high52 = max(r[2] for r in rows)
                    low52 = min(r[3] for r in rows)
                    ctx_lines.append(f"60日最高={high52:.2f} 最低={low52:.2f}")
            ctx_lines.append(weights_ctx)
            conn.close()

            prompt = (
                f"请分析以下股票并给出操作建议：\n"
                f"{'  '.join(ctx_lines)}\n\n"
                f"请回答：\n"
                f"1. 当前趋势判断（上升/震荡/下跌）\n"
                f"2. 操作建议（买入/持有/卖出/观望）及理由\n"
                f"3. 如果买入，建议止损价和目标价\n"
                f"4. 关键风险提示\n"
                f"请简洁回答，不超过100字。"
            )
            return _call_llm(prompt, system="你是A股量化交易专家，基于技术分析给出简洁操作建议。")

        def _done(result):
            panel.ai_suggest_label.setText(f"🦀 {code} 研判：{result}")
            panel.ai_suggest_label.setStyleSheet("color:#4fc3f7; font-size:12px; padding:4px;")
            self.status.showMessage(f"🦀 OpenClaw 研判完成")

        def _err(msg):
            panel.ai_suggest_label.setText(f"❌ 研判失败: {msg}")
            panel.ai_suggest_label.setStyleSheet("color:#ef5350; font-size:12px; padding:4px;")

        w = Worker(_do)
        w.finished.connect(_done)
        w.error.connect(_err)
        w.start()
        self._ai_suggest_worker = w

    def _action_condition(self, source: str):
        """条件单：设置止盈止损条件。"""
        code = getattr(self, "_active_action_code", "")
        self.status.showMessage(f"⏰ 条件单功能开发中... 选中: {code}")

    def _on_screening_stock_dblclick(self, row, col):
        item = self.screening.result_table.item(row, 0)
        if item:
            self._navigate_to_stock(item.text().strip())

    def _set_theme(self, theme: str):
        self._current_theme = theme
        self.setStyleSheet(DARK_STYLE if theme == "dark" else LIGHT_STYLE)

    def closeEvent(self, event):
        event.accept()

    def _show_about(self):
        QMessageBox.about(
            self, "关于 FinQuanta",
            "FinQuanta — AI 量化交易平台 v2.0\n\n"
            "多策略选股 / 多智能体决策 / 三仓对比\n"
            "事件驱动 / 基金跟踪 / 因子研究\n"
            "蒙特卡洛 / Walk-Forward / 组合优化\n\n"
            "基于 PyQt6 + SQLite + 多源行情 + LLM"
        )

    def _initial_load(self):
        self.status.showMessage("加载数据中...")
        self._load_dashboard()
        self._load_strategy_catalog()
        self._load_board_tree()
        self._refresh_ai_portfolio()
        try:
            from desktop.event_strategy import get_events
            self.event_panel.update_history(get_events(50))
        except Exception as e:
            _log.warning(f"event load: {e}")
        try:
            from desktop.fund_strategy import get_star_managers
            self.fund_panel.update_star_summary(get_star_managers())
        except Exception as e:
            _log.warning(f"fund load: {e}")
        self._load_default_index_chart()
        self._load_ai_config()
        self._load_settings_ai_config()
        self._load_push_config()
        self._load_openclaw_panel_config()
        # OpenClaw 自动连接（延迟3秒，等数据加载完）
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(3000, self._auto_connect_openclaw)
        QTimer.singleShot(3500, self._on_ops_center_refresh)
        try:
            from desktop.trend_verify import get_records, get_accuracy_stats
            self.trend_verify.update_records(get_records(200))
            self.trend_verify.update_stats(get_accuracy_stats())
        except Exception as e:
            _log.warning(f"trend_verify load: {e}")

    def _load_ai_config(self):
        """启动时从 SQLite 加载 AI API 配置，更新状态显示。"""
        try:
            from desktop.ai_trader import _get_api_config
            cfg = _get_api_config()
            key = cfg.get("api_key", "")
            base_url = cfg.get("base_url", "")
            model = cfg.get("model", "")

            # 更新 AI仓 配置状态标签
            if key:
                provider = "DeepSeek"
                _url_provider = {
                    "deepseek": "DeepSeek", "openai": "OpenAI",
                    "generativelanguage.googleapis": "Gemini",
                    "anthropic": "Claude", "dashscope": "通义千问",
                    "moonshot": "Kimi",
                }
                for url_key, prov in _url_provider.items():
                    if url_key in (base_url or "").lower():
                        provider = prov
                        break
                self.ai_portfolio.ai_config_label.setText(
                    f"✅ AI 已配置: {provider} / {model or 'default'}  "
                    f"（修改请到「⚙️ 设置」→ AI模型配置）"
                )
                self.ai_portfolio.ai_config_label.setStyleSheet("color:#66bb6a; font-size:12px;")
            else:
                self.ai_portfolio.ai_config_label.setText(
                    "⚠ AI 未配置，请到「⚙️ 设置」→ AI模型配置 中设置 API Key"
                )
                self.ai_portfolio.ai_config_label.setStyleSheet("color:#ffb74d; font-size:12px;")

            if model:
                idx = self.ai_portfolio.model_combo.findText(model)
                if idx >= 0:
                    self.ai_portfolio.model_combo.setCurrentIndex(idx)
                else:
                    self.ai_portfolio.model_combo.setCurrentText(model)

            if key:
                self.status.showMessage(f"已加载 AI 配置: {model or 'default'}")
        except Exception:
            pass

    def _load_settings_ai_config(self):
        """启动时将 AI 配置同步到设置面板。"""
        try:
            import json
            conn = self._get_db()
            row = conn.execute("SELECT value FROM kv_store WHERE key='ai_config'").fetchone()
            conn.close()
            if row:
                cfg = json.loads(row[0])
                key = cfg.get("api_key", "")
                base_url = cfg.get("base_url", "")
                provider = cfg.get("provider", "")
                if key:
                    self.settings.ai_key.setText(key)
                if base_url:
                    self.settings.ai_base_url.setText(base_url)
                if provider:
                    idx = self.settings.ai_provider.findText(provider)
                    if idx >= 0:
                        self.settings.ai_provider.setCurrentIndex(idx)
        except Exception:
            pass

    def _load_push_config(self):
        """启动时加载已保存的推送配置，回填到 UI。"""
        try:
            from signal_push import get_push_config
            cfg = get_push_config()
            key = cfg.get("serverchan_key", "")
            webhook = cfg.get("wecom_webhook", "")
            if key:
                self.settings.push_key.setText(key)
            if webhook:
                self.settings.wecom_webhook.setText(webhook)
            channels = []
            if key:
                channels.append("Server酱")
            if webhook:
                channels.append("企业微信")
            if channels:
                self.settings.push_status.setText(f"✅ 已配置: {' + '.join(channels)}")
                self.settings.push_status.setStyleSheet("color:#66bb6a; font-size:11px;")
        except Exception:
            pass

    def _load_openclaw_panel_config(self):
        """启动时加载 OpenClaw 面板配置。"""
        try:
            import json
            conn = self._get_db()
            row = conn.execute("SELECT value FROM kv_store WHERE key='openclaw_panel_cfg'").fetchone()
            conn.close()
            if row:
                cfg = json.loads(row[0])
                api_key = cfg.get("api_key", "")
                if api_key:
                    self.openclaw.api_key_input.setText(api_key)
                llm_idx = cfg.get("llm_engine_idx", 0)
                if 0 <= llm_idx < self.openclaw.llm_engine.count():
                    self.openclaw.llm_engine.setCurrentIndex(llm_idx)
                exec_idx = cfg.get("exec_mode_idx", 0)
                if 0 <= exec_idx < self.openclaw.exec_mode.count():
                    self.openclaw.exec_mode.setCurrentIndex(exec_idx)
                freq_idx = cfg.get("run_freq_idx", 0)
                if 0 <= freq_idx < self.openclaw.run_freq.count():
                    self.openclaw.run_freq.setCurrentIndex(freq_idx)
            else:
                # Default: inherit AI key from ai_portfolio
                ai_key = self.ai_portfolio.api_key_input.text().strip()
                if ai_key:
                    self.openclaw.api_key_input.setText(ai_key)
        except Exception:
            pass

    def _save_openclaw_panel_config(self):
        """保存 OpenClaw 面板配置到 DB。"""
        try:
            import json
            cfg = {
                "api_key": self.openclaw.api_key_input.text().strip(),
                "llm_engine_idx": self.openclaw.llm_engine.currentIndex(),
                "exec_mode_idx": self.openclaw.exec_mode.currentIndex(),
                "run_freq_idx": self.openclaw.run_freq.currentIndex(),
            }
            conn = self._get_db()
            conn.execute(
                "INSERT OR REPLACE INTO kv_store VALUES (?,?,datetime('now'))",
                ("openclaw_panel_cfg", json.dumps(cfg)),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    def _load_default_index_chart(self):
        """启动时在个股分析页显示上证指数 K 线（默认占位）。"""
        try:
            import numpy as np
            conn = self._get_db()
            # 尝试从 daily_kline 查找 000001（上证指数有时存为 sh000001）
            for code in ["000001", "sh000001", "999999"]:
                cur = conn.execute(
                    "SELECT date, open, high, low, close FROM daily_kline WHERE code=? ORDER BY date",
                    (code,),
                )
                rows = cur.fetchall()
                if len(rows) >= 50:
                    break

            if len(rows) < 50:
                # 取数据库中数据最多的股票作为默认展示
                cur = conn.execute("""
                    SELECT code FROM daily_kline GROUP BY code
                    ORDER BY COUNT(*) DESC LIMIT 1
                """)
                top = cur.fetchone()
                if top:
                    cur = conn.execute(
                        "SELECT date, open, high, low, close FROM daily_kline WHERE code=? ORDER BY date",
                        (top[0],),
                    )
                    rows = cur.fetchall()
                    # 查名称
                    cur_n = conn.execute("SELECT name FROM stock_list WHERE code=?", (top[0],))
                    rn = cur_n.fetchone()
                    name = rn[0] if rn else top[0]
                    self.stock_analysis.header_label.setText(f"默认展示: {top[0]} {name}")

            conn.close()

            if len(rows) >= 50:
                dates = [r[0] for r in rows]
                opens = np.array([r[1] for r in rows])
                highs = np.array([r[2] for r in rows])
                lows = np.array([r[3] for r in rows])
                closes = np.array([r[4] for r in rows])
                self.stock_analysis.update_chart(dates, opens, highs, lows, closes)
        except Exception:
            pass

    def _get_db(self) -> RepoCompatConnection:
        return RepoCompatConnection()

    def _get_names_and_boards(self, codes: list[str]) -> tuple[dict, dict]:
        """从 SQLite 查询股票名称和板块归属。"""
        names = {}
        boards = {}
        if not codes:
            return names, boards
        try:
            conn = self._get_db()
            for code in set(codes):
                if not code:
                    continue
                cur = conn.execute("SELECT name FROM stock_list WHERE code=?", (code,))
                row = cur.fetchone()
                if row:
                    names[code] = row[0]
                cur_b = conn.execute("SELECT board FROM board_stocks WHERE code=? LIMIT 1", (code,))
                row_b = cur_b.fetchone()
                if row_b:
                    boards[code] = row_b[0]
            conn.close()
        except Exception:
            pass
        return names, boards

    def _load_dashboard(self):
        """从 SQLite 数据库加载持仓和行情。"""
        import json

        pf = {}
        # 优先从 SQLite 读取手动仓（统一数据源）
        try:
            conn_pf = self._get_db()
            row_pf = conn_pf.execute(
                "SELECT value FROM kv_store WHERE key='manual_portfolio'"
            ).fetchone()
            conn_pf.close()
            if row_pf:
                pf = json.loads(row_pf[0])
        except Exception:
            pass

        # 兜底：从 portfolio.json 读取并迁移到 SQLite
        if not pf:
            pf_path = "portfolio.json"
            if os.path.exists(pf_path):
                try:
                    with open(pf_path, "r", encoding="utf-8") as f:
                        pf = json.load(f)
                    # 迁移到 SQLite
                    conn_mig = self._get_db()
                    conn_mig.execute(
                        "INSERT OR REPLACE INTO kv_store VALUES (?,?,datetime('now'))",
                        ("manual_portfolio", json.dumps(pf)),
                    )
                    conn_mig.commit()
                    conn_mig.close()
                    _log.info("migrated portfolio.json to SQLite kv_store")
                except Exception:
                    pf = {}

        positions = pf.get("positions", [])
        cash = float(pf.get("cash", 1_000_000))
        initial_capital = float(pf.get("initial_capital", 1_000_000))

        names = getattr(self, "_stock_names_cache", {})
        pos_details = []
        total_mv = 0.0
        total_cost = 0.0
        unrealized_pnl = 0.0
        today_pnl = 0.0

        # 批量获取实时行情
        pos_codes = [pos.get("code", "") for pos in positions if pos.get("code")]
        realtime_prices = {}
        if pos_codes:
            try:
                from desktop.realtime_data import get_realtime_quotes
                quotes = get_realtime_quotes(pos_codes, force=False)
                for code, q in quotes.items():
                    px = q.get("price", 0)
                    if px and px > 0:
                        realtime_prices[code] = float(px)
            except Exception:
                pass

        conn = self._get_db()
        for pos in positions:
            code = pos.get("code", "")
            entry = float(pos.get("entry_price", 0))
            shares = int(pos.get("shares", 0))
            price = entry
            prev_c = entry

            # 优先用实时行情，其次日K收盘
            if code in realtime_prices:
                price = realtime_prices[code]
            try:
                cur = conn.execute(
                    "SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 2",
                    (str(code),),
                )
                rows_db = cur.fetchall()
                if code not in realtime_prices and rows_db:
                    price = float(rows_db[0][0])
                if len(rows_db) >= 2:
                    prev_c = float(rows_db[1][0])
                elif rows_db:
                    prev_c = float(rows_db[0][0])
            except Exception:
                pass

            mv = price * shares
            cost = entry * shares
            pnl = mv - cost
            pnl_pct = pnl / cost * 100 if cost > 0 else 0
            day_pnl_val = (price - prev_c) * shares
            day_pnl_pct = (price - prev_c) / prev_c * 100 if prev_c > 0 else 0

            total_mv += mv
            total_cost += cost
            unrealized_pnl += pnl
            today_pnl += day_pnl_val

            pos_details.append({
                "代码": code,
                "名称": names.get(code, pos.get("name", "")),
                "买入价": round(entry, 2),
                "现价": round(price, 2),
                "昨收": round(prev_c, 2),
                "股数": shares,
                "市值": round(mv, 2),
                "成本": round(cost, 2),
                "浮动盈亏": round(pnl, 2),
                "盈亏%": round(pnl_pct, 2),
                "当日盈亏": round(day_pnl_val, 2),
                "当日%": round(day_pnl_pct, 2),
                "买入日": pos.get("entry_date", "-"),
                "阶段": "-",
            })

        total_equity = cash + total_mv
        total_return = (total_equity - initial_capital) / initial_capital * 100 if initial_capital > 0 else 0

        summary = {
            "total_equity": round(total_equity, 2),
            "total_return": round(total_return, 2),
            "position_value": round(total_mv, 2),
            "total_cost": round(total_cost, 2),
            "cash": round(cash, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "unrealized_pnl_pct": round(unrealized_pnl / total_cost * 100, 2) if total_cost > 0 else 0,
            "today_pnl": round(today_pnl, 2),
            "num_positions": len(positions),
            "max_positions": 8,
            "position_ratio": round(total_mv / total_equity * 100, 1) if total_equity > 0 else 0,
            "positions": pos_details,
        }

        conn.close()

        self.portfolio.update_summary(summary)
        self.portfolio.update_positions(pos_details)
        self.portfolio.update_history(pf.get("history", []))

        # 总览页：统一快照驱动（手动仓 + AI四仓）
        try:
            from desktop.snapshot_service import get_system_snapshot
            snap = get_system_snapshot()
            comp = snap.get("ai_portfolios", {})
            self.dashboard.update_metrics(summary, comp=comp)
            self.dashboard.update_comparison(comp, manual_summary=summary)

            all_states = {}
            # 手动仓转为统一格式
            all_states["manual_portfolio"] = {
                "positions": [
                    {"code": p.get("代码", ""), "name": p.get("名称", ""),
                     "entry_price": p.get("买入价", 0), "shares": p.get("股数", 0),
                     "entry_date": p.get("买入日", "")}
                    for p in pos_details
                ],
                "cash": cash,
            }
            snap_states = snap.get("ai_states", {})
            for mode in ("full_auto", "auto", "custom", "quantum"):
                all_states[mode] = snap_states.get(mode, {"positions": [], "cash": 0})

            # 合并价格（手动仓的价格也要加入）
            all_prices = dict(comp.get("prices", {}))
            for p in pos_details:
                code = p.get("代码", "")
                px = p.get("现价", 0)
                if code and px:
                    all_prices[code] = px

            self.dashboard.update_all_positions(all_states, all_prices)
        except Exception as e:
            _log.warning(f"dashboard comp/positions error: {e}")

        # 市场环境 + 组合风险（优先读取统一快照，缺失时后台刷新）
        from desktop.workers import Worker

        def _calc_market_and_risk():
            from desktop.snapshot_service import get_system_snapshot
            snap = get_system_snapshot()
            market = snap.get("market_state", {})
            risk = snap.get("risk", {}) or {"var95": 0, "var99": 0, "max_exposure": 0, "max_name": "-", "hhi": 0, "drawdown": 0}
            dist_count = market.get("dist_count", -1)
            market_ok = market.get("state", "neutral") != "risk_off"
            return {"market_ok": market_ok, "dist_count": dist_count, "risk": risk, "market": market}

        def _on_market_done(result):
            dist = result["dist_count"]
            market_state = result.get("market", {})
            if dist >= 0:
                self.dashboard.update_market(result["market_ok"], dist)
                if market_state.get("reason"):
                    self.dashboard.market_label.setText(
                        self.dashboard.market_label.text() + f" | {market_state.get('reason','')}"
                    )
            else:
                self.dashboard.market_label.setText("📊 市场环境：等待快照更新…")
                self.dashboard.market_label.setStyleSheet("color: #888; font-size: 13px;")

            r = result["risk"]
            var95 = abs(r.get("var95", 0))
            var99 = abs(r.get("var99", 0))
            exp = r.get("max_exposure", 0)
            hhi = r.get("hhi", 0)
            dd = r.get("drawdown", 0)

            # 更新风险卡片数值
            lbl95 = self.dashboard.risk_labels.get("VaR(95%)")
            if lbl95:
                lbl95.setText(f"¥{var95:,.0f}" if var95 > 0 else "暂无")
                lbl95.setStyleSheet(
                    f"color: {'#ef5350' if var95 > 50000 else '#ffb74d' if var95 > 20000 else '#4fc3f7'};"
                    f"font-size:15px; font-weight:bold; border:none;"
                )

            lbl99 = self.dashboard.risk_labels.get("VaR(99%)")
            if lbl99:
                lbl99.setText(f"¥{var99:,.0f}" if var99 > 0 else "暂无")
                lbl99.setStyleSheet(
                    f"color: {'#ef5350' if var99 > 80000 else '#ffb74d' if var99 > 40000 else '#ce93d8'};"
                    f"font-size:15px; font-weight:bold; border:none;"
                )

            lbl_exp = self.dashboard.risk_labels.get("最大单股敞口")
            if lbl_exp:
                if exp > 0:
                    lbl_exp.setText(f"{exp:.0%}  ({r.get('max_name', '-')})")
                    lbl_exp.setStyleSheet(
                        f"color: {'#ef5350' if exp > 0.4 else '#ffb74d' if exp > 0.25 else '#81c784'};"
                        f"font-size:15px; font-weight:bold; border:none;"
                    )
                else:
                    lbl_exp.setText("暂无持仓")

            lbl_hhi = self.dashboard.risk_labels.get("集中度HHI")
            if lbl_hhi:
                if hhi > 0:
                    level = "高度集中" if hhi > 0.5 else "中等集中" if hhi > 0.25 else "较分散"
                    lbl_hhi.setText(f"{hhi:.3f}  ({level})")
                    lbl_hhi.setStyleSheet(
                        f"color: {'#ef5350' if hhi > 0.5 else '#ffb74d' if hhi > 0.25 else '#81c784'};"
                        f"font-size:15px; font-weight:bold; border:none;"
                    )
                else:
                    lbl_hhi.setText("暂无持仓")

            self.dashboard.card_drawdown.set_value(
                f"{dd:.2%}" if dd != 0 else "0.00%", "", abs(dd) < 0.08
            )
            self.status.showMessage("总览数据加载完成")

        self._market_worker = Worker(_calc_market_and_risk)
        self._market_worker.finished.connect(_on_market_done)
        self._market_worker.error.connect(
            lambda e: _log.warning(f"market/risk load error: {e}")
        )
        self._market_worker.start()

    def _load_strategy_catalog(self):
        try:
            import json as _json
            profiles_path = os.path.join("data_cache", "strategy_catalog.json")
            if os.path.exists(profiles_path):
                with open(profiles_path, "r", encoding="utf-8") as f:
                    catalog = _json.load(f)
            else:
                from strategy_profiles import get_strategy_catalog
                catalog = get_strategy_catalog()
                os.makedirs("data_cache", exist_ok=True)
                with open(profiles_path, "w", encoding="utf-8") as f:
                    _json.dump(catalog, f, ensure_ascii=False, indent=2)
            for item in catalog:
                label = f"[{item.get('region', '-')}/{item.get('camp', '-')}] {item['name']}"
                self.screening.combo_strategy.addItem(label, item["id"])
                self.backtest.combo_strategy.addItem(label, item["id"])
        except Exception:
            self.screening.combo_strategy.addItem("SEPA / 股票魔法师", "sepa")
            self.backtest.combo_strategy.addItem("SEPA / 股票魔法师", "sepa")

    def _load_board_tree(self):
        """加载自定义板块树（内置数据包 + 本地缓存）。"""
        import json

        THS_BOARDS = {
            "人工智能": "885728", "芯片": "885756", "量子科技": "885823",
            "机器人": "885750", "AI应用": "886041", "算力": "886025",
            "无人机": "885706", "军工": "885660", "商业航天": "885801",
            "新能源汽车": "885790", "储能": "885918", "光伏": "885773",
            "锂电池": "885636", "半导体": "885762", "数据要素": "886028",
            "大数据": "885704", "云计算": "885758", "物联网": "885760",
            "5G": "885734", "自动驾驶": "885806", "脑机接口": "886042",
            "低空经济": "886057", "工业母机": "885926", "光刻机": "885832",
            "存储芯片": "885852", "充电桩": "885920", "风电": "885798",
            "氢能源": "885830", "创新药": "885738", "医疗器械": "885770",
            "CRO": "885854", "中药": "885796",
        }

        GROUPS = {
            "先进生产力（AI/芯片/量子/机器人）": [
                "人工智能", "芯片", "半导体", "量子科技", "机器人",
                "AI应用", "算力", "无人机", "脑机接口",
            ],
            "军工航天": ["军工", "商业航天", "低空经济"],
            "新能源全链": ["新能源汽车", "储能", "光伏", "锂电池", "充电桩", "风电", "氢能源"],
            "数字经济": ["大数据", "云计算", "数据要素", "物联网", "5G"],
            "智能驾驶": ["自动驾驶", "新能源汽车"],
            "硬科技（光刻/存储/工母）": ["光刻机", "存储芯片", "工业母机"],
            "生物医药": ["创新药", "医疗器械", "CRO", "中药"],
        }

        builtin_path = os.path.join("data_cache", "board_builtin.json")
        builtin_data = {}
        if os.path.exists(builtin_path):
            try:
                with open(builtin_path, "r", encoding="utf-8") as f:
                    builtin_data = json.load(f)
            except Exception:
                pass

        def _read_board(name):
            cache_path = os.path.join("data_cache", f"board_{name}.json")
            if os.path.exists(cache_path):
                try:
                    with open(cache_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, list) and data:
                        return data
                except Exception:
                    pass
            return builtin_data.get(name, [])

        # 从 SQLite 读取名称（毫秒级）
        stock_names = {}
        try:
            conn = self._get_db()
            cur = conn.execute("SELECT code, name FROM stock_list")
            stock_names = {str(r[0]): str(r[1]) for r in cur.fetchall()}
            conn.close()
        except Exception:
            pass

        # 从 SQLite 读取板块成分股
        board_stocks = {}
        try:
            conn = self._get_db()
            for bn in THS_BOARDS:
                cur = conn.execute("SELECT code FROM board_stocks WHERE board=?", (bn,))
                codes = [r[0] for r in cur.fetchall()]
                if codes:
                    board_stocks[bn] = codes
                else:
                    board_stocks[bn] = _read_board(bn)
            conn.close()
        except Exception:
            for bn in THS_BOARDS:
                board_stocks[bn] = _read_board(bn)

        self.screening.populate_board_tree(GROUPS, board_stocks, stock_names)
        self.screening.btn_refresh_boards.clicked.connect(
            lambda: self._refresh_boards(THS_BOARDS, GROUPS, stock_names)
        )
        self.screening.btn_scan_board.clicked.connect(self._on_scan_selected_board)
        self.screening.btn_sync_data.clicked.connect(self._on_sync_board_data)
        self.screening.btn_push_strong_buy.clicked.connect(self._on_push_strong_buy)
        self.screening.board_tree.itemClicked.connect(self._on_board_tree_click)
        self.screening.board_tree.itemDoubleClicked.connect(self._on_board_tree_dblclick)
        self.screening.board_stock_table.cellDoubleClicked.connect(self._on_board_stock_dblclick)
        self._board_stocks_cache = board_stocks
        self._board_groups = GROUPS
        self._stock_names_cache = stock_names

        total_stocks = sum(len(v) for v in board_stocks.values())
        self.status.showMessage(f"自定义板块加载完成：{len(THS_BOARDS)} 个板块，{total_stocks} 只成分股")

    def _refresh_boards(self, ths_boards, groups, stock_names):
        self.status.showMessage("刷新板块成分股中...")
        # 这里仅重新从缓存/内置数据读取，不走网络（网络刷新由网页端负责）
        import json
        builtin_path = os.path.join("data_cache", "board_builtin.json")
        builtin_data = {}
        if os.path.exists(builtin_path):
            try:
                with open(builtin_path, "r", encoding="utf-8") as f:
                    builtin_data = json.load(f)
            except Exception:
                pass
        board_stocks = {}
        for bn in ths_boards:
            cache_path = os.path.join("data_cache", f"board_{bn}.json")
            if os.path.exists(cache_path):
                try:
                    with open(cache_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, list) and data:
                        board_stocks[bn] = data
                        continue
                except Exception:
                    pass
            board_stocks[bn] = builtin_data.get(bn, [])
        self._board_stocks_cache = board_stocks
        self.screening.populate_board_tree(groups, board_stocks, stock_names)
        self.status.showMessage("板块成分股刷新完成")

    def _on_scan_selected_board(self):
        item = self.screening.board_tree.currentItem()
        if not item:
            self.status.showMessage("请先选择一个板块")
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict):
            self.status.showMessage("请选择一个板块或板块组")
            return
        node_type = data.get("type", "")
        if node_type == "board":
            bn = data.get("name", "")
            codes = self._board_stocks_cache.get(bn, [])
            if codes:
                self.status.showMessage(f"扫描板块 [{bn}]（{len(codes)} 只）...")
                self._scan_with_codes(codes)
                return
        elif node_type == "group":
            gname = data.get("name", "")
            if gname in self._board_groups:
                merged = set()
                for bn in self._board_groups[gname]:
                    merged.update(self._board_stocks_cache.get(bn, []))
                if merged:
                    self.status.showMessage(f"扫描板块组 [{gname}]（{len(merged)} 只）...")
                    self._scan_with_codes(list(merged))
                    return
        self.status.showMessage("请选择一个板块或板块组进行扫描")

    def _on_sync_board_data(self):
        """补全当前选中板块的日线数据。"""
        item = self.screening.board_tree.currentItem()
        board_name = None
        if item:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(data, dict):
                if data.get("type") == "board":
                    board_name = data.get("name")
                elif data.get("type") == "group":
                    board_name = None

        self.status.showMessage(f"补全数据中（{board_name or '全部板块'}）...")
        self.screening.btn_sync_data.setEnabled(False)

        try:
            from desktop.data_sync import sync_board_stocks
            result = sync_board_stocks(board_name, max_fetch=100)
            msg = (
                f"补全完成：拉取 {result['fetched']} 只，"
                f"失败 {result['failed']}，"
                f"剩余 {result['remaining']} 只待补全"
            )
            self.status.showMessage(msg)
            _log.info(f"sync_board_data: {msg}")

            if board_name and board_name in self._board_stocks_cache:
                self._load_board_stock_details(board_name, self._board_stocks_cache[board_name])
        except Exception as e:
            self.status.showMessage(f"补全失败: {e}")
            _log.error(f"sync_board_data error: {e}")
        finally:
            self.screening.btn_sync_data.setEnabled(True)

    def _on_push_strong_buy(self):
        """推送当前板块表格中「强烈买入」的股票到微信/企业微信。"""
        table = self.screening.board_stock_table
        rows = table.rowCount()
        if rows == 0:
            self.status.showMessage("请先选择板块并加载数据")
            return

        strong_buys = []
        for i in range(rows):
            advice_item = table.item(i, 8)  # 建议买入列
            if not advice_item:
                continue
            advice = advice_item.text()
            if "强烈" in advice or "建议买入" in advice:
                code = table.item(i, 1).text() if table.item(i, 1) else ""
                name = table.item(i, 0).text() if table.item(i, 0) else ""
                price = table.item(i, 2).text() if table.item(i, 2) else ""
                score = table.item(i, 6).text() if table.item(i, 6) else ""
                signal = table.item(i, 7).text() if table.item(i, 7) else ""
                board = table.item(i, 10).text() if table.item(i, 10) else ""
                strong_buys.append({
                    "code": code, "name": name, "price": price,
                    "score": score, "signal": signal, "board": board,
                    "advice": advice,
                })

        if not strong_buys:
            self.status.showMessage("当前板块中没有「强烈买入」或「建议买入」的股票")
            return

        self.screening.btn_push_strong_buy.setEnabled(False)
        self.status.showMessage(f"正在推送 {len(strong_buys)} 只强烈买入股票...")

        from desktop.workers import Worker

        def _do():
            from signal_push import push_signal
            now = __import__("datetime").datetime.now().strftime("%m-%d %H:%M")
            title = f"FinQuanta 强烈买入推荐"
            lines = [
                f"📡 选股雷达 — 强烈买入推荐",
                f"　　时间: {now}",
                f"　　共 {len(strong_buys)} 只候选",
                "",
            ]
            for i, s in enumerate(strong_buys[:20], 1):
                star = "★★★" if "强烈" in s["advice"] else "★★"
                lines.append(
                    f"　　({i}) {star} {s['code']} {s['name']}"
                )
                lines.append(
                    f"　　　　评分{s['score']}  价格{s['price']}  "
                    f"{s['signal']}  [{s['board']}]"
                )
            if len(strong_buys) > 20:
                lines.append(f"\n　　... 及其他 {len(strong_buys) - 20} 只")
            content = "\n".join(lines)
            result = push_signal(title, content)
            return result

        def _done(result):
            self.screening.btn_push_strong_buy.setEnabled(True)
            sc = result.get("serverchan", False)
            wc = result.get("wecom", False)
            channels = []
            if sc:
                channels.append("Server酱")
            if wc:
                channels.append("企业微信")
            if channels:
                self.status.showMessage(
                    f"✅ 已推送 {len(strong_buys)} 只股票到 {'+'.join(channels)}"
                )
            else:
                self.status.showMessage("⚠ 推送未成功，请检查推送配置")

        def _err(msg):
            self.screening.btn_push_strong_buy.setEnabled(True)
            self.status.showMessage(f"推送失败: {msg}")

        w = Worker(_do)
        w.finished.connect(_done)
        w.error.connect(_err)
        w.start()
        self._push_strong_buy_worker = w

    def _on_board_tree_click(self, item, column):
        """单击板块节点时加载成分股到右侧表格；单击个股跳转分析。"""
        try:
            self._handle_board_tree_click(item, column)
        except Exception as e:
            _log.error(f"board_tree_click error: {e}")
            self.status.showMessage(f"操作失败: {e}")

    def _handle_board_tree_click(self, item, column):
        """单击：板块/板块组 → 加载右侧表格；个股 → 仅选中（双击才跳转）。"""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict):
            return

        node_type = data.get("type", "")

        if node_type == "stock":
            return

        if node_type == "board":
            bn = data.get("name", "")
            codes = self._board_stocks_cache.get(bn, [])
            if codes:
                _log.info(f"board click: {bn}, {len(codes)} codes")
                self.status.showMessage(f"加载 [{bn}] {len(codes)} 只成分股...")
                self._load_board_stock_details(bn, codes)
            return

        if node_type == "group":
            gname = data.get("name", "")
            if gname in self._board_groups:
                merged_codes = []
                for b in self._board_groups[gname]:
                    merged_codes.extend(self._board_stocks_cache.get(b, []))
                unique = list(dict.fromkeys(merged_codes))
                if unique:
                    _log.info(f"group click: {gname}, {len(unique)} codes")
                    self.status.showMessage(f"加载板块组 [{gname}] {len(unique)} 只成分股...")
                    self._load_board_stock_details(gname, unique)

    @staticmethod
    def _compute_stock_score(closes, highs, lows, volumes):
        """纯 numpy 计算策略综合评分（0~100）和信号标签。"""
        import numpy as np
        n = len(closes)
        if n < 50:
            return 0, ""
        price = closes[-1]
        ma50 = float(np.mean(closes[-50:]))
        ma150 = float(np.mean(closes[-150:])) if n >= 150 else ma50
        ma200 = float(np.mean(closes[-200:])) if n >= 200 else ma150

        score = 0
        signals = []

        # 趋势模板条件
        if price > ma50:
            score += 12
        if price > ma150:
            score += 10
        if n >= 200 and ma50 > ma150 > ma200:
            score += 15
            signals.append("多头排列")
        if n >= 200:
            ma200_prev = float(np.mean(closes[-222:-22])) if n >= 222 else ma200
            if ma200 > ma200_prev:
                score += 8

        # 52 周位置
        h52 = float(np.max(highs[-250:])) if n >= 250 else float(np.max(highs))
        l52 = float(np.min(lows[-250:])) if n >= 250 else float(np.min(lows))
        if h52 > 0 and price >= h52 * 0.75:
            score += 8
        if l52 > 0 and price > l52 * 1.25:
            score += 5

        # VCP 波动收缩
        if n >= 40:
            vol_early = float(np.std(closes[-40:-20]) / max(np.mean(closes[-40:-20]), 1e-6))
            vol_recent = float(np.std(closes[-20:]) / max(np.mean(closes[-20:]), 1e-6))
            if vol_recent < vol_early * 0.8:
                score += 12
                signals.append("波动收缩")

        # 突破检测
        if n >= 20:
            high20 = float(np.max(closes[-21:-1]))
            if price >= high20 * 0.98:
                score += 15
                signals.append("接近突破")
            if price > high20:
                score += 5
                signals.append("已突破!")

        # 量能
        if n >= 50:
            vol_ma50 = float(np.mean(volumes[-50:]))
            vol_recent = float(np.mean(volumes[-5:]))
            if vol_ma50 > 0 and vol_recent > vol_ma50 * 1.2:
                score += 5
                signals.append("放量")
            elif vol_ma50 > 0 and vol_recent < vol_ma50 * 0.6:
                score += 3
                signals.append("缩量")

        # 动量
        if n >= 20:
            mom20 = (price / closes[-21] - 1) * 100 if closes[-21] > 0 else 0
            if mom20 > 5:
                score += 5
            elif mom20 < -10:
                score -= 5

        return min(100, max(0, score)), " ".join(signals)

    def _load_board_stock_details(self, board_name: str, codes: list[str]):
        """加载成分股行情 + 策略评分，突破潜力股优先排列。"""
        _log.info(f"load_board_details: {board_name}, {len(codes)} codes")
        import numpy as np
        names = dict(getattr(self, "_stock_names_cache", {}))
        rows = []

        try:
            conn = RepoCompatConnection()
            for code in codes:
                name = names.get(code, names.get(str(code), ""))
                price = 0.0
                pct = 0.0
                pct5 = 0.0
                vol = 0.0
                has_data = False
                score = 0
                signal = ""
                try:
                    cur = conn.execute(
                        "SELECT close, high, low, volume FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 260",
                        (str(code),),
                    )
                    rows_db = cur.fetchall()
                    if rows_db:
                        has_data = True
                        # 反转为时间正序
                        rows_db = rows_db[::-1]
                        closes_arr = np.array([float(r[0]) for r in rows_db])
                        highs_arr = np.array([float(r[1]) for r in rows_db])
                        lows_arr = np.array([float(r[2]) for r in rows_db])
                        vols_arr = np.array([float(r[3]) for r in rows_db])
                        nn = len(closes_arr)
                        price = float(closes_arr[-1])
                        if nn >= 2:
                            prev = float(closes_arr[-2])
                            pct = (price - prev) / prev * 100 if prev > 0 else 0
                        if nn >= 6:
                            ref5 = float(closes_arr[-6])
                            pct5 = (price - ref5) / ref5 * 100 if ref5 > 0 else 0
                        vol = float(vols_arr[-1])
                        score, signal = self._compute_stock_score(closes_arr, highs_arr, lows_arr, vols_arr)
                except Exception:
                    pass
                rows.append({
                    "name": name or code,
                    "code": code,
                    "price": price,
                    "pct_change": round(pct, 2),
                    "pct_5d": round(pct5, 2),
                    "volume": vol,
                    "board": board_name,
                    "_has_data": has_data,
                    "_score": score,
                    "_signal": signal,
                })
            conn.close()
        except Exception:
            pass

        # 按策略评分排序：高分优先（有突破信号的排最前）
        with_data = [r for r in rows if r.get("_has_data")]
        no_data = [r for r in rows if not r.get("_has_data")]
        with_data.sort(key=lambda x: x.get("_score", 0), reverse=True)
        no_data.sort(key=lambda x: x.get("code", ""))
        rows = with_data + no_data

        self.screening.populate_board_stocks(board_name, rows)
        n_signal = sum(1 for r in with_data if r.get("_score", 0) >= 50)
        self.status.showMessage(
            f"[{board_name}] 共 {len(rows)} 只（{n_signal} 只有突破潜力）"
        )

    def _on_board_tree_dblclick(self, item, column):
        """双击板块树里的个股跳转到个股分析。"""
        try:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(data, dict) and data.get("type") == "stock":
                code = data.get("code", "")
                if code:
                    _log.info(f"board_tree dblclick stock: {code}")
                    self._navigate_to_stock(code)
        except Exception as e:
            _log.error(f"board_tree_dblclick error: {e}")

    def _on_board_stock_dblclick(self, row, col):
        """双击成分股表格跳转到个股分析。"""
        item = self.screening.board_stock_table.item(row, 1)
        if item:
            code = item.text().strip()
            if code and len(code) == 6 and code.isdigit():
                self._navigate_to_stock(code)

    def _scan_with_codes(self, codes: list[str]):
        sid = self.screening.combo_strategy.currentData() or "sepa"
        sample = self.screening.spin_sample.value()
        self.screening.progress.setVisible(True)
        self.screening.status_label.setText("扫描中...")

        def _do():
            from services.stock_service import run_screening, get_strategy_params
            params = get_strategy_params(sid)
            return run_screening(
                sample_size=sample, strategy_id=sid, strategy_params=params,
                sector_codes=codes,
            )

        self._worker_scan = Worker(_do)
        self._worker_scan.finished.connect(self._on_scan_done)
        self._worker_scan.error.connect(lambda e: self._on_scan_error(e))
        self._worker_scan.start()

    def _on_quantum_optimize(self):
        """量子组合优化选股（支持多种策略和数据源）。"""
        n_select = self.screening.quantum_spin.value()
        mode_id = self.screening.quantum_mode.currentData() or "markowitz_qaoa"
        source = self.screening.quantum_source.currentText()

        # 风险厌恶系数
        lam_text = self.screening.quantum_lambda.currentText()
        lam = float(lam_text.split(" ")[0])

        self.status.showMessage(f"⚛️ 量子优化中（{mode_id}，选{n_select}只，λ={lam}）...")
        self.screening.btn_quantum_run.setEnabled(False)

        from desktop.workers import Worker

        def _do():
            import json
            from desktop.quantum.preprocessing import compute_stats
            from desktop.quantum.config import QOptConfig
            from desktop.quantum.evaluation import run_full_comparison

            conn = RepoCompatConnection()

            # 确定候选股票池
            codes = []
            if "扫描选股" in source:
                cur = conn.execute("SELECT value FROM kv_store WHERE key='last_scan_results'")
                row = cur.fetchone()
                if row:
                    raw = row[0]
                    scan = json.loads(raw) if isinstance(raw, str) else (raw or [])
                    codes = [s.get("代码", "") for s in scan[:60] if s.get("代码")]
            elif "手动" in source:
                raw = self.screening.quantum_codes_input.text().strip()
                codes = [c.strip() for c in raw.split(",") if c.strip() and len(c.strip()) == 6]
            else:
                boards = getattr(self, "_board_groups", {})
                for blist in boards.values():
                    for b in blist:
                        cur = conn.execute("SELECT code FROM board_stocks WHERE board=?", (b,))
                        for r in cur.fetchall():
                            codes.append(r[0])
                codes = list(set(codes))[:150]

            # 加载价格
            names = {}
            try:
                cur_n = conn.execute("SELECT code, name FROM stock_list")
                names = {r[0]: r[1] for r in cur_n.fetchall()}
            except Exception:
                pass

            prices = {}
            for code in codes:
                cur = conn.execute(
                    "SELECT close FROM daily_kline WHERE code=? ORDER BY date", (code,)
                )
                rows = [r[0] for r in cur.fetchall()]
                if len(rows) >= 30:
                    prices[code] = rows
            conn.close()

            if len(prices) < 5:
                return {"error": f"有效股票仅{len(prices)}只（至少5只）"}

            stats = compute_stats(prices, names)
            config = QOptConfig(
                max_holdings=n_select,
                risk_aversion=lam,
                seed=42,
                sa_iterations=3000,
                tabu_iterations=2000,
                qaoa_layers=2,
                qaoa_optimizer_maxiter=100,
            )

            comparison = run_full_comparison(stats, config)
            return comparison

        def _done(result):
            self.screening.btn_quantum_run.setEnabled(True)
            if "error" in result:
                self.screening.quantum_status.setText(f"❌ {result['error']}")
                return

            methods = result.get("methods", [])
            self.screening.update_quantum(methods)

            valid = [m for m in methods if m.get("valid")]
            best = next((m for m in valid if m.get("is_best")), None)
            n_stocks = result.get("stats_summary", {}).get("n_stocks", 0)
            if best:
                self.screening.quantum_status.setText(
                    f"✅ {len(valid)}种方法对比完成（{n_stocks}只候选）| "
                    f"最优: {best['method']} 夏普{best.get('sharpe_ratio',0):.2f} "
                    f"收益{best.get('portfolio_return',0):+.2f}% 风险{best.get('portfolio_risk',0):.2f}%"
                )
            else:
                self.screening.quantum_status.setText(f"完成，{len(valid)} 种方法结果")
            self.status.showMessage(f"⚛️ 量子优化完成")

        def _err(msg):
            self.screening.btn_quantum_run.setEnabled(True)
            self.screening.quantum_status.setText(f"❌ 失败: {msg}")
            self.status.showMessage(f"量子优化失败: {msg}")

        w = Worker(_do)
        w.finished.connect(_done)
        w.error.connect(_err)
        w.start()
        self._quantum_worker = w

    def _on_quantum_dblclick(self, row, col):
        item = self.screening.quantum_table.item(row, 1)
        if item:
            code = item.text().strip()
            if code and len(code) == 6 and code.isdigit():
                self._navigate_to_stock(code)

    def _on_pure_quantum_dblclick(self, row, col):
        item = self.screening.pure_q_table.item(row, 1)
        if item:
            code = item.text().strip().split(",")[0].strip()
            if code and len(code) == 6 and code.isdigit():
                self._navigate_to_stock(code)

    def _on_pure_quantum_optimize(self):
        """纯量子优化模式：不依赖策略评分，直接对股票池做量子算法优化。"""
        n_select = self.screening.pure_q_spin.value()
        algo = self.screening.pure_q_algo.currentText()
        objective = self.screening.pure_q_obj.currentText()
        source = self.screening.pure_q_source.currentText()
        lam_text = self.screening.pure_q_lambda.currentText()
        lam = float(lam_text)

        self.status.showMessage(f"⚛️ 纯量子优化中（{algo}，目标:{objective}，选{n_select}只）...")
        self.screening.btn_pure_q_run.setEnabled(False)
        self.screening.pure_q_status.setText("⏳ 优化计算中，请稍候...")

        from desktop.workers import Worker

        def _do():
            import json
            from desktop.quantum.preprocessing import compute_stats
            from desktop.quantum.config import QOptConfig
            from desktop.quantum.qubo_model import build_qubo, evaluate_solution
            from desktop.quantum.annealing_solver import solve_simulated_annealing, solve_tabu_search
            from desktop.quantum.qaoa_solver import solve_qaoa_classical
            from desktop.quantum.classical_baselines import (
                greedy_baseline, brute_force_baseline, random_sampling_baseline, mean_variance_baseline
            )
            import time, numpy as np

            conn = RepoCompatConnection()

            codes = []
            if "扫描选股" in source:
                cur = conn.execute("SELECT value FROM kv_store WHERE key='last_scan_results'")
                row = cur.fetchone()
                if row:
                    raw = row[0]
                    scan = json.loads(raw) if isinstance(raw, str) else (raw or [])
                    codes = [s.get("代码", "") for s in scan[:80] if s.get("代码")]
            elif "手动" in source:
                raw = self.screening.pure_q_codes_input.text().strip()
                codes = [c.strip() for c in raw.split(",") if c.strip() and len(c.strip()) == 6]
            else:
                cur = conn.execute("SELECT DISTINCT code FROM daily_kline")
                all_codes = [r[0] for r in cur.fetchall()]
                codes = all_codes[:200]

            names = {}
            try:
                cur_n = conn.execute("SELECT code, name FROM stock_list")
                names = {r[0]: r[1] for r in cur_n.fetchall()}
            except Exception:
                pass

            prices = {}
            for code in codes:
                cur = conn.execute(
                    "SELECT close FROM daily_kline WHERE code=? ORDER BY date", (code,)
                )
                rows = [r[0] for r in cur.fetchall()]
                if len(rows) >= 30:
                    prices[code] = rows
            conn.close()

            if len(prices) < 3:
                return {"error": f"有效股票仅{len(prices)}只（至少3只）"}

            # 调整风险厌恶系数（根据目标）
            obj_lam = lam
            if "最小方差" in objective:
                obj_lam = 5.0
            elif "最大收益" in objective:
                obj_lam = 0.2
            elif "CVaR" in objective:
                obj_lam = 3.0

            stats = compute_stats(prices, names)
            config = QOptConfig(
                max_holdings=n_select,
                risk_aversion=obj_lam,
                seed=42,
                sa_iterations=5000,
                tabu_iterations=3000,
                qaoa_layers=3,
                qaoa_optimizer_maxiter=200,
            )

            Q, _qubo_info = build_qubo(stats, config)
            n = len(stats.codes)

            results = []

            def _record(method_name, solution, t_ms):
                if solution is None:
                    return
                # Solvers return dict with 'best_x' or 'solution'; extract the array
                if isinstance(solution, dict):
                    solution = solution.get("best_x", solution.get("solution"))
                if solution is None:
                    return
                metrics = evaluate_solution(solution, stats, config)
                sel_idx = [i for i, v in enumerate(solution) if v == 1]
                sel_codes = [stats.codes[i] for i in sel_idx]
                sel_names = [stats.names[i] if i < len(stats.names) else sel_codes[j]
                             for j, i in enumerate(sel_idx)]
                raw_weights = metrics.get("weights", [1.0 / max(len(sel_idx), 1)] * len(sel_idx))
                energy = metrics.get("energy", 0)

                for k, idx_k in enumerate(sel_idx):
                    w_pct = raw_weights[k] * 100 if k < len(raw_weights) else 0
                    # 个股预期年化收益和风险
                    stock_ret = float(stats.mu[idx_k]) * 100 if idx_k < len(stats.mu) else 0
                    stock_risk = float(stats.annual_vols[idx_k]) * 100 if idx_k < len(stats.annual_vols) else 0
                    stock_sharpe = stock_ret / stock_risk if stock_risk > 0 else 0

                    results.append({
                        "method": method_name,
                        "code": sel_codes[k],
                        "name": sel_names[k],
                        "weight": w_pct,
                        "stock_return": stock_ret,
                        "stock_risk": stock_risk,
                        "stock_sharpe": stock_sharpe,
                        "energy": energy,
                        "runtime_ms": t_ms,
                        "valid": True,
                        "is_best": False,
                    })

            # --- 根据用户选择的算法执行 ---
            if "QAOA" in algo:
                t0 = time.time()
                sol = solve_qaoa_classical(Q, config)
                _record("QAOA量子变分", sol, (time.time() - t0) * 1000)

            if "模拟退火" in algo or "SA" in algo or "混合" in algo:
                t0 = time.time()
                sol = solve_simulated_annealing(Q, config)
                _record("模拟退火(量子隧穿)", sol, (time.time() - t0) * 1000)

            if "Tabu" in algo or "禁忌" in algo or "混合" in algo:
                t0 = time.time()
                sol = solve_tabu_search(Q, config)
                _record("Tabu禁忌搜索", sol, (time.time() - t0) * 1000)

            if "暴力" in algo:
                t0 = time.time()
                sol = brute_force_baseline(stats, config)
                _record("暴力枚举", sol.get("solution"), (time.time() - t0) * 1000)

            if "Monte Carlo" in algo or "随机" in algo:
                t0 = time.time()
                sol = random_sampling_baseline(stats, config)
                _record("蒙特卡洛采样", sol.get("solution"), (time.time() - t0) * 1000)

            # 总是运行贪心基准作为对比
            t0 = time.time()
            sol = greedy_baseline(stats, config)
            _record("贪心基准(TopK夏普)", sol.get("solution"), (time.time() - t0) * 1000)

            # 标记最优：对每个方法计算组合夏普，选最高的
            from collections import defaultdict
            method_sharpes = defaultdict(list)
            for r in results:
                m = r.get("method", "")
                if not m:
                    # find parent method (previous row with method name)
                    continue
                method_sharpes[m].append(r.get("stock_sharpe", 0))

            if method_sharpes:
                best_method = max(method_sharpes, key=lambda m: sum(method_sharpes[m]) / len(method_sharpes[m]))
                current_method = ""
                for r in results:
                    if r.get("method"):
                        current_method = r["method"]
                    if current_method == best_method:
                        r["is_best"] = True

            return {"results": results, "n_stocks": len(prices), "algo": algo, "objective": objective}

        def _done(result):
            self.screening.btn_pure_q_run.setEnabled(True)
            if "error" in result:
                self.screening.pure_q_status.setText(f"❌ {result['error']}")
                return
            rows = result.get("results", [])
            self.screening.update_pure_quantum(rows)
            # 找到最优方法首行
            best = next((r for r in rows if r.get("is_best") and r.get("method")), None)
            if best:
                self.screening.pure_q_status.setText(
                    f"✅ 完成 | {result['n_stocks']}只候选 | "
                    f"最优: {best['method']}  个股夏普{best.get('stock_sharpe',0):.2f}"
                )
            else:
                n_stocks = sum(1 for r in rows if r.get("code"))
                self.screening.pure_q_status.setText(f"完成，选出 {n_stocks} 只")
            self.status.showMessage("⚛️ 纯量子优化完成")

        def _err(msg):
            self.screening.btn_pure_q_run.setEnabled(True)
            self.screening.pure_q_status.setText(f"❌ 失败: {msg}")
            self.status.showMessage(f"纯量子优化失败: {msg}")

        w = Worker(_do)
        w.finished.connect(_done)
        w.error.connect(_err)
        w.start()
        self._pure_quantum_worker = w

    # ------------------------------------------------------------------
    _COMMODITIES = [
        {"code": "518880", "name": "黄金ETF(华安)", "type": "黄金"},
        {"code": "159934", "name": "黄金ETF(易方达)", "type": "黄金"},
        {"code": "159937", "name": "黄金ETF(博时)", "type": "黄金"},
        {"code": "518800", "name": "黄金股票ETF(国泰)", "type": "黄金股"},
        {"code": "159322", "name": "黄金股ETF(汇添富)", "type": "黄金股"},
        {"code": "161226", "name": "白银LOF(招商)", "type": "白银"},
        {"code": "159981", "name": "能源化工ETF(广发)", "type": "原油/化工"},
        {"code": "162411", "name": "华宝油气LOF", "type": "原油"},
        {"code": "501018", "name": "南方原油LOF", "type": "原油"},
        {"code": "159985", "name": "豆粕ETF(大成)", "type": "农产品"},
        {"code": "159660", "name": "玉米ETF(建信)", "type": "农产品"},
        {"code": "159980", "name": "有色金属ETF(诺安)", "type": "有色金属"},
        {"code": "512400", "name": "有色金属ETF(华宝)", "type": "有色金属"},
        {"code": "515220", "name": "煤炭ETF(华宝)", "type": "煤炭"},
        {"code": "159611", "name": "电力ETF(鹏华)", "type": "电力"},
        {"code": "516780", "name": "稀土ETF(国泰)", "type": "稀土"},
        {"code": "159869", "name": "铜ETF(华夏)", "type": "有色金属"},
        {"code": "159899", "name": "铁矿石ETF(华夏)", "type": "黑色金属"},
    ]

    def _on_commodity_load(self):
        """加载黄金/大宗商品行情（先抓实时报价，再补全历史数据）。"""
        self.status.showMessage("加载黄金/大宗商品数据，抓取实时行情...")
        self.screening.btn_commodity_load.setEnabled(False)

        def _fetch():
            import numpy as np
            import urllib.request, json, time

            codes = [c["code"] for c in self._COMMODITIES]

            # ---------- 1. 尝试 Sina 批量报价 ----------
            def _sina_batch(codes_batch):
                """返回 {code: {"price":..., "pct":..., "name":...}} 或空 {}。"""
                syms = ",".join(
                    ("sh" if c.startswith(("5", "1")) and c[0] == "5" or c.startswith("0") or c.startswith("6")
                     else "sz") + c
                    for c in codes_batch
                )
                # 使用代码首字符判断市场（5开头→sh，1/0/3/1开头→sz）
                parts = []
                for c in codes_batch:
                    parts.append(("sh" if c.startswith("5") else "sz") + c)
                url = "https://hq.sinajs.cn/list=" + ",".join(parts)
                try:
                    req = urllib.request.Request(url, headers={"Referer": "https://finance.sina.com.cn"})
                    with urllib.request.urlopen(req, timeout=8) as resp:
                        raw = resp.read().decode("gbk", errors="replace")
                    result = {}
                    for c, part in zip(codes_batch, parts):
                        # 找对应行
                        marker = f'var hq_str_{part}="'
                        idx = raw.find(marker)
                        if idx == -1:
                            continue
                        start = idx + len(marker)
                        end = raw.find('"', start)
                        if end == -1:
                            continue
                        fields = raw[start:end].split(",")
                        if len(fields) >= 9:
                            try:
                                name_raw = fields[0]
                                px = float(fields[3]) if fields[3] else 0.0
                                yc = float(fields[2]) if fields[2] else 0.0
                                pct_rt = (px / yc - 1) * 100 if yc > 0 and px > 0 else 0.0
                                result[c] = {"price": px, "pct_rt": round(pct_rt, 2), "yclose": yc, "name_rt": name_raw}
                            except Exception:
                                pass
                    return result
                except Exception:
                    return {}

            # 批量获取
            rt_data = {}
            batch_size = 10
            for i in range(0, len(codes), batch_size):
                batch = codes[i: i + batch_size]
                rt_data.update(_sina_batch(batch))
                time.sleep(0.05)

            # ---------- 2. 读取/补全历史 closes ----------
            conn = self._get_db()
            results = []
            for c in self._COMMODITIES:
                code = c["code"]
                cur = conn.execute(
                    "SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 25",
                    (code,),
                )
                rows = cur.fetchall()
                closes = [r[0] for r in reversed(rows)] if rows else []

                rt = rt_data.get(code, {})
                price = rt.get("price", 0.0)
                pct_rt = rt.get("pct_rt", 0.0)

                # 如果实时有价格但历史为空，尝试用 akshare 补全
                if not closes and price == 0:
                    # 尝试 akshare fund / etf history
                    try:
                        import akshare as ak
                        prefix = "sh" if code.startswith("5") else "sz"
                        df = ak.fund_etf_hist_em(symbol=code, period="daily", adjust="hfq")
                        if df is not None and len(df) > 0 and "收盘" in df.columns:
                            df = df.sort_values("日期")
                            closes = list(df["收盘"].astype(float).values[-25:])
                            if price == 0 and closes:
                                price = closes[-1]
                    except Exception:
                        pass

                # 如果实时价格仍为0但历史有数据
                if price == 0 and closes:
                    price = closes[-1]
                if price == 0 and pct_rt == 0:
                    # no data at all
                    results.append({**c, "price": 0, "pct": 0, "pct_5d": 0, "pct_20d": 0, "signal": "无数据"})
                    continue

                # 计算历史涨跌（以历史 closes 为准，无历史则只用实时）
                if closes:
                    pct5 = (price / closes[-5] - 1) * 100 if len(closes) >= 5 else 0.0
                    pct20 = (price / closes[-20] - 1) * 100 if len(closes) >= 20 else 0.0
                    pct_day = pct_rt if pct_rt != 0 else (
                        (price / closes[-1] - 1) * 100 if price != closes[-1] else 0.0
                    )
                    ma5 = float(np.mean(closes[-5:])) if len(closes) >= 5 else price
                    ma20 = float(np.mean(closes[-20:])) if len(closes) >= 20 else ma5
                else:
                    pct5 = pct20 = 0.0
                    pct_day = pct_rt
                    ma5 = ma20 = price

                signal = "多头" if price > ma5 > ma20 else "空头" if price < ma5 < ma20 else "震荡"
                # 覆盖名称（优先 ETF 预设名称，已经够准了）
                results.append({
                    **c,
                    "price": round(price, 3),
                    "pct": round(pct_day, 2),
                    "pct_5d": round(pct5, 2),
                    "pct_20d": round(pct20, 2),
                    "signal": signal,
                })
            conn.close()
            return results

        from desktop.workers import Worker
        self._worker_commodity = Worker(_fetch)

        def _done(results):
            self.screening.update_commodities(results)
            n_data = sum(1 for r in results if r.get("price", 0) > 0)
            self.status.showMessage(f"商品行情加载完成: {n_data}/{len(results)} 有数据")
            self.screening.btn_commodity_load.setEnabled(True)

        def _err(e):
            self.status.showMessage(f"商品行情加载失败: {e}")
            self.screening.btn_commodity_load.setEnabled(True)

        self._worker_commodity.finished.connect(_done)
        self._worker_commodity.error.connect(_err)
        self._worker_commodity.start()

    def _on_commodity_dblclick(self, row, col):
        item = self.screening.commodity_table.item(row, 0)
        if item:
            code = item.text().strip()
            if code and len(code) == 6 and code.isdigit():
                self._navigate_to_stock(code)

    def _on_scan(self):
        """纯本地 SQLite 选股扫描（不依赖 services 层）。"""
        sid = self.screening.combo_strategy.currentData() or "sepa"
        sample = self.screening.spin_sample.value()
        rs_min = self.screening.spin_rs.value()
        log_system_event(
            "ui",
            "scan",
            "手动触发扫描选股",
            detail=f"strategy={sid}, sample={sample}, rs_min={rs_min}",
        )
        self.screening.progress.setVisible(True)
        self.screening.status_label.setText("本地扫描中...")
        self.status.showMessage(f"本地选股扫描（{sid}，样本 {sample}）...")

        def _do_local_scan():
            return run_task(
                "UI扫描选股",
                "desktop_ui",
                self._run_local_scan,
                sid,
                sample,
                rs_min,
            )

        from desktop.workers import Worker
        self._worker_scan = Worker(_do_local_scan)
        self._worker_scan.finished.connect(self._on_scan_done)
        self._worker_scan.error.connect(lambda e: self._on_scan_error(str(e)))
        self._worker_scan.start()

    def _run_local_scan(self, strategy_id: str, sample: int, rs_min: int) -> list[dict]:
        """基于本地 SQLite 日线数据的多策略选股扫描。"""
        import numpy as np
        from desktop.strategy_engine import build_context, score_candidate

        conn = self._get_db()
        # 获取有足够日线数据的股票
        cur = conn.execute("""
            SELECT code, COUNT(*) as cnt FROM daily_kline
            GROUP BY code HAVING cnt >= 50
            ORDER BY cnt DESC LIMIT ?
        """, (sample,))
        code_list = [r[0] for r in cur.fetchall()]

        names = {}
        try:
            cur_n = conn.execute("SELECT code, name FROM stock_list")
            names = {r[0]: r[1] for r in cur_n.fetchall()}
        except Exception:
            pass

        # 板块归属
        board_map = {}
        try:
            cur_b = conn.execute("SELECT code, board FROM board_stocks")
            for r in cur_b.fetchall():
                if r[0] not in board_map:
                    board_map[r[0]] = r[1]
        except Exception:
            pass

        candidates = []
        for code in code_list:
            cur2 = conn.execute(
                "SELECT close, high, low, volume FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 260",
                (code,),
            )
            rows = cur2.fetchall()
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
            scored = score_candidate(strategy_id, ctx)
            score = scored["score"]
            signals = scored["signals"]
            signal_str = scored["signal_str"]
            rs = scored["rs"]
            vcp = scored["vcp"]
            breakout = scored["breakout"]
            contraction = scored["contraction"]
            vol_ratio = scored["vol_ratio"]
            dist_high = scored["dist_high"]

            if rs < rs_min:
                continue

            buy_advice = scored["buy_advice"]
            action_advice = scored["action_advice"]

            candidates.append({
                "代码": code,
                "名称": names.get(code, ""),
                "板块": board_map.get(code, ""),
                "策略": scored["strategy"],
                "价格": f"{price:.2f}",
                "RS": str(rs),
                "评分": str(score),
                "VCP": "✓" if vcp else "",
                "突破": "✓" if breakout else "",
                "收缩": f"{contraction:.2f}" if contraction else "",
                "量比": f"{vol_ratio:.1f}",
                "离高点%": f"{dist_high:+.1f}%",
                "建议买入": buy_advice,
                "建议操作": action_advice,
            })

        conn.close()
        candidates.sort(key=lambda x: int(x.get("评分", "0")), reverse=True)
        return candidates[:100]

    def _on_scan_done(self, candidates):
        self.screening.progress.setVisible(False)
        self.screening.populate_results(candidates or [])
        n = len(candidates) if candidates else 0
        log_system_event(
            "ui",
            "scan",
            "扫描完成",
            detail=f"candidates={n}",
        )
        self.screening.status_label.setText(f"扫描完成，{n} 只候选")
        self.status.showMessage(f"选股完成: {n} 只候选")
        # 缓存扫描结果供 AI 仓使用
        if candidates:
            self._save_scan_results(candidates)
            # 自动记录强烈买入信号到走势验证
            try:
                from desktop.trend_verify import record_signals
                sid = self.screening.combo_strategy.currentData() or "SEPA"
                n_recorded = record_signals(candidates, strategy=sid.upper())
                if n_recorded > 0:
                    self.status.showMessage(
                        f"选股完成: {n} 只候选，{n_recorded} 个强烈信号已记录到走势验证"
                    )
            except Exception:
                pass

    def _save_scan_results(self, candidates: list[dict]):
        """将选股雷达扫描结果缓存到 SQLite，供 AI 决策引擎使用。"""
        try:
            import json
            conn = self._get_db()
            conn.execute(
                "INSERT OR REPLACE INTO kv_store VALUES (?,?,?)",
                ("last_scan_results",
                 json.dumps(candidates[:100], ensure_ascii=False),
                 __import__("datetime").datetime.now().isoformat()),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    def _on_scan_error(self, msg):
        self.screening.progress.setVisible(False)
        self.screening.status_label.setText(f"扫描失败: {msg[:60]}")
        log_system_event("ui", "scan", "扫描失败", detail=msg[:500], level="error")
        self.status.showMessage("选股扫描失败")

    def _on_portfolio_refresh(self):
        self.status.showMessage("刷新持仓行情...")
        self._load_dashboard()
        self.status.showMessage("持仓行情已刷新")

    def _get_manual_portfolio(self) -> dict:
        """读取手动仓数据。"""
        import json
        try:
            conn = self._get_db()
            row = conn.execute("SELECT value FROM kv_store WHERE key='manual_portfolio'").fetchone()
            conn.close()
            if row:
                return json.loads(row[0])
        except Exception:
            pass
        return {"positions": [], "cash": 1_000_000, "initial_capital": 1_000_000, "history": []}

    def _save_manual_portfolio(self, pf: dict):
        """保存手动仓数据到 SQLite。"""
        import json
        try:
            conn = self._get_db()
            conn.execute(
                "INSERT OR REPLACE INTO kv_store VALUES (?,?,datetime('now'))",
                ("manual_portfolio", json.dumps(pf, ensure_ascii=False)),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            _log.error(f"save manual portfolio error: {e}")

    def _on_manual_buy(self):
        """手动仓买入。"""
        code = self.portfolio.buy_code.text().strip()
        if not code or len(code) != 6 or not code.isdigit():
            self.portfolio.buy_status.setText("❌ 请输入有效的6位股票代码")
            return

        price = self.portfolio.buy_price.value()
        shares = self.portfolio.buy_shares.value()
        stop_pct = self.portfolio.buy_stop.value()

        if price <= 0:
            # 自动获取最新价格
            try:
                from desktop.ai_trader import _get_real_price
                price = _get_real_price(code)
            except Exception:
                pass
            if price <= 0:
                self.portfolio.buy_status.setText("❌ 无法获取价格，请手动输入")
                return
            self.portfolio.buy_price.setValue(price)

        cost = price * shares * 1.0003
        pf = self._get_manual_portfolio()

        if cost > pf["cash"]:
            max_shares = int(pf["cash"] / (price * 1.0003) / 100) * 100
            self.portfolio.buy_status.setText(
                f"❌ 资金不足: 需要 ¥{cost:,.0f}，可用 ¥{pf['cash']:,.0f}（最多买 {max_shares} 股）"
            )
            return

        # 查名称
        names = getattr(self, "_stock_names_cache", {})
        name = names.get(code, "")
        if not name:
            try:
                conn = self._get_db()
                r = conn.execute("SELECT name FROM stock_list WHERE code=?", (code,)).fetchone()
                conn.close()
                name = r[0] if r else code
            except Exception:
                name = code

        today = __import__("datetime").date.today().isoformat()
        pf["positions"].append({
            "code": code, "name": name, "entry_price": round(price, 2),
            "shares": shares, "entry_date": today,
            "stop_loss": round(price * (1 - stop_pct / 100), 2),
        })
        pf["cash"] = round(pf["cash"] - cost, 2)
        pf.setdefault("history", []).append({
            "time": __import__("datetime").datetime.now().isoformat(),
            "action": "BUY", "code": code, "name": name,
            "price": price, "shares": shares,
        })
        self._save_manual_portfolio(pf)
        log_system_event(
            "ui",
            "manual_portfolio",
            "手动仓买入",
            detail=f"code={code}, name={name}, price={price:.2f}, shares={shares}",
        )
        try:
            from desktop.portfolio_tracker import log_operation
            log_operation("manual_portfolio", "BUY", f"{code} {name} {shares}股 @ {price:.2f}")
        except Exception:
            pass
        try:
            from desktop.snapshot_service import save_system_snapshot
            save_system_snapshot()
        except Exception:
            pass
        self.portfolio.buy_status.setText(f"✅ 买入 {code} {name} {shares}股 @ ¥{price:.2f}")
        self.portfolio.buy_status.setStyleSheet("color:#66bb6a;")
        self._load_dashboard()

    def _on_manual_sell(self):
        """手动仓卖出。"""
        code = self.portfolio.sell_code.text().strip()
        if not code or len(code) != 6:
            self.portfolio.sell_status.setText("❌ 请输入有效的股票代码")
            return

        pf = self._get_manual_portfolio()
        pos = None
        pos_idx = -1
        for i, p in enumerate(pf["positions"]):
            if p.get("code") == code:
                pos = p
                pos_idx = i
                break

        if pos is None:
            self.portfolio.sell_status.setText(f"❌ 未持有 {code}")
            return

        sell_price = self.portfolio.sell_price.value()
        if sell_price <= 0:
            try:
                from desktop.ai_trader import _get_real_price
                sell_price = _get_real_price(code)
            except Exception:
                pass
            if sell_price <= 0:
                self.portfolio.sell_status.setText("❌ 无法获取价格，请手动输入")
                return
            self.portfolio.sell_price.setValue(sell_price)

        sell_shares = self.portfolio.sell_shares.value()
        if sell_shares == 0:
            sell_shares = pos["shares"]

        if sell_shares > pos["shares"]:
            self.portfolio.sell_status.setText(f"❌ 持有 {pos['shares']} 股，不能卖 {sell_shares}")
            return

        revenue = sell_price * sell_shares * (1 - 0.0013)
        pnl = revenue - pos["entry_price"] * sell_shares
        pf["cash"] = round(pf["cash"] + revenue, 2)

        if sell_shares >= pos["shares"]:
            pf["positions"].pop(pos_idx)
        else:
            pf["positions"][pos_idx]["shares"] -= sell_shares

        pf.setdefault("history", []).append({
            "time": __import__("datetime").datetime.now().isoformat(),
            "action": "SELL", "code": code, "name": pos.get("name", ""),
            "price": sell_price, "shares": sell_shares, "pnl": round(pnl, 2),
            "entry_price": pos.get("entry_price", 0),
            "entry_date": pos.get("entry_date", ""),
        })
        self._save_manual_portfolio(pf)
        log_system_event(
            "ui",
            "manual_portfolio",
            "手动仓卖出",
            detail=f"code={code}, price={sell_price:.2f}, shares={sell_shares}, pnl={pnl:.2f}",
        )
        try:
            from desktop.portfolio_tracker import log_operation
            log_operation(
                "manual_portfolio",
                "SELL",
                f"{code} {sell_shares}股 @ {sell_price:.2f} pnl={pnl:.2f}",
            )
        except Exception:
            pass
        try:
            from desktop.snapshot_service import save_system_snapshot
            save_system_snapshot()
        except Exception:
            pass
        self.portfolio.sell_status.setText(
            f"✅ 卖出 {code} {sell_shares}股 @ ¥{sell_price:.2f}，盈亏 ¥{pnl:+,.2f}"
        )
        self.portfolio.sell_status.setStyleSheet("color:#66bb6a;" if pnl >= 0 else "color:#ef5350;")
        self._load_dashboard()

    def _on_backtest_run(self):
        sid = self.backtest.combo_strategy.currentData() or "sepa"
        local_strategy = sid
        sample = self.backtest.spin_sample.value()
        start = self.backtest.combo_start.currentText()
        start_fmt = f"{start[:4]}-{start[4:6]}-{start[6:8]}" if len(start) == 8 else start

        self.backtest.progress.setVisible(True)
        self.backtest.progress.setValue(0)
        self.status.showMessage(f"回测运行中（{local_strategy}）...")

        try:
            from desktop.local_backtest import run_local_backtest

            def _progress(pct, text):
                self.backtest.progress.setValue(int(pct * 100))
                self.status.showMessage(text)

            result = run_local_backtest(
                strategy=local_strategy,
                sample_size=sample,
                start_date=start_fmt,
                progress_callback=_progress,
            )

            self.backtest.progress.setVisible(False)

            if result.total_trades == 0:
                self.status.showMessage("回测完成，但无交易产生（可能数据不足）")
                return

            # 获取名称和板块
            bt_names, bt_boards = self._get_names_and_boards(
                [t.get("code", "") for t in result.trades]
            )
            self._last_bt_result = result
            # 更新指标表
            self.backtest.update_metrics_local(result)
            # 更新交易记录
            self.backtest.update_trades_local(result.trades, bt_names, bt_boards)
            # 更新资金曲线
            self.backtest.update_equity_chart(result.equity_curve)

            self.status.showMessage(
                f"回测完成: 收益 {result.total_return:.2%} 夏普 {result.sharpe_ratio:.2f} "
                f"胜率 {result.win_rate:.1%} 交易 {result.total_trades} 笔"
            )
        except Exception as e:
            self.backtest.progress.setVisible(False)
            _log.error(f"backtest error: {e}")
            self.status.showMessage(f"回测失败: {e}")

    def _on_backtest_done(self, result):
        self.backtest.progress.setVisible(False)
        if result:
            bt_names, bt_boards = self._get_names_and_boards(
                [t.code for t in result.trades]
            )
            self.backtest.update_metrics(result)
            self.backtest.update_trades(result.trades, bt_names, bt_boards)
            self.status.showMessage(f"回测完成: 收益 {result.total_return:.2%} 夏普 {result.sharpe_ratio:.2f}")
        else:
            self.status.showMessage("回测未产出结果")

    def _on_backtest_error(self, msg):
        self.backtest.progress.setVisible(False)
        self.status.showMessage(f"回测失败: {msg[:60]}")

    def _on_monte_carlo(self):
        """运行蒙特卡洛模拟。"""
        last_result = getattr(self, "_last_bt_result", None)
        if not last_result or last_result.total_trades < 5:
            self.status.showMessage("请先运行回测（至少5笔交易）再运行蒙特卡洛")
            return
        self.status.showMessage("蒙特卡洛模拟中（1000次）...")
        try:
            from desktop.local_backtest import run_monte_carlo
            mc = run_monte_carlo(last_result, 1000)
            if "error" in mc:
                self.backtest.mc_grade_label.setText(f"❌ {mc['error']}")
                self.status.showMessage(mc["error"])
                return
            metrics = mc["metrics"]
            self.backtest.mc_table.setRowCount(len(metrics))
            for i, m in enumerate(metrics):
                vals = [m["name"], m["actual"], m["sim_mean"], m["p5"], m["p95"], m["rank"]]
                for j, v in enumerate(vals):
                    item = QTableWidgetItem(v)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.backtest.mc_table.setItem(i, j, item)
            self.backtest.mc_grade_label.setText(mc["grade"])
            self.status.showMessage("蒙特卡洛模拟完成")
        except Exception as e:
            _log.error(f"monte_carlo error: {e}")
            self.status.showMessage(f"蒙特卡洛失败: {e}")

    def _on_walk_forward(self):
        """运行 Walk-Forward 分析。"""
        sid = self.backtest.combo_strategy.currentData() or "sepa"
        local_strategy = sid
        sample = self.backtest.spin_sample.value()
        self.status.showMessage(f"Walk-Forward 分析中（{local_strategy}）...")
        try:
            from desktop.local_backtest import run_walk_forward
            wf = run_walk_forward(local_strategy, sample, n_windows=4)
            if "error" in wf:
                self.backtest.wf_summary_label.setText(f"❌ {wf['error']}")
                self.status.showMessage(wf["error"])
                return
            windows = wf["windows"]
            self.backtest.wf_table.setRowCount(len(windows))
            red = QColor("#ef5350")
            green = QColor("#26a69a")
            for i, w in enumerate(windows):
                vals = [
                    w["window"], w["train_period"], w["val_period"],
                    w["train_return"], w["train_sharpe"], w["train_winrate"],
                    w["val_return"], w["val_sharpe"], w["val_winrate"],
                    w["val_mdd"], w["decay"],
                ]
                for j, v in enumerate(vals):
                    item = QTableWidgetItem(v)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if j == 10:
                        try:
                            dv = float(v.replace("%", "").replace("+", ""))
                            item.setForeground(green if dv > 30 else red if dv < 10 else QColor("#FF9800"))
                        except Exception:
                            pass
                    self.backtest.wf_table.setItem(i, j, item)
            self.backtest.wf_summary_label.setText(wf["summary"])
            self.status.showMessage("Walk-Forward 分析完成")
        except Exception as e:
            _log.error(f"walk_forward error: {e}")
            self.status.showMessage(f"Walk-Forward 失败: {e}")

    def _on_multi_compare(self):
        """多策略同时回测对比。"""
        sample = self.backtest.spin_sample.value()
        start = self.backtest.combo_start.currentText()
        start_fmt = f"{start[:4]}-{start[4:6]}-{start[6:8]}" if len(start) == 8 else start
        self.status.showMessage("多策略对比运行中（4种策略）...")
        self.backtest.btn_multi_compare.setEnabled(False)

        from desktop.workers import Worker

        def _do():
            from desktop.local_backtest import run_multi_strategy_backtest
            return run_multi_strategy_backtest(
                strategies=["trend", "breakout", "value", "momentum"],
                sample_size=sample, start_date=start_fmt,
            )

        def _done(results):
            self.backtest.btn_multi_compare.setEnabled(True)
            _labels = {"trend": "趋势/SEPA", "breakout": "突破/海龟", "value": "价值/格雷厄姆", "momentum": "动量/短线"}
            red = QColor("#ef5350")
            green = QColor("#26a69a")
            gold = QColor("#FFD740")

            valid = [k for k in ["trend", "breakout", "value", "momentum"] if k in results and "error" not in results[k]]
            self.backtest.compare_table.setRowCount(len(valid))
            for i, sid in enumerate(valid):
                r = results[sid]
                avg_rank = r.get("avg_rank", 99)
                vals = [
                    _labels.get(sid, sid),
                    f"{r['total_return']:.2%}",
                    f"{r['annual_return']:.2%}",
                    f"{r['max_drawdown']:.2%}",
                    f"{r['sharpe_ratio']:.2f}",
                    f"{r['win_rate']:.1%}",
                    f"{r['profit_loss_ratio']:.2f}",
                    str(r['total_trades']),
                    f"{r['avg_hold_days']:.0f}",
                    f"#{avg_rank:.1f}",
                ]
                for j, v in enumerate(vals):
                    item = QTableWidgetItem(v)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if j == 1:
                        try:
                            fv = float(v.replace("%", ""))
                            item.setForeground(red if fv > 0 else green)
                        except Exception:
                            pass
                    if j == 9 and avg_rank <= 1.5:
                        item.setForeground(gold)
                        item.setFont(QFont("", 11, QFont.Weight.Bold))
                    self.backtest.compare_table.setItem(i, j, item)

            summary = results.get("_summary", "对比完成")
            self.backtest.compare_summary.setText(f"🏆 {summary}")
            self.backtest.tabs.setCurrentIndex(4)
            self.status.showMessage("多策略对比完成")

        def _err(msg):
            self.backtest.btn_multi_compare.setEnabled(True)
            self.status.showMessage(f"多策略对比失败: {msg}")

        w = Worker(_do)
        w.finished.connect(_done)
        w.error.connect(_err)
        w.start()
        self._multi_bt_worker = w

    def _on_stock_analyze(self):
        """个股分析入口（防抖）。
        策略：
          1. 立即检查本地数据，如有则先渲染（快速响应）
          2. 同时后台拉取最新数据，完成后自动刷新图表
        """
        now = __import__("time").time()
        if hasattr(self, "_last_analyze_time") and now - self._last_analyze_time < 0.8:
            return
        self._last_analyze_time = now

        code = self.stock_analysis.code_input.text().strip()
        if not code or len(code) != 6 or not code.isdigit():
            self.status.showMessage("请输入有效的 6 位股票代码")
            return

        self.stock_analysis.btn_analyze.setEnabled(False)

        # --- 步骤1：检查本地数据是否存在 ---
        try:
            conn = self._get_db()
            row = conn.execute(
                "SELECT COUNT(*), MAX(date) FROM daily_kline WHERE code=?", (code,)
            ).fetchone()
            conn.close()
            cnt = row[0] if row else 0
            latest_date = row[1] if row and row[1] else ""
        except Exception:
            cnt = 0
            latest_date = ""

        # 判断是否需要拉取（缺数据 或 数据超过1个交易日未更新）
        from datetime import datetime as _dt, date as _date
        try:
            days_old = (_dt.today() - _dt.strptime(latest_date, "%Y-%m-%d")).days if latest_date else 999
        except Exception:
            days_old = 999

        has_local = cnt >= 20

        # --- 步骤2：如有本地数据先渲染，给用户即时反馈 ---
        if has_local:
            try:
                self._do_stock_analyze_local(code)
                if days_old > 1:
                    self.status.showMessage(
                        f"{code} 本地数据至 {latest_date}，后台补全中..."
                    )
                else:
                    self.status.showMessage(f"{code} 分析完成（数据至 {latest_date}）")
                    self.stock_analysis.btn_analyze.setEnabled(True)
                    return
            except Exception as e:
                _log.error(f"stock_analyze local error: {e}")

        # --- 步骤3：后台拉取最新数据（不超过1天则跳过）---
        if days_old <= 1 and has_local:
            self.stock_analysis.btn_analyze.setEnabled(True)
            return

        from desktop.workers import Worker

        def _fetch_and_save():
            """后台从腾讯拉取最新600天K线，写入DB。"""
            from desktop.data_sync import fetch_daily_tencent
            rows = fetch_daily_tencent(code)
            if rows:
                upsert_daily_kline_rows(rows)
                # Return latest date fetched
                latest = max(r[1] for r in rows)
                return {"code": code, "rows": len(rows), "latest": latest}
            return {"code": code, "rows": 0, "latest": latest_date}

        def _on_done(result):
            self.stock_analysis.btn_analyze.setEnabled(True)
            new_latest = result.get("latest", "")
            n_rows = result.get("rows", 0)
            try:
                self._do_stock_analyze_local(code)
                if n_rows > 0:
                    self.status.showMessage(
                        f"✅ {code} 数据已更新至 {new_latest}（新增/更新 {n_rows} 条）"
                    )
                else:
                    self.status.showMessage(f"{code} 分析完成（无新数据）")
            except Exception as e:
                _log.error(f"analyze after fetch error: {e}")
                self.status.showMessage(f"渲染失败: {e}")

        def _on_err(msg):
            self.stock_analysis.btn_analyze.setEnabled(True)
            if has_local:
                self.status.showMessage(f"⚠️ {code} 更新失败（显示本地缓存 {latest_date}）: {msg}")
            else:
                self.stock_analysis.header_label.setText(f"{code} — 数据获取失败")
                self.status.showMessage(f"数据获取失败: {msg}")

        w = Worker(_fetch_and_save)
        w.finished.connect(_on_done)
        w.error.connect(_on_err)
        w.start()
        self._stock_fetch_worker = w

    def _do_stock_analyze_local(self, code: str):
        """基于本地 SQLite 数据的个股分析（纯计算，不做网络请求）。"""
        import numpy as np
        _log.info(f"stock_analyze start: {code}")

        names = getattr(self, "_stock_names_cache", {})
        name = names.get(code, "")
        if not name:
            try:
                conn_n = self._get_db()
                cur_n = conn_n.execute("SELECT name FROM stock_list WHERE code=?", (code,))
                row_n = cur_n.fetchone()
                if not row_n:
                    cur_n = conn_n.execute("SELECT name FROM fund_holdings WHERE code=? LIMIT 1", (code,))
                    row_n = cur_n.fetchone()
                conn_n.close()
                if row_n:
                    name = row_n[0]
            except Exception:
                pass

        try:
            conn = self._get_db()
            cur = conn.execute(
                "SELECT date, open, high, low, close, volume FROM daily_kline WHERE code=? ORDER BY date",
                (str(code),),
            )
            rows = cur.fetchall()
            conn.close()
        except Exception:
            rows = []

        if len(rows) < 20:
            self.stock_analysis.header_label.setText(f"{code} {name} — 数据不足（{len(rows)} 条）")
            self.status.showMessage("个股分析：数据不足")
            return

        closes = np.array([float(r[4]) for r in rows])
        highs = np.array([float(r[3]) for r in rows])
        lows = np.array([float(r[2]) for r in rows])
        n = len(closes)
        price = float(closes[-1])

        ma50 = float(np.mean(closes[-50:])) if n >= 50 else price
        ma150 = float(np.mean(closes[-150:])) if n >= 150 else price
        ma200 = float(np.mean(closes[-200:])) if n >= 200 else price
        high_52w = float(np.max(highs[-250:])) if n >= 250 else float(np.max(highs))
        low_52w = float(np.min(lows[-250:])) if n >= 250 else float(np.min(lows))

        _log.info(f"stock_analyze data ready: {code}, {n} rows, price={price}")
        self.stock_analysis.update_header(code, name, price)
        self.stock_analysis.update_metrics({
            "ma50": round(ma50, 2), "ma150": round(ma150, 2), "ma200": round(ma200, 2),
            "high_52w": round(high_52w, 2), "low_52w": round(low_52w, 2),
            "rs_rating": 0,
        })

        trend = {}
        if n >= 200:
            ma200_prev = float(np.mean(closes[-222:-22])) if n >= 222 else ma200
            trend = {
                "condition_1_above_ma150_200": price > ma150 and price > ma200,
                "condition_2_ma150_gt_ma200": ma150 > ma200,
                "condition_3_ma200_rising": ma200 > ma200_prev,
                "condition_4_ma50_gt_ma150_200": ma50 > ma150 and ma50 > ma200,
                "condition_5_above_ma50": price > ma50,
                "condition_6_above_52w_low_25pct": price > low_52w * 1.25,
                "condition_7_within_52w_high_25pct": price >= high_52w * 0.75,
                "condition_8_rs_rating": True,
            }
            passed = all(trend.values())
        else:
            passed = False
        _log.info(f"stock_analyze trend done: {code}")
        self.stock_analysis.update_trend(trend, passed)
        self.stock_analysis.update_predictions([])

        # 提取个股特征（每只股票不同）
        volumes = np.array([float(r[5]) for r in rows])
        mom5 = (price / float(closes[-6]) - 1.0) if n >= 6 and closes[-6] > 0 else 0.0
        mom20 = (price / float(closes[-21]) - 1.0) if n >= 21 and closes[-21] > 0 else 0.0
        mom60 = (price / float(closes[-61]) - 1.0) if n >= 61 and closes[-61] > 0 else 0.0
        vol20 = float(np.std(closes[-20:]) / max(np.mean(closes[-20:]), 1e-6)) if n >= 20 else 0.02
        vol60 = float(np.std(closes[-60:]) / max(np.mean(closes[-60:]), 1e-6)) if n >= 60 else vol20
        ma_trend = (ma50 / max(ma150, 1e-6) - 1.0) if n >= 150 else 0.0
        ma_order = 1.0 if (n >= 200 and ma50 > ma150 > ma200) else (-1.0 if n >= 200 and ma50 < ma150 else 0.0)
        dist_from_high = (price / max(high_52w, 1e-6) - 1.0) if high_52w > 0 else 0.0
        dist_from_ma50 = (price / max(ma50, 1e-6) - 1.0) if ma50 > 0 else 0.0

        # ---- 情绪/事件驱动核心指标 ----
        # 换手率代理（量比 = 最近成交量 / 过去均量）
        vol_ma5 = float(np.mean(volumes[-5:])) if n >= 5 else 1.0
        vol_ma20 = float(np.mean(volumes[-20:])) if n >= 20 else vol_ma5
        vol_ratio = vol_ma5 / max(vol_ma20, 1.0)

        # 涨停/跌停检测（近5日有无涨停）
        recent_pcts = []
        for i in range(max(0, n - 5), n):
            if i > 0 and closes[i - 1] > 0:
                recent_pcts.append((closes[i] - closes[i - 1]) / closes[i - 1] * 100)
        has_limit_up = any(p >= 9.5 for p in recent_pcts)
        has_limit_down = any(p <= -9.5 for p in recent_pcts)
        max_recent_pct = max(recent_pcts) if recent_pcts else 0

        # 连续涨跌天数
        streak = 0
        for i in range(n - 1, max(0, n - 11), -1):
            if i > 0 and closes[i] > closes[i - 1]:
                streak += 1
            elif i > 0 and closes[i] < closes[i - 1]:
                streak -= 1
            else:
                break

        # 赚钱效应指数代理（近5日涨幅 > 0 的天数占比）
        profit_days = sum(1 for p in recent_pcts if p > 0)
        profit_effect = profit_days / max(len(recent_pcts), 1)

        # 封单强度代理（涨停日的量 vs 均量比）
        seal_strength = vol_ratio if has_limit_up else 0.0

        # 情绪阶段判定
        if has_limit_up and vol_ratio > 1.5 and streak >= 2:
            emotion_phase = "高潮"
            emotion_score = 0.9
        elif mom5 > 0.05 and vol_ratio > 1.2 and profit_effect > 0.6:
            emotion_phase = "发酵"
            emotion_score = 0.6
        elif mom5 > 0.02 and vol_ratio > 1.0:
            emotion_phase = "启动"
            emotion_score = 0.3
        elif mom5 < -0.05 and has_limit_down:
            emotion_phase = "冰点"
            emotion_score = -0.8
        elif mom5 < -0.03 and vol_ratio > 1.1:
            emotion_phase = "退潮"
            emotion_score = -0.5
        else:
            emotion_phase = "中性"
            emotion_score = 0.0

        # 事件冲击强度代理（单日异常涨跌幅 + 异常量比）
        last_pct = recent_pcts[-1] if recent_pcts else 0
        event_impact = 0.0
        if abs(last_pct) > 5 and vol_ratio > 2.0:
            event_impact = last_pct / 10.0
        elif abs(last_pct) > 3 and vol_ratio > 1.5:
            event_impact = last_pct / 15.0

        # 每个策略用不同权重组合个股特征，生成该策略在该股票上的专属参数
        strategy_preds = []
        strategy_configs = [
            {"name": "SEPA/趋势",
             "trend_w": 0.8 + mom20 * 2.0 + ma_order * 0.3,
             "revert_w": 0.15 - ma_trend * 0.5,
             "vol_scale": vol20 * 8.0},
            {"name": "CAN SLIM",
             "trend_w": 0.6 + mom60 * 1.5 + ma_order * 0.2,
             "revert_w": 0.25 - mom20 * 0.3,
             "vol_scale": vol20 * 6.0},
            {"name": "海龟/突破",
             "trend_w": 0.5 + mom20 * 1.8,
             "revert_w": 0.1,
             "vol_scale": vol60 * 10.0},
            {"name": "格雷厄姆/价值",
             "trend_w": -0.2 + dist_from_high * 0.5,
             "revert_w": 0.7 + dist_from_ma50 * 1.5,
             "vol_scale": vol20 * 5.0},
            {"name": "游资/短线",
             "trend_w": 0.3 + mom5 * 3.0,
             "revert_w": 0.05,
             "vol_scale": vol20 * 12.0},
            {"name": "私募/成长",
             "trend_w": 0.4 + mom60 * 1.0 + ma_trend * 1.5,
             "revert_w": 0.4 - mom20 * 0.5,
             "vol_scale": vol20 * 6.0},
            {"name": "情绪博弈",
             "trend_w": emotion_score * 1.5 + mom5 * 2.5 + (seal_strength - 1.0) * 0.8,
             "revert_w": max(0, 0.6 - emotion_score * 0.5 - profit_effect * 0.3),
             "vol_scale": vol20 * (8.0 + abs(emotion_score) * 5.0)},
            {"name": "事件驱动",
             "trend_w": event_impact * 3.0 + mom5 * 1.5 + (vol_ratio - 1.0) * 1.2,
             "revert_w": max(0, 0.5 - abs(event_impact) * 0.8),
             "vol_scale": vol20 * (6.0 + abs(event_impact) * 8.0)},
        ]
        for sc in strategy_configs:
            sc["trend_w"] = max(-1.5, min(2.0, sc["trend_w"]))
            sc["revert_w"] = max(0.0, min(1.0, sc["revert_w"]))
            sc["vol_scale"] = max(0.1, min(1.5, sc["vol_scale"]))
            strategy_preds.append(sc)

        _log.info(f"stock_analyze features done: {code}, drawing chart...")
        # 绘制 K 线图
        opens = [float(r[1]) for r in rows]
        highs_list = [float(r[2]) for r in rows]
        lows_list = [float(r[3]) for r in rows]
        closes_list = [float(r[4]) for r in rows]
        self.stock_analysis.update_chart(
            [r[0] for r in rows], opens, highs_list, lows_list, closes_list,
            predictions=strategy_preds,
        )

        _log.info(f"stock_analyze chart done: {code}, computing predictions...")
        # 多周期预测 + 持久化 + 校准
        pred_table_data = []
        if n >= 60:
            window = 60
            seg = closes[-window:]
            slope, _ = np.polyfit(np.arange(window), seg, 1)
            ma50_val = float(np.mean(closes[-50:])) if n >= 50 else price
            vol_val = float(np.std(seg[-20:]))
            today_str = str(rows[-1][0])[:10]

            horizon_days = {"5d": 5, "10d": 10, "20d": 20, "1m": 22, "1q": 63, "6m": 125, "1y": 250}

            for idx, sp in enumerate(strategy_preds):
                tw = sp.get("trend_w", 0.5)
                rw = sp.get("revert_w", 0.3)
                vs = sp.get("vol_scale", 0.4)

                # 模拟到最长周期
                max_days = 250
                rng = np.random.RandomState(42 + idx + 1)
                path = [price]
                for d in range(1, max_days + 1):
                    prev = path[-1]
                    next_p = prev + slope * tw + (ma50_val - prev) * rw * 0.02 + rng.normal(0, vol_val * vs)
                    path.append(max(next_p, prev * 0.9))

                row_data = {"strategy_name": sp["name"], "emotion_phase": emotion_phase}

                # 各周期预测涨跌%
                save_rows = []
                for h_key, h_days in horizon_days.items():
                    if h_days < len(path):
                        pred_price = path[h_days]
                        chg = (pred_price - price) / price * 100
                        row_data[f"pred_{h_key}"] = round(chg, 2)
                        save_rows.append((code, sp["name"], today_str, h_key, round(pred_price, 2)))
                    else:
                        row_data[f"pred_{h_key}"] = None

                # 持久化预测到 SQLite
                try:
                    conn = self._get_db()
                    for sr in save_rows:
                        conn.execute(
                            "INSERT OR REPLACE INTO predictions (code,strategy,predict_date,horizon,predicted_price) VALUES (?,?,?,?,?)",
                            sr,
                        )
                    conn.commit()
                    conn.close()
                except Exception:
                    pass

                # 校准：查 5 天前的预测 vs 今天实际价
                calib = "-"
                calib_note = ""
                try:
                    conn = self._get_db()
                    import datetime as _dt
                    try:
                        base = _dt.date.fromisoformat(today_str)
                    except Exception:
                        base = _dt.date.today()
                    past_5d = (base - _dt.timedelta(days=7)).isoformat()
                    cur = conn.execute(
                        "SELECT predicted_price FROM predictions WHERE code=? AND strategy=? AND horizon='5d' AND predict_date<=? ORDER BY predict_date DESC LIMIT 1",
                        (code, sp["name"], past_5d),
                    )
                    past_row = cur.fetchone()
                    conn.close()
                    if past_row and past_row[0]:
                        predicted = float(past_row[0])
                        pred_chg = (predicted - price) / price * 100
                        actual_chg = 0
                        error = abs(pred_chg - actual_chg)
                        if abs(predicted - price) / price < 0.03:
                            calib = "准确"
                            calib_note = f"预测 ¥{predicted:.2f} vs 实际 ¥{price:.2f}"
                        elif abs(predicted - price) / price < 0.08:
                            calib = "偏差小"
                            calib_note = f"预测 ¥{predicted:.2f} vs 实际 ¥{price:.2f}"
                        else:
                            calib = "偏差大"
                            calib_note = f"预测 ¥{predicted:.2f} vs 实际 ¥{price:.2f}"
                except Exception:
                    pass

                row_data["calibration"] = calib
                row_data["calibration_note"] = calib_note
                pred_table_data.append(row_data)

        self.stock_analysis.update_predictions(pred_table_data)

        _log.info(f"stock_analyze complete: {code}")
        self.status.showMessage(f"分析完成: {code} {name}　现价 ¥{price:.2f}")

    # ---- 事件驱动短期选股 ----
    def _on_event_analyze(self):
        text = self.event_panel.event_input.text().strip()
        if not text:
            self.status.showMessage("请输入事件描述")
            return
        self.status.showMessage(f"分析事件: {text}...")
        try:
            from desktop.event_strategy import (
                match_boards, backtest_event, recommend_stocks, study_event_history,
            )
            boards = match_boards(text)
            if not boards:
                self.event_panel.matched_label.setText(
                    f"⚠️ 未能从「{text}」中识别出关联板块，请尝试更具体的描述（如加入行业/国家/商品名称）"
                )
                self.status.showMessage("事件分析：未匹配到板块")
                return

            # 历史关联分析
            keywords = [kw for kw in KEYWORD_BOARD_MAP if kw in text] if False else []
            try:
                from desktop.event_strategy import KEYWORD_BOARD_MAP as _KBM
                keywords = [kw for kw in _KBM if kw in text]
            except Exception:
                pass

            history_info = ""
            if keywords:
                hist = study_event_history(keywords[0])
                pred = hist.get("prediction", {})
                total = hist.get("total_events", 0)
                s5 = next((s for s in hist.get("stats", []) if s["days"] == 5), None)
                history_info = (
                    f" | 📊 历史关联: {total} 次异动"
                    + (f", 5日胜率 {s5['win_rate']:.0f}%, 均涨跌 {s5['avg_return']:+.1f}%" if s5 else "")
                    + f" → {pred.get('direction', '-')}（置信度 {pred.get('confidence', 0)}%）"
                )

            self.event_panel.matched_label.setText(
                f"📌 匹配板块: {', '.join(boards)}{history_info}"
            )
            bt_results = backtest_event(boards)
            self.event_panel.update_backtest(bt_results)
            stocks = recommend_stocks(boards)
            self.event_panel.update_recommend(stocks)
            self.status.showMessage(
                f"事件分析完成: {len(boards)} 个板块, {len(stocks)} 只推荐"
            )
        except Exception as e:
            self.status.showMessage(f"事件分析失败: {e}")
            _log.error(f"event_analyze error: {e}")

    def _on_event_save(self):
        text = self.event_panel.event_input.text().strip()
        if not text:
            self.status.showMessage("请输入事件描述")
            return
        event_date = self.event_panel.event_date.date().toString("yyyy-MM-dd")
        try:
            from desktop.event_strategy import save_event, get_events
            boards = save_event(text, event_date)
            self.event_panel.matched_label.setText(f"✅ 已保存，匹配板块: {', '.join(boards)}")
            self.event_panel.update_history(get_events(50))
            self.status.showMessage("事件已保存")
        except Exception as e:
            self.status.showMessage(f"保存失败: {e}")

    def _on_fetch_news(self):
        self.status.showMessage("抓取财经快讯...")
        try:
            from desktop.event_strategy import fetch_news_eastmoney
            news = fetch_news_eastmoney(30)
            self.event_panel.update_news(news)
            self.status.showMessage(f"获取 {len(news)} 条快讯")
        except Exception as e:
            self.status.showMessage(f"抓取失败: {e}")

    def _on_fetch_broker(self):
        """抓取券商中国资讯 → 匹配板块 → 历史关联分析 → 预测。"""
        self.status.showMessage("正在抓取券商中国资讯 + 历史关联分析...")
        self.event_panel.btn_fetch_broker.setEnabled(False)
        try:
            from desktop.event_strategy import (
                fetch_broker_china_news, auto_analyze_news, analyze_news_with_history,
            )
            news = fetch_broker_china_news(30)
            if news:
                news = auto_analyze_news(news)
                self.status.showMessage("资讯获取完成，正在做历史关联分析...")
                news = analyze_news_with_history(news)
            self.event_panel.update_broker(news)
            n_bull = sum(1 for n in news if "看涨" in n.get("history_prediction", ""))
            n_bear = sum(1 for n in news if "看跌" in n.get("history_prediction", ""))
            self.event_panel.matched_label.setText(
                f"🏛️ 券商中国: {len(news)} 条资讯 → 历史关联分析完成 | "
                f"看涨 {n_bull} / 看跌 {n_bear} / 震荡 {len(news) - n_bull - n_bear}"
            )
            self.status.showMessage(f"券商中国资讯 + 历史分析完成: {len(news)} 条")
        except Exception as e:
            _log.error(f"fetch_broker error: {e}")
            self.status.showMessage(f"抓取失败: {e}")
        finally:
            self.event_panel.btn_fetch_broker.setEnabled(True)

    def _on_bt_board_click(self, row, col):
        results = getattr(self.event_panel, "_bt_results", [])
        if row < len(results):
            r = results[row]
            stocks = r.get("top_stocks", [])
            self.event_panel.bt_detail_label.setText(f"📊 {r['board']} 板块成分股表现")
            red = QColor("#ef5350")
            green = QColor("#26a69a")
            self.event_panel.bt_detail_table.setRowCount(len(stocks))
            for i, s in enumerate(stocks):
                vals = [s["code"], s["name"], f"{s['price']:.2f}",
                        f"{s['3d']:+.2f}%", f"{s['5d']:+.2f}%", f"{s['10d']:+.2f}%"]
                for j, v in enumerate(vals):
                    item = QTableWidgetItem(v)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if j >= 3:
                        try:
                            fv = float(v.replace("%", "").replace("+", ""))
                            item.setForeground(red if fv > 0 else green if fv < 0 else QColor("#888"))
                        except Exception:
                            pass
                    self.event_panel.bt_detail_table.setItem(i, j, item)

    def _on_event_stock_dblclick(self, row, col):
        item = self.event_panel.recommend_table.item(row, 0)
        if item:
            code = item.text().strip()
            if code and len(code) == 6:
                self._navigate_to_stock(code)

    def _on_event_stock_dblclick_bt(self, row, col):
        item = self.event_panel.bt_detail_table.item(row, 0)
        if item:
            code = item.text().strip()
            if code and len(code) == 6:
                self._navigate_to_stock(code)

    # ---- 基金持仓 ----
    def _on_fund_load(self):
        """一键加载：重仓股列表 + 公布后表现 + 持仓变化，全部自动计算。"""
        from desktop.fund_strategy import (
            load_and_compare, enrich_price_and_forecast, _prev_period,
            analyze_post_disclosure, compare_periods,
        )
        period = self.fund_panel.period_combo.currentText()
        self.status.showMessage(f"正在加载 {period} 基金重仓股（全量计算）...")
        self.fund_panel.status_label.setText("加载中：重仓股列表 + 公布后表现 + 持仓变化...")

        try:
            # 1) 重仓股列表 + 变动 + 股价 + 预测
            holdings = load_and_compare(period)
            enrich_price_and_forecast(holdings)

            prev_p = _prev_period(period) or "无"
            n_new = sum(1 for h in holdings if "新进" in h.get("change_type", ""))
            n_up = sum(1 for h in holdings if "增持" in h.get("change_type", ""))
            n_down = sum(1 for h in holdings if "减持" in h.get("change_type", ""))
            n_bull = sum(1 for h in holdings if "看多" in h.get("forecast", ""))
            n_bear = sum(1 for h in holdings if "看空" in h.get("forecast", ""))
            self.fund_panel.update_holdings(holdings)

            # 2) 公布后表现
            perf = analyze_post_disclosure(holdings, period)
            self.fund_panel.update_performance(perf)

            # 3) 持仓变化（当期 vs 上一期）
            if prev_p != "无":
                changes = compare_periods(prev_p, period)
                self.fund_panel.update_changes(changes)
                n_changes = len(changes)
            else:
                n_changes = 0

            self.fund_panel.status_label.setText(
                f"✅ {period} 共 {len(holdings)} 只（对比 {prev_p}："
                f"新进 {n_new} / 增持 {n_up} / 减持 {n_down} | "
                f"预测: 看多 {n_bull} / 看空 {n_bear} | "
                f"表现 {len(perf)} 只 / 变化 {n_changes} 条）"
            )
            self.status.showMessage(f"基金持仓全量加载完成: {len(holdings)} 只")
        except Exception as e:
            _log.error(f"fund load error: {e}")
            from desktop.fund_strategy import get_builtin_top_holdings, save_holdings
            holdings = get_builtin_top_holdings(period)
            save_holdings(period, holdings)
            self.fund_panel.update_holdings(holdings)
            self.fund_panel.status_label.setText(f"加载异常，使用内置数据 {len(holdings)} 只")

    def _on_fund_analyze(self):
        """单独刷新公布后表现。"""
        from desktop.fund_strategy import get_holdings, analyze_post_disclosure
        period = self.fund_panel.period_combo.currentText()
        holdings = get_holdings(period)
        if not holdings:
            self.status.showMessage("请先加载持仓数据")
            return
        self.status.showMessage("正在分析公布后表现...")
        results = analyze_post_disclosure(holdings, period)
        self.fund_panel.update_performance(results)
        self.fund_panel.status_label.setText(f"分析完成，共 {len(results)} 只有效数据")
        self.status.showMessage("基金重仓股表现分析完成")

    def _on_fund_compare(self):
        """单独刷新持仓变化。"""
        from desktop.fund_strategy import compare_periods
        period1 = self.fund_panel.compare_combo.currentText()
        period2 = self.fund_panel.period_combo.currentText()
        if period1 == period2:
            self.status.showMessage("请选择不同的报告期进行对比")
            return
        self.status.showMessage(f"正在对比 {period1} → {period2} 持仓变化...")
        changes = compare_periods(period1, period2)
        self.fund_panel.update_changes(changes)
        self.fund_panel.status_label.setText(
            f"对比完成: {period1} → {period2}，共 {len(changes)} 条变化记录"
        )
        self.status.showMessage("基金持仓变化对比完成")

    def _on_fund_stock_dblclick(self, row, col):
        item = self.fund_panel.perf_table.item(row, 0)
        if item:
            code = item.text().strip()
            if code and len(code) == 6:
                self._navigate_to_stock(code)

    def _on_fund_stock_dblclick_holdings(self, row, col):
        item = self.fund_panel.holdings_table.item(row, 0)
        if item:
            code = item.text().strip()
            if code and len(code) == 6:
                self._navigate_to_stock(code)

    def _on_fund_stock_dblclick_changes(self, row, col):
        item = self.fund_panel.changes_table.item(row, 0)
        if item:
            code = item.text().strip()
            if code and len(code) == 6:
                self._navigate_to_stock(code)

    def _on_star_mgr_load(self):
        """加载选中明星经理的持仓并分析公布前后表现。"""
        from desktop.fund_strategy import get_star_managers, analyze_manager_pre_post, STAR_MANAGERS
        idx = self.fund_panel.mgr_combo.currentIndex()
        managers = get_star_managers()
        if idx < 0 or idx >= len(managers):
            self.status.showMessage("请选择一位基金经理")
            return

        mgr_name = managers[idx]["name"]
        period = self.fund_panel.period_combo.currentText()
        self.status.showMessage(f"分析 {mgr_name} 在 {period} 的持仓...")

        # 经理概况
        mgr = managers[idx]
        rets_str = " / ".join(f"{y}: {v:+.1f}%" for y, v in sorted(mgr["annual_returns"].items()))
        info = (
            f"⭐ {mgr_name} | {mgr['fund']} | 风格: {mgr['style']}\n"
            f"📊 近5年业绩: {rets_str} | 均值: {mgr['avg_5y']:+.1f}%"
        )

        results = analyze_manager_pre_post(mgr_name, period)
        self.fund_panel.update_star_holdings(results, info)

        n_buy = sum(1 for r in results if "跟买" in r.get("signal", ""))
        n_warn = sum(1 for r in results if "不建议" in r.get("signal", ""))
        self.fund_panel.status_label.setText(
            f"⭐ {mgr_name} {period}: {len(results)} 只持仓 | "
            f"跟买信号 {n_buy} 只 / 不建议 {n_warn} 只"
        )
        self.status.showMessage(f"{mgr_name} 持仓分析完成")

    def _on_star_stock_dblclick(self, row, col):
        item = self.fund_panel.mgr_holdings_table.item(row, 0)
        if item:
            code = item.text().strip()
            if code and len(code) == 6:
                self._navigate_to_stock(code)

    # ---- 走势验证 ----
    def _on_trend_calibrate(self):
        """校准走势验证记录。"""
        self.status.showMessage("走势验证：校准中...")
        try:
            from desktop.trend_verify import calibrate, get_records, get_accuracy_stats
            result = calibrate()
            records = get_records(200)
            stats = get_accuracy_stats()
            self.trend_verify.update_records(records)
            self.trend_verify.update_stats(stats)
            self.status.showMessage(
                f"校准完成：更新 {result['updated']} 条，"
                f"准确率 {stats.get('accuracy', 0):.1f}%（共 {stats.get('total', 0)} 个信号）"
            )
        except Exception as e:
            self.status.showMessage(f"校准失败: {e}")

    def _on_trend_ai_analyze(self):
        """AI 深度分析选中的走势验证行。"""
        row = getattr(self.trend_verify, "_selected_row", -1)
        cache = getattr(self.trend_verify, "_records_cache", [])
        if row < 0 or row >= len(cache):
            self.status.showMessage("请先点击选择一行")
            return

        r = cache[row]
        code = r.get("code", "")
        name = r.get("name", "")
        sig_date = r.get("signal_date", "")
        sig_price = r.get("signal_price", 0)
        score = r.get("score", 0)

        self.trend_verify.detail_text.setText("🦀 AI 深度分析中...")
        self.trend_verify.btn_ai_analyze.setEnabled(False)

        from desktop.workers import Worker

        def _do():
            from desktop.ai_trader import _call_llm

            conn = RepoCompatConnection()
            rows = conn.execute(
                "SELECT date, close, high, low, volume FROM daily_kline "
                "WHERE code=? AND date>=? ORDER BY date LIMIT 30",
                (code, sig_date),
            ).fetchall()

            # 信号前数据
            rows_before = conn.execute(
                "SELECT close FROM daily_kline WHERE code=? AND date<? ORDER BY date DESC LIMIT 20",
                (code, sig_date),
            ).fetchall()
            conn.close()

            ctx_lines = [f"股票: {code} {name}，信号日: {sig_date}，信号价: {sig_price}，评分: {score}"]

            if rows:
                ctx_lines.append(f"信号后走势（{len(rows)}天）:")
                for d, c, h, l, v in rows[:10]:
                    pct = (c / sig_price - 1) * 100 if sig_price > 0 else 0
                    ctx_lines.append(f"  {d}: 收{c:.2f}({pct:+.1f}%) 高{h:.2f} 低{l:.2f} 量{v:.0f}")

            if rows_before:
                closes_b = [x[0] for x in reversed(rows_before)]
                import numpy as np
                ma5 = np.mean(closes_b[-5:]) if len(closes_b) >= 5 else 0
                ma20 = np.mean(closes_b[-20:]) if len(closes_b) >= 20 else 0
                ctx_lines.append(f"信号前: MA5={ma5:.2f} MA20={ma20:.2f}")

            # 已有的简单分析
            old_analysis = r.get("analysis", "")
            if old_analysis:
                ctx_lines.append(f"系统初步分析: {old_analysis}")

            pnl_summary = []
            for k, label in [("pnl_1d","1日"),("pnl_2d","2日"),("pnl_3d","3日"),
                              ("pnl_5d","5日"),("pnl_10d","10日"),("pnl_20d","20日")]:
                v = r.get(k)
                if v is not None:
                    pnl_summary.append(f"{label}:{v:+.2f}%")
            if pnl_summary:
                ctx_lines.append(f"实际收益: {', '.join(pnl_summary)}")

            prompt = (
                f"请对以下选股信号进行深度分析：\n"
                f"{'  '.join(ctx_lines)}\n\n"
                f"请从以下维度详细分析：\n"
                f"1. 信号发出时的市场环境和个股状态\n"
                f"2. 信号后的走势特征（趋势/反转/震荡）\n"
                f"3. 成交量变化说明了什么\n"
                f"4. 均线支撑/阻力是否有效\n"
                f"5. 该信号正确/错误的核心原因\n"
                f"6. 对该策略的改进建议\n"
                f"请用中文详细回答。"
            )
            return _call_llm(prompt, system="你是A股量化策略分析专家，擅长复盘选股信号的有效性。")

        def _done(result):
            self.trend_verify.btn_ai_analyze.setEnabled(True)
            lines = [f"🦀 AI 深度分析 — {code} {name}\n"]
            lines.append(result)
            self.trend_verify.detail_text.setText("\n".join(lines))

        def _err(msg):
            self.trend_verify.btn_ai_analyze.setEnabled(True)
            self.trend_verify.detail_text.setText(f"❌ AI 分析失败: {msg}")

        w = Worker(_do)
        w.finished.connect(_done)
        w.error.connect(_err)
        w.start()
        self._trend_ai_worker = w

    def _on_trend_verify_dblclick(self, row, col):
        item = self.trend_verify.table.item(row, 0)
        if item:
            code = item.text().strip()
            if code and len(code) == 6 and code.isdigit():
                self._navigate_to_stock(code)

    # ---- AI 模拟仓 ----
    def _on_ai_save_config(self):
        from desktop.ai_trader import save_ai_config
        key = self.ai_portfolio.api_key_input.text().strip()
        model = self.ai_portfolio.model_combo.currentText().strip()
        base_url = self.ai_portfolio.base_url_input.text().strip()
        if not key:
            self.status.showMessage("请输入 API Key")
            return
        save_ai_config(key, base_url=base_url, model=model)
        provider = self.ai_portfolio.provider_combo.currentText()
        # 同时保存 provider 选择
        try:
            import json
            conn = self._get_db()
            conn.execute(
                "INSERT OR REPLACE INTO kv_store VALUES (?,?,?)",
                ("ai_provider", json.dumps(provider), __import__("datetime").datetime.now().isoformat()),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass
        self.status.showMessage(f"AI 配置已保存：{provider} / {model}")

    def _on_ai_run_decision(self):
        """推荐仓：后台线程分析，不阻塞 UI。"""
        self.status.showMessage("AI 正在分析市场（推荐仓）...")
        self.ai_portfolio.analysis_label.setText("AI 分析中，请稍候...")
        self.ai_portfolio.btn_run_ai.setEnabled(False)

        from desktop.workers import Worker
        boards = self.ai_portfolio.get_selected_boards()
        if not boards:
            self.ai_portfolio.btn_run_ai.setEnabled(True)
            self.status.showMessage("请先勾选至少一个板块")
            return

        def _do():
            from desktop.ai_trader import run_ai_decision
            return run_ai_decision(",".join(boards), mode="manual")

        def _done(result):
            self.ai_portfolio.btn_run_ai.setEnabled(True)
            analysis = result.get("analysis", "")
            decisions = result.get("decisions", [])
            error = result.get("error", "")
            if error:
                self.ai_portfolio.analysis_label.setText(f"❌ {error}")
                self.status.showMessage("AI 决策失败")
            else:
                self.ai_portfolio.analysis_label.setText(f"📊 {analysis}")
                self.ai_portfolio.update_decisions(decisions)
                self._ai_pending_decisions = decisions
                self.status.showMessage(f"AI 推荐完成：{len(decisions)} 条建议")
            self._refresh_ai_portfolio()

        def _err(msg):
            self.ai_portfolio.btn_run_ai.setEnabled(True)
            self.ai_portfolio.analysis_label.setText(f"❌ 错误: {msg}")

        w = Worker(_do)
        w.finished.connect(_done)
        w.error.connect(_err)
        w.start()
        self._recommend_worker = w

    def _on_ai_decision_dblclick(self, row, col):
        item = self.ai_portfolio.decisions_table.item(row, 1)
        if item:
            code = item.text().strip()
            if code and len(code) == 6 and code.isdigit():
                self._navigate_to_stock(code)

    def _on_ai_pos_click(self, row, col):
        """单击：显示操作栏（明细/买入/卖出/条件单/看行情）。"""
        code_item = self.ai_portfolio.pos_table.item(row, 1)
        name_item = self.ai_portfolio.pos_table.item(row, 2)
        if not code_item:
            return
        code = code_item.text().strip()
        name = name_item.text().strip() if name_item else code
        if not code or len(code) != 6:
            return
        self._active_action_code = code
        self._active_action_source = "ai"
        self.ai_portfolio.action_stock_label.setText(f"{code} {name}")
        self.ai_portfolio.action_bar.setVisible(True)

    def _on_ai_pos_dblclick(self, row, col):
        """双击：跳转到个股行情。"""
        code_item = self.ai_portfolio.pos_table.item(row, 1)
        if code_item:
            code = code_item.text().strip()
            if code and len(code) == 6 and code.isdigit():
                self._navigate_to_stock(code)

    def _on_ai_execute_decisions(self):
        """推荐仓：人工确认后执行。"""
        from desktop.ai_portfolio import check_trading_time
        reject = check_trading_time()
        if reject:
            self.ai_portfolio.execute_results.setText(f"⛔ 非交易时间，无法执行: {reject}")
            self.status.showMessage(f"非交易时间: {reject}")
            return

        decisions = getattr(self, "_ai_pending_decisions", [])
        if not decisions:
            self.status.showMessage("没有待执行的决策")
            return
        self.status.showMessage("执行推荐仓决策...")
        try:
            from desktop.ai_trader import execute_ai_decisions
            results = execute_ai_decisions(decisions, mode="manual")
            self.ai_portfolio.execute_results.setText("\n".join(results))
            self._ai_pending_decisions = []
            self.ai_portfolio.btn_execute.setEnabled(False)
            self._refresh_ai_portfolio()
            self.status.showMessage(f"推荐仓执行完成：{len(results)} 条")
        except Exception as e:
            self.ai_portfolio.execute_results.setText(f"执行失败: {e}")
            _log.error(f"ai_execute error: {e}")

    def _on_save_openclaw(self):
        from desktop.openclaw_agent import save_openclaw_config
        key = self.settings.openclaw_key.text().strip()
        if not key:
            self.status.showMessage("请输入 OpenClaw API Key")
            return
        save_openclaw_config(key)
        self.status.showMessage("OpenClaw 配置已保存")

    def _on_settings_save_ai(self):
        """设置面板的 AI 模型配置保存。"""
        try:
            import json
            provider = self.settings.ai_provider.currentText()
            key = self.settings.ai_key.text().strip()
            base_url = self.settings.ai_base_url.text().strip()
            if not key:
                self.status.showMessage("请输入 API Key")
                return
            _PROVIDER_URLS = {
                "DeepSeek": "https://api.deepseek.com/v1",
                "OpenAI": "https://api.openai.com/v1",
                "Gemini": "https://generativelanguage.googleapis.com/v1beta",
                "Claude": "https://api.anthropic.com/v1",
            }
            if not base_url:
                base_url = _PROVIDER_URLS.get(provider, "https://api.deepseek.com/v1")

            conn = self._get_db()
            conn.execute(
                "INSERT OR REPLACE INTO kv_store VALUES (?,?,datetime('now'))",
                ("ai_config", json.dumps({
                    "api_key": key, "base_url": base_url,
                    "model": "", "provider": provider,
                })),
            )
            conn.commit()
            conn.close()

            # Sync to AI仓 panel
            self.ai_portfolio.api_key_input.setText(key)
            self.ai_portfolio.base_url_input.setText(base_url)

            self.status.showMessage(f"✅ AI 配置已保存 ({provider})")
        except Exception as e:
            self.status.showMessage(f"保存失败: {e}")

    def _on_save_push(self):
        """保存推送配置（Server 酱 + 企业微信）。"""
        key = self.settings.push_key.text().strip()
        webhook = self.settings.wecom_webhook.text().strip()
        if not key and not webhook:
            self.settings.push_status.setText("❌ 请至少配置一个推送渠道")
            self.settings.push_status.setStyleSheet("color:#ef5350;")
            return
        try:
            from signal_push import save_push_config, get_push_config
            cfg = get_push_config()
            cfg["serverchan_key"] = key
            cfg["wecom_webhook"] = webhook
            save_push_config(cfg)
            channels = []
            if key:
                channels.append("Server酱")
            if webhook:
                channels.append("企业微信")
            self.settings.push_status.setText(f"✅ 已保存: {' + '.join(channels)}")
            self.settings.push_status.setStyleSheet("color:#66bb6a;")
            self.status.showMessage(f"推送配置已保存（{' + '.join(channels)}）")
        except Exception as e:
            self.settings.push_status.setText(f"❌ 保存失败: {e}")
            self.settings.push_status.setStyleSheet("color:#ef5350;")

    def _on_test_push(self):
        """测试微信推送。"""
        key = self.settings.push_key.text().strip()
        if not key:
            self.settings.push_status.setText("❌ 请先输入 SendKey")
            self.settings.push_status.setStyleSheet("color:#ef5350;")
            return

        # 先保存再测试
        from signal_push import save_push_config, get_push_config
        cfg = get_push_config()
        cfg["serverchan_key"] = key
        save_push_config(cfg)

        self.settings.push_status.setText("⏳ 正在发送测试消息...")
        self.settings.push_status.setStyleSheet("color:#ffb74d;")
        self.settings.btn_test_push.setEnabled(False)

        from desktop.workers import Worker

        def _do():
            from signal_push import push_signal
            import urllib.error, json as _json

            # 先做一个快速检测，获取详细错误
            url = f"https://sctapi.ftqq.com/{key}.send"
            import urllib.request, urllib.parse
            data = urllib.parse.urlencode({
                "title": "FinQuanta测试",
                "desp": f"测试消息 {__import__('datetime').datetime.now().strftime('%H:%M:%S')}"
            }).encode("utf-8")
            req = urllib.request.Request(
                url, data=data, method="POST",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            try:
                resp = urllib.request.urlopen(req, timeout=10)
                body = _json.loads(resp.read().decode("utf-8", errors="ignore"))
                if body.get("code") == 0:
                    return {"status": "ok"}
                return {"status": "error", "msg": body.get("message", str(body))}
            except urllib.error.HTTPError as e:
                try:
                    err_body = _json.loads(e.read().decode("utf-8", errors="ignore"))
                    return {"status": "error", "msg": err_body.get("message", str(e)),
                            "code": err_body.get("code", e.code)}
                except Exception:
                    return {"status": "error", "msg": f"HTTP {e.code}: {e.reason}"}
            except Exception as e:
                return {"status": "error", "msg": str(e)}

        def _done(result):
            self.settings.btn_test_push.setEnabled(True)
            if result.get("status") == "ok":
                self.settings.push_status.setText("✅ 推送成功！请检查微信是否收到消息")
                self.settings.push_status.setStyleSheet("color:#66bb6a;")
            else:
                msg = result.get("msg", "未知错误")
                if "次数限制" in msg:
                    self.settings.push_status.setText(
                        "⚠ SendKey 有效，但今日免费额度已用完（5次/天）。明天再试或升级 Server 酱会员"
                    )
                    self.settings.push_status.setStyleSheet("color:#ffb74d;")
                elif "PUSH_KEY" in msg or "sendkey" in msg.lower():
                    self.settings.push_status.setText("❌ SendKey 无效，请检查是否正确")
                    self.settings.push_status.setStyleSheet("color:#ef5350;")
                else:
                    self.settings.push_status.setText(f"❌ 推送失败: {msg}")
                    self.settings.push_status.setStyleSheet("color:#ef5350;")

        def _err(msg):
            self.settings.btn_test_push.setEnabled(True)
            self.settings.push_status.setText(f"❌ 测试失败: {msg}")
            self.settings.push_status.setStyleSheet("color:#ef5350;")

        w = Worker(_do)
        w.finished.connect(_done)
        w.error.connect(_err)
        w.start()
        self._push_test_worker = w

    def _on_save_sched_config(self):
        """保存调度配置（启用/禁用的任务 + OpenClaw key）。"""
        import json
        disabled = set()
        for key, cb in self.settings.sched_checks.items():
            if not cb.isChecked():
                disabled.add(key)

        try:
            conn = self._get_db()
            conn.execute(
                "INSERT OR REPLACE INTO kv_store VALUES (?,?,datetime('now'))",
                ("sched_disabled_tasks", json.dumps(list(disabled))),
            )
            # Save OpenClaw key if provided
            oc_key = self.settings.openclaw_key.text().strip()
            if oc_key:
                from desktop.openclaw_agent import save_openclaw_config
                save_openclaw_config(oc_key)
            conn.commit()
            conn.close()
        except Exception as e:
            _log.error(f"save sched config error: {e}")

        # Update running daemon
        if self._daemon:
            self._daemon.disabled_tasks = disabled

        self.settings.sched_status.setText(
            f"✅ 调度配置已保存（{len(disabled)} 个任务禁用）"
        )
        self.settings.sched_status.setStyleSheet("color:#66bb6a; font-size:12px;")
        self.status.showMessage("调度配置已保存")

    def _on_run_pipeline_now(self):
        """立即执行全策略流水线。"""
        self.settings.btn_run_pipeline_now.setEnabled(False)
        self.settings.sched_status.setText("⏳ 全流水线执行中...")
        self.settings.sched_status.setStyleSheet("color:#ffb74d; font-size:12px;")
        self.status.showMessage("正在执行全策略流水线...")

        from desktop.workers import Worker

        def _do():
            if not self._daemon:
                from desktop.daemon_scheduler import DaemonScheduler
                boards = ["人工智能", "芯片", "量子科技", "军工", "新能源汽车"]
                temp = DaemonScheduler(boards)
                return temp.run_full_pipeline()
            return self._daemon.run_full_pipeline()

        def _done(results):
            self.settings.btn_run_pipeline_now.setEnabled(True)
            log_text = "\n".join(results)
            self.settings.sched_log.setText(log_text)
            ok_count = sum(1 for r in results if r.startswith("✅"))
            fail_count = sum(1 for r in results if r.startswith("❌"))
            self.settings.sched_status.setText(
                f"✅ 流水线完成: {ok_count} 成功, {fail_count} 失败"
            )
            self.settings.sched_status.setStyleSheet("color:#66bb6a; font-size:12px;")
            self.status.showMessage(f"全策略流水线完成")
            self._load_dashboard()
            self._refresh_ai_portfolio()

        def _err(msg):
            self.settings.btn_run_pipeline_now.setEnabled(True)
            self.settings.sched_status.setText(f"❌ 流水线失败: {msg}")
            self.settings.sched_status.setStyleSheet("color:#ef5350; font-size:12px;")

        w = Worker(_do)
        w.finished.connect(_done)
        w.error.connect(_err)
        w.start()
        self._pipeline_worker = w

    def _on_view_sched_log(self):
        """查看调度日志。"""
        try:
            lines = ["【最近任务运行】"]
            task_runs = get_recent_task_runs(20)
            if task_runs:
                for r in task_runs:
                    icon = "✅" if r["status"] == "success" else "❌"
                    lines.append(
                        f"{icon} {r['timestamp'][:19]} | {r['task_name']} | "
                        f"{r['trigger_source']} | {r['elapsed_ms']:.0f}ms"
                    )
                    if r.get("summary"):
                        lines.append(f"　　{r['summary']}")
            else:
                lines.append("暂无任务运行记录")

            lines.append("")
            lines.append("【最近系统事件】")
            events = get_recent_system_events(20)
            if events:
                for e in events:
                    lvl_icon = "🔴" if e["level"] == "error" else "🟡" if e["level"] == "warning" else "🔵"
                    lines.append(
                        f"{lvl_icon} {e['timestamp'][:19]} | {e['source']} | {e['title']}"
                    )
                    if e.get("detail"):
                        lines.append(f"　　{e['detail'][:160]}")
            else:
                lines.append("暂无系统事件")

            self.settings.sched_log.setText("\n".join(lines))
        except Exception as e:
            self.settings.sched_log.setText(f"读取日志失败: {e}")

    # ═══════════════════════════════════════════
    #  OpenClaw 智能体执行网关
    # ═══════════════════════════════════════════

    def _auto_connect_openclaw(self):
        """启动时自动连接 OpenClaw（静默，不阻塞）。"""
        try:
            self._on_openclaw_connect()
        except Exception:
            pass

    def _on_openclaw_save_cfg(self):
        """保存 OpenClaw 面板配置。"""
        self._save_openclaw_panel_config()
        self.status.showMessage("✅ OpenClaw 配置已保存")

    def _on_openclaw_connect(self):
        """连接 OpenClaw 引擎并加载数据源状态。"""
        # 保存 OpenClaw 面板配置
        self._save_openclaw_panel_config()
        self.openclaw.set_connected(True)
        self.status.showMessage("🦀 OpenClaw 引擎已连接")

        from desktop.workers import Worker

        def _do():
            from desktop.openclaw_engine import get_data_sources_status, get_performance_summary
            sources = get_data_sources_status()
            perf = get_performance_summary()
            return {"sources": sources, "perf": perf}

        def _done(result):
            self.openclaw.update_data_sources(result["sources"])
            self.openclaw.update_perf_cards(result.get("perf", {}))
            self.openclaw.monitor_log.append(
                f"[{__import__('datetime').datetime.now().strftime('%H:%M:%S')}] 连接成功，"
                f"已加载 {len(result['sources'])} 个数据源"
            )
            self._on_openclaw_refresh_ops()

        w = Worker(_do)
        w.finished.connect(_done)
        w.error.connect(lambda e: self.status.showMessage(f"连接失败: {e}"))
        w.start()
        self._oc_connect_worker = w

    def _on_openclaw_refresh_ops(self):
        """刷新运行中心。"""
        self.openclaw.ops_status.setText("⏳ 刷新中...")
        from desktop.workers import Worker

        def _do():
            return {
                "tasks": get_recent_task_runs(30),
                "events": get_recent_system_events(30),
            }

        def _done(data):
            self.openclaw.update_ops_center(data.get("tasks", []), data.get("events", []))
            self.openclaw.ops_status.setText(
                f"✅ 已刷新：任务{len(data.get('tasks', []))} 条，事件{len(data.get('events', []))} 条"
            )
            self.openclaw.ops_status.setStyleSheet("color:#66bb6a; font-size:12px;")

        def _err(msg):
            self.openclaw.ops_status.setText(f"❌ 刷新失败: {msg}")
            self.openclaw.ops_status.setStyleSheet("color:#ef5350; font-size:12px;")

        w = Worker(_do)
        w.finished.connect(_done)
        w.error.connect(_err)
        w.start()
        self._oc_ops_worker = w

    def _on_ops_center_refresh(self):
        """刷新顶级运行中心。"""
        self.ops_center.status_label.setText("⏳ 刷新中...")
        from desktop.workers import Worker

        def _do():
            from desktop.snapshot_service import get_system_snapshot
            return {
                "snapshot": get_system_snapshot(),
                "tasks": get_recent_task_runs(50),
                "events": get_recent_system_events(50),
            }

        def _done(data):
            self.ops_center.update_snapshot(data.get("snapshot", {}))
            self.ops_center.update_task_runs(data.get("tasks", []))
            self.ops_center.update_events(data.get("events", []))
            self.ops_center.status_label.setText(
                f"✅ 已刷新：任务{len(data.get('tasks', []))}条，事件{len(data.get('events', []))}条"
            )
            self.ops_center.status_label.setStyleSheet("color:#66bb6a; font-size:12px;")

        def _err(msg):
            self.ops_center.status_label.setText(f"❌ 刷新失败: {msg}")
            self.ops_center.status_label.setStyleSheet("color:#ef5350; font-size:12px;")

        w = Worker(_do)
        w.finished.connect(_done)
        w.error.connect(_err)
        w.start()
        self._ops_center_worker = w

    def _on_openclaw_pipeline(self):
        """执行 OpenClaw 全流程管线。"""
        log_system_event("ui", "openclaw", "手动触发OpenClaw全流程")
        self.openclaw.btn_run_pipeline.setEnabled(False)
        self.openclaw.pipeline_progress.setValue(0)
        self.openclaw.pipeline_log.clear()
        self.status.showMessage("🦀 全流程执行中...")

        from desktop.workers import Worker

        def _do():
            from desktop.openclaw_engine import run_full_pipeline
            boards = ["人工智能", "芯片", "量子科技", "军工", "新能源汽车"]

            def _cb(step, status, elapsed, summary):
                from PyQt6.QtCore import QMetaObject, Qt as QtCore_Qt, Q_ARG
                # Thread-safe UI update via signal
                pass  # UI updated after completion

            return run_full_pipeline(boards)

        def _done(result):
            self.openclaw.btn_run_pipeline.setEnabled(True)
            steps = result.get("steps", [])
            for i, s in enumerate(steps):
                status = "完成" if s.get("status") == "ok" else "失败"
                self.openclaw.update_pipeline_step(
                    i, status,
                    s.get("elapsed", "-"),
                    s.get("summary", s.get("error", ""))[:60],
                )
            self.openclaw.pipeline_progress.setValue(len(steps))
            self.openclaw.pipeline_progress.setFormat(f"完成 {len(steps)}/9")

            # 更新日志
            for s in steps:
                icon = "✅" if s["status"] == "ok" else "❌"
                self.openclaw.append_pipeline_log(
                    f"{icon} {s['name']}: {s.get('summary', s.get('error', ''))}"
                )

            errors = result.get("errors", [])
            if errors:
                self.openclaw.append_pipeline_log(f"\n⚠ 共 {len(errors)} 个错误")
            else:
                self.openclaw.append_pipeline_log("\n🎉 全流程执行成功！")

            # ── 填充决策层表格 ──
            candidates = result.get("candidates", [])
            from PyQt6.QtGui import QColor as _QC
            dt = self.openclaw.decision_result_table
            dt.setRowCount(len(candidates))
            for i, c in enumerate(candidates):
                score = c.get("score", 0)
                signal = "强烈买入" if score >= 70 else "建议买入" if score >= 50 else "观望"
                vals = [
                    c.get("code", ""), c.get("name", ""),
                    signal, "多" if score >= 50 else "中性",
                    f"{min(score, 100)}%", str(score),
                    f"{min(score / 5, 20):.0f}%",
                    f"动量{c.get('momentum_1m', 0):+.1f}% 波动{c.get('volatility', 0):.1f}%",
                ]
                for j, v in enumerate(vals):
                    item = QTableWidgetItem(str(v))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if j == 2:
                        color = _QC("#ef5350") if "强烈" in v else _QC("#4fc3f7") if "建议" in v else _QC("#888")
                        item.setForeground(color)
                    dt.setItem(i, j, item)

            # ── 填充执行层表格 ──
            decisions = result.get("decisions", [])
            et = self.openclaw.exec_table
            et.setRowCount(len(decisions))
            now_str = __import__("datetime").datetime.now().strftime("%H:%M:%S")
            for i, d in enumerate(decisions):
                action = d.get("action", "hold")
                action_label = {"buy": "买入", "sell": "卖出", "hold": "持有"}.get(action, action)
                vals = [
                    now_str, action_label,
                    d.get("code", ""), d.get("name", ""),
                    str(d.get("price", "")), str(d.get("shares", "")),
                    "已执行", d.get("reason", "")[:30],
                ]
                for j, v in enumerate(vals):
                    item = QTableWidgetItem(str(v))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if j == 1:
                        color = _QC("#ef5350") if "买" in v else _QC("#26a69a") if "卖" in v else _QC("#4fc3f7")
                        item.setForeground(color)
                    et.setItem(i, j, item)

            if not decisions:
                et.setRowCount(1)
                item = QTableWidgetItem("本次无交易指令（AI 分析未产出决策或非交易时间）")
                et.setItem(0, 0, item)

            # ── 填充反馈层 ──
            try:
                from desktop.openclaw_engine import get_performance_summary
                perf = get_performance_summary()
                self.openclaw.update_perf_cards(perf)
            except Exception:
                pass

            # 预警日志
            at = self.openclaw.alert_table
            alert_lines = []
            for c in candidates[:5]:
                if c.get("score", 0) >= 70:
                    alert_lines.append({
                        "time": now_str, "type": "强烈买入",
                        "code": c.get("code", ""), "content": f"评分{c['score']} {c.get('name','')}",
                        "status": "已推送",
                    })
            at.setRowCount(len(alert_lines))
            for i, a in enumerate(alert_lines):
                for j, k in enumerate(["time", "type", "code", "content", "status"]):
                    item = QTableWidgetItem(a.get(k, ""))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    at.setItem(i, j, item)

            # 反馈文本
            summary_lines = [f"📊 全流程执行摘要："]
            summary_lines.append(f"  候选股: {len(candidates)} 只")
            summary_lines.append(f"  AI 决策: {len(decisions)} 条")
            ok_steps = sum(1 for s in steps if s.get("status") == "ok")
            summary_lines.append(f"  成功步骤: {ok_steps}/8")
            if candidates:
                top3 = ", ".join(f"{c['code']}({c['score']})" for c in candidates[:3])
                summary_lines.append(f"  Top3: {top3}")
            self.openclaw.feedback_output.setText("\n".join(summary_lines))

            try:
                from desktop.portfolio_tracker import log_operation
                log_operation(
                    "openclaw",
                    "PIPELINE",
                    f"steps={len(steps)} candidates={len(candidates)} decisions={len(decisions)}",
                )
            except Exception:
                pass

            self.status.showMessage("🦀 全流程执行完成")
            self._load_dashboard()
            self._refresh_ai_portfolio()

        def _err(msg):
            self.openclaw.btn_run_pipeline.setEnabled(True)
            self.openclaw.append_pipeline_log(f"❌ 流水线执行失败: {msg}")
            self.status.showMessage(f"全流程失败: {msg}")

        w = Worker(_do)
        w.finished.connect(_done)
        w.error.connect(_err)
        w.start()
        self._oc_pipeline_worker = w

    def _on_openclaw_fetch_all(self):
        """感知层：全量数据拉取。"""
        self.openclaw.monitor_log.append(
            f"[{__import__('datetime').datetime.now().strftime('%H:%M:%S')}] 开始全量数据拉取..."
        )
        from desktop.workers import Worker

        def _do():
            from desktop.data_sync import refresh_latest_kline
            result = refresh_latest_kline(max_codes=500, threads=8)
            return result

        def _done(result):
            self.openclaw.monitor_log.append(
                f"[{__import__('datetime').datetime.now().strftime('%H:%M:%S')}] "
                f"✅ 拉取完成: {result['fetched']} 只更新, {result['rows_updated']} 条数据"
            )
            self._on_openclaw_connect()

        w = Worker(_do)
        w.finished.connect(_done)
        w.error.connect(lambda e: self.openclaw.monitor_log.append(f"❌ 拉取失败: {e}"))
        w.start()
        self._oc_fetch_worker = w

    def _on_openclaw_nl_strategy(self):
        """决策层：自然语言策略研判。"""
        query = self.openclaw.strategy_input.text().strip()
        if not query:
            self.status.showMessage("请输入策略描述")
            return

        self.openclaw.ai_analysis_output.setText("🧠 AI 研判中...")
        from desktop.workers import Worker

        def _do():
            from desktop.ai_trader import _call_llm, _get_api_config
            cfg = _get_api_config()
            if not cfg.get("api_key"):
                return {"error": "请先在「设置」中配置 API Key"}

            prompt = (
                f"你是一个专业的 A 股量化分析师。用户给出了一个策略描述：\n"
                f"「{query}」\n\n"
                f"请基于这个策略思路，分析当前市场环境，给出：\n"
                f"1. 符合条件的具体股票列表（代码+名称+理由），最多10只\n"
                f"2. 对每只股票的买入建议（信号强度、建议仓位比例）\n"
                f"3. 风险提示\n\n"
                f"请以结构化方式回答。"
            )
            response = _call_llm(prompt, system="你是专业A股量化分析师")
            return {"analysis": response, "query": query}

        def _done(result):
            if "error" in result:
                self.openclaw.ai_analysis_output.setText(f"❌ {result['error']}")
                return
            self.openclaw.ai_analysis_output.setText(result.get("analysis", ""))

        w = Worker(_do)
        w.finished.connect(_done)
        w.error.connect(lambda e: self.openclaw.ai_analysis_output.setText(f"❌ {e}"))
        w.start()
        self._oc_nl_worker = w

    def _on_openclaw_report(self):
        """反馈层：生成绩效报告。"""
        from desktop.workers import Worker

        def _do():
            from desktop.openclaw_engine import get_performance_summary
            perf = get_performance_summary()
            from desktop.ai_portfolio import get_comparison
            comp = get_comparison()
            lines = [f"📊 OpenClaw 绩效报告 — {date.today()}"]
            for mode, label in [("auto", "半自主仓"), ("full_auto", "完全自主仓"),
                                ("manual", "推荐仓"), ("custom", "自定义仓")]:
                c = comp.get(mode, {})
                lines.append(
                    f"\n{label}: 收益{c.get('return_pct',0):+.2f}% "
                    f"胜率{c.get('win_rate',0):.1f}% "
                    f"交易{c.get('total_trades',0)}笔"
                )
            return {"report": "\n".join(lines), "perf": perf}

        def _done(result):
            self.openclaw.feedback_output.setText(result.get("report", ""))
            self.openclaw.update_perf_cards(result.get("perf", {}))

        w = Worker(_do)
        w.finished.connect(_done)
        w.error.connect(lambda e: self.openclaw.feedback_output.setText(f"❌ {e}"))
        w.start()
        self._oc_report_worker = w

    def _on_openclaw_optimize(self):
        """反馈层：AI 策略调优建议。"""
        self.openclaw.feedback_output.setText("🔧 AI 分析策略表现并生成调优建议...")
        from desktop.workers import Worker

        def _do():
            from desktop.ai_trader import _call_llm, _get_api_config
            cfg = _get_api_config()
            if not cfg.get("api_key"):
                return "请先配置 API Key"
            from desktop.ai_portfolio import get_comparison
            comp = get_comparison()
            ctx = json.dumps(comp, ensure_ascii=False, default=str)
            prompt = (
                f"以下是我的量化交易系统各仓位的表现数据：\n{ctx}\n\n"
                f"请分析：\n"
                f"1. 哪些策略表现好？哪些需要调整？\n"
                f"2. 当前持仓集中度是否合理？\n"
                f"3. 建议调整的参数（如止损比例、持仓数、板块配置）\n"
                f"4. 下一步优化方向\n\n请给出具体、可操作的建议。"
            )
            return _call_llm(prompt, system="你是资深量化策略分析师")

        def _done(result):
            self.openclaw.feedback_output.setText(result)

        w = Worker(_do)
        w.finished.connect(_done)
        w.error.connect(lambda e: self.openclaw.feedback_output.setText(f"❌ {e}"))
        w.start()
        self._oc_opt_worker = w

    def _on_openclaw_learn(self):
        """立即执行学习：采集结果 → 评估 → 更新权重。"""
        log_system_event("ui", "openclaw", "手动触发OpenClaw学习")
        self.openclaw.evolve_status.setText("⏳ 正在学习...")
        self.openclaw.btn_learn_now.setEnabled(False)

        from desktop.workers import Worker

        def _do():
            from desktop.openclaw_learner import evaluate_and_learn, get_strategy_weights, get_learning_history
            result = evaluate_and_learn()
            weights = get_strategy_weights()
            history = get_learning_history(10)
            return {"result": result, "weights": weights, "history": history}

        def _done(data):
            self.openclaw.btn_learn_now.setEnabled(True)
            result = data["result"]
            weights = data["weights"]

            self.openclaw.update_strategy_weights(weights)
            self.openclaw.update_findings(result.get("learnings", []))

            n_strat = len(result.get("scan_perf", {}))
            n_learn = len(result.get("learnings", []))
            self.openclaw.evolve_status.setText(
                f"✅ 学习完成：{n_strat} 个策略评估，{n_learn} 条发现"
            )
            self.openclaw.evolve_status.setStyleSheet("color:#66bb6a; font-size:12px;")

            # 学习历史
            lines = []
            for h in data.get("history", []):
                lines.append(f"[{h['timestamp'][:16]}] {h['module']}/{h['metric']} = {h['value']}")
            self.openclaw.learning_log.setText("\n".join(lines) if lines else "暂无历史")

            try:
                from desktop.portfolio_tracker import log_operation
                log_operation(
                    "openclaw",
                    "LEARN",
                    f"strategies={len(result.get('scan_perf', {}))} findings={len(result.get('learnings', []))}",
                )
            except Exception:
                pass

            self.status.showMessage("🎯 OpenClaw 学习完成")

        def _err(msg):
            self.openclaw.btn_learn_now.setEnabled(True)
            self.openclaw.evolve_status.setText(f"❌ 学习失败: {msg}")

        w = Worker(_do)
        w.finished.connect(_done)
        w.error.connect(_err)
        w.start()
        self._oc_learn_worker = w

    def _on_openclaw_evolve_advice(self):
        """AI 生成自主进化建议。"""
        log_system_event("ui", "openclaw", "手动触发进化建议生成")
        self.openclaw.evolve_output.setText("🧠 AI 分析中...")
        from desktop.workers import Worker

        def _do():
            from desktop.openclaw_learner import evaluate_and_learn, generate_evolution_advice
            result = evaluate_and_learn()
            advice = generate_evolution_advice(result)
            return advice

        def _done(advice):
            self.openclaw.evolve_output.setText(advice)

        w = Worker(_do)
        w.finished.connect(_done)
        w.error.connect(lambda e: self.openclaw.evolve_output.setText(f"❌ {e}"))
        w.start()
        self._oc_evolve_worker = w

    def _on_openclaw_apply_weights(self):
        """将学习到的策略权重应用到完全自主仓。"""
        try:
            from desktop.openclaw_learner import get_strategy_weights
            weights = get_strategy_weights()
            if not weights:
                self.status.showMessage("⚠ 无学习数据，请先执行学习")
                return

            # 保存到 kv_store 供 ai_trader 读取
            import json
            conn = self._get_db()
            conn.execute(
                "INSERT OR REPLACE INTO kv_store VALUES (?,?,datetime('now'))",
                ("openclaw_strategy_weights", json.dumps(weights, default=str)),
            )
            conn.commit()
            conn.close()

            best = max(weights.items(), key=lambda x: x[1].get("weight", 0))
            self.openclaw.evolve_status.setText(
                f"✅ 策略权重已应用到完全自主仓 | 最优策略: {best[0]}(权重{best[1]['weight']:.1f})"
            )
            self.openclaw.evolve_status.setStyleSheet("color:#66bb6a; font-size:12px;")
            self.status.showMessage("✅ 学习权重已应用到完全自主仓")
        except Exception as e:
            self.status.showMessage(f"应用失败: {e}")

    def _on_openclaw_stock_dblclick(self, row, col):
        item = self.openclaw.decision_result_table.item(row, 0)
        if item:
            code = item.text().strip()
            if code and len(code) == 6 and code.isdigit():
                self._navigate_to_stock(code)

    def _on_ai_auto_cycle(self):
        """半自主仓：后台线程执行，不阻塞 UI。"""
        engine = self.ai_portfolio.engine_combo.currentText()
        boards = self.ai_portfolio.get_selected_boards()
        if not boards:
            self.status.showMessage("请先勾选至少一个板块")
            return
        board = boards[0]
        self.status.showMessage(f"半自主仓决策中（{engine}）...")
        self.ai_portfolio.btn_auto_run.setEnabled(False)

        from desktop.workers import Worker

        def _do():
            if "OpenClaw" in engine:
                from desktop.openclaw_agent import run_openclaw_auto_cycle
                return run_openclaw_auto_cycle(board)
            else:
                from desktop.ai_trader import run_auto_cycle
                return run_auto_cycle(",".join(boards))

        def _done(results):
            self.ai_portfolio.btn_auto_run.setEnabled(True)
            self.ai_portfolio.execute_results.setText(f"[半自主仓]\n" + "\n".join(results))
            self._refresh_ai_portfolio()
            self.status.showMessage(f"半自主仓完成：{len(results)} 条")

        def _err(msg):
            self.ai_portfolio.btn_auto_run.setEnabled(True)
            self.status.showMessage(f"半自主仓失败: {msg}")

        w = Worker(_do)
        w.finished.connect(_done)
        w.error.connect(_err)
        w.start()
        self._auto_worker = w

    def _on_quantum_buy(self):
        """买入量子优化选出的组合到量子仓。"""
        boards = self.ai_portfolio.get_selected_boards()
        if not boards:
            self.status.showMessage("请先勾选板块")
            return
        self.status.showMessage("⚛️ 量子优化 + 买入中...")
        self.ai_portfolio.btn_quantum_buy.setEnabled(False)

        from desktop.workers import Worker

        def _do():
            from desktop.quantum_optimizer import run_quantum_optimization
            from desktop.ai_portfolio import buy, get_state
            result = run_quantum_optimization(boards, n_select=5)
            best_key = result.get("recommended", "qaoa")
            best = result.get(best_key)
            if not best or not best.selected_codes:
                return ["量子优化未产出有效组合"]

            state = get_state("quantum")
            existing = {p["code"] for p in state["positions"]}
            msgs = [f"⚛️ 方法: {best.method} | 夏普 {best.sharpe:.2f}"]
            for i, code in enumerate(best.selected_codes):
                if code in existing:
                    continue
                name = best.selected_names[i] if i < len(best.selected_names) else ""
                # 获取价格
                conn = RepoCompatConnection()
                cur = conn.execute("SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 1", (code,))
                row = cur.fetchone()
                conn.close()
                price = row[0] if row else 0
                if price <= 0:
                    continue
                per = state["cash"] / max(5 - len(state["positions"]), 1)
                shares = int(per / price / 100) * 100
                if shares < 100:
                    shares = 100
                msg = buy("quantum", code, name, price, shares, round(price * 0.92, 2), f"量子{best_key.upper()}")
                msgs.append(msg)
                state = get_state("quantum")
            return msgs

        def _done(msgs):
            self.ai_portfolio.btn_quantum_buy.setEnabled(True)
            self.ai_portfolio.execute_results.setText("[⚛️ 量子仓]\n" + "\n".join(msgs))
            self._refresh_ai_portfolio()
            self.status.showMessage(f"量子仓买入完成: {len(msgs)} 条")

        def _err(msg):
            self.ai_portfolio.btn_quantum_buy.setEnabled(True)
            self.status.showMessage(f"量子仓失败: {msg}")

        w = Worker(_do)
        w.finished.connect(_done)
        w.error.connect(_err)
        w.start()
        self._quantum_buy_worker = w

    def _on_custom_buy_top3(self):
        """自定义仓：买入扫描 Top3。"""
        self.status.showMessage("自定义仓：买入扫描 Top3...")
        self.ai_portfolio.btn_custom_scan.setEnabled(False)
        from desktop.workers import Worker

        def _do():
            from desktop.custom_portfolio import auto_buy_top3_from_scan
            return auto_buy_top3_from_scan()

        def _done(results):
            self.ai_portfolio.btn_custom_scan.setEnabled(True)
            self.ai_portfolio.execute_results.setText(
                "[📌 自定义仓 Top3]\n" + "\n".join(results)
            )
            self._refresh_ai_portfolio()
            self._refresh_tracking()
            self.status.showMessage(f"自定义仓完成：{len(results)} 条")

        def _err(msg):
            self.ai_portfolio.btn_custom_scan.setEnabled(True)
            self.status.showMessage(f"自定义仓失败: {msg}")

        w = Worker(_do)
        w.finished.connect(_done)
        w.error.connect(_err)
        w.start()
        self._custom_worker = w

    def _on_custom_calibrate(self):
        """校准自定义仓的多周期表现。"""
        self.status.showMessage("校准自定义仓跟踪数据...")
        try:
            from desktop.custom_portfolio import calibrate_tracking, get_tracking_summary
            calibrate_tracking()
            records = get_tracking_summary()
            self.ai_portfolio.update_tracking(records)
            self.status.showMessage(f"校准完成：{len(records)} 条记录")
        except Exception as e:
            self.status.showMessage(f"校准失败: {e}")

    def _refresh_tracking(self):
        try:
            from desktop.custom_portfolio import get_tracking_summary
            records = get_tracking_summary()
            self.ai_portfolio.update_tracking(records)
        except Exception:
            pass

    def _on_tracking_dblclick(self, row, col):
        item = self.ai_portfolio.tracking_table.item(row, 0)
        if item:
            code = item.text().strip()
            if code and len(code) == 6 and code.isdigit():
                self._navigate_to_stock(code)

    def _on_full_auto_cycle(self):
        """完全自主仓：AI 全权决策+自动执行，无需确认。"""
        boards = self.ai_portfolio.get_selected_boards()
        if not boards:
            self.status.showMessage("请先勾选至少一个板块")
            return
        self.status.showMessage(f"🚀 完全自主仓运行中（板块: {', '.join(boards[:3])}）...")
        self.ai_portfolio.btn_full_auto.setEnabled(False)

        from desktop.workers import Worker

        def _do():
            from desktop.ai_trader import run_full_auto_cycle
            return run_full_auto_cycle(boards)

        def _done(results):
            self.ai_portfolio.btn_full_auto.setEnabled(True)
            self.ai_portfolio.execute_results.setText(
                f"[🚀 完全自主仓]\n" + "\n".join(results)
            )
            self._refresh_ai_portfolio()
            self.status.showMessage(f"完全自主仓完成：{len(results)} 条")

        def _err(msg):
            self.ai_portfolio.btn_full_auto.setEnabled(True)
            self.status.showMessage(f"完全自主仓失败: {msg}")

        w = Worker(_do)
        w.finished.connect(_done)
        w.error.connect(_err)
        w.start()
        self._full_auto_worker = w

    def _refresh_ai_portfolio(self):
        try:
            from desktop.ai_portfolio import get_log
            from desktop.snapshot_service import get_system_snapshot

            snap = get_system_snapshot()
            comp = snap.get("ai_portfolios", {})
            prices = comp.get("prices", {})
            all_states = snap.get("ai_states", {})
            for mode in ("full_auto", "auto", "manual", "custom", "quantum"):
                all_states.setdefault(mode, {"positions": [], "cash": 0})

            self.ai_portfolio.update_summary(all_states, prices, comp)
            self.ai_portfolio.update_log(
                get_log("auto", 10) + get_log("full_auto", 10),
                get_log("manual", 10),
            )
        except Exception as e:
            _log.error(f"refresh_ai_portfolio error: {e}")

    def _on_ai_send(self):
        msg = self.ai_chat.msg_input.text().strip()
        if not msg:
            return
        self.ai_chat.append_message("user", msg)
        self.ai_chat.clear_input()
        self.ai_chat.clear_pending_action()

        try:
            from desktop.system_assistant import handle_user_message
            result = handle_user_message(msg, self.ai_chat.session_id)
            if result.get("type") != "fallback_chat":
                self._handle_system_assistant_result(result)
                self.ai_chat.refresh_sessions()
                return
            if self.ai_chat.current_mode != "auto":
                self.ai_chat.append_message(
                    "system",
                    f"当前处于「{self.ai_chat.combo_chat_mode.currentText()}」模式，但这条输入未匹配系统动作，已回退到通用 AI 问答。"
                )
        except Exception as e:
            _log.warning(f"system assistant fallback to llm: {e}")

        self._start_general_ai_chat(msg)

    def _start_general_ai_chat(self, msg: str):
        from desktop.ai_trader import _get_api_config
        cfg = _get_api_config()
        if not cfg.get("api_key"):
            self.ai_chat.append_message(
                "system",
                "AI 功能需要配置 API Key 后使用。\n"
                "请在「🤖 AI仓」页面顶部填写 API Key 并点击「保存配置」，\n"
                "或在环境变量中设置 DEEPSEEK_API_KEY。"
            )
            return

        self.status.showMessage("AI 思考中...")
        self.ai_chat.btn_send.setEnabled(False)
        self.ai_chat.append_message("thinking", "正在读取持仓、策略、事件等数据，综合分析中...")

        from desktop.workers import Worker
        def _do_chat():
            from desktop.ai_trader import _call_llm
            ctx = self._build_full_ai_context()
            system = (
                "你是一个专业的 A 股量化交易助手，服务于用户的实盘交易决策。\n"
                "你能读取用户的全部数据，包括：手动模拟仓持仓、AI模拟仓持仓、选股扫描结果、"
                "短期事件选股结果、基金重仓跟踪、回测记录等。\n"
                "请基于这些真实数据回答用户问题，给出专业、具体、可操作的建议。\n"
                "如果涉及具体个股，请给出代码和名称。\n"
                "回答用中文，简洁专业。\n\n"
                "===== 用户数据摘要 =====\n"
                f"{ctx}"
            )
            return _call_llm(msg, system=system)

        worker = Worker(_do_chat)
        worker.finished.connect(self._on_ai_reply)
        worker.error.connect(lambda e: self._on_ai_reply(f"调用出错: {e}"))
        worker.start()
        self._ai_chat_worker = worker

    def _handle_system_assistant_result(self, payload):
        msg = self._format_system_assistant_payload(payload)
        if payload.get("type") == "action_required":
            self.ai_chat.show_pending_action(
                payload.get("action_id", ""),
                preview=payload.get("preview", {}),
                intent=payload.get("intent", {}),
            )
            self.status.showMessage("系统助手：等待确认执行")
        elif payload.get("type") in ("query_result", "explain_result", "task_result", "update_result"):
            self.ai_chat.clear_pending_action()
            self.status.showMessage("系统助手：执行完成")
            self._refresh_after_system_action(payload)
        elif payload.get("type") == "cancelled":
            self.ai_chat.clear_pending_action()
            self.status.showMessage("系统助手：已取消")
        else:
            self.status.showMessage("系统助手：处理完成")
        self.ai_chat.append_message("assistant", msg)
        self.ai_chat.refresh_action_history()

    def _refresh_after_system_action(self, payload):
        body = payload.get("result", payload)
        if payload.get("type") == "task_result":
            title = body.get("title", "")
            if "快照" in title:
                try:
                    self._load_dashboard()
                    self._refresh_ai_portfolio()
                except Exception:
                    pass
            elif "走势验证" in title:
                try:
                    self._on_trend_calibrate()
                except Exception:
                    pass
        if payload.get("type") == "update_result":
            title = body.get("title", "")
            data = body.get("data", {})
            if "手动仓" in title:
                try:
                    self._load_dashboard()
                    self._on_portfolio_refresh()
                except Exception:
                    pass
            if "调度时间" in title:
                try:
                    self.settings.set_schedule_time(
                        data.get("task_key", ""),
                        data.get("schedule_time", ""),
                    )
                except Exception:
                    pass

    def _format_system_assistant_payload(self, payload) -> str:
        body = payload.get("result", payload)
        msg_type = payload.get("type", "")
        if msg_type == "action_required":
            preview = payload.get("preview", {})
            intent = payload.get("intent", {})
            lines = [
                f"# {preview.get('title', '待确认操作')}",
                f"- 动作: `{intent.get('action_key', '-')}`",
                f"- 风险等级: `{intent.get('risk_level', 'low')}`",
                "",
                "## 变更预览",
                f"- 变更前: `{preview.get('before', {})}`",
                f"- 变更后: `{preview.get('after', {})}`",
                "",
                "> 下方操作卡片已就绪，点击“确认执行”即可继续。",
            ]
            return "\n".join(lines)

        title = body.get("title", "系统助手")
        summary = body.get("summary", payload.get("message", ""))
        lines = [f"# {title}"]
        if summary:
            lines.extend(["", summary])

        data = body.get("data")
        if isinstance(data, dict):
            reasons = data.get("reasons")
            if isinstance(reasons, list) and reasons:
                lines.extend(["", "## 原因说明"])
                lines.extend([f"- {item}" for item in reasons[:5]])
            suggested = data.get("suggested_actions")
            if isinstance(suggested, list) and suggested:
                lines.extend(["", "## 建议动作"])
                lines.extend([f"- `{item}`" for item in suggested[:5]])
            totals = data.get("totals")
            if isinstance(totals, dict):
                lines.extend(
                    [
                        "",
                        "## 系统总览",
                        f"- 总资产: `{totals.get('equity', 0):,.0f}`",
                        f"- 总现金: `{totals.get('cash', 0):,.0f}`",
                        f"- 总持仓数: `{totals.get('positions', 0)}`",
                    ]
                )
        elif isinstance(data, list) and data:
            lines.extend(["", "## 明细"])
            lines.extend([f"- `{str(item)[:160]}`" for item in data[:8]])

        if payload.get("type") == "error":
            lines = ["# 系统助手错误", "", payload.get("message", "未知错误")]
        return "\n".join(lines)

    def _on_ai_confirm_action(self):
        action_id = self.ai_chat.pending_action_id
        if not action_id:
            self.status.showMessage("没有待确认的系统动作")
            return
        self.ai_chat.btn_confirm_action.setEnabled(False)
        self.ai_chat.btn_cancel_action.setEnabled(False)
        self.ai_chat.append_message("thinking", "系统助手执行中...")
        self.status.showMessage("系统助手：执行中...")

        from desktop.workers import Worker

        def _do_confirm():
            from desktop.system_assistant import confirm_action
            return confirm_action(action_id)

        worker = Worker(_do_confirm)
        worker.finished.connect(self._on_ai_action_finished)
        worker.error.connect(lambda e: self._on_ai_action_finished({"ok": False, "type": "error", "message": str(e)}))
        worker.start()
        self._ai_action_worker = worker

    def _on_ai_cancel_action(self):
        action_id = self.ai_chat.pending_action_id
        if not action_id:
            self.status.showMessage("没有待取消的系统动作")
            return
        from desktop.system_assistant import cancel_action
        result = cancel_action(action_id)
        self.ai_chat.clear_pending_action()
        self.ai_chat.append_message("assistant", self._format_system_assistant_payload(result))
        self.ai_chat.refresh_action_history()
        self.status.showMessage("系统助手：已取消")

    def _on_ai_action_finished(self, payload):
        self.ai_chat.btn_confirm_action.setEnabled(True)
        self.ai_chat.btn_cancel_action.setEnabled(True)
        self._handle_system_assistant_result(payload)
        self.ai_chat.refresh_sessions()

    def _build_strategy_context(self) -> str:
        """构建策略体系说明，让 AI 理解每个策略的底层逻辑。"""
        return """【策略体系与底层逻辑】

1. SEPA/趋势模板（股票魔法师）:
   - 买入条件: 价格>MA50>MA150>MA200（多头排列）、MA200连续上升≥1个月、价格在52周高点75%以内、RS评分≥70
   - VCP形态: 波动率逐级收缩（后20日std < 前20日std×0.7）、成交量萎缩后放量突破
   - 卖出: 跌破MA50或从高点回撤>8%止损、盈利20%后回撤7%止盈
   - 评分逻辑: 多头排列+20, MA200上升+10, 近52周高点+10, VCP收缩+15, 突破+15

2. CAN SLIM（欧奈尔）:
   - C=当季EPS增长≥25%, A=年度EPS增长≥25%, N=新高/新产品, S=供需(成交量), L=龙头(RS≥80), I=机构持仓增加, M=市场方向
   - 买入: 放量突破+RS强势, 卖出: 跌破买入价8%止损

3. 海龟交易/通道突破:
   - 买入: 价格突破20日最高价, 加仓: 每上涨0.5×ATR加一个风险单位
   - 止损: 2×ATR, 卖出: 跌破10日最低价

4. 格雷厄姆价值:
   - 买入: PE<15, PB<1.5, 股息率>3%, 价格低于MA200的90%
   - 卖出: PE>20 或价格超过内在价值50%

5. 情绪博弈（游资）:
   - 核心: 量比>1.5+短期强势=放量信号, 涨停检测, 连板高度
   - 情绪阶段: 冰点→启动→发酵→高潮→退潮, 在冰点/启动买入, 高潮/退潮卖出

6. 事件驱动:
   - 核心: 新闻关键词→匹配板块→历史异动统计（3/5/10/20日胜率和均涨跌）→预测
   - 异动定义: 板块指数单日涨跌≥2%

7. 基金持仓跟踪:
   - 逻辑: 公募基金季报/半年报/年报重仓股变化分析
   - 公布前5/10日 vs 公布后5/10/20日股价对比 → 判断跟买价值
   - 评分: 基金增持+15, 新进+20, 减持-15, 持有基金数≥500再+15

8. 明星基金经理跟踪:
   - 10位经理: 张坤(消费), 葛兰(医药), 刘彦春(消费), 朱少醒(均衡), 谢治宇(GARP), 武阳(科技), 冯明远(半导体), 周蔚文(成长), 任桀(算力), 韩浩(科技)
   - 跟买信号: 公布后上涨+经理增持+公布前未抢跑 → 强烈跟买

9. 选股扫描评分体系:
   - 综合评分 = 多头排列(20) + MA200上升(10) + VCP收缩(15) + 突破(15) + 近高点(10) + 价格>MA50(10)
   - RS = 基于250日涨幅的相对强度百分位
   - 买入建议: 评分≥60+突破="强烈买入", ≥50+VCP="建议买入", ≥30="观望"
   - 操作建议: 评分≥50+突破+5日涨="加仓", 5日跌>8%="止损", 评分<10="卖出"

10. AI决策引擎:
    - 构建市场上下文 + 持仓上下文 + 候选股多策略评分 → 发送给LLM
    - LLM综合7个维度评分(SEPA趋势/VCP形态/价值评估/动量/情绪博弈/事件驱动/基金持仓) → 输出买卖决策JSON
    - 交易规则: 遵守A股交易时间(9:15-11:30, 13:00-15:00), T+1, 100股整数倍"""

    def _build_full_ai_context(self) -> str:
        """汇总所有模块数据，构建 AI 助手的完整上下文。"""
        import json
        parts = []

        # 用户关注的板块
        try:
            focus_boards = self.ai_portfolio.get_selected_boards()
            if focus_boards:
                parts.append(f"【用户关注板块】{', '.join(focus_boards)}")
        except Exception:
            pass

        try:
            conn = self._get_db()

            # 1) 手动仓持仓（从 SQLite 读取，统一数据源）
            pf_row = conn.execute("SELECT value FROM kv_store WHERE key='manual_portfolio'").fetchone()
            if pf_row:
                pf = json.loads(pf_row[0])
                positions = pf.get("positions", [])
                if positions:
                    lines = ["【手动模拟仓持仓】"]
                    total_value = 0
                    for p in positions:
                        code = p.get("code", "")
                        name = p.get("name", code)
                        shares = p.get("shares", 0)
                        entry = p.get("entry_price", 0)
                        cur_q = conn.execute(
                            "SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 1", (code,)
                        )
                        row = cur_q.fetchone()
                        cur_price = row[0] if row else entry
                        pnl = (cur_price - entry) / entry * 100 if entry > 0 else 0
                        mv = cur_price * shares
                        total_value += mv
                        lines.append(f"  {code} {name}: {shares}股, 成本{entry:.2f}, 现价{cur_price:.2f}, 盈亏{pnl:+.1f}%")
                    cash = pf.get("cash", 0)
                    lines.append(f"  现金: ¥{cash:,.0f}, 持仓市值: ¥{total_value:,.0f}")
                    parts.append("\n".join(lines))

            # 2) AI 仓（全部5种仓位）
            try:
                from desktop.ai_portfolio import get_state
                for mode_label, mode in [
                    ("完全自主仓", "full_auto"), ("半自主仓", "auto"),
                    ("推荐仓", "manual"), ("自定义仓", "custom"), ("量子仓", "quantum"),
                ]:
                    state = get_state(mode)
                    pos = state.get("positions", [])
                    if pos:
                        lines = [f"【{mode_label}】现金 ¥{state['cash']:,.0f}"]
                        for p in pos:
                            code = p["code"]
                            cur_q = conn.execute(
                                "SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 1", (code,)
                            )
                            row = cur_q.fetchone()
                            cp = row[0] if row else p["entry_price"]
                            pnl = (cp - p["entry_price"]) / p["entry_price"] * 100 if p["entry_price"] > 0 else 0
                            lines.append(f"  {code} {p.get('name','')}: {p['shares']}股, 成本{p['entry_price']:.2f}, 现价{cp:.2f}, 盈亏{pnl:+.1f}%")
                        parts.append("\n".join(lines))
            except Exception:
                pass

            # 3) 最近选股扫描结果（取评分 Top10）
            try:
                cur_s = conn.execute("""
                    SELECT code,
                        (SELECT close FROM daily_kline d2 WHERE d2.code=d1.code ORDER BY date DESC LIMIT 1) as price
                    FROM (SELECT DISTINCT code FROM daily_kline) d1
                    LIMIT 200
                """)
                # 简单取板块中有数据的股票
                names_q = conn.execute("SELECT code, name FROM stock_list LIMIT 500")
                nm = {r[0]: r[1] for r in names_q.fetchall()}
                boards_q = conn.execute("SELECT code, board FROM board_stocks LIMIT 2000")
                bd = {}
                for r in boards_q.fetchall():
                    if r[0] not in bd:
                        bd[r[0]] = r[1]
            except Exception:
                nm, bd = {}, {}

            # 4) 短期事件选股
            try:
                cur_e = conn.execute(
                    "SELECT event_text, matched_boards, event_date FROM events ORDER BY id DESC LIMIT 5"
                )
                events = cur_e.fetchall()
                if events:
                    lines = ["【最近事件选股】"]
                    for e in events:
                        lines.append(f"  {e[2]} {e[0]} → 板块: {e[1]}")
                    parts.append("\n".join(lines))
            except Exception:
                pass

            # 5) 基金重仓
            try:
                cur_f = conn.execute(
                    "SELECT code, name, holding_funds, change_type, sector FROM fund_holdings "
                    "ORDER BY holding_funds DESC LIMIT 10"
                )
                funds = cur_f.fetchall()
                if funds:
                    lines = ["【基金重仓 Top10】"]
                    for f in funds:
                        lines.append(f"  {f[0]} {f[1]}: {f[2]}只基金, {f[3] or '-'}, {f[4]}")
                    parts.append("\n".join(lines))
            except Exception:
                pass

            # 6) 最近 AI 交易记录
            try:
                cur_log = conn.execute(
                    "SELECT timestamp, action, code, detail FROM ai_trade_log ORDER BY id DESC LIMIT 10"
                )
                logs = cur_log.fetchall()
                if logs:
                    lines = ["【最近AI交易记录】"]
                    for l in logs:
                        lines.append(f"  {l[0][:16]} {l[1]} {l[2]}: {l[3]}")
                    parts.append("\n".join(lines))
            except Exception:
                pass

            # 7) 最近回测结果
            last_bt = getattr(self, "_last_bt_result", None)
            if last_bt and last_bt.total_trades > 0:
                parts.append(
                    f"【最近回测结果】收益 {last_bt.total_return:.2%}, 夏普 {last_bt.sharpe_ratio:.2f}, "
                    f"胜率 {last_bt.win_rate:.1%}, 回撤 {last_bt.max_drawdown:.2%}, "
                    f"交易 {last_bt.total_trades} 笔"
                )

            conn.close()

            # 8) 策略体系说明
            parts.append(self._build_strategy_context())
        except Exception:
            parts.append("（数据读取部分异常，但仍可回答一般问题）")

        return "\n\n".join(parts) if parts else "（暂无持仓和交易数据）"

    def _on_ai_reply(self, reply):
        self.ai_chat.btn_send.setEnabled(True)
        self.ai_chat.append_message("assistant", str(reply))
        self.ai_chat.refresh_sessions()
        self.status.showMessage("AI 回复完成")

    def _on_auto_refresh(self):
        """每60秒自动刷新：更新仪表盘价格和持仓盈亏。"""
        try:
            self._load_dashboard()
        except Exception as e:
            _log.debug(f"auto refresh error: {e}")

    def _check_scheduled_task(self):
        """每分钟检查一次是否到了定时任务时间（三仓同时运行）。"""
        try:
            from desktop.auto_scheduler import check_and_run
            boards = self.ai_portfolio.get_selected_boards()
            if not boards:
                return
            result = check_and_run(boards[0], boards=boards)
            if result:
                n_full = len(result.get("full_auto_results", []))
                n_auto = len(result.get("auto_results", []))
                n_manual = len(result.get("manual_suggestions", []))
                pushed = "已推送微信" if result.get("pushed") else "未推送"
                self.status.showMessage(
                    f"⏰ 定时任务完成: 完全自主 {n_full} / 半自主 {n_auto} / 推荐 {n_manual} 条, {pushed}"
                )
                self.ai_portfolio.execute_results.setText(
                    f"[定时任务 {result.get('time', '')}]\n"
                    f"🟣 完全自主仓:\n" + "\n".join(result.get("full_auto_results", [])) + "\n"
                    f"🔴 半自主仓:\n" + "\n".join(result.get("auto_results", []))
                )
                self._refresh_ai_portfolio()
                _log.info(f"scheduled: full={n_full}, auto={n_auto}, manual={n_manual}, {pushed}")
        except Exception as e:
            _log.error(f"scheduled task error: {e}")
