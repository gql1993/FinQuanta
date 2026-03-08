"""选股雷达面板 + 自定义板块"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSpinBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QGroupBox, QProgressBar, QTreeWidget, QTreeWidgetItem,
    QSplitter, QTabWidget, QStackedWidget,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor, QBrush


class ScreeningPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        title = QLabel("📡 选股雷达")
        title.setFont(QFont("", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        tabs = QTabWidget()
        tabs.addTab(self._build_board_tab(), "⭐ 自定义板块")
        tabs.addTab(self._build_scan_tab(), "🔍 扫描选股")
        layout.addWidget(tabs)

    def _build_board_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        top = QHBoxLayout()
        self.btn_refresh_boards = QPushButton("🔄 刷新成分股")
        self.btn_scan_board = QPushButton("🔍 扫描选中板块")
        self.btn_sync_data = QPushButton("📥 补全板块数据")
        self.btn_sync_data.setToolTip("从网络拉取缺失股票的日线数据，让所有个股都能计算评分")
        top.addWidget(self.btn_refresh_boards)
        top.addWidget(self.btn_scan_board)
        top.addWidget(self.btn_sync_data)
        top.addStretch()
        layout.addLayout(top)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        left_w = QWidget()
        left_layout = QVBoxLayout(left_w)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_label = QLabel("板块导航")
        left_label.setFont(QFont("", 11, QFont.Weight.Bold))
        left_layout.addWidget(left_label)
        self.board_tree = QTreeWidget()
        self.board_tree.setHeaderLabels(["板块", "成分股数"])
        self.board_tree.setAlternatingRowColors(True)
        self.board_tree.setMinimumWidth(320)
        self.board_tree.setColumnWidth(0, 260)
        self.board_tree.setColumnWidth(1, 60)
        self.board_tree.setIndentation(20)
        self.board_tree.setStyleSheet("QTreeWidget { font-size: 13px; }")
        left_layout.addWidget(self.board_tree)
        splitter.addWidget(left_w)

        right_w = QWidget()
        right_layout = QVBoxLayout(right_w)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.board_detail_label = QLabel("点击左侧板块查看成分股")
        self.board_detail_label.setFont(QFont("", 12, QFont.Weight.Bold))
        right_layout.addWidget(self.board_detail_label)
        self.board_stock_table = QTableWidget()
        self.board_stock_table.setColumnCount(11)
        self.board_stock_table.setHorizontalHeaderLabels([
            "名称", "代码", "最新价", "涨幅%", "5日涨幅%", "成交量", "评分", "信号",
            "建议买入", "建议操作", "板块",
        ])
        self.board_stock_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.board_stock_table.setAlternatingRowColors(True)
        self.board_stock_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.board_stock_table.setSortingEnabled(True)
        self.board_stock_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        right_layout.addWidget(self.board_stock_table)
        splitter.addWidget(right_w)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([420, 800])
        layout.addWidget(splitter)
        return w

    def _build_scan_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        params = QHBoxLayout()
        params.addWidget(QLabel("策略:"))
        self.combo_strategy = QComboBox()
        self.combo_strategy.setMinimumWidth(180)
        params.addWidget(self.combo_strategy)

        params.addWidget(QLabel("样本数:"))
        self.spin_sample = QSpinBox()
        self.spin_sample.setRange(50, 800)
        self.spin_sample.setValue(300)
        self.spin_sample.setSingleStep(50)
        params.addWidget(self.spin_sample)

        params.addWidget(QLabel("最低RS:"))
        self.spin_rs = QSpinBox()
        self.spin_rs.setRange(30, 95)
        self.spin_rs.setValue(70)
        params.addWidget(self.spin_rs)

        self.btn_scan = QPushButton("🔍 开始扫描")
        self.btn_scan.setStyleSheet("font-size: 14px; padding: 10px 24px;")
        params.addWidget(self.btn_scan)

        self.btn_push = QPushButton("📤 推送突破信号")
        params.addWidget(self.btn_push)
        params.addStretch()
        layout.addLayout(params)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.result_table = QTableWidget()
        self.result_table.setColumnCount(14)
        self.result_table.setHorizontalHeaderLabels([
            "代码", "名称", "板块", "策略", "价格", "RS", "评分",
            "VCP", "突破", "收缩", "量比", "离高点%", "建议买入", "建议操作",
        ])
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.result_table.setAlternatingRowColors(True)
        self.result_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.result_table.setSortingEnabled(True)
        layout.addWidget(self.result_table)

        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("color: #888;")
        layout.addWidget(self.status_label)
        return w

    def populate_board_tree(self, groups: dict[str, list[str]], board_stocks: dict[str, list[str]],
                            stock_names: dict[str, str]):
        self.board_tree.clear()
        for gname, boards in groups.items():
            total_in_group = sum(len(board_stocks.get(bn, [])) for bn in boards)
            group_item = QTreeWidgetItem([f"📂 {gname}", f"{total_in_group}"])
            group_item.setFont(0, QFont("", 11, QFont.Weight.Bold))
            group_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "group", "name": gname})
            for bn in boards:
                stocks = board_stocks.get(bn, [])
                board_item = QTreeWidgetItem([f"📊 {bn}", str(len(stocks))])
                board_item.setFont(0, QFont("", 10, QFont.Weight.Bold))
                board_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "board", "name": bn})
                for code in stocks[:100]:
                    name = stock_names.get(code, stock_names.get(str(code), ""))
                    display = f"{name}（{code}）" if name else code
                    stock_item = QTreeWidgetItem([display, ""])
                    stock_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "stock", "code": code})
                    board_item.addChild(stock_item)
                group_item.addChild(board_item)
            self.board_tree.addTopLevelItem(group_item)
        self.board_tree.resizeColumnToContents(0)
        self.board_tree.resizeColumnToContents(1)

    def populate_board_stocks(self, board_name: str, stocks: list[dict]):
        """填充右侧成分股表格（策略评分优先排列）。"""
        n_signal = sum(1 for s in stocks if s.get("_score", 0) >= 50)
        self.board_detail_label.setText(
            f"📊 {board_name}（{len(stocks)} 只成分股，{n_signal} 只有突破潜力）"
        )
        self.board_stock_table.setSortingEnabled(False)
        self.board_stock_table.blockSignals(True)
        self.board_stock_table.setUpdatesEnabled(False)
        self.board_stock_table.setRowCount(len(stocks))

        red = QBrush(QColor("#ef5350"))
        green = QBrush(QColor("#26a69a"))
        gold = QBrush(QColor("#FFD740"))

        for i, s in enumerate(stocks):
            score = s.get("_score", 0)
            signal = s.get("_signal", "")
            chg = s.get("pct_change", 0)
            chg5 = s.get("pct_5d", 0)

            # 策略研判：建议买入 / 建议操作
            buy_advice, action_advice = self._compute_advice(score, signal, chg, chg5)

            name_item = QTableWidgetItem(s.get("name", ""))
            code_item = QTableWidgetItem(s.get("code", ""))
            price_item = QTableWidgetItem(f"{s.get('price', 0):.2f}" if s.get("price") else "-")
            chg_item = QTableWidgetItem(f"{chg:+.2f}%" if chg else "-")
            chg5_item = QTableWidgetItem(f"{chg5:+.2f}%" if chg5 else "-")
            vol_item = QTableWidgetItem(self._fmt_volume(s.get("volume", 0)))
            score_item = QTableWidgetItem(str(score))
            signal_item = QTableWidgetItem(signal)
            buy_item = QTableWidgetItem(buy_advice)
            action_item = QTableWidgetItem(action_advice)
            board_item = QTableWidgetItem(s.get("board", board_name))

            for item in [name_item, code_item, price_item, chg_item, chg5_item,
                         vol_item, score_item, signal_item, buy_item, action_item, board_item]:
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            if chg and chg > 0:
                chg_item.setForeground(red)
            elif chg and chg < 0:
                chg_item.setForeground(green)
            if chg5 and chg5 > 0:
                chg5_item.setForeground(red)
            elif chg5 and chg5 < 0:
                chg5_item.setForeground(green)

            if score >= 70:
                score_item.setForeground(red)
                name_item.setForeground(red)
            elif score >= 50:
                score_item.setForeground(gold)
            if "突破" in signal:
                signal_item.setForeground(red)
            elif signal:
                signal_item.setForeground(gold)

            if "买入" in buy_advice:
                buy_item.setForeground(red)
                buy_item.setFont(QFont("", 10, QFont.Weight.Bold))
            elif "观望" in buy_advice:
                buy_item.setForeground(QBrush(QColor("#FF9800")))
            else:
                buy_item.setForeground(QBrush(QColor("#888")))

            if "卖出" in action_advice:
                action_item.setForeground(green)
                action_item.setFont(QFont("", 10, QFont.Weight.Bold))
            elif "持有" in action_advice:
                action_item.setForeground(QBrush(QColor("#4fc3f7")))
            elif "加仓" in action_advice:
                action_item.setForeground(red)
                action_item.setFont(QFont("", 10, QFont.Weight.Bold))

            self.board_stock_table.setItem(i, 0, name_item)
            self.board_stock_table.setItem(i, 1, code_item)
            self.board_stock_table.setItem(i, 2, price_item)
            self.board_stock_table.setItem(i, 3, chg_item)
            self.board_stock_table.setItem(i, 4, chg5_item)
            self.board_stock_table.setItem(i, 5, vol_item)
            self.board_stock_table.setItem(i, 6, score_item)
            self.board_stock_table.setItem(i, 7, signal_item)
            self.board_stock_table.setItem(i, 8, buy_item)
            self.board_stock_table.setItem(i, 9, action_item)
            self.board_stock_table.setItem(i, 10, board_item)

        self.board_stock_table.setUpdatesEnabled(True)
        self.board_stock_table.blockSignals(False)
        self.board_stock_table.setSortingEnabled(True)

    @staticmethod
    def _compute_advice(score, signal, chg, chg5) -> tuple[str, str]:
        """
        基于多策略综合评分、信号、涨幅，给出买入建议和操作建议。
        返回 (建议买入, 建议操作)
        """
        buy = ""
        action = ""

        has_break = "突破" in str(signal)
        has_vcp = "收缩" in str(signal) or "VCP" in str(signal)
        has_trend = "多头" in str(signal) or "排列" in str(signal)

        # 买入研判
        if score >= 60 and has_break:
            buy = "🟢 强烈买入"
        elif score >= 50 and (has_break or has_vcp):
            buy = "🔵 建议买入"
        elif score >= 40 and has_trend:
            buy = "🔵 建议买入"
        elif score >= 30:
            buy = "⚪ 观望"
        elif score > 0:
            buy = "⚪ 暂不买入"
        else:
            buy = "⛔ 不买入"

        # 操作研判（针对已持有）
        try:
            chg_f = float(chg) if chg else 0
            chg5_f = float(chg5) if chg5 else 0
        except (ValueError, TypeError):
            chg_f, chg5_f = 0, 0

        if score >= 50 and has_break and chg5_f > 0:
            action = "📈 加仓"
        elif score >= 40 and chg_f > 0:
            action = "💎 持有"
        elif score >= 20 and chg5_f > -5:
            action = "💎 持有"
        elif chg5_f < -8:
            action = "🔴 卖出止损"
        elif score < 15 and chg5_f < -3:
            action = "🟡 减仓"
        elif score < 10:
            action = "🔴 卖出"
        else:
            action = "💎 持有"

        return buy, action

    @staticmethod
    def _fmt_volume(v) -> str:
        try:
            v = float(v)
            if v >= 1e8:
                return f"{v / 1e8:.1f}亿"
            if v >= 1e4:
                return f"{v / 1e4:.0f}万"
            return f"{v:.0f}"
        except (ValueError, TypeError):
            return "-"

    def populate_results(self, candidates: list[dict]):
        red = QBrush(QColor("#ef5350"))
        green = QBrush(QColor("#26a69a"))
        orange = QBrush(QColor("#FF9800"))
        cyan = QBrush(QColor("#4fc3f7"))

        self.result_table.setRowCount(len(candidates))
        cols = ["代码", "名称", "板块", "策略", "价格", "RS", "评分",
                "VCP", "突破", "收缩", "量比", "离高点%"]
        for i, c in enumerate(candidates):
            for j, col in enumerate(cols):
                val = c.get(col, "")
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.result_table.setItem(i, j, item)

            buy_advice = c.get("建议买入", "")
            action_advice = c.get("建议操作", "")
            buy_item = QTableWidgetItem(buy_advice)
            action_item = QTableWidgetItem(action_advice)
            buy_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            action_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            if "买入" in buy_advice:
                buy_item.setForeground(red)
                buy_item.setFont(QFont("", 10, QFont.Weight.Bold))
            elif "观望" in buy_advice:
                buy_item.setForeground(orange)
            if "卖出" in action_advice:
                action_item.setForeground(green)
                action_item.setFont(QFont("", 10, QFont.Weight.Bold))
            elif "持有" in action_advice:
                action_item.setForeground(cyan)
            elif "加仓" in action_advice:
                action_item.setForeground(red)
                action_item.setFont(QFont("", 10, QFont.Weight.Bold))

            self.result_table.setItem(i, 12, buy_item)
            self.result_table.setItem(i, 13, action_item)

        self.status_label.setText(f"共 {len(candidates)} 只候选")
