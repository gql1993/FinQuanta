"""基金持仓跟踪策略面板"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QTabWidget, QComboBox, QSplitter,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor


class FundPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        title = QLabel("🏦 基金持仓跟踪策略")
        title.setFont(QFont("", 16, QFont.Weight.Bold))
        layout.addWidget(title)
        layout.addWidget(QLabel("基于公募基金季报/半年报/年报重仓股，分析持仓变化规律预测个股走势"))

        # 控制行
        ctl = QHBoxLayout()
        ctl.addWidget(QLabel("报告期:"))
        self.period_combo = QComboBox()
        self.period_combo.addItems([
            "2025-Q4", "2025-Q3", "2025-Q2", "2025-Q1",
            "2024-Q4", "2024-Q3", "2024-Q2",
        ])
        ctl.addWidget(self.period_combo)
        self.btn_load = QPushButton("📥 加载持仓数据")
        self.btn_load.setStyleSheet("font-size: 13px; padding: 8px 16px;")
        ctl.addWidget(self.btn_load)
        self.btn_analyze = QPushButton("🔍 分析公布后表现")
        self.btn_analyze.setStyleSheet("font-size: 13px; padding: 8px 16px; background: #FF6F00;")
        ctl.addWidget(self.btn_analyze)

        ctl.addWidget(QLabel("对比:"))
        self.compare_combo = QComboBox()
        self.compare_combo.addItems(["2025-Q3", "2025-Q2", "2025-Q1", "2024-Q4", "2024-Q3"])
        ctl.addWidget(self.compare_combo)
        self.btn_compare = QPushButton("📊 对比持仓变化")
        ctl.addWidget(self.btn_compare)
        ctl.addStretch()
        layout.addLayout(ctl)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #4fc3f7; font-size: 12px;")
        layout.addWidget(self.status_label)

        # Tabs
        tabs = QTabWidget()
        tabs.addTab(self._build_holdings_tab(), "📋 重仓股列表")
        tabs.addTab(self._build_performance_tab(), "📈 公布后表现")
        tabs.addTab(self._build_changes_tab(), "🔄 持仓变化")
        tabs.addTab(self._build_star_tab(), "⭐ 明星经理")
        layout.addWidget(tabs)

    def _build_holdings_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.holdings_table = QTableWidget()
        self.holdings_table.setColumnCount(7)
        self.holdings_table.setHorizontalHeaderLabels([
            "代码", "名称", "持有基金数", "行业", "变动", "近20日涨跌", "策略预测",
        ])
        self.holdings_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.holdings_table.setAlternatingRowColors(True)
        self.holdings_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.holdings_table.setSortingEnabled(True)
        layout.addWidget(self.holdings_table)
        return w

    def _build_performance_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.perf_table = QTableWidget()
        self.perf_table.setColumnCount(11)
        self.perf_table.setHorizontalHeaderLabels([
            "代码", "名称", "行业", "持有基金数", "现价",
            "5日%", "10日%", "20日%", "60日%", "趋势", "公布日期",
        ])
        self.perf_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.perf_table.setAlternatingRowColors(True)
        self.perf_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.perf_table.setSortingEnabled(True)
        layout.addWidget(self.perf_table)
        return w

    def _build_changes_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.changes_table = QTableWidget()
        self.changes_table.setColumnCount(6)
        self.changes_table.setHorizontalHeaderLabels([
            "代码", "名称", "行业", "变动类型", "当前基金数", "变化数",
        ])
        self.changes_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.changes_table.setAlternatingRowColors(True)
        self.changes_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.changes_table.setSortingEnabled(True)
        layout.addWidget(self.changes_table)
        return w

    def update_holdings(self, holdings: list[dict]):
        red = QColor("#ef5350")
        green = QColor("#26a69a")
        gold = QColor("#FFD740")
        orange = QColor("#FF9800")
        self.holdings_table.setRowCount(len(holdings))
        for i, h in enumerate(holdings):
            change = h.get("change_type", "") or "-"
            pct_chg = h.get("pct_chg", "-")
            forecast = h.get("forecast", "-")
            vals = [
                h.get("code", ""), h.get("name", ""),
                str(h.get("holding_funds", 0)), h.get("sector", ""),
                change, pct_chg, forecast,
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 4:
                    if "新进" in v:
                        item.setForeground(gold)
                    elif "增持" in v:
                        item.setForeground(red)
                    elif "减持" in v:
                        item.setForeground(green)
                    item.setFont(QFont("", 11, QFont.Weight.Bold))
                elif j == 5:
                    try:
                        fv = float(v.replace("%", "").replace("+", ""))
                        item.setForeground(red if fv > 0 else green if fv < 0 else QColor("#888"))
                        item.setFont(QFont("", 10, QFont.Weight.Bold))
                    except Exception:
                        pass
                elif j == 6:
                    if "看多" in v:
                        item.setForeground(red)
                    elif "看空" in v:
                        item.setForeground(green)
                    else:
                        item.setForeground(orange)
                    item.setFont(QFont("", 10, QFont.Weight.Bold))
                self.holdings_table.setItem(i, j, item)

    def update_performance(self, results: list[dict]):
        red = QColor("#ef5350")
        green = QColor("#26a69a")
        # 如果尚未公布，更新列标题说明数据含义
        not_published = any("尚未公布" in r.get("disclosure_date", "") for r in results)
        if not_published:
            self.perf_table.setHorizontalHeaderLabels([
                "代码", "名称", "行业", "持有基金数", "现价",
                "近5日%", "近10日%", "近20日%", "近60日%", "趋势", "公布日期",
            ])
        else:
            self.perf_table.setHorizontalHeaderLabels([
                "代码", "名称", "行业", "持有基金数", "现价",
                "公布后5日%", "公布后10日%", "公布后20日%", "公布后60日%", "趋势", "公布日期",
            ])
        self.perf_table.setRowCount(len(results))
        for i, r in enumerate(results):
            def _fmt_pct(v):
                if v is None:
                    return "-"
                return f"{v:+.2f}%"
            vals = [
                r["code"], r["name"], r.get("sector", ""),
                str(r.get("holding_funds", 0)), f"{r['price']:.2f}",
                _fmt_pct(r.get("pct_5d")), _fmt_pct(r.get("pct_10d")),
                _fmt_pct(r.get("pct_20d")), _fmt_pct(r.get("pct_60d")),
                r.get("trend", ""),
                r.get("disclosure_date", "-"),
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if 5 <= j <= 8:
                    try:
                        fv = float(v.replace("%", "").replace("+", ""))
                        item.setForeground(red if fv > 0 else green if fv < 0 else QColor("#888"))
                    except Exception:
                        pass
                if j == 9:
                    color = red if v == "上升" else green if v == "下降" else QColor("#FF9800")
                    item.setForeground(color)
                if j == 10:
                    if "尚未公布" in v:
                        item.setForeground(QColor("#FF9800"))
                        item.setFont(QFont("", 10, QFont.Weight.Bold))
                    else:
                        item.setForeground(QColor("#4fc3f7"))
                self.perf_table.setItem(i, j, item)

    def update_changes(self, changes: list[dict]):
        red = QColor("#ef5350")
        green = QColor("#26a69a")
        gold = QColor("#FFD740")
        self.changes_table.setRowCount(len(changes))
        for i, c in enumerate(changes):
            vals = [
                c["code"], c["name"], c.get("sector", ""),
                c["change"], str(c.get("curr_funds", 0)),
                f"{c.get('delta_funds', 0):+d}",
            ]
            change_colors = {
                "新进": red, "增持": red,
                "减持": green, "退出": green,
                "持平": QColor("#888"),
            }
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 3:
                    item.setForeground(change_colors.get(v, QColor("#888")))
                    item.setFont(QFont("", 11, QFont.Weight.Bold))
                if j == 5:
                    try:
                        fv = int(v.replace("+", ""))
                        item.setForeground(red if fv > 0 else green if fv < 0 else QColor("#888"))
                    except Exception:
                        pass
                self.changes_table.setItem(i, j, item)

    # ---- 明星经理 ----
    def _build_star_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        top = QHBoxLayout()
        top.addWidget(QLabel("选择经理:"))
        self.mgr_combo = QComboBox()
        self.mgr_combo.setMinimumWidth(200)
        top.addWidget(self.mgr_combo)
        self.btn_load_mgr = QPushButton("📊 加载持仓 & 分析")
        self.btn_load_mgr.setStyleSheet("font-size: 13px; padding: 8px 14px; background: #FF6F00;")
        top.addWidget(self.btn_load_mgr)
        top.addStretch()
        layout.addLayout(top)

        self.mgr_info_label = QLabel("")
        self.mgr_info_label.setStyleSheet("font-size: 12px; color: #aaa; padding: 4px 0;")
        self.mgr_info_label.setWordWrap(True)
        layout.addWidget(self.mgr_info_label)

        # 经理概览表
        self.mgr_summary_table = QTableWidget()
        self.mgr_summary_table.setColumnCount(5)
        self.mgr_summary_table.setHorizontalHeaderLabels([
            "经理", "代表基金", "风格", "近5年均值%", "近年业绩",
        ])
        self.mgr_summary_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.mgr_summary_table.setAlternatingRowColors(True)
        self.mgr_summary_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.mgr_summary_table.setMaximumHeight(180)
        layout.addWidget(self.mgr_summary_table)

        # 持仓公布前后表现表
        layout.addWidget(QLabel("▼ 持仓公布前后股价变化 & 跟买信号"))
        self.mgr_holdings_table = QTableWidget()
        self.mgr_holdings_table.setColumnCount(11)
        self.mgr_holdings_table.setHorizontalHeaderLabels([
            "代码", "名称", "权重%", "变动", "现价",
            "公布前10日%", "公布前5日%", "公布后5日%", "公布后10日%", "公布后20日%",
            "跟买信号",
        ])
        self.mgr_holdings_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.mgr_holdings_table.setAlternatingRowColors(True)
        self.mgr_holdings_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.mgr_holdings_table.setSortingEnabled(True)
        layout.addWidget(self.mgr_holdings_table)

        return w

    def update_star_summary(self, managers: list[dict]):
        self.mgr_combo.clear()
        for m in managers:
            self.mgr_combo.addItem(f"{m['name']}（近5年 {m['avg_5y']:+.1f}%）")

        self.mgr_summary_table.setRowCount(len(managers))
        for i, m in enumerate(managers):
            rets = m.get("annual_returns", {})
            ret_str = " / ".join(f"{y}:{v:+.1f}%" for y, v in sorted(rets.items()))
            vals = [m["name"], m["fund"], m["style"], f"{m['avg_5y']:+.1f}%", ret_str]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 3:
                    try:
                        fv = float(v.replace("%", "").replace("+", ""))
                        item.setForeground(
                            QColor("#ef5350") if fv > 0 else QColor("#26a69a") if fv < 0 else QColor("#888")
                        )
                        item.setFont(QFont("", 11, QFont.Weight.Bold))
                    except Exception:
                        pass
                self.mgr_summary_table.setItem(i, j, item)

    def update_star_holdings(self, results: list[dict], manager_info: str = ""):
        red = QColor("#ef5350")
        green = QColor("#26a69a")
        gold = QColor("#FFD740")

        if manager_info:
            self.mgr_info_label.setText(manager_info)

        self.mgr_holdings_table.setRowCount(len(results))
        for i, r in enumerate(results):
            def _f(v):
                return f"{v:+.2f}%" if v is not None else "-"
            vals = [
                r.get("code", ""), r.get("name", ""),
                f"{r.get('weight', 0):.1f}", r.get("change", "-"),
                str(r.get("price", "-")),
                _f(r.get("pre_10d")), _f(r.get("pre_5d")),
                _f(r.get("post_5d")), _f(r.get("post_10d")), _f(r.get("post_20d")),
                r.get("signal", "-"),
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                # 变动列
                if j == 3:
                    if "增持" in v:
                        item.setForeground(red)
                    elif "新进" in v:
                        item.setForeground(gold)
                    elif "减持" in v:
                        item.setForeground(green)
                    item.setFont(QFont("", 10, QFont.Weight.Bold))
                # 涨跌列
                if 5 <= j <= 9:
                    try:
                        fv = float(v.replace("%", "").replace("+", ""))
                        item.setForeground(red if fv > 0 else green if fv < 0 else QColor("#888"))
                    except Exception:
                        pass
                # 信号列
                if j == 10:
                    if "强烈跟买" in v:
                        item.setForeground(red)
                    elif "建议跟买" in v:
                        item.setForeground(QColor("#42a5f5"))
                    elif "不建议" in v:
                        item.setForeground(green)
                    else:
                        item.setForeground(QColor("#888"))
                    item.setFont(QFont("", 10, QFont.Weight.Bold))
                self.mgr_holdings_table.setItem(i, j, item)
