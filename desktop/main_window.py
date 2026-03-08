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
import sqlite3
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
from desktop.panels.settings import SettingsPanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AetherQuant — AI 量化交易平台")
        self.setMinimumSize(1280, 800)
        self.resize(1440, 900)

        init_db()
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

        # 定时任务检查器（每分钟检查一次是否到了 10:00 或 14:00）
        self._scheduler_timer = QTimer(self)
        self._scheduler_timer.timeout.connect(self._check_scheduled_task)
        self._scheduler_timer.start(60_000)

        QTimer.singleShot(500, self._safe_initial_load)

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
        self.settings = SettingsPanel()

        self.tabs.addTab(self.dashboard, "📈 总览")
        self.tabs.addTab(self.screening, "📡 选股")
        self.tabs.addTab(self.short_term, "⚡ 短期选股")
        self.tabs.addTab(self.portfolio, "💼 手动仓")
        self.tabs.addTab(self.ai_portfolio, "🤖 AI仓")
        self.tabs.addTab(self.backtest, "📊 回测")
        self.tabs.addTab(self.stock_analysis, "📉 个股")
        self.tabs.addTab(self.ai_chat, "🤖 AI")
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
        self.portfolio.btn_refresh.clicked.connect(self._on_portfolio_refresh)
        self.backtest.btn_run.clicked.connect(self._on_backtest_run)
        self.backtest.btn_monte_carlo.clicked.connect(self._on_monte_carlo)
        self.backtest.btn_walkforward.clicked.connect(self._on_walk_forward)
        self.backtest.btn_multi_compare.clicked.connect(self._on_multi_compare)
        self.stock_analysis.btn_analyze.clicked.connect(self._on_stock_analyze)
        self.stock_analysis.code_input.returnPressed.connect(self._on_stock_analyze)
        self.ai_chat.btn_send.clicked.connect(self._on_ai_send)
        self.ai_chat.msg_input.returnPressed.connect(self._on_ai_send)
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
        self.ai_portfolio.btn_save_config.clicked.connect(self._on_ai_save_config)
        self.ai_portfolio.btn_save_openclaw.clicked.connect(self._on_save_openclaw)
        self.ai_portfolio.btn_run_ai.clicked.connect(self._on_ai_run_decision)
        self.ai_portfolio.btn_execute.clicked.connect(self._on_ai_execute_decisions)
        self.ai_portfolio.btn_auto_run.clicked.connect(self._on_ai_auto_cycle)
        self.ai_portfolio.btn_full_auto.clicked.connect(self._on_full_auto_cycle)
        self.ai_portfolio.btn_custom_scan.clicked.connect(self._on_custom_buy_top3)
        self.ai_portfolio.btn_custom_calibrate.clicked.connect(self._on_custom_calibrate)
        self.ai_portfolio.decisions_table.cellDoubleClicked.connect(self._on_ai_decision_dblclick)
        self.ai_portfolio.pos_table.cellDoubleClicked.connect(self._on_ai_pos_dblclick)
        self.ai_portfolio.tracking_table.cellDoubleClicked.connect(self._on_tracking_dblclick)
        self.settings.combo_theme.currentTextChanged.connect(
            lambda t: self._set_theme("dark" if t == "深色" else "light")
        )
        self.dashboard.pos_table.cellDoubleClicked.connect(self._on_dashboard_stock_dblclick)
        self.portfolio.pos_table.cellDoubleClicked.connect(self._on_portfolio_stock_dblclick)
        self.screening.result_table.cellDoubleClicked.connect(self._on_screening_stock_dblclick)

    def _on_dashboard_stock_dblclick(self, row, col):
        item = self.dashboard.pos_table.item(row, 0)
        if item:
            self._navigate_to_stock(item.text().strip())

    def _on_portfolio_stock_dblclick(self, row, col):
        item = self.portfolio.pos_table.item(row, 0)
        if item:
            self._navigate_to_stock(item.text().strip())

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
            self, "关于 AetherQuant",
            "AetherQuant — AI 量化交易平台 v2.0\n\n"
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
        except Exception:
            pass
        try:
            from desktop.fund_strategy import get_star_managers
            self.fund_panel.update_star_summary(get_star_managers())
        except Exception:
            pass
        self._load_default_index_chart()

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

    def _get_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(os.path.join("data_cache", "quant.db"), timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

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
        """从 SQLite 数据库加载持仓和行情（毫秒级）。"""
        import json

        pf = {}
        pf_path = "portfolio.json"
        if os.path.exists(pf_path):
            try:
                with open(pf_path, "r", encoding="utf-8") as f:
                    pf = json.load(f)
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

        conn = self._get_db()
        for pos in positions:
            code = pos.get("code", "")
            entry = float(pos.get("entry_price", 0))
            shares = int(pos.get("shares", 0))
            price = entry
            prev_c = entry

            try:
                cur = conn.execute(
                    "SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 2",
                    (str(code),),
                )
                rows_db = cur.fetchall()
                if rows_db:
                    price = float(rows_db[0][0])
                if len(rows_db) >= 2:
                    prev_c = float(rows_db[1][0])
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

        self.dashboard.update_metrics(summary)
        self.dashboard.update_positions(pos_details)
        self.portfolio.update_summary(summary)
        self.portfolio.update_positions(pos_details)

        # 本地计算市场环境（从沪深300指数日线判断）
        try:
            import numpy as np
            conn = self._get_db()
            cur = conn.execute(
                "SELECT close, volume FROM daily_kline WHERE code='000300' ORDER BY date DESC LIMIT 30"
            )
            idx_rows = cur.fetchall()
            conn.close()
            if len(idx_rows) >= 25:
                idx_rows = idx_rows[::-1]
                closes = np.array([r[0] for r in idx_rows])
                volumes = np.array([r[1] for r in idx_rows])
                dist_count = 0
                for i in range(1, len(closes)):
                    pct = (closes[i] - closes[i-1]) / closes[i-1]
                    vol_up = volumes[i] > volumes[i-1]
                    if pct < -0.002 and vol_up:
                        dist_count += 1
                self.dashboard.update_market(dist_count < 5, dist_count)
            else:
                self.dashboard.market_label.setText("📊 市场环境数据不足（需沪深300指数日线）")
                self.dashboard.market_label.setStyleSheet("color: #888; font-size: 13px;")
        except Exception:
            self.dashboard.market_label.setText("📊 市场环境暂无数据")
            self.dashboard.market_label.setStyleSheet("color: #888; font-size: 13px;")

        self.status.showMessage("数据加载完成")

    def _on_dashboard_loaded(self, data):
        pass

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
        db_path = os.path.join("data_cache", "quant.db")
        rows = []

        try:
            conn = sqlite3.connect(db_path, timeout=5)
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

    def _on_scan(self):
        """纯本地 SQLite 选股扫描（不依赖 services 层）。"""
        sid = self.screening.combo_strategy.currentData() or "sepa"
        sample = self.screening.spin_sample.value()
        rs_min = self.screening.spin_rs.value()
        self.screening.progress.setVisible(True)
        self.screening.status_label.setText("本地扫描中...")
        self.status.showMessage(f"本地选股扫描（{sid}，样本 {sample}）...")

        def _do_local_scan():
            return self._run_local_scan(sid, sample, rs_min)

        from desktop.workers import Worker
        self._worker_scan = Worker(_do_local_scan)
        self._worker_scan.finished.connect(self._on_scan_done)
        self._worker_scan.error.connect(lambda e: self._on_scan_error(str(e)))
        self._worker_scan.start()

    def _run_local_scan(self, strategy_id: str, sample: int, rs_min: int) -> list[dict]:
        """基于本地 SQLite 日线数据的多策略选股扫描。"""
        import numpy as np

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

            ma50 = float(np.mean(closes[-50:]))
            ma150 = float(np.mean(closes[-150:])) if n >= 150 else ma50
            ma200 = float(np.mean(closes[-200:])) if n >= 200 else ma150

            # RS 评分（相对强度：近 250 日涨幅排名的百分位）
            pct_250 = (price / float(closes[0]) - 1) * 100 if closes[0] > 0 else 0

            # SEPA 趋势评分
            score = 0
            signals = []
            if price > ma50:
                score += 10
            if n >= 200 and ma50 > ma150 > ma200:
                score += 20
                signals.append("多头排列")
            if n >= 200:
                ma200_prev = float(np.mean(closes[-222:-22])) if n >= 222 else ma200
                if ma200 > ma200_prev:
                    score += 10
                    signals.append("MA200上升")

            h52 = float(np.max(highs[-250:])) if n >= 250 else float(np.max(highs))
            l52 = float(np.min(lows[-250:])) if n >= 250 else float(np.min(lows))
            if h52 > 0 and price >= h52 * 0.75:
                score += 10
            dist_high = round((price / h52 - 1) * 100, 1) if h52 > 0 else 0

            # VCP 检测
            vcp = False
            if n >= 40:
                vol_early = float(np.std(closes[-40:-20]) / max(np.mean(closes[-40:-20]), 1e-6))
                vol_recent = float(np.std(closes[-20:]) / max(np.mean(closes[-20:]), 1e-6))
                if vol_recent < vol_early * 0.7:
                    vcp = True
                    score += 15
                    signals.append("VCP收缩")

            # 突破检测
            breakout = False
            if n >= 20:
                high20 = float(np.max(closes[-21:-1]))
                if price >= high20:
                    breakout = True
                    score += 15
                    signals.append("突破")

            # 量比
            vol_ratio = 0
            if n >= 20 and np.mean(vols[-20:]) > 0:
                vol_ratio = round(float(vols[-1]) / float(np.mean(vols[-20:])), 1)

            # 收缩度
            contraction = 0
            if n >= 40:
                contraction = round(vol_recent / max(vol_early, 1e-6), 2) if vol_early > 0 else 0

            # RS 伪排名
            rs = min(99, max(1, int(50 + pct_250 * 0.3)))

            if rs < rs_min:
                continue

            # 买入/操作建议
            signal_str = " ".join(signals)
            pct5 = (price / float(closes[-6]) - 1) * 100 if n >= 6 and closes[-6] > 0 else 0
            pct1 = (price / float(closes[-2]) - 1) * 100 if n >= 2 and closes[-2] > 0 else 0

            buy_advice = ""
            action_advice = ""
            if score >= 60 and breakout:
                buy_advice = "🟢 强烈买入"
            elif score >= 50 and (breakout or vcp):
                buy_advice = "🔵 建议买入"
            elif score >= 40 and "多头排列" in signal_str:
                buy_advice = "🔵 建议买入"
            elif score >= 30:
                buy_advice = "⚪ 观望"
            elif score > 0:
                buy_advice = "⚪ 暂不买入"
            else:
                buy_advice = "⛔ 不买入"

            if score >= 50 and breakout and pct5 > 0:
                action_advice = "📈 加仓"
            elif score >= 40 and pct1 > 0:
                action_advice = "💎 持有"
            elif pct5 < -8:
                action_advice = "🔴 卖出止损"
            elif score < 15 and pct5 < -3:
                action_advice = "🟡 减仓"
            elif score < 10:
                action_advice = "🔴 卖出"
            else:
                action_advice = "💎 持有"

            candidates.append({
                "代码": code,
                "名称": names.get(code, ""),
                "板块": board_map.get(code, ""),
                "策略": strategy_id.upper(),
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
        self.screening.status_label.setText(f"扫描完成，{n} 只候选")
        self.status.showMessage(f"选股完成: {n} 只候选")
        # 缓存扫描结果供 AI 仓使用
        if candidates:
            self._save_scan_results(candidates)

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
        self.status.showMessage("选股扫描失败")

    def _on_portfolio_refresh(self):
        self.status.showMessage("刷新持仓行情...")
        self._load_dashboard()
        self.status.showMessage("持仓行情已刷新")

    def _on_backtest_run(self):
        strategy_map = {
            "sepa": "trend", "canslim": "trend", "turtle": "breakout",
            "graham": "value", "buffett": "value", "lynch": "momentum",
        }
        sid = self.backtest.combo_strategy.currentData() or "sepa"
        local_strategy = strategy_map.get(sid, "trend")
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
        strategy_map = {
            "sepa": "trend", "canslim": "trend", "turtle": "breakout",
            "graham": "value", "buffett": "value",
        }
        sid = self.backtest.combo_strategy.currentData() or "sepa"
        local_strategy = strategy_map.get(sid, "trend")
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
        """个股分析入口（防抖 + 后台加载网络数据）。"""
        now = __import__("time").time()
        if hasattr(self, "_last_analyze_time") and now - self._last_analyze_time < 0.8:
            return
        self._last_analyze_time = now

        code = self.stock_analysis.code_input.text().strip()
        if not code or len(code) != 6 or not code.isdigit():
            self.status.showMessage("请输入有效的 6 位股票代码")
            return

        self.stock_analysis.btn_analyze.setEnabled(False)
        self.status.showMessage(f"分析 {code}...")

        # 先尝试本地数据
        try:
            conn = self._get_db()
            cur = conn.execute(
                "SELECT COUNT(*) FROM daily_kline WHERE code=?", (code,)
            )
            cnt = cur.fetchone()[0]
            conn.close()
        except Exception:
            cnt = 0

        if cnt >= 20:
            try:
                self._do_stock_analyze_local(code)
            except Exception as e:
                _log.error(f"stock_analyze error: {e}")
                self.status.showMessage(f"分析失败: {e}")
            finally:
                self.stock_analysis.btn_analyze.setEnabled(True)
        else:
            self.status.showMessage(f"{code} 本地数据不足，正在后台获取...")
            from desktop.workers import Worker

            def _fetch_and_analyze():
                from desktop.data_sync import fetch_daily_tencent
                fetched = fetch_daily_tencent(code)
                if fetched:
                    c = self._get_db()
                    c.executemany(
                        "INSERT OR REPLACE INTO daily_kline "
                        "(code, date, open, high, low, close, volume, amount, pct_change) "
                        "VALUES (?,?,?,?,?,?,?,?,?)", fetched,
                    )
                    c.commit()
                    c.close()
                return code

            def _on_fetch_done(result_code):
                self.stock_analysis.btn_analyze.setEnabled(True)
                try:
                    self._do_stock_analyze_local(result_code)
                except Exception as e:
                    _log.error(f"stock_analyze error after fetch: {e}")
                    self.status.showMessage(f"分析失败: {e}")

            def _on_fetch_err(msg):
                self.stock_analysis.btn_analyze.setEnabled(True)
                self.stock_analysis.header_label.setText(f"{code} — 数据获取失败")
                self.status.showMessage(f"数据获取失败: {msg}")

            w = Worker(_fetch_and_analyze)
            w.finished.connect(_on_fetch_done)
            w.error.connect(_on_fetch_err)
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

    def _on_stock_done(self, data):
        pass

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
        self.status.showMessage(f"AI 配置已保存：{provider} / {model}")

    def _on_ai_run_decision(self):
        """推荐仓：后台线程分析，不阻塞 UI。"""
        self.status.showMessage("AI 正在分析市场（推荐仓）...")
        self.ai_portfolio.analysis_label.setText("AI 分析中，请稍候...")
        self.ai_portfolio.btn_run_ai.setEnabled(False)

        from desktop.workers import Worker
        boards = self.ai_portfolio.get_selected_boards() or ["人工智能"]

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

    def _on_ai_pos_dblclick(self, row, col):
        item = self.ai_portfolio.pos_table.item(row, 0)
        if item:
            code = item.text().strip()
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
        key = self.ai_portfolio.openclaw_key_input.text().strip()
        if not key:
            self.status.showMessage("请输入 OpenClaw API Key")
            return
        save_openclaw_config(key)
        self.status.showMessage("OpenClaw 配置已保存")

    def _on_ai_auto_cycle(self):
        """半自主仓：后台线程执行，不阻塞 UI。"""
        engine = self.ai_portfolio.engine_combo.currentText()
        boards = self.ai_portfolio.get_selected_boards() or ["人工智能"]
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
        boards = self.ai_portfolio.get_selected_boards() or ["人工智能"]
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
            from desktop.ai_portfolio import get_state, get_log, get_comparison
            comp = get_comparison()
            prices = comp.get("prices", {})

            auto_state = get_state("auto")
            manual_state = get_state("manual")

            self.ai_portfolio.update_summary(auto_state, manual_state, prices, comp)
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

            # 1) 手动仓持仓
            pf_path = "portfolio.json"
            if os.path.exists(pf_path):
                with open(pf_path, "r", encoding="utf-8") as f:
                    pf = json.load(f)
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

            # 2) AI 仓
            try:
                from desktop.ai_portfolio import get_state
                for mode_label, mode in [("AI自主仓", "auto"), ("AI推荐仓", "manual")]:
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
        pass

    def _check_scheduled_task(self):
        """每分钟检查一次是否到了定时任务时间（三仓同时运行）。"""
        try:
            from desktop.auto_scheduler import check_and_run
            boards = self.ai_portfolio.get_selected_boards() or ["人工智能"]
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
