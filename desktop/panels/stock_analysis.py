"""个股分析面板"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QTabWidget, QCheckBox, QComboBox, QGridLayout,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor
import numpy as np
import json
from desktop.ui_tokens import APP_FONT


class StockAnalysisPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        title = QLabel("📉 个股分析")
        title.setFont(QFont("", APP_FONT["page_title"], QFont.Weight.Bold))
        layout.addWidget(title)

        input_row = QHBoxLayout()
        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("输入股票代码，例如 603881")
        self.code_input.setMinimumWidth(200)
        input_row.addWidget(self.code_input)

        self.btn_analyze = QPushButton("分析")
        self.btn_analyze.setStyleSheet(
            f"font-size: {APP_FONT['section']}px; padding: 8px 20px;"
        )
        input_row.addWidget(self.btn_analyze)

        self.btn_refresh = QPushButton("🔄 强制刷新")
        input_row.addWidget(self.btn_refresh)

        quick_codes = ["603881", "002975", "688001", "300604", "002150"]
        for qc in quick_codes:
            btn = QPushButton(qc)
            btn.setStyleSheet("padding: 6px 12px;")
            btn.clicked.connect(lambda checked, c=qc: self._quick_code(c))
            input_row.addWidget(btn)
        input_row.addStretch()
        layout.addLayout(input_row)

        self.header_label = QLabel("")
        self.header_label.setFont(QFont("", APP_FONT["section"], QFont.Weight.Bold))
        layout.addWidget(self.header_label)

        metrics = QHBoxLayout()
        self.metric_labels = {}
        for name in ["MA50", "MA150", "MA200", "52周高点", "52周低点", "RS评级"]:
            lbl = QLabel(f"{name}: -")
            lbl.setStyleSheet(f"font-size: {APP_FONT['body']}px;")
            metrics.addWidget(lbl)
            self.metric_labels[name] = lbl
        layout.addLayout(metrics)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_chart_tab(), "K线图")
        self.tabs.addTab(self._build_trend_tab(), "趋势模板")
        self.tabs.addTab(self._build_prediction_tab(), "多策略预测")
        layout.addWidget(self.tabs)

    def _quick_code(self, code: str):
        self.code_input.setText(code)
        self.btn_analyze.click()

    def _build_chart_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        # 周期切换按钮
        period_row = QHBoxLayout()
        self._period_buttons = {}
        self.current_period = "daily"
        for label, key in [("日K", "daily"), ("周K", "weekly"), ("月K", "monthly"), ("季K", "quarterly")]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(key == "daily")
            btn.setStyleSheet(
                f"QPushButton {{ padding:4px 14px; font-size:{APP_FONT['body']}px; background:#1a1a2e; color:#8b949e; "
                "border:1px solid #30363d; border-radius:4px; }"
                "QPushButton:checked { background:#1f6feb; color:#fff; border-color:#1f6feb; }"
                "QPushButton:hover { background:#21262d; }"
            )
            btn.clicked.connect(lambda checked, k=key: self._on_period_change(k))
            period_row.addWidget(btn)
            self._period_buttons[key] = btn
        period_row.addStretch()
        layout.addLayout(period_row)

        self._has_chart = False
        self.web_view = None
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            self.web_view = QWebEngineView()
            layout.addWidget(self.web_view, stretch=1)
            self._has_chart = True
        except ImportError:
            lbl = QLabel("需要安装 PyQt6-WebEngine 才能显示 K 线图")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(lbl)

        # 策略预测线勾选框
        self._strategy_checkboxes = {}
        self._strategy_colors = {}
        self._pred_palette = ["#3F51B5", "#009688", "#FF9800", "#9C27B0", "#00ACC1", "#8BC34A", "#FF5252", "#FFD740"]
        self._strategy_check_layout = QHBoxLayout()
        self._strategy_check_layout.setSpacing(8)
        lbl = QLabel("预测线：")
        lbl.setStyleSheet(f"color: #888; font-size: {APP_FONT['body']}px;")
        self._strategy_check_layout.addWidget(lbl)
        self._strategy_check_layout.addStretch()
        layout.addLayout(self._strategy_check_layout)

        self._cached_chart_args = None
        return w

    def _on_period_change(self, period: str):
        """切换 K 线周期（日/周/月/季），重新渲染图表。"""
        self.current_period = period
        for k, btn in self._period_buttons.items():
            btn.setChecked(k == period)
        if hasattr(self, "_raw_daily_data") and self._raw_daily_data:
            dates, opens, highs, lows, closes = self._raw_daily_data
            converted = self._convert_period(dates, opens, highs, lows, closes, period)
            preds = self._cached_chart_args[5] if hasattr(self, "_cached_chart_args") and len(self._cached_chart_args) > 5 else None
            self.update_chart(*converted, predictions=preds, _skip_raw_save=True)

    @staticmethod
    def _convert_period(dates, opens, highs, lows, closes, period):
        """将日线数据转为周/月/季线。"""
        if period == "daily":
            return dates, opens, highs, lows, closes

        import datetime as _dt
        groups = {}
        for i, d in enumerate(dates):
            ds = str(d)[:10]
            try:
                dt = _dt.date.fromisoformat(ds)
            except Exception:
                continue
            if period == "weekly":
                key = dt - _dt.timedelta(days=dt.weekday())
            elif period == "monthly":
                key = dt.replace(day=1)
            else:
                q = (dt.month - 1) // 3
                key = dt.replace(month=q * 3 + 1, day=1)
            if key not in groups:
                groups[key] = {"dates": [], "o": [], "h": [], "l": [], "c": []}
            g = groups[key]
            g["dates"].append(ds)
            g["o"].append(float(opens[i]))
            g["h"].append(float(highs[i]))
            g["l"].append(float(lows[i]))
            g["c"].append(float(closes[i]))

        sorted_keys = sorted(groups.keys())
        r_dates = [str(k) for k in sorted_keys]
        r_opens = [groups[k]["o"][0] for k in sorted_keys]
        r_highs = [max(groups[k]["h"]) for k in sorted_keys]
        r_lows = [min(groups[k]["l"]) for k in sorted_keys]
        r_closes = [groups[k]["c"][-1] for k in sorted_keys]
        return r_dates, r_opens, r_highs, r_lows, r_closes

    def _setup_strategy_checkboxes(self, predictions):
        """根据策略列表动态生成勾选框。"""
        self._updating_checkboxes = True
        for cb in self._strategy_checkboxes.values():
            cb.stateChanged.disconnect()
            self._strategy_check_layout.removeWidget(cb)
            cb.deleteLater()
        self._strategy_checkboxes.clear()
        self._strategy_colors.clear()

        if not predictions:
            self._updating_checkboxes = False
            return

        for idx, pred in enumerate(predictions):
            name = pred.get("name", f"策略{idx+1}")
            color = self._pred_palette[idx % len(self._pred_palette)]
            cb = QCheckBox(name)
            cb.setChecked(True)
            cb.setStyleSheet(
                f"color: {color}; font-size: {APP_FONT['emphasis']}px; font-weight: bold; padding: 1px 0;"
            )
            self._strategy_check_layout.addWidget(cb)
            self._strategy_checkboxes[name] = cb
            self._strategy_colors[name] = color

        for cb in self._strategy_checkboxes.values():
            cb.stateChanged.connect(self._on_strategy_checkbox_changed)
        self._updating_checkboxes = False

    def _on_strategy_checkbox_changed(self):
        """勾选框变化时重绘图表（防止递归）。"""
        if getattr(self, "_updating_checkboxes", False):
            return
        if self._cached_chart_args:
            self.update_chart(*self._cached_chart_args)

    def update_chart(self, dates, opens, highs, lows, closes, predictions=None, _skip_raw_save=False):
        """用 Plotly 生成 K 线图 HTML，加载到 WebEngine。"""
        if not self._has_chart or self.web_view is None:
            return

        if not _skip_raw_save:
            self._raw_daily_data = (dates, opens, highs, lows, closes)
        self._cached_chart_args = (dates, opens, highs, lows, closes, predictions)
        new_names = [p.get("name", f"策略{i}") for i, p in enumerate(predictions or [])]
        old_names = list(self._strategy_checkboxes.keys())
        if new_names != old_names:
            self._setup_strategy_checkboxes(predictions)
        n = len(closes)
        if n < 5:
            return

        show_n = min(n, 250)
        date_strs = [str(d)[:10] for d in dates[-show_n:]]
        o_arr = [float(v) for v in opens[-show_n:]]
        h_arr = [float(v) for v in highs[-show_n:]]
        l_arr = [float(v) for v in lows[-show_n:]]
        c_arr = [float(v) for v in closes[-show_n:]]
        all_closes = np.array(closes, dtype=float)

        # 构建 Plotly traces JSON
        traces = []
        # K 线
        traces.append({
            "type": "candlestick",
            "x": date_strs,
            "open": o_arr, "high": h_arr, "low": l_arr, "close": c_arr,
            "increasing": {"line": {"color": "#ef5350"}},
            "decreasing": {"line": {"color": "#26a69a"}},
            "name": "K线",
        })

        # MA 均线
        for ma_len, color, ma_name in [(50, "#FF9800", "MA50"), (150, "#2196F3", "MA150"), (200, "#9C27B0", "MA200")]:
            if n >= ma_len:
                ma = np.convolve(all_closes, np.ones(ma_len) / ma_len, mode="valid")
                ma_dates = date_strs[show_n - len(ma[-show_n:]):]
                ma_vals = [round(float(v), 2) for v in ma[-len(ma_dates):]]
                traces.append({
                    "type": "scatter", "mode": "lines",
                    "x": ma_dates, "y": ma_vals,
                    "line": {"color": color, "width": 1.5},
                    "name": ma_name,
                })

        # 回测预测线
        if n >= 60:
            window = 60
            bt_dates, bt_vals = [], []
            bt_start = max(window, n - show_n)
            for i in range(bt_start, n):
                seg = all_closes[i - window:i]
                x_seg = np.arange(window)
                slope, intercept = np.polyfit(x_seg, seg, 1)
                pred = float(np.mean(seg[-20:])) * 0.3 + (intercept + slope * window) * 0.7
                idx_in_show = i - (n - show_n)
                if 0 <= idx_in_show < show_n:
                    bt_dates.append(date_strs[idx_in_show])
                    bt_vals.append(round(pred, 2))
            if bt_dates:
                traces.append({
                    "type": "scatter", "mode": "lines",
                    "x": bt_dates, "y": bt_vals,
                    "line": {"color": "#E91E63", "width": 2, "dash": "dot"},
                    "name": "回测预测",
                })

        # 未来预测线
        if n >= 60:
            window = 60
            recent = all_closes[-window:]
            slope, intercept = np.polyfit(np.arange(window), recent, 1)
            daily_slope = slope
            ma50_now = float(np.mean(all_closes[-50:])) if n >= 50 else float(all_closes[-1])
            volatility = float(np.std(recent[-20:]))
            last_price = float(all_closes[-1])
            last_date = date_strs[-1]

            import datetime as _dt
            try:
                base_date = _dt.date.fromisoformat(last_date)
            except Exception:
                base_date = _dt.date.today()
            fc_dates = [(base_date + _dt.timedelta(days=int(d * 1.5))).isoformat() for d in range(1, 21)]

            def _sim(tw, rw, vs, seed):
                rng = np.random.RandomState(seed)
                path = [last_price]
                for d in range(1, 21):
                    prev = path[-1]
                    path.append(max(prev * 0.9, prev + daily_slope * tw + (ma50_now - prev) * rw * 0.02 + rng.normal(0, volatility * vs)))
                return [round(v, 2) for v in path[1:]]

            fc_mid = _sim(0.7, 0.3, 0.4, 42)
            fc_upper = [round(v + volatility * np.sqrt(i + 1) * 0.4, 2) for i, v in enumerate(fc_mid)]
            fc_lower = [round(v - volatility * np.sqrt(i + 1) * 0.4, 2) for i, v in enumerate(fc_mid)]

            traces.append({"type": "scatter", "mode": "lines", "x": fc_dates, "y": fc_upper,
                           "line": {"color": "#E91E63", "width": 1, "dash": "dash"}, "showlegend": False, "name": "上界"})
            traces.append({"type": "scatter", "mode": "lines", "x": fc_dates, "y": fc_lower,
                           "line": {"color": "#E91E63", "width": 1, "dash": "dash"}, "showlegend": False, "name": "下界"})
            traces.append({"type": "scatter", "mode": "lines", "x": fc_dates, "y": fc_mid,
                           "line": {"color": "#E91E63", "width": 2.5}, "name": "基准预测"})

            if predictions:
                for idx, pred in enumerate(predictions):
                    name = pred.get("name", f"策略{idx+1}")
                    color = self._strategy_colors.get(name, self._pred_palette[idx % len(self._pred_palette)])
                    cb = self._strategy_checkboxes.get(name)
                    if cb and not cb.isChecked():
                        continue
                    path = _sim(pred.get("trend_w", 0.5), pred.get("revert_w", 0.3), pred.get("vol_scale", 0.4), 42 + idx + 1)
                    traces.append({
                        "type": "scatter", "mode": "lines",
                        "x": fc_dates, "y": path,
                        "line": {"color": color, "width": 2.5},
                        "name": name,
                    })

        layout_cfg = {
            "template": "plotly_dark",
            "paper_bgcolor": "#1a1a2e", "plot_bgcolor": "#1a1a2e",
            "margin": {"l": 50, "r": 20, "t": 10, "b": 60},
            "xaxis": {
                "rangeslider": {
                    "visible": True,
                    "bgcolor": "#0d1117",
                    "bordercolor": "#30363d",
                    "thickness": 0.06,
                },
                "fixedrange": False,
                "type": "category",
            },
            "yaxis": {"fixedrange": False},
            "legend": {"orientation": "h", "y": -0.12, "x": 0, "font": {"size": 10}},
            "dragmode": "pan",
        }

        import pathlib as _pathlib
        _chart_html_path = _pathlib.Path(__file__).parent.parent / "resources" / "_chart.html"
        _plotly_js_path = _pathlib.Path(__file__).parent.parent / "resources" / "plotly.min.js"
        _plotly_src_tag = f'<script src="file:///{_plotly_js_path.resolve().as_posix()}"></script>'
        html = f"""<!DOCTYPE html><html><head>
        {_plotly_src_tag}
        <style>
            html, body {{ margin:0; padding:0; width:100%; height:100%; overflow:hidden; background:#1a1a2e; }}
            #chart {{ width:100%; height:100%; }}
            /* zoom hint */
            #zoom-hint {{ position:fixed; top:6px; right:8px; font-size:{APP_FONT['caption']}px; color:#555;
                          pointer-events:none; z-index:99; }}
        </style>
        </head><body>
        <div id="chart"></div>
        <div id="zoom-hint">滚轮缩放 · 拖拽平移 · 双击重置</div>
        <script>
        var traces = {json.dumps(traces)};
        var layout = {json.dumps(layout_cfg)};
        var config = {{
            responsive: true,
            displayModeBar: true,
            modeBarButtonsToRemove: ['lasso2d', 'select2d', 'sendDataToCloud'],
            displaylogo: false,
            scrollZoom: true
        }};
        Plotly.newPlot('chart', traces, layout, config);

        /* 鼠标滚轮缩放 X 轴 */
        var chartDiv = document.getElementById('chart');
        chartDiv.addEventListener('wheel', function(e) {{
            e.preventDefault();
            var xRange = chartDiv._fullLayout.xaxis.range;
            if (!xRange) return;
            var len = xRange[1] - xRange[0];
            var factor = e.deltaY < 0 ? 0.85 : 1.18;
            var center = (xRange[0] + xRange[1]) / 2;
            var newLen = len * factor;
            var newRange = [center - newLen / 2, center + newLen / 2];
            Plotly.relayout(chartDiv, {{'xaxis.range': newRange}});
        }}, {{passive: false}});

        window.addEventListener('resize', function() {{
            Plotly.Plots.resize(chartDiv);
        }});
        </script></body></html>"""

        # 写入本地文件再用 setUrl 加载（避免 setHtml 大小限制和 file:// 安全策略）
        try:
            _chart_html_path.parent.mkdir(parents=True, exist_ok=True)
            _chart_html_path.write_text(html, encoding="utf-8")
            from PyQt6.QtCore import QUrl
            self.web_view.setUrl(QUrl.fromLocalFile(str(_chart_html_path.resolve())))
        except Exception:
            self.web_view.setHtml("<h3 style='color:#888;text-align:center;padding:60px;'>图表加载失败</h3>")

    def _build_trend_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.trend_checks = {}
        conditions = [
            "股价 > MA150 且 MA200",
            "MA150 > MA200",
            "MA200 上升趋势",
            "MA50 > MA150 且 MA200",
            "股价 > MA50",
            "股价 > 52周低点×125%",
            "股价距52周高点≤25%",
            "RS 评级 ≥ 70",
        ]
        for cond in conditions:
            lbl = QLabel(f"  ❓ {cond}")
            lbl.setFont(QFont("", APP_FONT["body"]))
            layout.addWidget(lbl)
            self.trend_checks[cond] = lbl
        self.trend_result_label = QLabel("")
        self.trend_result_label.setFont(QFont("", APP_FONT["section"], QFont.Weight.Bold))
        layout.addWidget(self.trend_result_label)
        layout.addStretch()
        return w

    def _build_prediction_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.pred_table = QTableWidget()
        self.pred_table.setColumnCount(12)
        self.pred_table.setHorizontalHeaderLabels([
            "策略", "5日", "10日", "20日", "1月", "1季", "半年", "1年",
            "情绪阶段", "建议", "5日校准", "校准说明",
        ])
        self.pred_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.pred_table.setAlternatingRowColors(True)
        layout.addWidget(self.pred_table)
        return w

    def update_header(self, code: str, name: str, price: float):
        self.header_label.setText(f"{code} {name}　　现价 ¥{price:.2f}")

    def update_metrics(self, result: dict):
        self.metric_labels["MA50"].setText(f"MA50: {result.get('ma50', '-')}")
        self.metric_labels["MA150"].setText(f"MA150: {result.get('ma150', '-')}")
        self.metric_labels["MA200"].setText(f"MA200: {result.get('ma200', '-')}")
        self.metric_labels["52周高点"].setText(f"52高: {result.get('high_52w', '-')}")
        self.metric_labels["52周低点"].setText(f"52低: {result.get('low_52w', '-')}")
        self.metric_labels["RS评级"].setText(f"RS: {result.get('rs_rating', '-'):.0f}")

    def update_trend(self, trend_details: dict, passed: bool):
        keys = [
            ("condition_1_above_ma150_200", "股价 > MA150 且 MA200"),
            ("condition_2_ma150_gt_ma200", "MA150 > MA200"),
            ("condition_3_ma200_rising", "MA200 上升趋势"),
            ("condition_4_ma50_gt_ma150_200", "MA50 > MA150 且 MA200"),
            ("condition_5_above_ma50", "股价 > MA50"),
            ("condition_6_above_52w_low_25pct", "股价 > 52周低点×125%"),
            ("condition_7_within_52w_high_25pct", "股价距52周高点≤25%"),
            ("condition_8_rs_rating", "RS 评级 ≥ 70"),
        ]
        for key, label in keys:
            ok = trend_details.get(key, False)
            icon = "✅" if ok else "❌"
            self.trend_checks[label].setText(f"  {icon} {label}")
            color = "#4caf50" if ok else "#ef5350"
            self.trend_checks[label].setStyleSheet(f"color: {color}; font-size: {APP_FONT['body']}px;")
        if passed:
            self.trend_result_label.setText("✅ 通过趋势模板！处于 Stage 2 上升阶段")
            self.trend_result_label.setStyleSheet("color: #4caf50;")
        else:
            count = sum(1 for k, _ in keys if trend_details.get(k, False))
            self.trend_result_label.setText(f"通过 {count}/8 个条件")
            self.trend_result_label.setStyleSheet("color: #ff9800;")

    def update_predictions(self, preds: list[dict]):
        self.pred_table.setRowCount(len(preds))
        red = QColor("#ef5350")
        green = QColor("#26a69a")
        gray = QColor("#888888")

        for i, p in enumerate(preds):
            horizons = ["5d", "10d", "20d", "1m", "1q", "6m", "1y"]
            horizon_labels = []
            for h in horizons:
                val = p.get(f"pred_{h}")
                if val is not None:
                    horizon_labels.append(f"{val:+.2f}%")
                else:
                    horizon_labels.append("-")

            chg20 = p.get("pred_20d", 0) or 0
            if chg20 > 3:
                advice = "看多"
            elif chg20 > 0:
                advice = "偏多"
            elif chg20 > -3:
                advice = "观望"
            else:
                advice = "偏空"

            calib = p.get("calibration", "-")
            calib_note = p.get("calibration_note", "")

            vals = [
                p.get("strategy_name", ""),
            ] + horizon_labels + [
                p.get("emotion_phase", "-"),
                advice,
                calib,
                calib_note,
            ]

            for j, v in enumerate(vals):
                item = QTableWidgetItem(str(v))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if 1 <= j <= 7:
                    try:
                        fv = float(str(v).replace("%", "").replace("+", ""))
                        if fv > 0:
                            item.setForeground(red)
                        elif fv < 0:
                            item.setForeground(green)
                    except ValueError:
                        pass
                if j == 9:
                    if advice in ("看多",):
                        item.setForeground(red)
                    elif advice in ("偏空",):
                        item.setForeground(green)
                if j == 10:
                    if calib == "准确":
                        item.setForeground(red)
                    elif calib == "偏差大":
                        item.setForeground(green)
                self.pred_table.setItem(i, j, item)
