"""事件驱动短期选股面板"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QGroupBox, QTabWidget, QDateEdit, QComboBox,
)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QFont, QColor


class EventPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        title = QLabel("⚡ 事件驱动短期选股")
        title.setFont(QFont("", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        # 事件输入区
        input_box = QGroupBox("事件录入")
        ig = QVBoxLayout(input_box)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("事件描述:"))
        self.event_input = QLineEdit()
        self.event_input.setPlaceholderText("例如: 特高压政策利好 / 芯片国产替代 / 量子计算突破")
        self.event_input.setMinimumWidth(400)
        row1.addWidget(self.event_input)
        row1.addWidget(QLabel("日期:"))
        self.event_date = QDateEdit()
        self.event_date.setDate(QDate.currentDate())
        self.event_date.setCalendarPopup(True)
        row1.addWidget(self.event_date)
        ig.addLayout(row1)

        row2 = QHBoxLayout()
        self.btn_analyze = QPushButton("🔍 分析事件")
        self.btn_analyze.setStyleSheet("font-size: 14px; padding: 8px 20px; background: #FF6F00;")
        row2.addWidget(self.btn_analyze)
        self.btn_fetch_news = QPushButton("📰 抓取最新财经快讯")
        row2.addWidget(self.btn_fetch_news)
        self.btn_fetch_broker = QPushButton("🏛️ 券商中国资讯")
        self.btn_fetch_broker.setStyleSheet("font-size: 13px; padding: 8px 14px; background: #1565C0;")
        row2.addWidget(self.btn_fetch_broker)
        self.btn_save = QPushButton("💾 保存事件")
        row2.addWidget(self.btn_save)
        row2.addStretch()
        ig.addLayout(row2)

        self.matched_label = QLabel("")
        self.matched_label.setStyleSheet("color: #4fc3f7; font-size: 13px;")
        self.matched_label.setWordWrap(True)
        ig.addWidget(self.matched_label)
        layout.addWidget(input_box)

        # Tabs
        tabs = QTabWidget()
        tabs.addTab(self._build_recommend_tab(), "🎯 短期推荐")
        tabs.addTab(self._build_backtest_tab(), "📊 历史回测")
        tabs.addTab(self._build_news_tab(), "📰 财经快讯")
        tabs.addTab(self._build_broker_tab(), "🏛️ 券商中国")
        tabs.addTab(self._build_history_tab(), "📋 事件记录")
        layout.addWidget(tabs)

    def _build_recommend_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.recommend_table = QTableWidget()
        self.recommend_table.setColumnCount(7)
        self.recommend_table.setHorizontalHeaderLabels([
            "代码", "名称", "板块", "现价", "5日涨幅%", "量比", "信号",
        ])
        self.recommend_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.recommend_table.setAlternatingRowColors(True)
        self.recommend_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.recommend_table.setSortingEnabled(True)
        layout.addWidget(self.recommend_table)
        return w

    def _build_backtest_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.backtest_table = QTableWidget()
        self.backtest_table.setColumnCount(5)
        self.backtest_table.setHorizontalHeaderLabels([
            "板块", "成分股数", "3日均涨幅%", "5日均涨幅%", "10日均涨幅%",
        ])
        self.backtest_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.backtest_table.setAlternatingRowColors(True)
        layout.addWidget(self.backtest_table)

        self.bt_detail_label = QLabel("点击上方板块行查看成分股详情")
        self.bt_detail_label.setStyleSheet("color: #888;")
        layout.addWidget(self.bt_detail_label)
        self.bt_detail_table = QTableWidget()
        self.bt_detail_table.setColumnCount(6)
        self.bt_detail_table.setHorizontalHeaderLabels(["代码", "名称", "现价", "3日%", "5日%", "10日%"])
        self.bt_detail_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.bt_detail_table.setAlternatingRowColors(True)
        self.bt_detail_table.setSortingEnabled(True)
        layout.addWidget(self.bt_detail_table)
        return w

    def _build_news_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.news_table = QTableWidget()
        self.news_table.setColumnCount(3)
        self.news_table.setHorizontalHeaderLabels(["日期", "标题", "摘要"])
        self.news_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.news_table.setAlternatingRowColors(True)
        self.news_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.news_table)
        return w

    def _build_broker_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(QLabel("券商中国及研报资讯 | 自动匹配板块 + 历史关联分析 + 预测"))
        self.broker_table = QTableWidget()
        self.broker_table.setColumnCount(9)
        self.broker_table.setHorizontalHeaderLabels([
            "日期", "标题", "来源", "关联板块",
            "历史异动数", "5日均涨跌%", "5日胜率%", "历史预测", "置信度%",
        ])
        self.broker_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.broker_table.setAlternatingRowColors(True)
        self.broker_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.broker_table.setSortingEnabled(True)
        layout.addWidget(self.broker_table)
        return w

    def update_broker(self, news: list[dict]):
        red = QColor("#ef5350")
        green = QColor("#26a69a")
        orange = QColor("#FF9800")
        cyan = QColor("#4fc3f7")
        self.broker_table.setRowCount(len(news))
        for i, n in enumerate(news):
            boards = n.get("matched_boards", [])
            boards_str = ", ".join(boards[:3]) if boards else "-"

            h_events = n.get("history_events", 0)
            h_5d_avg = n.get("history_5d_avg")
            h_5d_wr = n.get("history_5d_winrate")
            h_pred = n.get("history_prediction", "-")
            h_conf = n.get("history_confidence", 0)

            vals = [
                n.get("date", ""),
                n.get("title", "")[:55],
                n.get("source", ""),
                boards_str,
                str(h_events) if h_events else "-",
                f"{h_5d_avg:+.1f}%" if h_5d_avg is not None else "-",
                f"{h_5d_wr:.0f}%" if h_5d_wr is not None else "-",
                h_pred,
                f"{h_conf}%" if h_conf else "-",
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 3 and boards_str != "-":
                    item.setForeground(cyan)
                if j == 5:
                    try:
                        fv = float(v.replace("%", "").replace("+", ""))
                        item.setForeground(red if fv > 0 else green if fv < 0 else QColor("#888"))
                        item.setFont(QFont("", 10, QFont.Weight.Bold))
                    except Exception:
                        pass
                if j == 6:
                    try:
                        fv = float(v.replace("%", ""))
                        item.setForeground(red if fv >= 55 else green if fv < 45 else orange)
                        item.setFont(QFont("", 10, QFont.Weight.Bold))
                    except Exception:
                        pass
                if j == 7:
                    if "看涨" in v:
                        item.setForeground(red)
                    elif "看跌" in v:
                        item.setForeground(green)
                    else:
                        item.setForeground(orange)
                    item.setFont(QFont("", 10, QFont.Weight.Bold))
                if j == 8:
                    try:
                        cv = int(v.replace("%", ""))
                        if cv >= 60:
                            item.setForeground(red)
                        elif cv >= 40:
                            item.setForeground(orange)
                        else:
                            item.setForeground(QColor("#888"))
                    except Exception:
                        pass
                self.broker_table.setItem(i, j, item)

    def _build_history_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(4)
        self.history_table.setHorizontalHeaderLabels(["日期", "事件", "匹配板块", "来源"])
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.history_table.setAlternatingRowColors(True)
        layout.addWidget(self.history_table)
        return w

    def update_recommend(self, stocks: list[dict]):
        red = QColor("#ef5350")
        green = QColor("#26a69a")
        self.recommend_table.setRowCount(len(stocks))
        for i, s in enumerate(stocks):
            vals = [
                s.get("code", ""), s.get("name", ""), s.get("board", ""),
                f"{s.get('price', 0):.2f}", f"{s.get('mom5', 0):+.2f}%",
                f"{s.get('vol_ratio', 0):.1f}", s.get("signals", ""),
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 4:
                    try:
                        fv = float(v.replace("%", "").replace("+", ""))
                        item.setForeground(red if fv > 0 else green if fv < 0 else QColor("#888"))
                    except Exception:
                        pass
                self.recommend_table.setItem(i, j, item)

    def update_backtest(self, results: list[dict]):
        red = QColor("#ef5350")
        green = QColor("#26a69a")
        self.backtest_table.setRowCount(len(results))
        self._bt_results = results
        for i, r in enumerate(results):
            vals = [
                r.get("board", ""), str(r.get("stocks", 0)),
                f"{r.get('avg_3d', 0):+.2f}%",
                f"{r.get('avg_5d', 0):+.2f}%",
                f"{r.get('avg_10d', 0):+.2f}%",
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j >= 2:
                    try:
                        fv = float(v.replace("%", "").replace("+", ""))
                        item.setForeground(red if fv > 0 else green if fv < 0 else QColor("#888"))
                    except Exception:
                        pass
                self.backtest_table.setItem(i, j, item)

    def update_news(self, news: list[dict]):
        self.news_table.setRowCount(len(news))
        for i, n in enumerate(news):
            vals = [n.get("date", ""), n.get("title", ""), n.get("digest", "")[:80]]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                if j == 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.news_table.setItem(i, j, item)

    def update_history(self, events: list[dict]):
        self.history_table.setRowCount(len(events))
        for i, e in enumerate(events):
            boards_str = ", ".join(e.get("boards", []))
            vals = [e.get("date", ""), e.get("text", ""), boards_str, e.get("source", "")]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                if j == 0 or j == 3:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.history_table.setItem(i, j, item)
