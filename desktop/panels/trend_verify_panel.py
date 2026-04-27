"""走势验证面板"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QTextEdit, QSplitter, QComboBox, QLineEdit,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor


class TrendVerifyPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        title = QLabel("📊 走势验证")
        title.setFont(QFont("", 16, QFont.Weight.Bold))
        layout.addWidget(title)
        layout.addWidget(QLabel("记录每次选股信号，跟踪未来实际走势，验证策略有效性。点击任意行查看分析详情。"))

        # 控制行
        ctl = QHBoxLayout()
        self.btn_calibrate = QPushButton("🔄 校准走势")
        self.btn_calibrate.setStyleSheet("font-size: 13px; padding: 8px 16px; background: #FF6F00;")
        ctl.addWidget(self.btn_calibrate)
        self.btn_batch_failure = QPushButton("🧠 批量失败归因")
        self.btn_batch_failure.setStyleSheet("font-size: 13px; padding: 8px 16px; background: #6A1B9A;")
        ctl.addWidget(self.btn_batch_failure)
        self.btn_ai_analyze = QPushButton("🦀 AI深度分析选中行")
        self.btn_ai_analyze.setStyleSheet("font-size: 13px; padding: 8px 16px; background: #1565C0;")
        ctl.addWidget(self.btn_ai_analyze)
        ctl.addStretch()
        layout.addLayout(ctl)

        # 准确率汇总
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("font-size: 13px; color: #4fc3f7; padding: 6px;")
        self.stats_label.setWordWrap(True)
        layout.addWidget(self.stats_label)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("策略"))
        self.filter_strategy = QComboBox()
        self.filter_strategy.addItem("全部")
        filter_row.addWidget(self.filter_strategy)

        filter_row.addWidget(QLabel("根因"))
        self.filter_root_cause = QComboBox()
        self.filter_root_cause.addItem("全部")
        filter_row.addWidget(self.filter_root_cause)

        filter_row.addWidget(QLabel("市场环境"))
        self.filter_market = QComboBox()
        self.filter_market.addItem("全部")
        filter_row.addWidget(self.filter_market)

        filter_row.addWidget(QLabel("结果"))
        self.filter_result = QComboBox()
        self.filter_result.addItems(["全部", "仅失败", "仅正确", "仅待验证"])
        filter_row.addWidget(self.filter_result)

        self.filter_keyword = QLineEdit()
        self.filter_keyword.setPlaceholderText("代码 / 名称 / 板块 / 标签")
        self.filter_keyword.setClearButtonEnabled(True)
        filter_row.addWidget(self.filter_keyword)

        self.btn_reset_filters = QPushButton("重置筛选")
        filter_row.addWidget(self.btn_reset_filters)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        summary_group = QGroupBox("失败归因汇总")
        summary_layout = QVBoxLayout(summary_group)
        self.failure_summary = QTextEdit()
        self.failure_summary.setReadOnly(True)
        self.failure_summary.setMaximumHeight(120)
        self.failure_summary.setStyleSheet(
            "font-size:12px; background:#0d1117; color:#d0d7de; padding:8px; "
            "border:1px solid #30363d; border-radius:6px;"
        )
        self.failure_summary.setPlaceholderText("批量失败归因后，这里会显示失败根因、标签和策略分布汇总。")
        summary_layout.addWidget(self.failure_summary)
        layout.addWidget(summary_group)

        # 记录表
        self.table = QTableWidget()
        self.table.setColumnCount(19)
        self.table.setHorizontalHeaderLabels([
            "代码", "名称", "板块", "信号日", "信号价", "评分", "策略", "信号",
            "1日%", "2日%", "3日%", "5日%", "10日%", "20日%", "60日%", "结果", "归因", "标签", "分析原因",
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.cellClicked.connect(self._on_row_clicked)

        # 上下分割：表格 + 分析详情
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.table)

        # 分析详情面板
        detail_w = QWidget()
        detail_layout = QVBoxLayout(detail_w)
        detail_layout.setContentsMargins(4, 4, 4, 4)
        self.detail_title = QLabel("📋 点击上方任意行查看分析详情")
        self.detail_title.setFont(QFont("", 12, QFont.Weight.Bold))
        self.detail_title.setStyleSheet("color:#4fc3f7;")
        detail_layout.addWidget(self.detail_title)

        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setMaximumHeight(200)
        self.detail_text.setStyleSheet(
            "font-size:13px; background:#0d1117; color:#e0e0e0; padding:8px; "
            "border:1px solid #30363d; border-radius:6px;"
        )
        detail_layout.addWidget(self.detail_text)
        splitter.addWidget(detail_w)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

        self._all_records_cache = []
        self._records_cache = []
        self.filter_strategy.currentIndexChanged.connect(self._apply_filters)
        self.filter_root_cause.currentIndexChanged.connect(self._apply_filters)
        self.filter_market.currentIndexChanged.connect(self._apply_filters)
        self.filter_result.currentIndexChanged.connect(self._apply_filters)
        self.filter_keyword.textChanged.connect(self._apply_filters)
        self.btn_reset_filters.clicked.connect(self._reset_filters)

    def update_stats(self, stats: dict):
        if stats.get("total", 0) == 0:
            self.stats_label.setText("暂无校准数据，请先执行选股扫描并校准")
            return

        parts = [
            f"📊 总信号 {stats['total']} 个",
            f"✅ 正确 {stats['correct']} 个",
            f"准确率 {stats['accuracy']:.1f}%",
            f"1日均涨 {stats.get('avg_pnl_1d', 0):+.2f}%",
            f"2日均涨 {stats.get('avg_pnl_2d', 0):+.2f}%",
            f"3日均涨 {stats.get('avg_pnl_3d', 0):+.2f}%",
            f"5日均涨 {stats['avg_pnl_5d']:+.2f}%",
            f"10日均涨 {stats['avg_pnl_10d']:+.2f}%",
            f"20日均涨 {stats['avg_pnl_20d']:+.2f}%",
        ]

        by_type = stats.get("by_type", {})
        for st, d in by_type.items():
            parts.append(f"| {st}: {d['accuracy']:.0f}%准确({d['total']}个)")

        self.stats_label.setText(" | ".join(parts))

    def update_failure_summary(self, summary: dict):
        if summary.get("failed_total", 0) == 0:
            self.failure_summary.setText("暂无失败信号归因数据。可先校准走势，再执行“批量失败归因”。")
            return

        lines = [f"失败信号共 {summary.get('failed_total', 0)} 个"]
        markets = summary.get("top_market_regimes", [])
        if markets:
            lines.append("市场环境: " + " | ".join(f"{item['label']} {item['count']}个" for item in markets))
        roots = summary.get("top_root_causes", [])
        if roots:
            lines.append("Top根因: " + " | ".join(f"{item['label']} {item['count']}次" for item in roots))
        tags = summary.get("top_tags", [])
        if tags:
            lines.append("Top标签: " + " | ".join(f"{item['label']} {item['count']}次" for item in tags))
        strategies = summary.get("by_strategy", [])
        if strategies:
            lines.append("策略分布:")
            for item in strategies:
                lines.append(f"  • {item['strategy']}: 失败{item['failed']}个，主因 {item.get('top_cause') or '待归因'}")
        self.failure_summary.setText("\n".join(lines))

    def _reset_filters(self):
        self.filter_strategy.setCurrentIndex(0)
        self.filter_root_cause.setCurrentIndex(0)
        self.filter_market.setCurrentIndex(0)
        self.filter_result.setCurrentIndex(0)
        self.filter_keyword.clear()

    def _refresh_filter_options(self, records: list[dict]):
        current_strategy = self.filter_strategy.currentText()
        current_root = self.filter_root_cause.currentText()
        current_market = self.filter_market.currentText()

        strategies = sorted({(r.get("strategy") or "").strip() for r in records if (r.get("strategy") or "").strip()})
        roots = sorted({(r.get("root_cause") or "").strip() for r in records if (r.get("root_cause") or "").strip()})
        markets = sorted({(r.get("market_regime") or "").strip() for r in records if (r.get("market_regime") or "").strip()})

        for combo, values, current in [
            (self.filter_strategy, strategies, current_strategy),
            (self.filter_root_cause, roots, current_root),
            (self.filter_market, markets, current_market),
        ]:
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("全部")
            for value in values:
                combo.addItem(value)
            idx = combo.findText(current)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            combo.blockSignals(False)

    def _apply_filters(self):
        keyword = self.filter_keyword.text().strip().lower()
        strategy = self.filter_strategy.currentText()
        root_cause = self.filter_root_cause.currentText()
        market = self.filter_market.currentText()
        result_filter = self.filter_result.currentText()

        filtered = []
        for record in self._all_records_cache:
            if strategy != "全部" and (record.get("strategy") or "") != strategy:
                continue
            if root_cause != "全部" and (record.get("root_cause") or "") != root_cause:
                continue
            if market != "全部" and (record.get("market_regime") or "") != market:
                continue

            correct = record.get("correct", -1)
            if result_filter == "仅失败" and correct != 0:
                continue
            if result_filter == "仅正确" and correct != 1:
                continue
            if result_filter == "仅待验证" and correct != -1:
                continue

            if keyword:
                haystack = " ".join([
                    str(record.get("code", "")),
                    str(record.get("name", "")),
                    str(record.get("board", "")),
                    str(record.get("strategy", "")),
                    str(record.get("root_cause", "")),
                    " ".join(record.get("failure_tags", []) or []),
                ]).lower()
                if keyword not in haystack:
                    continue
            filtered.append(record)

        self._render_records(filtered)

    def _on_row_clicked(self, row, col):
        """点击行时显示分析详情。"""
        if not hasattr(self, "_records_cache") or row >= len(self._records_cache):
            return
        r = self._records_cache[row]
        code = r.get("code", "")
        name = r.get("name", "")
        board = r.get("board", "")
        sig_date = r.get("signal_date", "")
        sig_price = r.get("signal_price", 0)
        score = r.get("score", 0)
        strategy = r.get("strategy", "SEPA")
        analysis = r.get("analysis", "")
        root_cause = r.get("root_cause", "")
        failure_tags = r.get("failure_tags", []) or []
        improvement_hint = r.get("improvement_hint", "")
        market_regime = r.get("market_regime", "")

        self.detail_title.setText(
            f"📋 {code} {name}  [{board}]  策略: {strategy}  "
            f"信号日: {sig_date}  信号价: {sig_price}  评分: {score}"
        )

        lines = []

        # 策略来源
        lines.append(f"【策略来源】{strategy} 策略生成的选股信号")
        lines.append("")

        # 分析原因（分号分割→换行）
        if analysis and analysis != "待分析" and analysis != "-":
            lines.append(f"【{strategy} 策略分析原因】")
            for reason in analysis.split("；"):
                reason = reason.strip()
                if reason:
                    lines.append(f"  • {reason}")
        else:
            lines.append(f"【{strategy} 策略分析原因】暂无（点击「🦀 AI深度分析选中行」可触发AI分析）")

        lines.append("")

        lines.append("【结构化归因】")
        lines.append(f"  • 根因: {root_cause or '待归因'}")
        lines.append(f"  • 标签: {' / '.join(failure_tags) if failure_tags else '待归因'}")
        lines.append(f"  • 市场环境: {market_regime or '未知'}")
        lines.append(f"  • 改进建议: {improvement_hint or '待生成'}")
        lines.append("")

        # 走势数据汇总
        lines.append("【走势数据】")
        for period, key in [("1日", "pnl_1d"), ("2日", "pnl_2d"), ("3日", "pnl_3d"),
                            ("5日", "pnl_5d"), ("10日", "pnl_10d"), ("20日", "pnl_20d"),
                            ("60日", "pnl_60d")]:
            val = r.get(key)
            if val is not None:
                icon = "📈" if val > 0 else "📉" if val < 0 else "➡️"
                lines.append(f"  {icon} {period}: {val:+.2f}%")

        lines.append("")

        # 结论
        correct = r.get("correct", -1)
        if correct == 1:
            lines.append(f"【结论】✅ {strategy} 策略信号正确 — 该策略在 {name} 上有效")
        elif correct == 0:
            lines.append(f"【结论】❌ {strategy} 策略信号错误 — 需分析原因，考虑调整 {strategy} 参数")
        else:
            lines.append(f"【结论】⏳ {strategy} 策略待验证 — 数据不足")

        self.detail_text.setText("\n".join(lines))
        self._selected_row = row

    def update_records(self, records: list[dict]):
        self._all_records_cache = list(records or [])
        self._refresh_filter_options(self._all_records_cache)
        self._apply_filters()

    def _render_records(self, records: list[dict]):
        self._records_cache = records
        red = QColor("#ef5350")
        green = QColor("#26a69a")
        gold = QColor("#FFD740")

        self.table.setRowCount(len(records))
        for i, r in enumerate(records):
            def _f(v):
                return f"{v:+.2f}%" if v is not None else "-"

            correct = r.get("correct", -1)
            if correct == 1:
                result_text = "✅ 正确"
            elif correct == 0:
                result_text = "❌ 错误"
            else:
                result_text = "⏳ 待验证"

            # 统一信号显示：去掉原始 emoji 前缀，按评分重新标注
            raw_signal = (r.get("signal_type", "") or "建议买入").replace("🟢 ", "").replace("🔵 ", "").replace("🟡 ", "")
            score_val = r.get("score", 0) or 0
            try:
                score_val = int(score_val)
            except (ValueError, TypeError):
                score_val = 0
            if score_val >= 70:
                signal_display = f"强烈买入"
            elif score_val >= 50:
                signal_display = f"建议买入"
            else:
                signal_display = raw_signal or "观望"

            # 策略名称
            strategy = r.get("strategy", "SEPA") or "SEPA"

            vals = [
                r.get("code", ""), r.get("name", ""), r.get("board", ""),
                r.get("signal_date", ""), f"{r.get('signal_price', 0):.2f}",
                str(r.get("score", "")),
                strategy,
                signal_display,
                _f(r.get("pnl_1d")), _f(r.get("pnl_2d")),
                _f(r.get("pnl_3d")), _f(r.get("pnl_5d")), _f(r.get("pnl_10d")),
                _f(r.get("pnl_20d")), _f(r.get("pnl_60d")),
                result_text,
                r.get("root_cause", "") or "-",
                " / ".join(r.get("failure_tags", []) or []) or "-",
                r.get("analysis", "") or "-",
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                # 策略列颜色（列6）
                if j == 6:
                    _strat_colors = {
                        "SEPA": "#CE93D8", "CANSLIM": "#4fc3f7", "TURTLE": "#66BB6A",
                        "GRAHAM": "#FF7043", "BUFFETT": "#FFD740", "LYNCH": "#ef5350",
                    }
                    item.setForeground(QColor(_strat_colors.get(v.upper(), "#4fc3f7")))
                    item.setFont(QFont("", 10, QFont.Weight.Bold))
                # 信号列颜色（列7）
                if j == 7:
                    if "强烈" in v:
                        item.setForeground(red)
                        item.setFont(QFont("", 10, QFont.Weight.Bold))
                    elif "建议" in v:
                        item.setForeground(QColor("#4fc3f7"))
                    else:
                        item.setForeground(QColor("#888"))
                # 涨跌颜色（列8-14）
                if 8 <= j <= 14 and v != "-":
                    try:
                        fv = float(v.replace("%", "").replace("+", ""))
                        item.setForeground(red if fv > 0 else green if fv < 0 else QColor("#888"))
                        item.setFont(QFont("", 10, QFont.Weight.Bold))
                    except Exception:
                        pass
                # 结果颜色（列15）
                if j == 15:
                    if "正确" in v:
                        item.setForeground(red)
                    elif "错误" in v:
                        item.setForeground(green)
                    else:
                        item.setForeground(gold)
                    item.setFont(QFont("", 10, QFont.Weight.Bold))
                # 归因/标签/分析列左对齐
                if j in (16, 17, 18):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(i, j, item)
