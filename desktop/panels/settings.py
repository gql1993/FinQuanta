"""设置面板"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QGroupBox, QGridLayout, QComboBox, QCheckBox,
    QSpinBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QScrollArea, QTextEdit,
)
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtCore import Qt


class SettingsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)

        title = QLabel("⚙️ 设置")
        title.setFont(QFont("", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        # ═══════════════════════════════════════════════════
        # 1. 自动化调度引擎（原 OpenClaw 功能 + daemon_scheduler）
        # ═══════════════════════════════════════════════════
        sched_group = QGroupBox("🤖 自动化调度引擎")
        sched_group.setStyleSheet("QGroupBox{font-size:14px;font-weight:bold;}")
        sl = QVBoxLayout(sched_group)

        desc = QLabel(
            "配置每日自动执行的策略流水线：数据拉取 → 选股扫描 → 短期选股 → "
            "基金持仓分析 → 综合研判 → 微信推送 → AI 建仓。"
        )
        desc.setStyleSheet("color:#8b949e; font-size:11px; padding:2px 0 6px 0;")
        desc.setWordWrap(True)
        sl.addWidget(desc)

        # 任务开关表
        self.sched_checks = {}
        self.sched_time_labels = {}
        self.sched_time_defaults = {}
        task_grid = QGridLayout()
        task_grid.addWidget(QLabel("任务"), 0, 0)
        task_grid.addWidget(QLabel("启用"), 0, 1)
        task_grid.addWidget(QLabel("时间"), 0, 2)
        task_grid.addWidget(QLabel("说明"), 0, 3)

        _tasks = [
            ("fetch_data",    "刷新实时行情",   "09:50,11:00,12:00,13:00,14:00", "每小时刷新报价"),
            ("refresh_kline", "刷新K线日线",    "10:00, 13:30", "8线程并发补全日K"),
            ("refresh_boards","补全板块成分股", "10:02", "K线刷新后补全缺失数据"),
            ("scan_stocks",   "选股雷达扫描",   "10:05", "SEPA策略扫描Top50"),
            ("push_strong",   "推送强烈买入",   "10:08", "自动推送到微信/企微"),
            ("short_term",    "短期选股+NLP",   "10:10", "新闻情绪+基金持仓"),
            ("custom_top3",   "自定义仓Top3",   "10:12", "自动买入扫描Top3"),
            ("ai_decision",   "AI 四仓决策",    "10:15, 14:00", "完全自主+AI推荐"),
            ("quantum_buy",   "量子仓优化",     "10:20(仅周一)", "每周一量子优化买入"),
            ("auto_sell",     "自动卖出检查",   "10:18, 14:05", "5种规则+ATR止损+推送"),
            ("risk_calc",     "组合风险计算",   "10:30~14:30(5次)", "VaR/HHI/敞口"),
            ("watchlist_scan","关注股异常扫描", "11:00, 14:00", "大涨大跌/放量/突破"),
            ("trend_verify",  "走势验证校准",   "15:30", "1~60日走势校准"),
            ("custom_cal",    "自定义仓校准",   "15:30", "Top3实际表现"),
            ("daily_report",  "日报推送",       "15:30", "六仓对比+准确率"),
            ("auto_learn",    "自主学习进化",   "15:35", "策略权重更新"),
            ("auto_backtest", "周期性回测",     "16:00", "验证策略历史效果"),
            ("alert_check",   "止损止盈预警",   "全天(5min)", "实时监控+推送"),
        ]

        for i, (key, name, time_str, tip) in enumerate(_tasks, 1):
            cb = QCheckBox(name)
            cb.setChecked(True)
            self.sched_checks[key] = cb
            self.sched_time_defaults[key] = time_str
            task_grid.addWidget(cb, i, 0, 1, 2)
            time_lbl = QLabel(time_str)
            time_lbl.setStyleSheet("color:#4fc3f7; font-size:11px;")
            self.sched_time_labels[key] = time_lbl
            task_grid.addWidget(time_lbl, i, 2)
            tip_lbl = QLabel(tip)
            tip_lbl.setStyleSheet("color:#666; font-size:11px;")
            task_grid.addWidget(tip_lbl, i, 3)

        sl.addLayout(task_grid)

        # 调度引擎选择
        engine_row = QHBoxLayout()
        engine_row.addWidget(QLabel("调度引擎:"))
        self.sched_engine = QComboBox()
        self.sched_engine.addItems([
            "内置 Daemon（推荐）",
            "OpenClaw Agent",
        ])
        engine_row.addWidget(self.sched_engine)

        engine_row.addWidget(QLabel("OpenClaw Key:"))
        self.openclaw_key = QLineEdit()
        self.openclaw_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.openclaw_key.setPlaceholderText("仅使用 OpenClaw 时需要")
        self.openclaw_key.setMaximumWidth(250)
        engine_row.addWidget(self.openclaw_key)
        engine_row.addStretch()
        sl.addLayout(engine_row)

        # 操作按钮
        btn_row = QHBoxLayout()
        self.btn_save_sched = QPushButton("💾 保存调度配置")
        self.btn_save_sched.setStyleSheet("font-size:13px; padding:8px 16px;")
        btn_row.addWidget(self.btn_save_sched)

        self.btn_run_pipeline_now = QPushButton("▶ 立即执行全流水线")
        self.btn_run_pipeline_now.setStyleSheet(
            "font-size:13px; padding:8px 16px; background:#1b5e20;"
        )
        btn_row.addWidget(self.btn_run_pipeline_now)

        self.btn_view_sched_log = QPushButton("📋 查看调度日志")
        btn_row.addWidget(self.btn_view_sched_log)
        btn_row.addStretch()
        sl.addLayout(btn_row)

        # 调度状态
        self.sched_status = QLabel("调度引擎: 运行中")
        self.sched_status.setStyleSheet("color:#66bb6a; font-size:12px; padding:4px;")
        sl.addWidget(self.sched_status)

        # 日志区
        self.sched_log = QTextEdit()
        self.sched_log.setReadOnly(True)
        self.sched_log.setMaximumHeight(120)
        self.sched_log.setPlaceholderText("调度执行日志...")
        self.sched_log.setStyleSheet("font-size:11px; background:#0d1117;")
        sl.addWidget(self.sched_log)

        layout.addWidget(sched_group)

        # ═══════════════════════════════════════════════════
        # 2. 微信推送
        # ═══════════════════════════════════════════════════
        push_group = QGroupBox("📤 消息推送")
        pg = QGridLayout(push_group)

        pg.addWidget(QLabel("Server酱 Key:"), 0, 0)
        self.push_key = QLineEdit()
        self.push_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.push_key.setPlaceholderText("SCTxxxxxxxxxxxxx（免费版5条/天）")
        pg.addWidget(self.push_key, 0, 1)

        pg.addWidget(QLabel("企业微信 Webhook:"), 1, 0)
        self.wecom_webhook = QLineEdit()
        self.wecom_webhook.setEchoMode(QLineEdit.EchoMode.Password)
        self.wecom_webhook.setPlaceholderText("https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx（无次数限制）")
        pg.addWidget(self.wecom_webhook, 1, 1)

        self.btn_save_push = QPushButton("💾 保存")
        pg.addWidget(self.btn_save_push, 0, 2)
        self.btn_test_push = QPushButton("🔔 测试推送")
        pg.addWidget(self.btn_test_push, 1, 2)
        self.push_status = QLabel("")
        pg.addWidget(self.push_status, 2, 0, 1, 3)
        layout.addWidget(push_group)

        # ═══════════════════════════════════════════════════
        # 3. AI 模型配置
        # ═══════════════════════════════════════════════════
        ai_group = QGroupBox("🤖 AI 模型配置")
        ag = QGridLayout(ai_group)
        ag.addWidget(QLabel("API Provider:"), 0, 0)
        self.ai_provider = QComboBox()
        self.ai_provider.addItems(["DeepSeek", "OpenAI", "Gemini", "Claude", "自定义"])
        ag.addWidget(self.ai_provider, 0, 1)
        ag.addWidget(QLabel("API Key:"), 1, 0)
        self.ai_key = QLineEdit()
        self.ai_key.setEchoMode(QLineEdit.EchoMode.Password)
        ag.addWidget(self.ai_key, 1, 1)
        ag.addWidget(QLabel("API Base URL:"), 2, 0)
        self.ai_base_url = QLineEdit()
        self.ai_base_url.setPlaceholderText("https://api.deepseek.com/v1")
        ag.addWidget(self.ai_base_url, 2, 1)
        self.btn_save_ai = QPushButton("💾 保存 AI 配置")
        ag.addWidget(self.btn_save_ai, 3, 0, 1, 2)
        layout.addWidget(ai_group)

        # ═══════════════════════════════════════════════════
        # 4. 数据 + 外观
        # ═══════════════════════════════════════════════════
        data_group = QGroupBox("📦 数据配置")
        dg = QGridLayout(data_group)
        dg.addWidget(QLabel("缓存目录:"), 0, 0)
        self.cache_dir_label = QLabel("data_cache")
        dg.addWidget(self.cache_dir_label, 0, 1)
        self.btn_clear_cache = QPushButton("🗑️ 清理缓存")
        dg.addWidget(self.btn_clear_cache, 0, 2)
        self.btn_export_db = QPushButton("📤 导出数据库")
        dg.addWidget(self.btn_export_db, 1, 0)
        self.btn_import_db = QPushButton("📥 导入数据库")
        dg.addWidget(self.btn_import_db, 1, 1)
        layout.addWidget(data_group)

        theme_group = QGroupBox("🎨 外观")
        tg = QHBoxLayout(theme_group)
        tg.addWidget(QLabel("主题:"))
        self.combo_theme = QComboBox()
        self.combo_theme.addItems(["深色", "浅色"])
        tg.addWidget(self.combo_theme)
        tg.addStretch()
        layout.addWidget(theme_group)

        layout.addStretch()

        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def set_schedule_time(self, task_key: str, time_text: str):
        label = self.sched_time_labels.get(task_key)
        if label:
            label.setText(time_text or self.sched_time_defaults.get(task_key, "-"))
