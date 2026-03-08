"""AI 自主交易模拟仓面板"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QGridLayout, QLineEdit, QComboBox, QTextEdit, QTabWidget,
    QCheckBox, QFrame, QScrollArea,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor


class AIPortfolioPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        title = QLabel("🤖 AI 自主交易模拟仓")
        title.setFont(QFont("", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        # API 配置区
        api_row1 = QHBoxLayout()
        api_row1.addWidget(QLabel("平台:"))
        self.provider_combo = QComboBox()
        self.provider_combo.addItems([
            "DeepSeek", "OpenAI", "Google Gemini", "Claude", "通义千问", "月之暗面 Kimi", "自定义",
        ])
        self.provider_combo.currentTextChanged.connect(self._on_provider_changed)
        api_row1.addWidget(self.provider_combo)
        api_row1.addWidget(QLabel("模型:"))
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.setMinimumWidth(180)
        api_row1.addWidget(self.model_combo)
        api_row1.addStretch()
        layout.addLayout(api_row1)

        api_row2 = QHBoxLayout()
        api_row2.addWidget(QLabel("API Key:"))
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("sk-xxxxxxxx")
        self.api_key_input.setMinimumWidth(300)
        api_row2.addWidget(self.api_key_input)
        api_row2.addWidget(QLabel("Base URL:"))
        self.base_url_input = QLineEdit()
        self.base_url_input.setPlaceholderText("https://api.deepseek.com/v1")
        self.base_url_input.setMinimumWidth(250)
        api_row2.addWidget(self.base_url_input)
        self.btn_save_config = QPushButton("💾 保存配置")
        api_row2.addWidget(self.btn_save_config)
        api_row2.addStretch()
        layout.addLayout(api_row2)

        self._on_provider_changed("DeepSeek")

        # OpenClaw 配置行
        oc_row = QHBoxLayout()
        oc_row.addWidget(QLabel("OpenClaw:"))
        self.openclaw_key_input = QLineEdit()
        self.openclaw_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.openclaw_key_input.setPlaceholderText("OpenClaw API Key（自主仓用）")
        self.openclaw_key_input.setMinimumWidth(300)
        oc_row.addWidget(self.openclaw_key_input)
        self.btn_save_openclaw = QPushButton("💾 保存 OpenClaw")
        oc_row.addWidget(self.btn_save_openclaw)
        self.engine_combo = QComboBox()
        self.engine_combo.addItems(["DeepSeek/GPT（直接API）", "OpenClaw Agent"])
        self.engine_combo.setToolTip("自主仓决策引擎：直接 API 或通过 OpenClaw Agent")
        oc_row.addWidget(QLabel("自主仓引擎:"))
        oc_row.addWidget(self.engine_combo)
        oc_row.addStretch()
        layout.addLayout(oc_row)

        # 操作行
        action_row = QHBoxLayout()
        self.btn_full_auto = QPushButton("🚀 完全自主仓")
        self.btn_full_auto.setStyleSheet("font-size: 13px; padding: 8px 16px; background: #7b1fa2;")
        self.btn_full_auto.setToolTip("AI 全权决策+自动执行，无需人工确认")
        action_row.addWidget(self.btn_full_auto)
        self.btn_auto_run = QPushButton("🔄 半自主仓")
        self.btn_auto_run.setStyleSheet("font-size: 13px; padding: 8px 16px; background: #d32f2f;")
        self.btn_auto_run.setToolTip("AI 决策+执行，需人工触发（半自主仓）")
        action_row.addWidget(self.btn_auto_run)
        self.btn_run_ai = QPushButton("🤖 推荐仓建议")
        self.btn_run_ai.setStyleSheet("font-size: 13px; padding: 8px 16px; background: #FF6F00;")
        self.btn_run_ai.setToolTip("AI 给出建议，你确认后执行（推荐仓）")
        action_row.addWidget(self.btn_run_ai)
        self.btn_execute = QPushButton("▶ 确认执行")
        self.btn_execute.setStyleSheet("background: #388e3c; font-size: 13px; padding: 8px 16px;")
        self.btn_execute.setEnabled(False)
        action_row.addWidget(self.btn_execute)
        self.btn_custom_scan = QPushButton("📌 自定义仓(扫描Top3)")
        self.btn_custom_scan.setStyleSheet("font-size: 12px; padding: 8px 14px; background: #00695c;")
        self.btn_custom_scan.setToolTip("买入选股雷达扫描结果 Top3 到自定义仓")
        action_row.addWidget(self.btn_custom_scan)
        self.btn_custom_calibrate = QPushButton("📊 校准跟踪")
        self.btn_custom_calibrate.setStyleSheet("font-size: 12px; padding: 8px 14px;")
        self.btn_custom_calibrate.setToolTip("对比自定义仓买入后 5日/1月/1季/半年的实际表现")
        action_row.addWidget(self.btn_custom_calibrate)
        action_row.addStretch()
        layout.addLayout(action_row)

        # 板块多选区
        board_frame = QFrame()
        board_frame.setStyleSheet(
            "QFrame { background:#161b22; border:1px solid #30363d; border-radius:6px; padding:6px; }"
        )
        board_inner = QVBoxLayout(board_frame)
        board_inner.setContentsMargins(8, 4, 8, 4)
        board_inner.setSpacing(4)
        board_header = QHBoxLayout()
        board_header.addWidget(QLabel("📂 选择板块（多选）:"))
        self.btn_board_all = QPushButton("全选")
        self.btn_board_all.setStyleSheet("padding:2px 8px; font-size:11px;")
        self.btn_board_all.clicked.connect(lambda: self._toggle_boards(True))
        board_header.addWidget(self.btn_board_all)
        self.btn_board_none = QPushButton("全不选")
        self.btn_board_none.setStyleSheet("padding:2px 8px; font-size:11px;")
        self.btn_board_none.clicked.connect(lambda: self._toggle_boards(False))
        board_header.addWidget(self.btn_board_none)
        board_header.addStretch()
        board_inner.addLayout(board_header)

        board_grid = QHBoxLayout()
        board_grid.setSpacing(6)
        self._board_checkboxes = {}
        _BOARDS = [
            "人工智能", "芯片", "半导体", "量子科技", "机器人", "军工",
            "商业航天", "新能源汽车", "储能", "算力", "AI应用", "无人机",
            "光伏", "锂电池", "创新药", "医疗器械",
        ]
        for bn in _BOARDS:
            cb = QCheckBox(bn)
            cb.setStyleSheet("font-size:12px; padding:2px 4px;")
            if bn in ("人工智能", "芯片", "量子科技"):
                cb.setChecked(True)
            board_grid.addWidget(cb)
            self._board_checkboxes[bn] = cb
        board_inner.addLayout(board_grid)
        layout.addWidget(board_frame)

        # AI 分析结果
        self.analysis_label = QLabel("点击「AI 一键决策」让 AI 分析市场并给出买卖建议")
        self.analysis_label.setStyleSheet("color: #4fc3f7; font-size: 13px; padding: 8px;")
        self.analysis_label.setWordWrap(True)
        layout.addWidget(self.analysis_label)

        # Tabs
        tabs = QTabWidget()
        tabs.addTab(self._build_summary_tab(), "📊 持仓总览")
        tabs.addTab(self._build_decisions_tab(), "🤖 AI 决策")
        tabs.addTab(self._build_history_tab(), "📋 交易日志")
        tabs.addTab(self._build_tracking_tab(), "📌 自定义仓跟踪")
        layout.addWidget(tabs)

    _PROVIDER_CONFIG = {
        "DeepSeek": {
            "models": ["deepseek-chat", "deepseek-reasoner"],
            "base_url": "https://api.deepseek.com/v1",
            "key_hint": "sk-xxxxxxxx (platform.deepseek.com)",
        },
        "OpenAI": {
            "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1", "o1-mini", "o3-mini"],
            "base_url": "https://api.openai.com/v1",
            "key_hint": "sk-xxxxxxxx (platform.openai.com)",
        },
        "Google Gemini": {
            "models": ["gemini-2.0-flash", "gemini-2.0-pro", "gemini-1.5-pro", "gemini-1.5-flash"],
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "key_hint": "AIzaxxxxxxxx (aistudio.google.com)",
        },
        "Claude": {
            "models": ["claude-sonnet-4-20250514", "claude-3-5-sonnet-20241022", "claude-3-haiku-20240307"],
            "base_url": "https://api.anthropic.com/v1",
            "key_hint": "sk-ant-xxxxxxxx (console.anthropic.com)",
        },
        "通义千问": {
            "models": ["qwen-plus", "qwen-turbo", "qwen-max"],
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "key_hint": "sk-xxxxxxxx (bailian.console.aliyun.com)",
        },
        "月之暗面 Kimi": {
            "models": ["moonshot-v1-128k", "moonshot-v1-32k", "moonshot-v1-8k"],
            "base_url": "https://api.moonshot.cn/v1",
            "key_hint": "sk-xxxxxxxx (platform.moonshot.cn)",
        },
        "自定义": {
            "models": ["custom-model"],
            "base_url": "",
            "key_hint": "自定义 API Key",
        },
    }

    def _toggle_boards(self, checked: bool):
        for cb in self._board_checkboxes.values():
            cb.setChecked(checked)

    def get_selected_boards(self) -> list[str]:
        return [bn for bn, cb in self._board_checkboxes.items() if cb.isChecked()]

    def _on_provider_changed(self, provider: str):
        cfg = self._PROVIDER_CONFIG.get(provider, self._PROVIDER_CONFIG["自定义"])
        self.model_combo.clear()
        self.model_combo.addItems(cfg["models"])
        self.base_url_input.setText(cfg["base_url"])
        self.api_key_input.setPlaceholderText(cfg["key_hint"])

    def _build_summary_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        # 对比面板
        comp_box = QGroupBox("📊 双仓对比")
        cg = QGridLayout(comp_box)
        cg.addWidget(QLabel(""), 0, 0)
        for j, h in enumerate(["总资产", "收益率", "胜率", "交易数", "总盈亏"]):
            lbl = QLabel(h)
            lbl.setFont(QFont("", 10, QFont.Weight.Bold))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cg.addWidget(lbl, 0, j + 1)
        for i, mode_label in enumerate(["🟣 完全自主仓(AI全权)", "🔴 半自主仓(AI+触发)", "🟢 推荐仓(AI+人工)", "📌 自定义仓(Top3跟踪)"]):
            lbl = QLabel(mode_label)
            lbl.setFont(QFont("", 10, QFont.Weight.Bold))
            cg.addWidget(lbl, i + 1, 0)
        self.comp_labels = {}
        for i in range(4):
            for j in range(5):
                lbl = QLabel("-")
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl.setFont(QFont("", 11))
                cg.addWidget(lbl, i + 1, j + 1)
                self.comp_labels[(i, j)] = lbl
        layout.addWidget(comp_box)

        summary_box = QGroupBox("自主仓持仓")
        sg = QVBoxLayout(summary_box)

        self.pos_table = QTableWidget()
        self.pos_table.setColumnCount(9)
        self.pos_table.setHorizontalHeaderLabels([
            "代码", "名称", "买入价", "现价", "盈亏%", "股数", "市值", "买入日", "建议",
        ])
        self.pos_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.pos_table.setAlternatingRowColors(True)
        self.pos_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.pos_table)
        return w

    def _build_decisions_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.decisions_table = QTableWidget()
        self.decisions_table.setColumnCount(6)
        self.decisions_table.setHorizontalHeaderLabels([
            "操作", "代码", "名称", "价格", "股数", "理由",
        ])
        self.decisions_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.decisions_table.setAlternatingRowColors(True)
        layout.addWidget(self.decisions_table)

        self.execute_results = QTextEdit()
        self.execute_results.setReadOnly(True)
        self.execute_results.setMaximumHeight(150)
        self.execute_results.setPlaceholderText("执行结果将显示在这里...")
        layout.addWidget(self.execute_results)
        return w

    def _build_history_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.log_table = QTableWidget()
        self.log_table.setColumnCount(4)
        self.log_table.setHorizontalHeaderLabels(["时间", "操作", "代码", "详情"])
        self.log_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.log_table.setAlternatingRowColors(True)
        layout.addWidget(self.log_table)
        return w

    def update_summary(self, auto_state: dict, manual_state: dict, prices: dict, comp: dict):
        red = QColor("#ef5350")
        green = QColor("#26a69a")

        # 对比表
        for i, mode_key in enumerate(["full_auto", "auto", "manual", "custom"]):
            c = comp.get(mode_key, {})
            vals = [
                f"¥{c.get('equity', 0):,.0f}",
                f"{c.get('return_pct', 0):+.2f}%",
                f"{c.get('win_rate', 0):.1f}%",
                str(c.get("total_trades", 0)),
                f"¥{c.get('total_pnl', 0):+,.0f}",
            ]
            for j, v in enumerate(vals):
                lbl = self.comp_labels.get((i, j))
                if lbl:
                    lbl.setText(v)
                    if j in (1, 4):
                        try:
                            fv = float(v.replace("%", "").replace("¥", "").replace(",", "").replace("+", ""))
                            lbl.setStyleSheet(f"color: {'#ef5350' if fv > 0 else '#26a69a' if fv < 0 else '#888'};")
                        except Exception:
                            pass

        # 自主仓持仓表
        positions = auto_state.get("positions", [])
        self.pos_table.setRowCount(len(positions))
        for i, p in enumerate(positions):
            price = prices.get(p["code"], p["entry_price"])
            pnl_pct = (price - p["entry_price"]) / p["entry_price"] * 100
            mv = price * p["shares"]
            vals = [
                p["code"], p.get("name", ""), f"{p['entry_price']:.2f}",
                f"{price:.2f}", f"{pnl_pct:+.2f}%", str(p["shares"]),
                f"¥{mv:,.0f}", p.get("entry_date", ""), "",
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 4:
                    item.setForeground(red if pnl_pct > 0 else green if pnl_pct < 0 else QColor("#888"))
                self.pos_table.setItem(i, j, item)

    def update_decisions(self, decisions: list[dict]):
        self.decisions_table.setRowCount(len(decisions))
        colors = {"buy": QColor("#ef5350"), "sell": QColor("#26a69a"), "hold": QColor("#4fc3f7")}
        labels = {"buy": "买入", "sell": "卖出", "hold": "持有"}
        for i, d in enumerate(decisions):
            action = d.get("action", "")
            vals = [
                labels.get(action, action),
                d.get("code", ""),
                d.get("name", ""),
                str(d.get("price", "")),
                str(d.get("shares", "")),
                d.get("reason", ""),
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 0:
                    item.setForeground(colors.get(action, QColor("#888")))
                    item.setFont(QFont("", 11, QFont.Weight.Bold))
                self.decisions_table.setItem(i, j, item)
        self.btn_execute.setEnabled(bool(decisions))

    def update_log(self, auto_logs: list[dict], manual_logs: list[dict]):
        # 合并并按时间排序
        all_logs = []
        for log in auto_logs:
            log["_mode"] = "自主仓"
            all_logs.append(log)
        for log in manual_logs:
            log["_mode"] = "推荐仓"
            all_logs.append(log)
        all_logs.sort(key=lambda x: x.get("time", ""), reverse=True)

        self.log_table.setColumnCount(5)
        self.log_table.setHorizontalHeaderLabels(["时间", "仓位", "操作", "代码", "详情"])
        self.log_table.setRowCount(len(all_logs))
        for i, log in enumerate(all_logs):
            vals = [
                log.get("time", "")[:19],
                log.get("_mode", ""),
                log.get("action", ""),
                log.get("code", ""),
                log.get("detail", ""),
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 1:
                    item.setForeground(QColor("#d32f2f") if v == "自主仓" else QColor("#388e3c"))
                if j == 2:
                    color = QColor("#ef5350") if v == "BUY" else QColor("#26a69a") if v == "SELL" else QColor("#888")
                    item.setForeground(color)
                self.log_table.setItem(i, j, item)

    def _build_tracking_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(QLabel("📌 自定义仓：买入选股 Top3 后的多周期实际表现跟踪"))
        self.tracking_table = QTableWidget()
        self.tracking_table.setColumnCount(11)
        self.tracking_table.setHorizontalHeaderLabels([
            "代码", "名称", "板块", "买入日", "买入价", "评分",
            "5日盈亏%", "1月盈亏%", "1季盈亏%", "半年盈亏%", "校准日期",
        ])
        self.tracking_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tracking_table.setAlternatingRowColors(True)
        self.tracking_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tracking_table.setSortingEnabled(True)
        layout.addWidget(self.tracking_table)

        self.tracking_summary = QLabel("")
        self.tracking_summary.setStyleSheet("color:#4fc3f7; font-size:12px; padding:4px;")
        self.tracking_summary.setWordWrap(True)
        layout.addWidget(self.tracking_summary)
        return w

    def update_tracking(self, records: list[dict]):
        red = QColor("#ef5350")
        green = QColor("#26a69a")
        self.tracking_table.setRowCount(len(records))
        total_5d, total_20d, total_60d, total_120d = [], [], [], []

        for i, r in enumerate(records):
            vals = [
                r.get("code", ""), r.get("name", ""), r.get("board", ""),
                r.get("buy_date", ""), f"{r.get('buy_price', 0):.2f}",
                str(r.get("score", "")),
            ]
            for period_key, label in [("pnl_5d", "5d"), ("pnl_20d", "20d"), ("pnl_60d", "60d"), ("pnl_120d", "120d")]:
                v = r.get(period_key)
                if v is not None:
                    vals.append(f"{v:+.2f}%")
                    {"pnl_5d": total_5d, "pnl_20d": total_20d, "pnl_60d": total_60d, "pnl_120d": total_120d}[period_key].append(v)
                else:
                    vals.append("-")
            vals.append(r.get("calibrated", "") or "-")

            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if 6 <= j <= 9 and v != "-":
                    try:
                        fv = float(v.replace("%", "").replace("+", ""))
                        item.setForeground(red if fv > 0 else green if fv < 0 else QColor("#888"))
                        item.setFont(QFont("", 10, QFont.Weight.Bold))
                    except Exception:
                        pass
                self.tracking_table.setItem(i, j, item)

        parts = []
        for name, arr in [("5日", total_5d), ("1月", total_20d), ("1季", total_60d), ("半年", total_120d)]:
            if arr:
                avg = sum(arr) / len(arr)
                win = sum(1 for x in arr if x > 0)
                parts.append(f"{name}: 均值{avg:+.1f}% 胜率{win}/{len(arr)}")
        self.tracking_summary.setText(
            f"📊 跟踪汇总（{len(records)}只）: " + " | ".join(parts) if parts else "暂无校准数据"
        )
