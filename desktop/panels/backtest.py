"""回测分析面板"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSpinBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QGroupBox, QProgressBar, QTabWidget, QTextEdit,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor
import json


class BacktestPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        title = QLabel("📊 回测分析")
        title.setFont(QFont("", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        params = QHBoxLayout()
        params.addWidget(QLabel("策略:"))
        self.combo_strategy = QComboBox()
        self.combo_strategy.setMinimumWidth(180)
        params.addWidget(self.combo_strategy)

        params.addWidget(QLabel("样本数:"))
        self.spin_sample = QSpinBox()
        self.spin_sample.setRange(50, 500)
        self.spin_sample.setValue(200)
        params.addWidget(self.spin_sample)

        params.addWidget(QLabel("起始日:"))
        self.combo_start = QComboBox()
        self.combo_start.addItems(["20220101", "20220601", "20230101", "20230601", "20240101"])
        self.combo_start.setCurrentText("20220601")
        self.combo_start.setEditable(True)
        params.addWidget(self.combo_start)

        self.btn_run = QPushButton("🚀 运行回测")
        self.btn_run.setStyleSheet("font-size: 14px; padding: 10px 24px;")
        params.addWidget(self.btn_run)

        self.btn_monte_carlo = QPushButton("🎲 蒙特卡洛")
        params.addWidget(self.btn_monte_carlo)

        self.btn_walkforward = QPushButton("📐 Walk-Forward")
        params.addWidget(self.btn_walkforward)
        self.btn_multi_compare = QPushButton("🏆 多策略对比")
        self.btn_multi_compare.setStyleSheet("background:#7b1fa2; font-size:13px; padding:8px 16px;")
        params.addWidget(self.btn_multi_compare)
        params.addStretch()
        layout.addLayout(params)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_metrics_tab(), "核心指标")
        self.tabs.addTab(self._build_trades_tab(), "交易记录")
        self.tabs.addTab(self._build_mc_tab(), "蒙特卡洛")
        self.tabs.addTab(self._build_wf_tab(), "Walk-Forward")
        self.tabs.addTab(self._build_compare_tab(), "🏆 多策略对比")
        layout.addWidget(self.tabs)

    def _build_metrics_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.metrics_table = QTableWidget()
        self.metrics_table.setColumnCount(2)
        self.metrics_table.setHorizontalHeaderLabels(["指标", "值"])
        self.metrics_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.metrics_table.setAlternatingRowColors(True)
        layout.addWidget(self.metrics_table)
        self.chart_placeholder = QLabel("回测完成后将在此显示资金曲线")
        self.chart_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.chart_placeholder.setStyleSheet("color: #888; font-size: 14px; padding: 40px;")
        layout.addWidget(self.chart_placeholder)
        return w

    def _build_trades_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.trades_table = QTableWidget()
        self.trades_table.setColumnCount(11)
        self.trades_table.setHorizontalHeaderLabels([
            "代码", "名称", "板块", "买入日", "买入价", "卖出日", "卖出价",
            "盈亏%", "天数", "买入逻辑", "卖出逻辑",
        ])
        self.trades_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.trades_table.setAlternatingRowColors(True)
        self.trades_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.trades_table.setSortingEnabled(True)
        layout.addWidget(self.trades_table)
        return w

    def _build_mc_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.mc_table = QTableWidget()
        self.mc_table.setColumnCount(6)
        self.mc_table.setHorizontalHeaderLabels([
            "指标", "实际值", "模拟均值", "5%分位", "95%分位", "排名",
        ])
        self.mc_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.mc_table)
        self.mc_grade_label = QLabel("运行蒙特卡洛后显示结果")
        self.mc_grade_label.setFont(QFont("", 13))
        self.mc_grade_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.mc_grade_label)
        return w

    def _build_wf_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.wf_table = QTableWidget()
        self.wf_table.setColumnCount(11)
        self.wf_table.setHorizontalHeaderLabels([
            "窗口", "训练期", "验证期", "训练收益", "训练夏普", "训练胜率",
            "验证收益", "验证夏普", "验证胜率", "验证回撤", "衰减率",
        ])
        self.wf_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.wf_table)
        self.wf_summary_label = QLabel("运行 Walk-Forward 后显示结果")
        self.wf_summary_label.setFont(QFont("", 13))
        self.wf_summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.wf_summary_label)
        return w

    def _build_compare_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.compare_table = QTableWidget()
        self.compare_table.setColumnCount(10)
        self.compare_table.setHorizontalHeaderLabels([
            "策略", "总收益", "年化", "最大回撤", "夏普", "胜率",
            "盈亏比", "交易数", "均持天数", "综合排名",
        ])
        self.compare_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.compare_table.setAlternatingRowColors(True)
        self.compare_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.compare_table.setSortingEnabled(True)
        layout.addWidget(self.compare_table)
        self.compare_summary = QLabel("点击「🏆 多策略对比」运行4种策略并排对比")
        self.compare_summary.setFont(QFont("", 13))
        self.compare_summary.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.compare_summary)
        return w

    def update_metrics(self, result):
        items = [
            ("总收益率", f"{result.total_return:.2%}"),
            ("年化收益", f"{result.annual_return:.2%}"),
            ("最大回撤", f"{result.max_drawdown:.2%}"),
            ("夏普比率", f"{result.sharpe_ratio:.2f}"),
            ("Sortino", f"{getattr(result, 'sortino_ratio', 0):.2f}"),
            ("Calmar", f"{getattr(result, 'calmar_ratio', 0):.2f}"),
            ("胜率", f"{result.win_rate:.1%}"),
            ("盈亏比", f"{result.profit_loss_ratio:.2f}"),
            ("交易次数", str(result.total_trades)),
            ("平均持有天数", f"{result.avg_hold_days:.0f}"),
            ("最大连亏", str(result.max_consecutive_losses)),
        ]
        self.metrics_table.setRowCount(len(items))
        for i, (name, val) in enumerate(items):
            self.metrics_table.setItem(i, 0, QTableWidgetItem(name))
            self.metrics_table.setItem(i, 1, QTableWidgetItem(val))

    def update_trades(self, trades, names: dict = None, boards: dict = None):
        if names is None:
            names = {}
        if boards is None:
            boards = {}
        self.trades_table.setRowCount(len(trades))
        red = QColor("#ef5350")
        green = QColor("#26a69a")
        for i, t in enumerate(trades):
            code = t.code
            vals = [
                code, names.get(code, ""), boards.get(code, ""),
                t.entry_date, f"{t.entry_price:.2f}",
                t.exit_date, f"{t.exit_price:.2f}",
                f"{t.pnl_pct:.1%}", str(t.hold_days),
                str(getattr(t, "entry_reason", ""))[:30],
                str(t.exit_reason)[:30],
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 7:
                    pnl = t.pnl_pct
                    item.setForeground(red if pnl > 0 else green if pnl < 0 else QColor("#888"))
                self.trades_table.setItem(i, j, item)

    def update_metrics_local(self, result):
        """从 LocalBacktestResult 更新指标。"""
        items = [
            ("总收益率", f"{result.total_return:.2%}"),
            ("年化收益", f"{result.annual_return:.2%}"),
            ("最大回撤", f"{result.max_drawdown:.2%}"),
            ("夏普比率", f"{result.sharpe_ratio:.2f}"),
            ("胜率", f"{result.win_rate:.1%}"),
            ("盈亏比", f"{result.profit_loss_ratio:.2f}"),
            ("交易次数", str(result.total_trades)),
            ("胜/负", f"{result.winning_trades}/{result.losing_trades}"),
            ("平均持有天数", f"{result.avg_hold_days:.0f}"),
            ("最大连亏", str(result.max_consecutive_losses)),
        ]
        self.metrics_table.setRowCount(len(items))
        for i, (name, val) in enumerate(items):
            name_item = QTableWidgetItem(name)
            val_item = QTableWidgetItem(val)
            val_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.metrics_table.setItem(i, 0, name_item)
            self.metrics_table.setItem(i, 1, val_item)
        self.chart_placeholder.setText(
            f"收益 {result.total_return:.2%} | 回撤 {result.max_drawdown:.2%} | "
            f"夏普 {result.sharpe_ratio:.2f} | 胜率 {result.win_rate:.1%}"
        )

    def update_trades_local(self, trades: list[dict], names: dict = None, boards: dict = None):
        """从 dict 列表更新交易记录。"""
        if names is None:
            names = {}
        if boards is None:
            boards = {}
        self.trades_table.setRowCount(len(trades))
        red = QColor("#ef5350")
        green = QColor("#26a69a")
        for i, t in enumerate(trades):
            code = t.get("code", "")
            vals = [
                code, names.get(code, t.get("name", "")), boards.get(code, t.get("board", "")),
                t.get("entry_date", ""),
                f"{t.get('entry_price', 0):.2f}",
                t.get("exit_date", ""), f"{t.get('exit_price', 0):.2f}",
                f"{t.get('pnl_pct', 0):.1%}", str(t.get("hold_days", 0)),
                t.get("entry_reason", ""), t.get("reason", t.get("exit_reason", "")),
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(str(v))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 7:
                    pnl = t.get("pnl_pct", 0)
                    item.setForeground(red if pnl > 0 else green if pnl < 0 else QColor("#888"))
                self.trades_table.setItem(i, j, item)

    def update_equity_chart(self, equity_curve: list[dict]):
        """用 Plotly 在 chart_placeholder 位置渲染资金曲线。"""
        if not equity_curve:
            return
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            if not hasattr(self, "_equity_web"):
                self._equity_web = QWebEngineView()
                parent_layout = self.tabs.widget(0).layout()
                idx = parent_layout.indexOf(self.chart_placeholder)
                parent_layout.removeWidget(self.chart_placeholder)
                self.chart_placeholder.hide()
                parent_layout.insertWidget(idx, self._equity_web)

            dates = [e["date"] for e in equity_curve]
            values = [round(e["equity"], 2) for e in equity_curve]
            initial = values[0] if values else 1e6
            nav = [round(v / initial, 4) for v in values]

            traces = json.dumps([{
                "type": "scatter", "mode": "lines",
                "x": dates, "y": nav,
                "line": {"color": "#1976D2", "width": 2},
                "fill": "tozeroy", "fillcolor": "rgba(25,118,210,0.1)",
                "name": "策略净值",
            }])
            layout = json.dumps({
                "template": "plotly_dark",
                "paper_bgcolor": "#1a1a2e", "plot_bgcolor": "#1a1a2e",
                "margin": {"l": 50, "r": 20, "t": 10, "b": 30},
                "yaxis": {"title": "净值"},
                "legend": {"orientation": "h", "y": -0.1},
            })
            import pathlib as _pathlib
            _bt_html_path = _pathlib.Path(__file__).parent.parent / "resources" / "_bt_chart.html"
            _plotly_js_path = _pathlib.Path(__file__).parent.parent / "resources" / "plotly.min.js"
            _plotly_src_tag = f'<script src="file:///{_plotly_js_path.resolve().as_posix()}"></script>'
            html = f"""<!DOCTYPE html><html><head>
            {_plotly_src_tag}
            <style>html,body{{margin:0;height:100%;background:#1a1a2e;}}#c{{width:100%;height:100%;}}</style>
            </head><body><div id="c"></div><script>
            Plotly.newPlot('c',{traces},{layout},{{responsive:true,displayModeBar:false}});
            window.addEventListener('resize',function(){{Plotly.Plots.resize(document.getElementById('c'));}});
            </script></body></html>"""
            try:
                _bt_html_path.parent.mkdir(parents=True, exist_ok=True)
                _bt_html_path.write_text(html, encoding="utf-8")
                from PyQt6.QtCore import QUrl
                self._equity_web.setUrl(QUrl.fromLocalFile(str(_bt_html_path.resolve())))
            except Exception:
                self._equity_web.setHtml("<h3 style='color:#888;text-align:center;'>图表加载失败</h3>")
        except ImportError:
            self.chart_placeholder.setText(
                f"资金曲线：起始 ¥{equity_curve[0]['equity']:,.0f} → "
                f"终止 ¥{equity_curve[-1]['equity']:,.0f}"
            )
