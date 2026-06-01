"""策略竞技场面板 — 19 种策略赛马（19×1）"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class ArenaPanel(QWidget):
    """Display arena participants: leaderboard + holdings + last run log."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        title = QLabel("🏆 策略竞技场 — 19 种策略赛马")
        title.setFont(QFont("", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        hint = QLabel(
            "每位操作手独立 1 个模拟仓（各 100 万），对应 strategy_profiles 全部 19 种策略，"
            " 选股规则与「选股雷达」一致，公平对比谁更适合 A 股。"
            " 原「AI 仓」四仓仍在，与此竞技场分开统计。"
            " 交易日默认 10:17 / 14:03 自动跑一轮（客户端或 daemon 运行时生效）。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8b949e; font-size:12px; padding:4px 0 8px 0;")
        layout.addWidget(hint)

        btn_row = QHBoxLayout()
        self.btn_run = QPushButton("▶ 跑一轮竞技场")
        self.btn_run.setStyleSheet("font-size:13px; padding:8px 20px; background:#1565C0; color:white;")
        self.btn_run.setToolTip("共享快照 → 19 种策略各跑一轮 → 更新排行榜")
        btn_row.addWidget(self.btn_run)
        self.btn_refresh = QPushButton("🔄 刷新")
        self.btn_refresh.setStyleSheet("font-size:13px; padding:8px 16px;")
        btn_row.addWidget(self.btn_refresh)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.summary_label = QLabel("加载中...")
        self.summary_label.setStyleSheet("color:#4fc3f7; font-size:13px; padding:6px;")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        lb_box = QGroupBox("📊 排行榜（综合分 = 收益 + 胜率 + 样本量）")
        lb_layout = QVBoxLayout(lb_box)
        self.leaderboard_table = QTableWidget()
        self.leaderboard_table.setColumnCount(9)
        self.leaderboard_table.setHorizontalHeaderLabels([
            "排名", "操作手", "策略/类型", "总资产", "收益率", "胜率", "持仓", "交易", "综合分",
        ])
        self.leaderboard_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.leaderboard_table.setAlternatingRowColors(True)
        self.leaderboard_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.leaderboard_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        lb_layout.addWidget(self.leaderboard_table)
        layout.addWidget(lb_box)

        pos_box = QGroupBox("📋 全部操作手当前持仓")
        pos_layout = QVBoxLayout(pos_box)
        self.positions_table = QTableWidget()
        self.positions_table.setColumnCount(8)
        self.positions_table.setHorizontalHeaderLabels([
            "操作手", "代码", "名称", "买入价", "现价", "盈亏%", "股数", "买入日",
        ])
        self.positions_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.positions_table.setAlternatingRowColors(True)
        self.positions_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        pos_layout.addWidget(self.positions_table)
        layout.addWidget(pos_box)

        log_box = QGroupBox("📝 最近一次运行摘要")
        log_layout = QVBoxLayout(log_box)
        self.run_log = QTextEdit()
        self.run_log.setReadOnly(True)
        self.run_log.setMaximumHeight(140)
        self.run_log.setStyleSheet("font-family: Consolas, monospace; font-size:11px;")
        log_layout.addWidget(self.run_log)
        layout.addWidget(log_box)

        self.btn_run.clicked.connect(self._on_run_clicked)
        self.btn_refresh.clicked.connect(self.refresh)

    def _on_run_clicked(self):
        if callable(getattr(self, "_run_handler", None)):
            self._run_handler()

    def set_run_handler(self, handler):
        self._run_handler = handler

    def refresh(self):
        try:
            from desktop.arena.leaderboard import format_leaderboard_text, get_leaderboard
            from desktop.arena.participants import DEFAULT_PARTICIPANTS
            from desktop.ai_portfolio import get_modes_comparison, get_state
            from desktop.data_access import get_kv_json

            lb = get_leaderboard()
            self._update_leaderboard(lb.get("rows", []))

            modes = [p.mode for p in DEFAULT_PARTICIPANTS]
            comp = get_modes_comparison(modes)
            prices = comp.get("prices", {})
            self._update_positions(DEFAULT_PARTICIPANTS, prices)

            leader_name = "-"
            if lb.get("leader"):
                for row in lb.get("rows", []):
                    if row.get("participant_id") == lb["leader"]:
                        leader_name = row.get("display_name", "-")
                        break
            self.summary_label.setText(
                f"领先: {leader_name}  |  更新: {lb.get('generated_at', '')}  |  "
                + format_leaderboard_text(lb).split("\n")[-1]
            )

            last_run = get_kv_json("arena_run_latest", {}) or {}
            lines = [last_run.get("leaderboard_text", "尚未运行竞技场")]
            run_log = last_run.get("run_log", {})
            if run_log:
                lines.append("")
                lines.append("--- 各操作手 ---")
                for pid, msgs in run_log.items():
                    preview = (msgs[0] if msgs else "无")[:100]
                    lines.append(f"{pid}: {preview}")
            self.run_log.setPlainText("\n".join(lines))
        except Exception as exc:
            self.summary_label.setText(f"刷新失败: {exc}")

    def _update_leaderboard(self, rows: list[dict]):
        self.leaderboard_table.setRowCount(len(rows))
        red = QColor("#ef5350")
        green = QColor("#26a69a")
        for i, row in enumerate(rows):
            strategy = row.get("strategy_id") or row.get("pipeline", "")
            vals = [
                str(row.get("rank", i + 1)),
                row.get("display_name", ""),
                strategy,
                f"¥{row.get('equity', 0):,.0f}",
                f"{row.get('return_pct', 0):+.2f}%",
                f"{row.get('win_rate', 0):.0f}%",
                str(row.get("positions", 0)),
                str(row.get("total_trades", 0)),
                f"{row.get('composite_score', 0):.1f}",
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 4:
                    try:
                        fv = float(v.replace("%", "").replace("+", ""))
                        item.setForeground(green if fv > 0 else red if fv < 0 else QColor("#888"))
                    except ValueError:
                        pass
                if j == 0 and row.get("rank") == 1:
                    item.setFont(QFont("", 10, QFont.Weight.Bold))
                self.leaderboard_table.setItem(i, j, item)

    def _update_positions(self, participants, prices: dict):
        from desktop.ai_portfolio import get_state

        rows_data = []
        for p in participants:
            state = get_state(p.mode)
            for pos in state.get("positions", []):
                rows_data.append((p.display_name, pos))

        self.positions_table.setRowCount(len(rows_data))
        red = QColor("#ef5350")
        green = QColor("#26a69a")
        for i, (label, p) in enumerate(rows_data):
            code = p.get("code", "")
            entry = float(p.get("entry_price", 0) or 0)
            price = float(prices.get(code, entry) or entry)
            pnl = (price / entry - 1) * 100 if entry > 0 else 0
            vals = [
                label,
                code,
                p.get("name", ""),
                f"{entry:.2f}",
                f"{price:.2f}",
                f"{pnl:+.2f}%",
                str(p.get("shares", 0)),
                p.get("entry_date", ""),
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 5:
                    item.setForeground(green if pnl > 0 else red if pnl < 0 else QColor("#888"))
                self.positions_table.setItem(i, j, item)
