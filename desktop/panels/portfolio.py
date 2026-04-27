"""模拟仓面板（同花顺风格）"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QLineEdit, QDoubleSpinBox, QSpinBox, QTabWidget, QGridLayout,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor
from desktop.ui_tokens import APP_FONT


class PortfolioPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        title = QLabel("💼 模拟仓管理")
        title.setFont(QFont("", APP_FONT["page_title"], QFont.Weight.Bold))
        layout.addWidget(title)

        summary_box = QGroupBox("账户总览")
        sg = QGridLayout(summary_box)
        self.summary_labels = {}
        items = [
            ("总资产", 0, 0), ("总收益", 0, 1), ("总市值", 0, 2), ("总成本", 0, 3),
            ("可用现金", 1, 0), ("浮动盈亏", 1, 1), ("当日盈亏", 1, 2), ("仓位比例", 1, 3),
        ]
        for name, r, c in items:
            lbl = QLabel(f"{name}: -")
            lbl.setFont(QFont("", APP_FONT["body"]))
            sg.addWidget(lbl, r, c)
            self.summary_labels[name] = lbl
        layout.addWidget(summary_box)

        self.inner_tabs = QTabWidget()
        self.inner_tabs.addTab(self._build_positions_tab(), "📊 持仓")
        self.inner_tabs.addTab(self._build_buy_tab(), "🛒 买入")
        self.inner_tabs.addTab(self._build_sell_tab(), "📤 卖出")
        self.inner_tabs.addTab(self._build_history_tab(), "📋 交易记录")
        layout.addWidget(self.inner_tabs)

    def _build_positions_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        top = QHBoxLayout()
        self.btn_refresh = QPushButton("🔄 刷新行情")
        top.addWidget(self.btn_refresh)
        self.freshness_label = QLabel("数据新鲜度: -")
        self.freshness_label.setStyleSheet("color: #888;")
        top.addWidget(self.freshness_label)
        top.addStretch()
        layout.addLayout(top)

        self.pos_table = QTableWidget()
        self.pos_table.setColumnCount(15)
        self.pos_table.setHorizontalHeaderLabels([
            "代码", "名称", "买入价", "现价", "昨收", "股数",
            "市值", "浮动盈亏", "盈亏%", "当日盈亏", "当日%", "买入日", "持有天数", "建议", "阶段",
        ])
        self.pos_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.pos_table.setAlternatingRowColors(True)
        self.pos_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.pos_table)

        # 单击操作栏（仿同花顺：明细/买入/卖出/条件单/看行情）
        self.action_bar = QWidget()
        self.action_bar.setVisible(False)
        ab = QHBoxLayout(self.action_bar)
        ab.setContentsMargins(0, 4, 0, 4)
        self.action_stock_label = QLabel("")
        self.action_stock_label.setFont(QFont("", APP_FONT["caption"], QFont.Weight.Bold))
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
        self.btn_action_ai_suggest.setToolTip("OpenClaw 分析该股票，给出买入/持有/卖出建议")
        ab.addWidget(self.btn_action_ai_suggest)

        ab.addStretch()

        # AI 建议结果展示
        self.ai_suggest_label = QLabel("")
        self.ai_suggest_label.setStyleSheet(
            f"color:#4fc3f7; font-size:{APP_FONT['body']}px; padding:4px;"
        )
        self.ai_suggest_label.setWordWrap(True)
        self.ai_suggest_label.setVisible(False)

        layout.addWidget(self.action_bar)
        layout.addWidget(self.ai_suggest_label)
        return w

    def _build_buy_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        form = QGridLayout()

        form.addWidget(QLabel("股票代码:"), 0, 0)
        self.buy_code = QLineEdit()
        self.buy_code.setPlaceholderText("例如: 603881")
        form.addWidget(self.buy_code, 0, 1)

        form.addWidget(QLabel("买入价格:"), 1, 0)
        self.buy_price = QDoubleSpinBox()
        self.buy_price.setRange(0.01, 9999)
        self.buy_price.setValue(10.0)
        self.buy_price.setDecimals(2)
        form.addWidget(self.buy_price, 1, 1)

        form.addWidget(QLabel("买入股数:"), 2, 0)
        self.buy_shares = QSpinBox()
        self.buy_shares.setRange(100, 100000)
        self.buy_shares.setValue(1000)
        self.buy_shares.setSingleStep(100)
        form.addWidget(self.buy_shares, 2, 1)

        form.addWidget(QLabel("止损比例(%):"), 3, 0)
        self.buy_stop = QDoubleSpinBox()
        self.buy_stop.setRange(3, 20)
        self.buy_stop.setValue(8.0)
        self.buy_stop.setDecimals(1)
        form.addWidget(self.buy_stop, 3, 1)

        self.btn_buy = QPushButton("买入")
        self.btn_buy.setStyleSheet(
            f"background: #388e3c; font-size: {APP_FONT['section']}px; padding: 10px;"
        )
        form.addWidget(self.btn_buy, 4, 0, 1, 2)
        self.buy_status = QLabel("")
        form.addWidget(self.buy_status, 5, 0, 1, 2)

        layout.addLayout(form)
        layout.addStretch()
        return w

    def _build_sell_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        form = QGridLayout()

        form.addWidget(QLabel("股票代码:"), 0, 0)
        self.sell_code = QLineEdit()
        self.sell_code.setPlaceholderText("例如: 603881")
        form.addWidget(self.sell_code, 0, 1)

        form.addWidget(QLabel("卖出价格:"), 1, 0)
        self.sell_price = QDoubleSpinBox()
        self.sell_price.setRange(0.01, 9999)
        self.sell_price.setDecimals(2)
        form.addWidget(self.sell_price, 1, 1)

        form.addWidget(QLabel("卖出股数(0=全部):"), 2, 0)
        self.sell_shares = QSpinBox()
        self.sell_shares.setRange(0, 100000)
        self.sell_shares.setValue(0)
        self.sell_shares.setSingleStep(100)
        form.addWidget(self.sell_shares, 2, 1)

        self.btn_sell = QPushButton("卖出")
        self.btn_sell.setStyleSheet(
            f"background: #d32f2f; font-size: {APP_FONT['section']}px; padding: 10px;"
        )
        form.addWidget(self.btn_sell, 3, 0, 1, 2)
        self.sell_status = QLabel("")
        form.addWidget(self.sell_status, 4, 0, 1, 2)

        layout.addLayout(form)
        layout.addStretch()
        return w

    def _build_history_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(9)
        self.history_table.setHorizontalHeaderLabels([
            "代码", "买入日", "买入价", "卖出日", "卖出价",
            "股数", "盈亏", "盈亏%", "原因",
        ])
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.history_table)
        return w

    def update_summary(self, s: dict):
        self.summary_labels["总资产"].setText(f"总资产: ¥{s.get('total_equity', 0):,.2f}")
        self.summary_labels["总收益"].setText(f"总收益: {s.get('total_return', 0):+.2f}%")
        self.summary_labels["总市值"].setText(f"总市值: ¥{s.get('position_value', 0):,.2f}")
        self.summary_labels["总成本"].setText(f"总成本: ¥{s.get('total_cost', 0):,.2f}")
        self.summary_labels["可用现金"].setText(f"可用现金: ¥{s.get('cash', 0):,.2f}")
        pnl = s.get("unrealized_pnl", 0)
        self.summary_labels["浮动盈亏"].setText(f"浮动盈亏: ¥{pnl:+,.2f}")
        today = s.get("today_pnl", 0)
        self.summary_labels["当日盈亏"].setText(f"当日盈亏: ¥{today:+,.2f}")
        self.summary_labels["仓位比例"].setText(f"仓位比例: {s.get('position_ratio', 0):.1f}%")

    def update_positions(self, positions: list[dict]):
        self.pos_table.setRowCount(len(positions))
        from datetime import date as _date
        today = _date.today()
        for i, p in enumerate(positions):
            cols = ["代码", "名称", "买入价", "现价", "昨收", "股数",
                    "市值", "浮动盈亏", "盈亏%", "当日盈亏", "当日%"]
            for j, col in enumerate(cols):
                val = p.get(col, "")
                if isinstance(val, float):
                    val = f"{val:.2f}" if abs(val) < 10000 else f"{val:,.0f}"
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.pos_table.setItem(i, j, item)
            # 买入日
            entry_date = p.get("买入日", p.get("entry_date", "-"))
            item = QTableWidgetItem(str(entry_date))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.pos_table.setItem(i, 11, item)
            # 持有天数
            hold_days_n = 0
            try:
                ed = _date.fromisoformat(str(entry_date)[:10])
                hold_days_n = (today - ed).days
            except Exception:
                pass
            item = QTableWidgetItem(str(hold_days_n))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.pos_table.setItem(i, 12, item)

            # 建议（基于盈亏%、持有天数、当日%综合判定）
            pnl_pct = 0.0
            day_pct = 0.0
            try:
                raw = p.get("盈亏%", 0)
                pnl_pct = float(str(raw).replace("%", "").replace("+", "").replace(",", "")) if raw else 0
            except Exception:
                pass
            try:
                raw = p.get("当日%", 0)
                day_pct = float(str(raw).replace("%", "").replace("+", "").replace(",", "")) if raw else 0
            except Exception:
                pass

            # 智能建议（规则 + OpenClaw 学习反馈）
            advice = "持有"
            advice_color = QColor("#888888")

            # 基础规则
            if pnl_pct <= -8:
                advice = "⛔ 止损卖出"
                advice_color = QColor("#ef5350")
            elif pnl_pct <= -5:
                advice = "⚠ 关注止损"
                advice_color = QColor("#FF9800")
            elif pnl_pct >= 25 and day_pct <= -3:
                advice = "🔔 止盈卖出"
                advice_color = QColor("#FF9800")
            elif pnl_pct >= 20:
                advice = "📈 部分止盈"
                advice_color = QColor("#4CAF50")
            elif hold_days_n >= 25 and pnl_pct < 2:
                advice = "⏰ 时间止损"
                advice_color = QColor("#FF9800")
            elif pnl_pct >= 15:
                advice = "🛡 持有上调止损"
                advice_color = QColor("#4CAF50")
            elif pnl_pct >= 5:
                advice = "✅ 持有保本"
                advice_color = QColor("#4CAF50")
            elif day_pct <= -7:
                advice = "🚨 异常大跌"
                advice_color = QColor("#ef5350")
            elif day_pct <= -4:
                advice = "⚠ 警惕异动"
                advice_color = QColor("#FF9800")
            elif day_pct >= 7:
                advice = "🔥 大涨关注止盈"
                advice_color = QColor("#4CAF50")
            elif pnl_pct > 0:
                advice = "💎 继续持有"
                advice_color = QColor("#4fc3f7")
            else:
                advice = "📊 观察中"
                advice_color = QColor("#888")

            item = QTableWidgetItem(advice)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setForeground(advice_color)
            self.pos_table.setItem(i, 13, item)

            # 阶段
            item = QTableWidgetItem(p.get("阶段", "-"))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.pos_table.setItem(i, 14, item)

    def update_history(self, history: list[dict]):
        """更新交易记录表。"""
        red = QColor("#ef5350")
        green = QColor("#26a69a")
        self.history_table.setRowCount(len(history))
        for i, h in enumerate(history):
            action = h.get("action", "")
            pnl = h.get("pnl", 0)
            price = h.get("price", 0)
            shares = h.get("shares", 0)

            if action == "BUY":
                vals = [
                    h.get("code", ""),
                    h.get("time", "")[:10],
                    f"{price:.2f}",
                    "", "", str(shares), "", "", "",
                ]
            elif action == "SELL":
                entry_price = h.get("entry_price", 0)
                pnl_pct = (price - entry_price) / entry_price * 100 if entry_price > 0 else 0
                vals = [
                    h.get("code", ""),
                    h.get("entry_date", ""),
                    f"{entry_price:.2f}" if entry_price else "",
                    h.get("time", "")[:10],
                    f"{price:.2f}",
                    str(shares),
                    f"{pnl:+,.2f}" if pnl else "",
                    f"{pnl_pct:+.2f}%" if entry_price else "",
                    h.get("reason", ""),
                ]
            else:
                vals = [
                    h.get("code", ""), h.get("time", "")[:10],
                    f"{price:.2f}" if price else "",
                    "", "", str(shares), "", "", action,
                ]

            for j, v in enumerate(vals):
                item = QTableWidgetItem(str(v))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 0:
                    color = green if action == "BUY" else red if action == "SELL" else QColor("#888")
                    item.setForeground(color)
                if j == 6 and v:
                    try:
                        fv = float(v.replace(",", "").replace("+", ""))
                        item.setForeground(red if fv > 0 else green if fv < 0 else QColor("#888"))
                    except Exception:
                        pass
                self.history_table.setItem(i, j, item)
