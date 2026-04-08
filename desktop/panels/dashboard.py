"""主面板：市场总览 + 持仓摘要 + 风险仪表盘"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
    QGridLayout, QTableWidget, QTableWidgetItem, QHeaderView,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class MetricCard(QWidget):
    def __init__(self, title: str, value: str = "-", delta: str = "", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("color: #888; font-size: 12px;")
        self.value_label = QLabel(value)
        self.value_label.setFont(QFont("", 18, QFont.Weight.Bold))
        self.delta_label = QLabel(delta)
        self.delta_label.setStyleSheet("font-size: 11px;")
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        if delta:
            layout.addWidget(self.delta_label)

    def set_value(self, value: str, delta: str = "", positive: bool = True):
        self.value_label.setText(value)
        color = "#ef5350" if positive else "#26a69a"
        self.value_label.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {color};")
        self.delta_label.setText(delta)
        self.delta_label.setStyleSheet(f"font-size: 11px; color: {color};")


class DashboardPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        title = QLabel("📈 市场总览与持仓摘要")
        title.setFont(QFont("", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        # 六仓合计摘要卡片（一行）
        metrics_layout = QHBoxLayout()
        self.card_equity = MetricCard("总资产(6仓)")
        self.card_pnl = MetricCard("浮动盈亏(6仓)")
        self.card_today = MetricCard("当日盈亏")
        self.card_positions = MetricCard("总持仓数")
        self.card_cash = MetricCard("总可用现金")
        self.card_drawdown = MetricCard("当前回撤")
        for card in [self.card_equity, self.card_pnl, self.card_today,
                     self.card_positions, self.card_cash, self.card_drawdown]:
            metrics_layout.addWidget(card)
        layout.addLayout(metrics_layout)

        market_group = QGroupBox("市场环境")
        mg_layout = QHBoxLayout(market_group)
        self.market_label = QLabel("加载中...")
        self.market_label.setFont(QFont("", 13))
        mg_layout.addWidget(self.market_label)
        layout.addWidget(market_group)

        risk_group = QGroupBox("组合风险速览")
        rg_layout = QGridLayout(risk_group)
        rg_layout.setSpacing(12)
        self.risk_labels = {}
        risk_items = [
            ("VaR(95%)", "📉 VaR(95%)", "在95%置信水平下，日最大潜在亏损", "#4fc3f7"),
            ("VaR(99%)", "📉 VaR(99%)", "在99%置信水平下，日最大潜在亏损", "#ce93d8"),
            ("最大单股敞口", "🎯 最大单股敞口", "单只股票占组合比例最高", "#ffb74d"),
            ("集中度HHI", "📊 集中度(HHI)", "越接近1越集中，0.25以下为分散", "#81c784"),
        ]
        for i, (key, title, tip, color) in enumerate(risk_items):
            card = QWidget()
            card.setStyleSheet(
                f"background: rgba({int(color[1:3],16)},{int(color[3:5],16)},{int(color[5:7],16)},0.05);"
                f"border: 1px solid rgba({int(color[1:3],16)},{int(color[3:5],16)},{int(color[5:7],16)},0.15);"
                f"border-radius: 6px; padding: 6px;"
            )
            cl = QVBoxLayout(card)
            cl.setContentsMargins(8, 4, 8, 4)
            cl.setSpacing(2)
            title_lbl = QLabel(title)
            title_lbl.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: bold; border: none;")
            cl.addWidget(title_lbl)
            val_lbl = QLabel("-")
            val_lbl.setFont(QFont("", 15, QFont.Weight.Bold))
            val_lbl.setStyleSheet("color: #e0e0e0; border: none;")
            cl.addWidget(val_lbl)
            tip_lbl = QLabel(tip)
            tip_lbl.setStyleSheet("color: #555; font-size: 10px; border: none;")
            tip_lbl.setWordWrap(True)
            cl.addWidget(tip_lbl)
            rg_layout.addWidget(card, 0, i)
            self.risk_labels[key] = val_lbl
        layout.addWidget(risk_group)

        # 六仓摘要对比（手动仓 + 5 个 AI 仓）
        comp_group = QGroupBox("六仓持仓摘要")
        cg = QGridLayout(comp_group)
        cg.setSpacing(6)
        _headers = ["总资产", "浮动盈亏", "收益率", "持仓数", "可用现金", "胜率", "交易数", "总盈亏"]
        cg.addWidget(QLabel(""), 0, 0)
        for j, h in enumerate(_headers):
            lbl = QLabel(h)
            lbl.setFont(QFont("", 10, QFont.Weight.Bold))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cg.addWidget(lbl, 0, j + 1)
        _mode_labels = [
            "💼 手动仓",
            "🟣 完全自主仓", "🔵 AI推荐仓", "📌 自定义仓", "⚛️ 量子仓",
        ]
        for i, ml in enumerate(_mode_labels):
            lbl = QLabel(ml)
            lbl.setFont(QFont("", 10, QFont.Weight.Bold))
            cg.addWidget(lbl, i + 1, 0)
        self.dash_comp_labels = {}
        for i in range(5):
            for j in range(len(_headers)):
                lbl = QLabel("-")
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl.setFont(QFont("", 11))
                cg.addWidget(lbl, i + 1, j + 1)
                self.dash_comp_labels[(i, j)] = lbl
        layout.addWidget(comp_group)

        # pos_table kept as hidden dummy for compatibility
        self.pos_table = QTableWidget()
        self.pos_table.setVisible(False)

        layout.addStretch()

    def update_metrics(self, manual_summary: dict, comp: dict = None):
        """更新六仓合计摘要卡片。"""
        m_eq = manual_summary.get("total_equity", 0)
        m_pnl = manual_summary.get("unrealized_pnl", 0)
        m_today = manual_summary.get("today_pnl", 0)
        m_pos = manual_summary.get("num_positions", 0)
        m_cash = manual_summary.get("cash", 0)

        total_eq = m_eq
        total_pnl = m_pnl
        total_pos = m_pos
        total_cash = m_cash
        if comp:
            for mode in ["full_auto", "auto", "custom", "quantum"]:
                c = comp.get(mode, {})
                total_eq += c.get("equity", 0)
                total_pnl += c.get("total_pnl", 0)
                total_pos += c.get("positions", 0)
                total_cash += c.get("cash", 0)

        initial_all = 6_000_000
        total_ret = (total_eq - initial_all) / initial_all * 100 if initial_all > 0 else 0

        self.card_equity.set_value(f"¥{total_eq:,.0f}", f"{total_ret:+.2f}%", total_ret >= 0)
        self.card_pnl.set_value(f"¥{total_pnl:+,.0f}", "", total_pnl >= 0)
        self.card_today.set_value(f"¥{m_today:+,.0f}", "", m_today >= 0)
        self.card_positions.set_value(str(total_pos), "6仓合计")
        self.card_cash.set_value(f"¥{total_cash:,.0f}", "")

    _MODE_COLORS = {
        "manual_portfolio": ("#FDD835", "💼 手动仓"),
        "full_auto": ("#CE93D8", "🟣 完全自主"),
        "auto":      ("#ef5350", "🔴 半自主"),
        "manual":    ("#66BB6A", "🟢 推荐仓"),
        "custom":    ("#FF7043", "📌 自定义"),
        "quantum":   ("#4FC3F7", "⚛️ 量子仓"),
    }

    def update_comparison(self, comp: dict, manual_summary: dict = None):
        """更新六仓摘要对比表（手动仓 + 5 AI 仓）。
        列: 总资产, 浮动盈亏, 收益率, 持仓数, 可用现金, 胜率, 交易数, 总盈亏
        """
        def _color(lbl, v_str, color_cols=()):
            lbl.setText(v_str)
            try:
                fv = float(v_str.replace("%", "").replace("¥", "").replace(",", "").replace("+", ""))
                lbl.setStyleSheet(f"color: {'#ef5350' if fv > 0 else '#26a69a' if fv < 0 else '#888'};")
            except Exception:
                lbl.setStyleSheet("")

        # 第 0 行：手动仓
        if manual_summary:
            eq = manual_summary.get("total_equity", 0)
            pnl = manual_summary.get("unrealized_pnl", 0)
            ret = manual_summary.get("total_return", 0)
            n_pos = manual_summary.get("num_positions", 0)
            cash = manual_summary.get("cash", 0)
            vals = [
                f"¥{eq:,.0f}",
                f"¥{pnl:+,.0f}",
                f"{ret:+.2f}%",
                str(n_pos),
                f"¥{cash:,.0f}",
                "-",
                str(n_pos),
                f"¥{pnl:+,.0f}",
            ]
            for j, v in enumerate(vals):
                lbl = self.dash_comp_labels.get((0, j))
                if lbl:
                    if j in (1, 2, 7):
                        _color(lbl, v)
                    else:
                        lbl.setText(v)

        # 第 1-5 行：AI 仓
        for i, mode_key in enumerate(["full_auto", "auto", "custom", "quantum"]):
            c = comp.get(mode_key, {})
            eq = c.get("equity", 0)
            ret = c.get("return_pct", 0)
            total_pnl = c.get("total_pnl", 0)
            positions = c.get("positions", 0)
            cash = c.get("cash", 0)
            win_rate = c.get("win_rate", 0)
            trades = c.get("total_trades", 0)

            # 浮动盈亏 = equity - initial
            unrealized = eq - 1_000_000

            vals = [
                f"¥{eq:,.0f}",
                f"¥{unrealized:+,.0f}",
                f"{ret:+.2f}%",
                str(positions),
                f"¥{cash:,.0f}",
                f"{win_rate:.1f}%",
                str(trades),
                f"¥{total_pnl:+,.0f}",
            ]
            for j, v in enumerate(vals):
                lbl = self.dash_comp_labels.get((i + 1, j))
                if lbl:
                    if j in (1, 2, 7):
                        _color(lbl, v)
                    else:
                        lbl.setText(v)

    def update_all_positions(self, all_states: dict, prices: dict):
        """更新全仓持仓汇总表。"""
        red = QColor("#ef5350")
        green = QColor("#26a69a")
        merged = []
        for mode_key in ["manual_portfolio", "full_auto", "auto", "custom", "quantum"]:
            state = all_states.get(mode_key, {})
            for p in state.get("positions", []):
                merged.append((mode_key, p))

        self.pos_table.setSortingEnabled(False)
        self.pos_table.setRowCount(len(merged))
        for i, (mode_key, p) in enumerate(merged):
            color_hex, label = self._MODE_COLORS.get(mode_key, ("#888", mode_key))
            entry_price = p.get("entry_price", 0) or 0
            price = prices.get(p.get("code", ""), entry_price)
            pnl_pct = (price - entry_price) / entry_price * 100 if entry_price > 0 else 0
            mv = price * p.get("shares", 0)

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
                "",
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 4:
                    item.setForeground(red if pnl_pct > 0 else green if pnl_pct < 0 else QColor("#888"))
                self.pos_table.setItem(i, j + 1, item)
        self.pos_table.setSortingEnabled(True)

    def update_positions(self, positions: list[dict]):
        """兼容旧调用（手动仓数据）。"""
        pass

    def update_market(self, ok: bool, dist: int):
        if ok:
            self.market_label.setText(f"🟢 市场环境健康 — 分布日: {dist}/5，适合执行买入策略")
            self.market_label.setStyleSheet("color: #4caf50; font-size: 13px;")
        else:
            self.market_label.setText(f"🔴 市场环境偏弱 — 分布日: {dist}/5，建议减仓或暂停买入")
            self.market_label.setStyleSheet("color: #ef5350; font-size: 13px;")

    def update_risk(self, risk: dict):
        """接受 dict 格式的风险数据并更新显示。"""
        if not risk:
            return
        var95 = abs(risk.get("var95", 0))
        var99 = abs(risk.get("var99", 0))
        exp = risk.get("max_exposure", 0)
        hhi = risk.get("hhi", 0)

        if var95 > 0:
            self.risk_labels["VaR(95%)"].setText(f"¥{var95:,.0f}")
        if var99 > 0:
            self.risk_labels["VaR(99%)"].setText(f"¥{var99:,.0f}")
        if exp > 0:
            self.risk_labels["最大单股敞口"].setText(
                f"{exp:.0%}  ({risk.get('max_name', '-')})"
            )
        if hhi > 0:
            level = "高度集中" if hhi > 0.5 else "中等集中" if hhi > 0.25 else "较分散"
            self.risk_labels["集中度HHI"].setText(f"{hhi:.3f}  ({level})")

        dd = risk.get("drawdown", 0)
        self.card_drawdown.set_value(f"{dd:.2%}", "", abs(dd) < 0.08)
