"""选股雷达面板 + 自定义板块"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSpinBox, QTableWidget, QTableWidgetItem, QLineEdit,
    QHeaderView, QGroupBox, QProgressBar, QTreeWidget, QTreeWidgetItem,
    QSplitter, QTabWidget, QStackedWidget, QCheckBox,
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

        self.inner_tabs = QTabWidget()
        self.inner_tabs.addTab(self._build_board_tab(), "⭐ 自定义板块")
        self.inner_tabs.addTab(self._build_scan_tab(), "🔍 扫描选股")
        self.inner_tabs.addTab(self._build_quantum_tab(), "⚛️ 量子优化")
        self.inner_tabs.addTab(self._build_commodity_tab(), "🥇 黄金/大宗")
        # 走势验证和回测子tab由外部注入
        self._verify_tab_idx = -1
        self._backtest_tab_idx = -1
        layout.addWidget(self.inner_tabs)

    def add_verify_tab(self, widget):
        """外部注入走势验证面板。"""
        self._verify_tab_idx = self.inner_tabs.addTab(widget, "✅ 走势验证")

    def add_backtest_tab(self, widget):
        """外部注入回测面板。"""
        self._backtest_tab_idx = self.inner_tabs.addTab(widget, "📊 回测")

    def _build_board_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        top = QHBoxLayout()
        self.btn_refresh_boards = QPushButton("🔄 刷新成分股")
        self.btn_scan_board = QPushButton("🔍 扫描选中板块")
        self.btn_sync_data = QPushButton("📥 补全板块数据")
        self.btn_sync_data.setToolTip("从网络拉取缺失股票的日线数据，让所有个股都能计算评分")
        self.btn_push_strong_buy = QPushButton("📤 推送强烈买入")
        self.btn_push_strong_buy.setStyleSheet("padding:6px 14px; background:#E65100; color:white;")
        self.btn_push_strong_buy.setToolTip("将当前板块中「强烈买入」的股票推送到微信/企业微信")
        top.addWidget(self.btn_refresh_boards)
        top.addWidget(self.btn_scan_board)
        top.addWidget(self.btn_sync_data)
        top.addWidget(self.btn_push_strong_buy)
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

    # ===== 量子优化 =====
    _QUANTUM_STRATEGIES = [
        ("markowitz_qaoa", "Markowitz均值-方差 + QAOA", "经典组合优化问题的量子求解"),
        ("markowitz_qa", "Markowitz均值-方差 + 量子退火", "模拟量子退火搜索最优组合"),
        ("min_variance", "最小方差组合", "不追求收益最大化，只追求风险最小化"),
        ("risk_parity_q", "风险平价 + 量子优化", "各资产风险贡献相等的量子求解"),
        ("max_diversification", "最大分散化组合", "最大化组合分散度（相关性最低）"),
        ("cvar_optimization", "CVaR条件风险优化", "尾部风险控制，比VaR更保守"),
        ("momentum_quantum", "动量因子 + 量子组合", "先用动量因子筛选，再量子优化配置"),
        ("strategy_fusion", "策略融合 + 量子优化", "基于扫描选股结果，量子优化最终组合"),
    ]

    def _build_quantum_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 4, 4, 4)

        title_label = QLabel("⚛️ 量子组合优化选股")
        title_label.setFont(QFont("", 14, QFont.Weight.Bold))
        title_label.setStyleSheet("color:#CE93D8;")
        layout.addWidget(title_label)

        # 两个子模式切换
        quantum_inner = QTabWidget()
        quantum_inner.addTab(self._build_quantum_strategy_mode(), "🔗 策略融合模式")
        quantum_inner.addTab(self._build_quantum_pure_mode(), "⚛️ 纯量子优化模式")
        layout.addWidget(quantum_inner)
        return w

    def _build_quantum_strategy_mode(self) -> QWidget:
        """策略融合模式：结合传统策略 + 量子优化。"""
        w = QWidget()
        layout = QVBoxLayout(w)

        # 模式选择
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("优化模式:"))
        self.quantum_mode = QComboBox()
        self.quantum_mode.setMinimumWidth(300)
        for sid, name, desc in self._QUANTUM_STRATEGIES:
            self.quantum_mode.addItem(f"{name}", sid)
        self.quantum_mode.currentIndexChanged.connect(self._on_quantum_mode_changed)
        mode_row.addWidget(self.quantum_mode)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        self.quantum_mode_desc = QLabel(self._QUANTUM_STRATEGIES[0][2])
        self.quantum_mode_desc.setStyleSheet("color:#8b949e; font-size:11px; padding:2px 0 6px 0;")
        layout.addWidget(self.quantum_mode_desc)

        # 参数行
        param_row = QHBoxLayout()
        param_row.addWidget(QLabel("选股数:"))
        self.quantum_spin = QSpinBox()
        self.quantum_spin.setRange(3, 15)
        self.quantum_spin.setValue(5)
        param_row.addWidget(self.quantum_spin)

        param_row.addWidget(QLabel("风险厌恶:"))
        self.quantum_lambda = QComboBox()
        self.quantum_lambda.addItems(["0.5 (激进)", "1.0 (均衡)", "1.5 (稳健)", "2.0 (保守)", "3.0 (极保守)"])
        self.quantum_lambda.setCurrentIndex(1)
        param_row.addWidget(self.quantum_lambda)

        param_row.addWidget(QLabel("数据源:"))
        self.quantum_source = QComboBox()
        self.quantum_source.addItems(["全部板块成分股", "扫描选股结果(Top100)", "手动输入代码"])
        param_row.addWidget(self.quantum_source)

        self.btn_quantum_run = QPushButton("⚛️ 运行量子优化")
        self.btn_quantum_run.setStyleSheet("font-size:13px; padding:8px 18px; background:#7b1fa2;")
        param_row.addWidget(self.btn_quantum_run)
        param_row.addStretch()
        layout.addLayout(param_row)

        # 手动代码输入（默认隐藏）
        self.quantum_codes_input = QLineEdit()
        self.quantum_codes_input.setPlaceholderText("输入股票代码，逗号分隔（如 600519,300750,002594）")
        self.quantum_codes_input.setVisible(False)
        layout.addWidget(self.quantum_codes_input)

        self.quantum_status = QLabel("选择优化模式和参数，点击运行")
        self.quantum_status.setStyleSheet("color:#4fc3f7; font-size:12px; padding:4px;")
        self.quantum_status.setWordWrap(True)
        layout.addWidget(self.quantum_status)

        # 结果表（扩展列）
        self.quantum_table = QTableWidget()
        self.quantum_table.setColumnCount(10)
        self.quantum_table.setHorizontalHeaderLabels([
            "方法", "代码", "名称", "权重%", "预期收益%", "预期风险%",
            "夏普", "约束", "能量值", "用时ms",
        ])
        self.quantum_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.quantum_table.setAlternatingRowColors(True)
        self.quantum_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.quantum_table.setSortingEnabled(True)
        layout.addWidget(self.quantum_table)

        # 策略说明区
        info_label = QLabel(
            "📚 量子组合优化策略清单:\n"
            "1. Markowitz均值-方差+QAOA — 经典投资组合理论的量子变分求解\n"
            "2. Markowitz均值-方差+量子退火 — 用模拟退火(含量子隧穿)搜索最优\n"
            "3. 最小方差组合 — 不考虑收益，纯粹最小化风险\n"
            "4. 风险平价+量子优化 — 各资产风险贡献相等\n"
            "5. 最大分散化组合 — 最大化组合内分散度(相关性最低)\n"
            "6. CVaR条件风险优化 — 控制尾部极端风险\n"
            "7. 动量因子+量子组合 — 先选动量强股，再量子优化配置\n"
            "8. 策略融合+量子优化 — 基于扫描选股评分，量子优化最终组合(推荐)"
        )
        info_label.setStyleSheet("color:#666; font-size:11px; padding:6px; background:#0d1117; border-radius:6px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        return w

    def _build_quantum_pure_mode(self) -> QWidget:
        """纯量子组合优化：不依赖传统策略，直接对所选股票池做量子优化。"""
        w = QWidget()
        layout = QVBoxLayout(w)

        desc = QLabel(
            "纯量子组合优化：直接对候选股票池使用 QAOA / 量子退火 / Tabu Search 等算法\n"
            "进行全局最优化搜索，不依赖传统策略评分，结果由数学模型驱动。"
        )
        desc.setStyleSheet("color:#8b949e; font-size:11px; padding:4px 0 8px 0;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        cfg_row1 = QHBoxLayout()
        cfg_row1.addWidget(QLabel("算法:"))
        self.pure_q_algo = QComboBox()
        self.pure_q_algo.addItems([
            "QAOA 量子近似优化",
            "模拟退火 (量子隧穿)",
            "Tabu Search 禁忌搜索",
            "SA + QAOA 混合",
            "暴力枚举 (≤12只)",
            "Monte Carlo 随机采样",
        ])
        cfg_row1.addWidget(self.pure_q_algo)

        cfg_row1.addWidget(QLabel("目标:"))
        self.pure_q_obj = QComboBox()
        self.pure_q_obj.addItems([
            "最大夏普比率",
            "最小方差",
            "最大收益(激进)",
            "最低CVaR(保守)",
        ])
        cfg_row1.addWidget(self.pure_q_obj)
        cfg_row1.addStretch()
        layout.addLayout(cfg_row1)

        cfg_row2 = QHBoxLayout()
        cfg_row2.addWidget(QLabel("选股数:"))
        self.pure_q_spin = QSpinBox()
        self.pure_q_spin.setRange(2, 15)
        self.pure_q_spin.setValue(5)
        cfg_row2.addWidget(self.pure_q_spin)

        cfg_row2.addWidget(QLabel("风险厌恶 λ:"))
        self.pure_q_lambda = QComboBox()
        self.pure_q_lambda.addItems(["0.5", "1.0", "1.5", "2.0", "3.0"])
        self.pure_q_lambda.setCurrentIndex(1)
        cfg_row2.addWidget(self.pure_q_lambda)

        cfg_row2.addWidget(QLabel("数据源:"))
        self.pure_q_source = QComboBox()
        self.pure_q_source.addItems(["全部板块成分股", "扫描选股结果(Top100)", "手动输入代码"])
        self.pure_q_source.currentTextChanged.connect(
            lambda t: self.pure_q_codes_input.setVisible(t == "手动输入代码")
        )
        cfg_row2.addWidget(self.pure_q_source)

        self.btn_pure_q_run = QPushButton("⚛️ 运行纯量子优化")
        self.btn_pure_q_run.setStyleSheet(
            "font-size:13px; padding:8px 18px; background:#1a237e; color:#90caf9;"
        )
        cfg_row2.addWidget(self.btn_pure_q_run)
        cfg_row2.addStretch()
        layout.addLayout(cfg_row2)

        self.pure_q_codes_input = QLineEdit()
        self.pure_q_codes_input.setPlaceholderText("股票代码，逗号分隔，如 600519,300750,002594")
        self.pure_q_codes_input.setVisible(False)
        layout.addWidget(self.pure_q_codes_input)

        self.pure_q_status = QLabel("配置参数后点击运行")
        self.pure_q_status.setStyleSheet("color:#4fc3f7; font-size:12px; padding:4px;")
        self.pure_q_status.setWordWrap(True)
        layout.addWidget(self.pure_q_status)

        # 结果表
        self.pure_q_table = QTableWidget()
        self.pure_q_table.setColumnCount(9)
        self.pure_q_table.setHorizontalHeaderLabels([
            "算法", "代码", "名称", "权重%", "预期收益%", "预期风险%", "夏普", "能量值", "用时ms",
        ])
        self.pure_q_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.pure_q_table.setAlternatingRowColors(True)
        self.pure_q_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.pure_q_table.setSortingEnabled(True)
        layout.addWidget(self.pure_q_table)

        return w

    def update_pure_quantum(self, results: list[dict]):
        """更新纯量子优化结果表（每只股票单独一行）。"""
        red = QColor("#ef5350")
        green = QColor("#26a69a")
        blue = QColor("#90caf9")
        gold = QColor("#FFD740")
        self.pure_q_table.setSortingEnabled(False)
        self.pure_q_table.setRowCount(len(results))
        for i, r in enumerate(results):
            method = r.get("method", "")
            energy = r.get("energy")
            runtime = r.get("runtime_ms")

            vals = [
                method,
                r.get("code", ""),
                r.get("name", ""),
                f"{r.get('weight', 0):.1f}",
                f"{r.get('stock_return', 0):+.2f}",
                f"{r.get('stock_risk', 0):.2f}",
                f"{r.get('stock_sharpe', 0):.2f}",
                f"{energy:.4f}" if energy is not None else "0.0000",
                f"{runtime:.0f}" if runtime is not None else "0",
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 0 and method:
                    item.setForeground(gold if r.get("is_best") else blue)
                    item.setFont(QFont("", 10, QFont.Weight.Bold))
                if j == 4:
                    try:
                        fv = float(v)
                        item.setForeground(red if fv > 0 else green if fv < 0 else QColor("#888"))
                    except Exception:
                        pass
                if j == 6:
                    try:
                        fv = float(v)
                        item.setForeground(red if fv > 1 else green if fv < 0 else QColor("#888"))
                    except Exception:
                        pass
                if r.get("is_best") and j in (1, 2):
                    item.setForeground(gold)
                self.pure_q_table.setItem(i, j, item)
        self.pure_q_table.setSortingEnabled(True)

    def _on_quantum_mode_changed(self, idx):
        if 0 <= idx < len(self._QUANTUM_STRATEGIES):
            self.quantum_mode_desc.setText(self._QUANTUM_STRATEGIES[idx][2])
        self.quantum_codes_input.setVisible(
            self.quantum_source.currentText() == "手动输入代码"
        )

    def update_quantum(self, results: list[dict]):
        """更新量子优化结果表（展开为每只股票一行）。"""
        red = QColor("#ef5350")
        green = QColor("#26a69a")
        purple = QColor("#CE93D8")
        gold = QColor("#FFD740")

        # 展开：每个方法的每只股票一行
        rows = []
        for r in results:
            if not r.get("valid"):
                rows.append({
                    "method": r.get("method", ""), "code": "", "name": "",
                    "weight": "", "ret": "", "risk": "", "sharpe": "",
                    "constraint": "N", "energy": "", "runtime": "",
                })
                continue
            codes = r.get("selected_codes", [])
            names = r.get("selected_names", [])
            weights = r.get("weights", [])
            method = r.get("method", "")
            ret = f"{r.get('portfolio_return', 0):+.2f}"
            risk = f"{r.get('portfolio_risk', 0):.2f}"
            sharpe = f"{r.get('sharpe_ratio', 0):.2f}"
            constraint = "Y" if r.get("constraint_satisfied") else "N"
            energy = f"{r.get('energy', 0):.4f}"
            runtime = f"{r.get('runtime_ms', 0):.0f}"
            is_best = r.get("is_best", False)
            n = len(codes)
            for k in range(max(n, 1)):
                rows.append({
                    "method": method,
                    "code": codes[k] if k < len(codes) else "",
                    "name": names[k] if k < len(names) else "",
                    "weight": f"{weights[k]*100:.1f}" if k < len(weights) else "",
                    "ret": ret, "risk": risk, "sharpe": sharpe,
                    "constraint": constraint, "energy": energy,
                    "runtime": runtime, "is_best": is_best,
                })

        self.quantum_table.setSortingEnabled(False)
        self.quantum_table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            vals = [
                row["method"], row["code"], row["name"], row["weight"],
                row["ret"], row["risk"], row["sharpe"],
                row["constraint"], row["energy"], row["runtime"],
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 0 and v:
                    item.setForeground(gold if row.get("is_best") else purple)
                    item.setFont(QFont("", 10, QFont.Weight.Bold))
                if j == 6 and v:
                    try:
                        fv = float(v)
                        item.setForeground(red if fv > 1 else green if fv < 0 else QColor("#888"))
                    except Exception:
                        pass
                if row.get("is_best") and j in (1, 2):
                    item.setForeground(gold)
                self.quantum_table.setItem(i, j, item)
        self.quantum_table.setSortingEnabled(True)

    # ===== 黄金/大宗商品 =====
    def _build_commodity_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(QLabel("🥇 黄金、原油、大宗商品 ETF/期货相关标的"))

        ctl = QHBoxLayout()
        self.btn_commodity_load = QPushButton("📥 加载商品行情")
        self.btn_commodity_load.setStyleSheet("font-size:13px; padding:8px 16px;")
        ctl.addWidget(self.btn_commodity_load)
        ctl.addStretch()
        layout.addLayout(ctl)

        self.commodity_table = QTableWidget()
        self.commodity_table.setColumnCount(8)
        self.commodity_table.setHorizontalHeaderLabels([
            "代码", "名称", "类型", "最新价", "涨跌%", "5日%", "20日%", "信号",
        ])
        self.commodity_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.commodity_table.setAlternatingRowColors(True)
        self.commodity_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.commodity_table.setSortingEnabled(True)
        layout.addWidget(self.commodity_table)
        return w

    def update_commodities(self, items: list[dict]):
        red = QColor("#ef5350")
        green = QColor("#26a69a")
        gold = QColor("#FFD740")
        self.commodity_table.setRowCount(len(items))
        for i, c in enumerate(items):
            vals = [
                c.get("code", ""), c.get("name", ""), c.get("type", ""),
                f"{c.get('price', 0):.3f}", f"{c.get('pct', 0):+.2f}%",
                f"{c.get('pct_5d', 0):+.2f}%", f"{c.get('pct_20d', 0):+.2f}%",
                c.get("signal", ""),
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j in (4, 5, 6):
                    try:
                        fv = float(v.replace("%", "").replace("+", ""))
                        item.setForeground(red if fv > 0 else green if fv < 0 else QColor("#888"))
                    except Exception:
                        pass
                if j == 2 and "黄金" in v:
                    item.setForeground(gold)
                self.commodity_table.setItem(i, j, item)
