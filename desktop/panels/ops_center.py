"""运行中心面板：统一查看快照、任务运行和系统事件。"""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QGridLayout, QTableWidget, QTableWidgetItem, QHeaderView,
)


class OpsCenterPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        title = QLabel("🛰 运行中心")
        title.setFont(QFont("", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        self.status_label = QLabel("等待刷新...")
        self.status_label.setStyleSheet("color:#4fc3f7; font-size:12px;")
        layout.addWidget(self.status_label)

        btn_row = QHBoxLayout()
        self.btn_refresh = QPushButton("🔄 刷新运行中心")
        self.btn_refresh.setStyleSheet("font-size:12px; padding:6px 14px;")
        btn_row.addWidget(self.btn_refresh)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        snap_group = QGroupBox("📌 系统快照")
        sg = QGridLayout(snap_group)
        self.snap_labels = {}
        items = [
            ("全仓总资产", 0, 0), ("总可用现金", 0, 1), ("总持仓数", 0, 2),
            ("市场状态", 1, 0), ("组合VaR95", 1, 1), ("市场原因", 1, 2),
        ]
        for name, r, c in items:
            lbl = QLabel(f"{name}: -")
            lbl.setFont(QFont("", 11))
            sg.addWidget(lbl, r, c)
            self.snap_labels[name] = lbl
        layout.addWidget(snap_group)

        task_group = QGroupBox("📋 最近任务运行")
        tl = QVBoxLayout(task_group)
        self.task_table = QTableWidget()
        self.task_table.setColumnCount(5)
        self.task_table.setHorizontalHeaderLabels(["时间", "任务", "来源", "状态", "摘要"])
        self.task_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.task_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.task_table.setAlternatingRowColors(True)
        tl.addWidget(self.task_table)
        layout.addWidget(task_group)

        event_group = QGroupBox("🧾 最近系统事件")
        el = QVBoxLayout(event_group)
        self.event_table = QTableWidget()
        self.event_table.setColumnCount(5)
        self.event_table.setHorizontalHeaderLabels(["时间", "来源", "分类", "级别", "标题"])
        self.event_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.event_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.event_table.setAlternatingRowColors(True)
        el.addWidget(self.event_table)
        layout.addWidget(event_group)

    def update_snapshot(self, snap: dict):
        totals = snap.get("totals", {})
        market = snap.get("market_state", {})
        risk = snap.get("risk", {})
        self.snap_labels["全仓总资产"].setText(f"全仓总资产: ¥{totals.get('equity', 0):,.0f}")
        self.snap_labels["总可用现金"].setText(f"总可用现金: ¥{totals.get('cash', 0):,.0f}")
        self.snap_labels["总持仓数"].setText(f"总持仓数: {totals.get('positions', 0)}")
        self.snap_labels["市场状态"].setText(f"市场状态: {market.get('state', '-')}")
        self.snap_labels["组合VaR95"].setText(f"组合VaR95: ¥{abs(risk.get('var95', 0)):,.0f}")
        self.snap_labels["市场原因"].setText(f"市场原因: {market.get('reason', '-')}")

    def update_task_runs(self, runs: list[dict]):
        self.task_table.setRowCount(len(runs))
        for i, r in enumerate(runs):
            vals = [
                (r.get("timestamp", "") or "")[:19],
                r.get("task_name", ""),
                r.get("trigger_source", ""),
                r.get("status", ""),
                r.get("summary", ""),
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(str(v))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 3:
                    item.setForeground(QColor("#66bb6a" if v == "success" else "#ef5350" if v == "error" else "#ffb74d"))
                self.task_table.setItem(i, j, item)

    def update_events(self, events: list[dict]):
        self.event_table.setRowCount(len(events))
        for i, e in enumerate(events):
            vals = [
                (e.get("timestamp", "") or "")[:19],
                e.get("source", ""),
                e.get("category", ""),
                e.get("level", ""),
                e.get("title", ""),
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(str(v))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 3:
                    item.setForeground(QColor("#ef5350" if v == "error" else "#ffb74d" if v == "warning" else "#4fc3f7"))
                self.event_table.setItem(i, j, item)
