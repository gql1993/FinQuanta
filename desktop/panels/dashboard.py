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

        metrics_layout = QHBoxLayout()
        self.card_equity = MetricCard("总资产")
        self.card_pnl = MetricCard("浮动盈亏")
        self.card_today = MetricCard("当日盈亏")
        self.card_positions = MetricCard("持仓数")
        self.card_cash = MetricCard("可用现金")
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
        self.risk_labels = {}
        risk_items = ["VaR(95%)", "VaR(99%)", "最大单股敞口", "集中度HHI"]
        for i, name in enumerate(risk_items):
            lbl = QLabel(name + ": -")
            lbl.setStyleSheet("font-size: 13px;")
            rg_layout.addWidget(lbl, 0, i)
            self.risk_labels[name] = lbl
        layout.addWidget(risk_group)

        pos_group = QGroupBox("当前持仓")
        pg_layout = QVBoxLayout(pos_group)
        self.pos_table = QTableWidget()
        self.pos_table.setColumnCount(8)
        self.pos_table.setHorizontalHeaderLabels(
            ["代码", "名称", "现价", "成本", "盈亏%", "当日%", "市值", "阶段"]
        )
        self.pos_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.pos_table.setAlternatingRowColors(True)
        self.pos_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        pg_layout.addWidget(self.pos_table)
        layout.addWidget(pos_group)

        layout.addStretch()

    def update_metrics(self, summary: dict):
        eq = summary.get("total_equity", 0)
        ret = summary.get("total_return", 0)
        self.card_equity.set_value(f"¥{eq:,.0f}", f"{ret:+.2f}%", ret >= 0)

        pnl = summary.get("unrealized_pnl", 0)
        pnl_pct = summary.get("unrealized_pnl_pct", 0)
        self.card_pnl.set_value(f"¥{pnl:+,.0f}", f"{pnl_pct:+.2f}%", pnl >= 0)

        today = summary.get("today_pnl", 0)
        self.card_today.set_value(f"¥{today:+,.0f}", "", today >= 0)

        n = summary.get("num_positions", 0)
        mx = summary.get("max_positions", 8)
        self.card_positions.set_value(f"{n}/{mx}", "")

        cash = summary.get("cash", 0)
        self.card_cash.set_value(f"¥{cash:,.0f}", "")

    def update_positions(self, positions: list[dict]):
        self.pos_table.setRowCount(len(positions))
        for i, p in enumerate(positions):
            items = [
                p.get("代码", ""), p.get("名称", ""),
                f"{p.get('现价', 0):.2f}", f"{p.get('成本', 0):.0f}",
                f"{p.get('盈亏%', 0):+.2f}%", f"{p.get('当日%', 0):+.2f}%",
                f"¥{p.get('市值', 0):,.0f}", p.get("阶段", "-"),
            ]
            for j, text in enumerate(items):
                item = QTableWidgetItem(str(text))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j in (4, 5):
                    try:
                        v = float(str(text).replace("%", "").replace("+", "").replace(",", ""))
                        item.setForeground(
                            Qt.GlobalColor.red if v > 0 else
                            Qt.GlobalColor.green if v < 0 else
                            Qt.GlobalColor.gray
                        )
                    except ValueError:
                        pass
                self.pos_table.setItem(i, j, item)

    def update_market(self, ok: bool, dist: int):
        if ok:
            self.market_label.setText(f"🟢 市场环境健康 — 分布日: {dist}/5，适合执行买入策略")
            self.market_label.setStyleSheet("color: #4caf50; font-size: 13px;")
        else:
            self.market_label.setText(f"🔴 市场环境偏弱 — 分布日: {dist}/5，建议减仓或暂停买入")
            self.market_label.setStyleSheet("color: #ef5350; font-size: 13px;")

    def update_risk(self, report):
        if report is None:
            return
        self.risk_labels["VaR(95%)"].setText(f"VaR(95%): ¥{report.var_95_1d:,.0f}")
        self.risk_labels["VaR(99%)"].setText(f"VaR(99%): ¥{report.var_99_1d:,.0f}")
        self.risk_labels["最大单股敞口"].setText(
            f"最大单股: {report.max_single_exposure:.0%} ({report.max_single_name})"
        )
        self.risk_labels["集中度HHI"].setText(f"HHI: {report.concentration_hhi:.3f}")
        dd = report.current_drawdown
        self.card_drawdown.set_value(f"{dd:.2%}", "", dd < 0.08)
