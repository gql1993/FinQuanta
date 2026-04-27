"""AI 自主交易模拟仓面板"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QGridLayout, QLineEdit, QComboBox, QTextEdit, QTabWidget,
    QCheckBox, QFrame, QScrollArea,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

_AI_PORTFOLIO_THEME = {
    "dark": {
        "board_bg": "#161b22",
        "board_border": "#30363d",
        "text": "#e0e0e0",
        "muted": "#8b949e",
        "button_bg": "#16213e",
        "button_border": "#33384d",
        "button_hover": "#1a2744",
        "accent": "#4fc3f7",
    },
    "light": {
        "board_bg": "#ffffff",
        "board_border": "#dddddd",
        "text": "#333333",
        "muted": "#666666",
        "button_bg": "#f5f7fb",
        "button_border": "#d6dbe6",
        "button_hover": "#e9eef7",
        "accent": "#1976d2",
    },
}


class AIPortfolioPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme = "dark"
        layout = QVBoxLayout(self)

        title = QLabel("🤖 AI 自主交易模拟仓")
        title.setFont(QFont("", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        # AI 配置状态（只读展示，修改请到设置页）
        self.ai_config_label = QLabel("AI 配置：加载中...")
        self.ai_config_label.setStyleSheet("color:#8b949e; font-size:12px; padding:2px 0;")
        layout.addWidget(self.ai_config_label)

        # 兼容旧引用（隐藏的虚拟控件）
        self.provider_combo = QComboBox(); self.provider_combo.setVisible(False)
        self.model_combo = QComboBox(); self.model_combo.setVisible(False)
        self.api_key_input = QLineEdit(); self.api_key_input.setVisible(False)
        self.base_url_input = QLineEdit(); self.base_url_input.setVisible(False)
        self.btn_save_config = QPushButton(); self.btn_save_config.setVisible(False)
        self.engine_combo = QComboBox(); self.engine_combo.setVisible(False)

        # 操作行（4仓：完全自主 / AI推荐 / 自定义 / 量子）
        action_row1 = QHBoxLayout()
        self.btn_full_auto = QPushButton("🟣 完全自主仓")
        self.btn_full_auto.setStyleSheet("font-size: 13px; padding: 8px 20px; background: #7b1fa2;")
        self.btn_full_auto.setToolTip("AI 全权决策+自动执行，无需人工确认")
        action_row1.addWidget(self.btn_full_auto)
        self.btn_auto_run = QPushButton("🔵 AI推荐仓")
        self.btn_auto_run.setStyleSheet("font-size: 13px; padding: 8px 20px; background: #1565C0;")
        self.btn_auto_run.setToolTip("AI 分析市场并推荐买卖，人工确认后执行")
        action_row1.addWidget(self.btn_auto_run)
        self.btn_custom_scan = QPushButton("📌 自定义仓(Top3)")
        self.btn_custom_scan.setStyleSheet("font-size: 13px; padding: 8px 20px; background: #00695c;")
        self.btn_custom_scan.setToolTip("买入选股雷达 Top3 到自定义仓")
        action_row1.addWidget(self.btn_custom_scan)
        self.btn_quantum_buy = QPushButton("⚛️ 量子仓买入")
        self.btn_quantum_buy.setStyleSheet("font-size: 13px; padding: 8px 20px; background:#4a148c;")
        self.btn_quantum_buy.setToolTip("量子优化选出的最优组合")
        action_row1.addWidget(self.btn_quantum_buy)
        action_row1.addStretch()
        layout.addLayout(action_row1)

        # 辅助操作行
        action_row2 = QHBoxLayout()
        self.btn_custom_calibrate = QPushButton("📊 校准跟踪")
        self.btn_custom_calibrate.setStyleSheet("font-size: 11px; padding: 6px 12px;")
        action_row2.addWidget(self.btn_custom_calibrate)
        action_row2.addStretch()
        layout.addLayout(action_row2)

        # 兼容旧引用
        self.btn_run_ai = QPushButton(); self.btn_run_ai.setVisible(False)
        self.btn_execute = QPushButton(); self.btn_execute.setVisible(False)

        # 板块多选区
        board_frame = QFrame()
        self._board_frame = board_frame
        board_inner = QVBoxLayout(board_frame)
        board_inner.setContentsMargins(8, 4, 8, 4)
        board_inner.setSpacing(4)
        board_header = QHBoxLayout()
        board_title = QLabel("📂 选择板块（多选）:")
        self._board_title = board_title
        board_header.addWidget(board_title)
        self.btn_board_all = QPushButton("全选")
        self.btn_board_all.clicked.connect(lambda: self._toggle_boards(True))
        board_header.addWidget(self.btn_board_all)
        self.btn_board_none = QPushButton("全不选")
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
        self._apply_theme_styles()

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

    def set_theme(self, theme: str):
        self._theme = "light" if str(theme).lower() == "light" else "dark"
        self._apply_theme_styles()

    def _apply_theme_styles(self):
        palette = _AI_PORTFOLIO_THEME.get(self._theme, _AI_PORTFOLIO_THEME["dark"])
        self._board_frame.setStyleSheet(
            "QFrame { background:%s; border:1px solid %s; border-radius:6px; padding:6px; }"
            % (palette["board_bg"], palette["board_border"])
        )
        self._board_title.setStyleSheet(
            "color:%s; font-size:12px; font-weight:bold;" % palette["text"]
        )
        btn_style = (
            "QPushButton { background:%s; color:%s; border:1px solid %s; border-radius:8px; padding:2px 8px; font-size:11px; }"
            "QPushButton:hover { background:%s; color:%s; }"
        ) % (
            palette["button_bg"],
            palette["text"],
            palette["button_border"],
            palette["button_hover"],
            palette["accent"],
        )
        self.btn_board_all.setStyleSheet(btn_style)
        self.btn_board_none.setStyleSheet(btn_style)
        checkbox_style = (
            "QCheckBox { color:%s; font-size:12px; padding:2px 4px; }"
            "QCheckBox::indicator { width:14px; height:14px; }"
        ) % palette["text"]
        for cb in self._board_checkboxes.values():
            cb.setStyleSheet(checkbox_style)

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
        for j, h in enumerate(["总资产", "收益率", "已平仓胜率", "浮盈占比", "交易数", "总盈亏"]):
            lbl = QLabel(h)
            lbl.setFont(QFont("", 10, QFont.Weight.Bold))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cg.addWidget(lbl, 0, j + 1)
        for i, mode_label in enumerate(["🟣 完全自主仓(AI全权)", "🔵 AI推荐仓(AI+确认)", "📌 自定义仓(Top3)", "⚛️ 量子仓(QAOA/QA)"]):
            lbl = QLabel(mode_label)
            lbl.setFont(QFont("", 10, QFont.Weight.Bold))
            cg.addWidget(lbl, i + 1, 0)
        self.comp_labels = {}
        for i in range(4):
            for j in range(6):
                lbl = QLabel("-")
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl.setFont(QFont("", 11))
                cg.addWidget(lbl, i + 1, j + 1)
                self.comp_labels[(i, j)] = lbl
        layout.addWidget(comp_box)

        summary_box = QGroupBox("全仓持仓汇总")
        sg = QVBoxLayout(summary_box)

        self.pos_table = QTableWidget()
        self.pos_table.setColumnCount(10)
        self.pos_table.setHorizontalHeaderLabels([
            "仓位类型", "代码", "名称", "买入价", "现价", "盈亏%", "股数", "市值", "买入日", "建议",
        ])
        self.pos_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.pos_table.setAlternatingRowColors(True)
        self.pos_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.pos_table.setSortingEnabled(True)
        sg.addWidget(self.pos_table)

        # 单击操作栏
        self.action_bar = QWidget()
        self.action_bar.setVisible(False)
        ab = QHBoxLayout(self.action_bar)
        ab.setContentsMargins(0, 4, 0, 4)
        self.action_stock_label = QLabel("")
        self.action_stock_label.setFont(QFont("", 11, QFont.Weight.Bold))
        self.action_stock_label.setStyleSheet("color:#4fc3f7;")
        ab.addWidget(self.action_stock_label)

        self.btn_action_detail = QPushButton("📋 明细")
        self.btn_action_detail.setStyleSheet("padding:6px 14px;")
        ab.addWidget(self.btn_action_detail)

        self.btn_action_buy = QPushButton("🛒 买入")
        self.btn_action_buy.setStyleSheet("padding:6px 14px; background:#2E7D32;")
        ab.addWidget(self.btn_action_buy)

        self.btn_action_sell = QPushButton("📤 卖出")
        self.btn_action_sell.setStyleSheet("padding:6px 14px; background:#C62828;")
        ab.addWidget(self.btn_action_sell)

        self.btn_action_condition = QPushButton("⏰ 条件单")
        self.btn_action_condition.setStyleSheet("padding:6px 14px;")
        ab.addWidget(self.btn_action_condition)

        self.btn_action_chart = QPushButton("📈 看行情")
        self.btn_action_chart.setStyleSheet("padding:6px 14px; background:#1565C0;")
        ab.addWidget(self.btn_action_chart)

        self.btn_action_ai_suggest = QPushButton("🦀 AI研判")
        self.btn_action_ai_suggest.setStyleSheet("padding:6px 14px; background:#E65100; color:white;")
        ab.addWidget(self.btn_action_ai_suggest)

        ab.addStretch()

        self.ai_suggest_label = QLabel("")
        self.ai_suggest_label.setStyleSheet("color:#4fc3f7; font-size:12px; padding:4px;")
        self.ai_suggest_label.setWordWrap(True)
        self.ai_suggest_label.setVisible(False)

        sg.addWidget(self.action_bar)
        sg.addWidget(self.ai_suggest_label)

        layout.addWidget(summary_box)
        return w

    def _build_decisions_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.decision_guard_label = QLabel("验证守门：待生成")
        self.decision_guard_label.setStyleSheet("color:#8b949e; font-size:12px; padding:4px 0;")
        self.decision_guard_label.setWordWrap(True)
        layout.addWidget(self.decision_guard_label)
        self.decisions_table = QTableWidget()
        self.decisions_table.setColumnCount(8)
        self.decisions_table.setHorizontalHeaderLabels([
            "操作", "代码", "名称", "价格", "股数", "验证", "验证分", "理由",
        ])
        self.decisions_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.decisions_table.setAlternatingRowColors(True)
        layout.addWidget(self.decisions_table)

        self.execute_results = QTextEdit()
        self.execute_results.setReadOnly(True)
        self.execute_results.setMaximumHeight(150)
        self.execute_results.setPlaceholderText("执行结果将显示在这里...")
        layout.addWidget(self.execute_results)

        self.decision_compare_text = QTextEdit()
        self.decision_compare_text.setReadOnly(True)
        self.decision_compare_text.setMaximumHeight(120)
        self.decision_compare_text.setPlaceholderText("最近一次自主仓决策：原始决策 vs 守门后决策 对照。")
        layout.addWidget(self.decision_compare_text)
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

    # 仓位类型配色
    _MODE_COLORS = {
        "full_auto": ("#CE93D8", "🟣 完全自主"),
        "auto":      ("#4FC3F7", "🔵 AI推荐"),
        "custom":    ("#FF7043", "📌 自定义"),
        "quantum":   ("#66BB6A", "⚛️ 量子仓"),
    }

    def update_summary(self, all_states: dict, prices: dict, comp: dict):
        """4仓对比: full_auto / auto / custom / quantum"""
        red = QColor("#ef5350")
        green = QColor("#26a69a")

        # 合并原 auto + manual 的数据到 auto
        if "manual" in comp:
            # 把 manual 的交易数和盈亏合并到 auto
            auto_c = comp.get("auto", {})
            manual_c = comp.get("manual", {})
            if manual_c.get("total_trades", 0) > 0 and auto_c:
                auto_c["total_trades"] = auto_c.get("total_trades", 0) + manual_c.get("total_trades", 0)
                auto_c["total_pnl"] = auto_c.get("total_pnl", 0) + manual_c.get("total_pnl", 0)

        # 对比表（4仓）
        for i, mode_key in enumerate(["full_auto", "auto", "custom", "quantum"]):
            c = comp.get(mode_key, {})
            vals = [
                f"¥{c.get('equity', 0):,.0f}",
                f"{c.get('return_pct', 0):+.2f}%",
                f"{c.get('win_rate', 0):.1f}%",
                f"{c.get('open_win_rate', 0):.1f}%",
                str(c.get("total_trades", 0)),
                f"¥{c.get('total_pnl', 0):+,.0f}",
            ]
            for j, v in enumerate(vals):
                lbl = self.comp_labels.get((i, j))
                if lbl:
                    lbl.setText(v)
                    if j in (1, 5):
                        try:
                            fv = float(v.replace("%", "").replace("¥", "").replace(",", "").replace("+", ""))
                            lbl.setStyleSheet(f"color: {'#ef5350' if fv > 0 else '#26a69a' if fv < 0 else '#888'};")
                        except Exception:
                            pass

        # 合并全部仓位到一张表（4仓，manual归入auto显示）
        merged = []
        for mode_key in ["full_auto", "auto", "manual", "custom", "quantum"]:
            # manual 的持仓显示为 auto（AI推荐仓）
            display_key = "auto" if mode_key == "manual" else mode_key
            state = all_states.get(mode_key, {})
            for p in state.get("positions", []):
                merged.append((display_key, p))

        self.pos_table.setSortingEnabled(False)
        self.pos_table.setRowCount(len(merged))
        for i, (mode_key, p) in enumerate(merged):
            color_hex, label = self._MODE_COLORS.get(mode_key, ("#888", mode_key))
            entry_price = p.get("entry_price", 0) or 0
            price = prices.get(p.get("code", ""), entry_price)
            pnl_pct = (price - entry_price) / entry_price * 100 if entry_price > 0 else 0
            mv = price * p.get("shares", 0)

            # 仓位类型列
            type_item = QTableWidgetItem(label)
            type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            type_item.setForeground(QColor(color_hex))
            type_item.setFont(QFont("", 10, QFont.Weight.Bold))
            self.pos_table.setItem(i, 0, type_item)

            vals = [
                p.get("code", ""), p.get("name", ""),
                f"{entry_price:.2f}" if entry_price else "-",
                f"{price:.2f}" if price else "-",
                f"{pnl_pct:+.2f}%",
                str(p.get("shares", 0)),
                f"¥{mv:,.0f}",
                p.get("entry_date", ""),
                p.get("suggestion", ""),
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 4:
                    item.setForeground(red if pnl_pct > 0 else green if pnl_pct < 0 else QColor("#888"))
                self.pos_table.setItem(i, j + 1, item)
        self.pos_table.setSortingEnabled(True)

    def update_decisions(
        self,
        decisions: list[dict],
        verification_summary: dict | None = None,
        guardrail_summary: dict | None = None,
    ):
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
                str(d.get("verification", "-")),
                str(d.get("verification_score", "-")),
                d.get("reason", ""),
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 0:
                    item.setForeground(colors.get(action, QColor("#888")))
                    item.setFont(QFont("", 11, QFont.Weight.Bold))
                if j == 5:
                    text = str(v)
                    if text == "verified":
                        item.setForeground(QColor("#66BB6A"))
                    elif text == "questionable":
                        item.setForeground(QColor("#FFB300"))
                    elif text == "rejected":
                        item.setForeground(QColor("#EF5350"))
                self.decisions_table.setItem(i, j, item)
        self.btn_execute.setEnabled(bool(decisions))

        self.update_decision_guard_summary(verification_summary, guardrail_summary)

    def update_decision_guard_summary(
        self,
        verification_summary: dict | None = None,
        guardrail_summary: dict | None = None,
    ):
        verification_summary = verification_summary or {}
        guardrail_summary = guardrail_summary or {}
        if verification_summary or guardrail_summary:
            self.decision_guard_label.setText(
                "验证守门："
                f"通过 {verification_summary.get('verified_count', 0)} | "
                f"存疑 {verification_summary.get('questionable_count', 0)} | "
                f"高风险 {verification_summary.get('rejected_count', 0)} | "
                f"拦截买入 {guardrail_summary.get('blocked_buy_count', 0)} | "
                f"存疑放行 {guardrail_summary.get('annotated_buy_count', 0)}"
            )
        else:
            self.decision_guard_label.setText("验证守门：当前这批决策未经过验证层或暂无摘要")

    def update_decision_comparison(
        self,
        raw_decisions: list[dict] | None = None,
        filtered_decisions: list[dict] | None = None,
        guardrail_summary: dict | None = None,
    ):
        raw_decisions = raw_decisions or []
        filtered_decisions = filtered_decisions or []
        guardrail_summary = guardrail_summary or {}

        def _fmt(items: list[dict]) -> str:
            if not items:
                return "无"
            labels = []
            for item in items[:6]:
                action = str(item.get("action", "") or "")
                code = str(item.get("code", "") or "")
                labels.append(f"{action.upper()} {code}".strip())
            extra = f" 等{len(items)}条" if len(items) > 6 else ""
            return " / ".join(labels) + extra

        blocked = int(guardrail_summary.get("blocked_buy_count", 0) or 0)
        annotated = int(guardrail_summary.get("annotated_buy_count", 0) or 0)
        lines = [
            f"原始决策: {_fmt(raw_decisions)}",
            f"守门后决策: {_fmt(filtered_decisions)}",
            f"守门摘要: 拦截买入 {blocked} 条，存疑放行 {annotated} 条",
        ]
        self.decision_compare_text.setText("\n".join(lines))

    def update_log(self, auto_logs: list[dict], manual_logs: list[dict]):
        # 合并并按时间排序
        all_logs = []
        for log in auto_logs:
            log["_mode"] = "自主仓"
            all_logs.append(log)
        for log in manual_logs:
            log["_mode"] = "AI推荐仓"
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
