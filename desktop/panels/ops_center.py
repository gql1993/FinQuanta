"""运行中心面板：统一查看快照、任务运行和系统事件。"""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QGridLayout, QTableWidget, QTableWidgetItem, QHeaderView,
)
from desktop.ui_tokens import APP_FONT


class OpsCenterPanel(QWidget):
    suggestion_jump_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        title = QLabel("🛰 运行中心")
        title.setFont(QFont("", APP_FONT["page_title"], QFont.Weight.Bold))
        layout.addWidget(title)

        self.status_label = QLabel("等待刷新...")
        self.status_label.setStyleSheet(f"color:#4fc3f7; font-size:{APP_FONT['body']}px;")
        layout.addWidget(self.status_label)

        btn_row = QHBoxLayout()
        self.btn_refresh = QPushButton("🔄 刷新运行中心")
        self.btn_refresh.setStyleSheet(f"font-size:{APP_FONT['body']}px; padding:6px 14px;")
        btn_row.addWidget(self.btn_refresh)
        self.btn_self_check = QPushButton("🩺 立即自检")
        self.btn_self_check.setStyleSheet(f"font-size:{APP_FONT['body']}px; padding:6px 14px;")
        btn_row.addWidget(self.btn_self_check)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        self.self_check_label = QLabel("链路健康: 待检测")
        self.self_check_label.setStyleSheet(f"color:#ffb74d; font-size:{APP_FONT['body']}px;")
        layout.addWidget(self.self_check_label)
        self.self_check_suggestion = QLabel("修复建议: 点击「立即自检」后显示。")
        self.self_check_suggestion.setWordWrap(True)
        self.self_check_suggestion.setStyleSheet(f"color:#b0bec5; font-size:{APP_FONT['caption']}px;")
        layout.addWidget(self.self_check_suggestion)
        self.btn_copy_diagnostics = QPushButton("📋 复制诊断信息")
        self.btn_copy_diagnostics.setStyleSheet(f"font-size:{APP_FONT['body']}px; padding:6px 14px;")
        self.btn_copy_diagnostics.setEnabled(False)
        self.btn_jump_suggestion = QPushButton("🧭 按建议自动跳转")
        self.btn_jump_suggestion.setStyleSheet(f"font-size:{APP_FONT['body']}px; padding:6px 14px;")
        self.btn_jump_suggestion.setEnabled(False)
        action_row = QHBoxLayout()
        action_row.addWidget(self.btn_copy_diagnostics)
        action_row.addWidget(self.btn_jump_suggestion)
        action_row.addStretch()
        layout.addLayout(action_row)
        self._diagnostics_text = ""
        self._jump_target = ""
        self.btn_copy_diagnostics.clicked.connect(self.copy_diagnostics)
        self.btn_jump_suggestion.clicked.connect(self.request_suggestion_jump)

        snap_group = QGroupBox("📌 系统快照")
        sg = QGridLayout(snap_group)
        self.snap_labels = {}
        items = [
            ("全仓总资产", 0, 0), ("总可用现金", 0, 1), ("总持仓数", 0, 2),
            ("市场状态", 1, 0), ("组合VaR95", 1, 1), ("市场原因", 1, 2),
            ("Daemon状态", 2, 0), ("Daemon心跳", 2, 1), ("下一任务", 2, 2),
        ]
        for name, r, c in items:
            lbl = QLabel(f"{name}: -")
            lbl.setFont(QFont("", APP_FONT["caption"]))
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

    def update_daemon(self, daemon: dict):
        daemon = daemon or {}
        active = bool(daemon.get("active", False))
        hb = str(daemon.get("heartbeat_at", "") or "-")
        next_task = daemon.get("next_task", {}) or {}
        next_name = str(next_task.get("task_name", "") or "-")
        next_time = str(next_task.get("scheduled_at", "") or "-")
        self.snap_labels["Daemon状态"].setText(f"Daemon状态: {'运行中' if active else '未运行'}")
        self.snap_labels["Daemon心跳"].setText(f"Daemon心跳: {hb}")
        self.snap_labels["下一任务"].setText(f"下一任务: {next_name} @ {next_time}")
        state_color = "#66bb6a" if active else "#ef5350"
        self.snap_labels["Daemon状态"].setStyleSheet(
            f"color:{state_color}; font-size:{APP_FONT['caption']}px;"
        )

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

    def update_daemon_health(self, report: dict):
        report = report or {}
        ok = bool(report.get("ok", False))
        checks = report.get("checks", []) or []
        suggestions = report.get("suggestions", []) or []
        self._jump_target = str(report.get("jump_target", "") or "")
        self._diagnostics_text = str(report.get("diagnostics", "") or "")
        failed = [c for c in checks if not bool(c.get("ok", False))]
        detail_lines = [
            f"{'✅' if bool(c.get('ok', False)) else '❌'} {c.get('name', '-')}: {c.get('detail', '-')}"
            for c in checks
        ]
        if ok:
            text = "链路健康: 正常（daemon、排程、推送链路均可用）"
            color = "#66bb6a"
        else:
            failed_names = ",".join(str(c.get("name", "")) for c in failed) or "unknown"
            text = f"链路健康: 异常（{failed_names}）"
            color = "#ef5350"
        self.self_check_label.setText(text)
        self.self_check_label.setStyleSheet(f"color:{color}; font-size:{APP_FONT['body']}px;")
        self.self_check_label.setToolTip("\n".join(detail_lines))
        if suggestions:
            self.self_check_suggestion.setText("修复建议: " + " | ".join(str(s) for s in suggestions))
        else:
            self.self_check_suggestion.setText("修复建议: 暂无")
        self.btn_copy_diagnostics.setEnabled(bool(self._diagnostics_text.strip()))
        self.btn_jump_suggestion.setEnabled(bool(self._jump_target.strip()))

    def copy_diagnostics(self):
        text = self._diagnostics_text.strip()
        if not text:
            self.self_check_suggestion.setText("修复建议: 当前无可复制的诊断信息，请先执行立即自检。")
            return
        QApplication.clipboard().setText(text)
        self.self_check_suggestion.setText("修复建议: 已复制诊断信息，可直接发给运维/开发定位。")

    def request_suggestion_jump(self):
        target = self._jump_target.strip()
        if not target:
            self.self_check_suggestion.setText("修复建议: 当前无可跳转目标，请先执行立即自检。")
            return
        self.suggestion_jump_requested.emit(target)

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
