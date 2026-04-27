"""设置面板"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QGroupBox, QGridLayout, QComboBox, QCheckBox,
    QSpinBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QScrollArea, QTextEdit,
)
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtCore import Qt, QTimer
from desktop.ui_tokens import APP_FONT


class SettingsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.scroll = scroll
        container = QWidget()
        layout = QVBoxLayout(container)

        title = QLabel("⚙️ 设置")
        title.setFont(QFont("", APP_FONT["page_title"], QFont.Weight.Bold))
        layout.addWidget(title)

        # ═══════════════════════════════════════════════════
        # 1. 自动化调度引擎（原 OpenClaw 功能 + daemon_scheduler）
        # ═══════════════════════════════════════════════════
        sched_group = QGroupBox("🤖 自动化调度引擎")
        self.sched_group = sched_group
        sched_group.setStyleSheet(f"QGroupBox{{font-size:{APP_FONT['section']}px;font-weight:bold;}}")
        sl = QVBoxLayout(sched_group)

        desc = QLabel(
            "配置每日自动执行的策略流水线：数据拉取 → 选股扫描 → 短期选股 → "
            "基金持仓分析 → 综合研判 → 微信推送 → AI 建仓。"
        )
        desc.setStyleSheet(
            f"color:#8b949e; font-size:{APP_FONT['caption']}px; padding:2px 0 6px 0;"
        )
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
            ("openclaw_pipeline", "OpenClaw自主全流程", "10:25", "无人值守选股/研判/风控/执行"),
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
            time_lbl.setStyleSheet(f"color:#4fc3f7; font-size:{APP_FONT['caption']}px;")
            self.sched_time_labels[key] = time_lbl
            task_grid.addWidget(time_lbl, i, 2)
            tip_lbl = QLabel(tip)
            tip_lbl.setStyleSheet(f"color:#666; font-size:{APP_FONT['caption']}px;")
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

        oc_daemon_group = QGroupBox("🦀 OpenClaw 后台运行")
        ocg = QGridLayout(oc_daemon_group)
        oc_desc = QLabel("无需打开桌面客户端；API 常驻后由后台 daemon 在工作日自动触发 OpenClaw 自主全流程。")
        oc_desc.setWordWrap(True)
        oc_desc.setStyleSheet(f"color:#8b949e; font-size:{APP_FONT['caption']}px;")
        ocg.addWidget(oc_desc, 0, 0, 1, 4)
        ocg.addWidget(QLabel("执行时间:"), 1, 0)
        self.openclaw_daemon_time = QLineEdit()
        self.openclaw_daemon_time.setPlaceholderText("HH:MM，例如 10:25")
        self.openclaw_daemon_time.setMaximumWidth(120)
        ocg.addWidget(self.openclaw_daemon_time, 1, 1)
        ocg.addWidget(QLabel("关注板块:"), 1, 2)
        self.openclaw_daemon_boards = QLineEdit()
        self.openclaw_daemon_boards.setPlaceholderText("人工智能,芯片,量子科技")
        ocg.addWidget(self.openclaw_daemon_boards, 1, 3)
        self.openclaw_daemon_last_run = QLabel("上次后台执行：暂无记录")
        self.openclaw_daemon_last_run.setWordWrap(True)
        self.openclaw_daemon_last_run.setStyleSheet(f"color:#4fc3f7; font-size:{APP_FONT['caption']}px;")
        ocg.addWidget(self.openclaw_daemon_last_run, 2, 0, 1, 4)
        self.btn_test_openclaw_daemon = QPushButton("▶ 立即测试后台 OpenClaw")
        self.btn_test_openclaw_daemon.setStyleSheet(
            f"font-size:{APP_FONT['emphasis']}px; padding:6px 14px; background:#0f766e;"
        )
        ocg.addWidget(self.btn_test_openclaw_daemon, 3, 0, 1, 2)
        self.openclaw_daemon_test_status = QLabel("")
        self.openclaw_daemon_test_status.setStyleSheet(f"color:#94a3b8; font-size:{APP_FONT['caption']}px;")
        ocg.addWidget(self.openclaw_daemon_test_status, 3, 2, 1, 2)
        self.openclaw_alert_enabled = QCheckBox("启用失败/告警推送")
        self.openclaw_alert_enabled.setChecked(True)
        ocg.addWidget(self.openclaw_alert_enabled, 4, 0)
        ocg.addWidget(QLabel("静默窗口:"), 4, 1)
        self.openclaw_alert_suppress_seconds = QSpinBox()
        self.openclaw_alert_suppress_seconds.setRange(0, 86400)
        self.openclaw_alert_suppress_seconds.setSingleStep(300)
        self.openclaw_alert_suppress_seconds.setSuffix(" 秒")
        ocg.addWidget(self.openclaw_alert_suppress_seconds, 4, 2)
        ocg.addWidget(QLabel("连续失败升级:"), 5, 0)
        self.openclaw_alert_escalate_after = QSpinBox()
        self.openclaw_alert_escalate_after.setRange(1, 100)
        self.openclaw_alert_escalate_after.setSuffix(" 次")
        ocg.addWidget(self.openclaw_alert_escalate_after, 5, 1)
        self.btn_save_openclaw_alert_policy = QPushButton("💾 保存告警策略")
        ocg.addWidget(self.btn_save_openclaw_alert_policy, 5, 2)
        self.btn_reset_openclaw_alert_policy = QPushButton("↩ 默认告警策略")
        ocg.addWidget(self.btn_reset_openclaw_alert_policy, 5, 3)
        self.openclaw_alert_policy_status = QLabel("告警策略：-")
        self.openclaw_alert_policy_status.setWordWrap(True)
        self.openclaw_alert_policy_status.setStyleSheet(f"color:#94a3b8; font-size:{APP_FONT['caption']}px;")
        ocg.addWidget(self.openclaw_alert_policy_status, 6, 0, 1, 4)
        sl.addWidget(oc_daemon_group)
        self.openclaw_daemon_group = oc_daemon_group

        # 操作按钮
        btn_row = QHBoxLayout()
        self.btn_save_sched = QPushButton("💾 保存调度配置")
        self.btn_save_sched.setStyleSheet(f"font-size:{APP_FONT['emphasis']}px; padding:8px 16px;")
        btn_row.addWidget(self.btn_save_sched)

        self.btn_run_pipeline_now = QPushButton("▶ 立即执行全流水线")
        self.btn_run_pipeline_now.setStyleSheet(
            f"font-size:{APP_FONT['emphasis']}px; padding:8px 16px; background:#1b5e20;"
        )
        btn_row.addWidget(self.btn_run_pipeline_now)

        self.btn_view_sched_log = QPushButton("📋 查看调度日志")
        btn_row.addWidget(self.btn_view_sched_log)
        btn_row.addStretch()
        sl.addLayout(btn_row)

        # 调度状态
        self.sched_status = QLabel("调度引擎: 运行中")
        self.sched_status.setStyleSheet(
            f"color:#66bb6a; font-size:{APP_FONT['body']}px; padding:4px;"
        )
        sl.addWidget(self.sched_status)

        # 日志区
        self.sched_log = QTextEdit()
        self.sched_log.setReadOnly(True)
        self.sched_log.setMaximumHeight(120)
        self.sched_log.setPlaceholderText("调度执行日志...")
        self.sched_log.setStyleSheet(f"font-size:{APP_FONT['caption']}px; background:#0d1117;")
        sl.addWidget(self.sched_log)

        layout.addWidget(sched_group)

        # ═══════════════════════════════════════════════════
        # 2. 微信推送
        # ═══════════════════════════════════════════════════
        push_group = QGroupBox("📤 消息推送")
        self.push_group = push_group
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
        self.ai_group = ai_group
        ag = QGridLayout(ai_group)
        ag.addWidget(QLabel("API Provider:"), 0, 0)
        self.ai_provider = QComboBox()
        self.ai_provider.addItems(["DeepSeek", "OpenAI", "Gemini", "Claude", "自定义"])
        ag.addWidget(self.ai_provider, 0, 1)
        ag.addWidget(QLabel("默认模型:"), 1, 0)
        self.ai_model = QComboBox()
        self.ai_model.addItems(
            [
                "deepseek-chat",
                "gpt-4o",
                "gemini-pro",
                "claude-3-sonnet",
                "qwen-max",
                "moonshot-v1-8k",
            ]
        )
        ag.addWidget(self.ai_model, 1, 1)
        ag.addWidget(QLabel("API Key:"), 2, 0)
        self.ai_key = QLineEdit()
        self.ai_key.setEchoMode(QLineEdit.EchoMode.Password)
        ag.addWidget(self.ai_key, 2, 1)
        ag.addWidget(QLabel("API Base URL:"), 3, 0)
        self.ai_base_url = QLineEdit()
        self.ai_base_url.setPlaceholderText("https://api.deepseek.com/v1")
        ag.addWidget(self.ai_base_url, 3, 1)
        self.btn_save_ai = QPushButton("💾 保存 AI 配置")
        ag.addWidget(self.btn_save_ai, 4, 0, 1, 2)
        self.ai_status = QLabel("")
        ag.addWidget(self.ai_status, 5, 0, 1, 2)
        layout.addWidget(ai_group)

        # ═══════════════════════════════════════════════════
        # 4. OpenClaw 策略参数中心
        # ═══════════════════════════════════════════════════
        policy_group = QGroupBox("🧭 OpenClaw 策略参数中心")
        self.policy_group = policy_group
        pg2 = QGridLayout(policy_group)
        policy_desc = QLabel("配置 CoordinatorAgent 的执行分流阈值。学习引擎会基于后验表现小幅调参，你也可以在这里手动覆盖。")
        policy_desc.setWordWrap(True)
        policy_desc.setStyleSheet(f"color:#8b949e; font-size:{APP_FONT['caption']}px;")
        pg2.addWidget(policy_desc, 0, 0, 1, 4)
        pg2.addWidget(QLabel("观察模式守门拦截率 ≥"), 1, 0)
        self.coord_observe_blocked_ratio = QSpinBox()
        self.coord_observe_blocked_ratio.setRange(30, 100)
        self.coord_observe_blocked_ratio.setSuffix("%")
        pg2.addWidget(self.coord_observe_blocked_ratio, 1, 1)
        pg2.addWidget(QLabel("sell_only 舆情阈值 <"), 1, 2)
        self.coord_sell_only_sentiment = QSpinBox()
        self.coord_sell_only_sentiment.setRange(5, 60)
        self.coord_sell_only_sentiment.setSuffix("%")
        pg2.addWidget(self.coord_sell_only_sentiment, 1, 3)
        pg2.addWidget(QLabel("limit_buy 舆情阈值 <"), 2, 0)
        self.coord_limit_buy_sentiment = QSpinBox()
        self.coord_limit_buy_sentiment.setRange(10, 80)
        self.coord_limit_buy_sentiment.setSuffix("%")
        pg2.addWidget(self.coord_limit_buy_sentiment, 2, 1)
        pg2.addWidget(QLabel("limit_buy 买入上限"), 2, 2)
        self.coord_limit_buy_max_count = QSpinBox()
        self.coord_limit_buy_max_count.setRange(1, 5)
        self.coord_limit_buy_max_count.setSuffix(" 条")
        pg2.addWidget(self.coord_limit_buy_max_count, 2, 3)
        pg2.addWidget(QLabel("学习调参最小样本"), 3, 0)
        self.coord_learning_min_samples = QSpinBox()
        self.coord_learning_min_samples.setRange(1, 30)
        self.coord_learning_min_samples.setSuffix(" 个")
        pg2.addWidget(self.coord_learning_min_samples, 3, 1)
        self.coord_policy_note = QLabel("最近调参：-")
        self.coord_policy_note.setWordWrap(True)
        self.coord_policy_note.setStyleSheet(f"color:#94a3b8; font-size:{APP_FONT['caption']}px;")
        pg2.addWidget(self.coord_policy_note, 3, 2, 1, 2)
        self.btn_save_coord_policy = QPushButton("💾 保存策略参数")
        pg2.addWidget(self.btn_save_coord_policy, 4, 0, 1, 2)
        self.btn_reset_coord_policy = QPushButton("↩ 恢复默认")
        pg2.addWidget(self.btn_reset_coord_policy, 4, 2)
        self.coord_policy_status = QLabel("")
        pg2.addWidget(self.coord_policy_status, 5, 0, 1, 4)
        layout.addWidget(policy_group)

        # ═══════════════════════════════════════════════════
        # 5. 无人值守交易安全闸
        # ═══════════════════════════════════════════════════
        guard_group = QGroupBox("🛡 无人值守交易安全闸")
        self.trade_guard_group = guard_group
        gg = QGridLayout(guard_group)
        guard_desc = QLabel("后台 OpenClaw 自动执行前的硬约束。默认禁止无人值守买入，卖出可用于降风险。")
        guard_desc.setWordWrap(True)
        guard_desc.setStyleSheet(f"color:#8b949e; font-size:{APP_FONT['caption']}px;")
        gg.addWidget(guard_desc, 0, 0, 1, 4)
        self.trade_guard_enabled = QCheckBox("启用安全闸")
        self.trade_guard_enabled.setChecked(True)
        gg.addWidget(self.trade_guard_enabled, 1, 0)
        self.trade_guard_buy_enabled = QCheckBox("允许无人值守买入")
        gg.addWidget(self.trade_guard_buy_enabled, 1, 1)
        self.trade_guard_sell_enabled = QCheckBox("买入关闭时仍允许卖出")
        self.trade_guard_sell_enabled.setChecked(True)
        gg.addWidget(self.trade_guard_sell_enabled, 1, 2, 1, 2)
        gg.addWidget(QLabel("每日买入金额上限"), 2, 0)
        self.trade_guard_daily_amount = QSpinBox()
        self.trade_guard_daily_amount.setRange(0, 10000000)
        self.trade_guard_daily_amount.setSingleStep(1000)
        self.trade_guard_daily_amount.setSuffix(" 元")
        gg.addWidget(self.trade_guard_daily_amount, 2, 1)
        gg.addWidget(QLabel("单票买入金额上限"), 2, 2)
        self.trade_guard_single_amount = QSpinBox()
        self.trade_guard_single_amount.setRange(0, 10000000)
        self.trade_guard_single_amount.setSingleStep(1000)
        self.trade_guard_single_amount.setSuffix(" 元")
        gg.addWidget(self.trade_guard_single_amount, 2, 3)
        gg.addWidget(QLabel("每日买入次数上限"), 3, 0)
        self.trade_guard_daily_count = QSpinBox()
        self.trade_guard_daily_count.setRange(0, 1000)
        self.trade_guard_daily_count.setSuffix(" 次")
        gg.addWidget(self.trade_guard_daily_count, 3, 1)
        gg.addWidget(QLabel("单批金额上限"), 3, 2)
        self.trade_guard_batch_amount = QSpinBox()
        self.trade_guard_batch_amount.setRange(0, 10000000)
        self.trade_guard_batch_amount.setSingleStep(1000)
        self.trade_guard_batch_amount.setSuffix(" 元")
        gg.addWidget(self.trade_guard_batch_amount, 3, 3)
        gg.addWidget(QLabel("单批买入次数"), 4, 0)
        self.trade_guard_batch_count = QSpinBox()
        self.trade_guard_batch_count.setRange(0, 100)
        self.trade_guard_batch_count.setSuffix(" 次")
        gg.addWidget(self.trade_guard_batch_count, 4, 1)
        gg.addWidget(QLabel("单票日内次数"), 4, 2)
        self.trade_guard_symbol_daily_count = QSpinBox()
        self.trade_guard_symbol_daily_count.setRange(0, 100)
        self.trade_guard_symbol_daily_count.setSuffix(" 次")
        gg.addWidget(self.trade_guard_symbol_daily_count, 4, 3)
        gg.addWidget(QLabel("板块日内金额"), 5, 0)
        self.trade_guard_sector_daily_amount = QSpinBox()
        self.trade_guard_sector_daily_amount.setRange(0, 10000000)
        self.trade_guard_sector_daily_amount.setSingleStep(1000)
        self.trade_guard_sector_daily_amount.setSuffix(" 元")
        gg.addWidget(self.trade_guard_sector_daily_amount, 5, 1)
        gg.addWidget(QLabel("板块日内次数"), 5, 2)
        self.trade_guard_sector_daily_count = QSpinBox()
        self.trade_guard_sector_daily_count.setRange(0, 100)
        self.trade_guard_sector_daily_count.setSuffix(" 次")
        gg.addWidget(self.trade_guard_sector_daily_count, 5, 3)
        gg.addWidget(QLabel("买入冷却时间"), 6, 0)
        self.trade_guard_cooldown_minutes = QSpinBox()
        self.trade_guard_cooldown_minutes.setRange(0, 1440)
        self.trade_guard_cooldown_minutes.setSuffix(" 分钟")
        gg.addWidget(self.trade_guard_cooldown_minutes, 6, 1)
        self.trade_guard_sim_required = QCheckBox("要求仿真门禁通过")
        self.trade_guard_sim_required.setChecked(True)
        gg.addWidget(self.trade_guard_sim_required, 6, 2)
        self.trade_guard_sim_runs = QSpinBox()
        self.trade_guard_sim_runs.setRange(1, 100)
        self.trade_guard_sim_runs.setSuffix(" 次成功试运行")
        gg.addWidget(self.trade_guard_sim_runs, 6, 3)
        gg.addWidget(QLabel("黑名单"), 7, 0)
        self.trade_guard_blacklist = QLineEdit()
        self.trade_guard_blacklist.setPlaceholderText("600519,300750")
        gg.addWidget(self.trade_guard_blacklist, 7, 1)
        gg.addWidget(QLabel("白名单"), 7, 2)
        self.trade_guard_whitelist = QLineEdit()
        self.trade_guard_whitelist.setPlaceholderText("留空表示不限制")
        gg.addWidget(self.trade_guard_whitelist, 7, 3)
        self.trade_guard_usage = QLabel("今日用量：-")
        self.trade_guard_usage.setWordWrap(True)
        self.trade_guard_usage.setStyleSheet(f"color:#4fc3f7; font-size:{APP_FONT['caption']}px;")
        gg.addWidget(self.trade_guard_usage, 8, 0, 1, 4)
        self.trade_guard_sim_status = QLabel("仿真门禁：-")
        self.trade_guard_sim_status.setWordWrap(True)
        self.trade_guard_sim_status.setStyleSheet(f"color:#4fc3f7; font-size:{APP_FONT['caption']}px;")
        gg.addWidget(self.trade_guard_sim_status, 9, 0, 1, 4)
        self.btn_save_trade_guard = QPushButton("💾 保存安全闸")
        gg.addWidget(self.btn_save_trade_guard, 10, 0, 1, 2)
        self.btn_reset_trade_guard = QPushButton("↩ 恢复默认安全闸")
        gg.addWidget(self.btn_reset_trade_guard, 10, 2)
        self.trade_guard_status = QLabel("")
        gg.addWidget(self.trade_guard_status, 11, 0, 1, 4)
        layout.addWidget(guard_group)

        # ═══════════════════════════════════════════════════
        # 6. API 生产安全
        # ═══════════════════════════════════════════════════
        security_group = QGroupBox("🔐 API 生产安全")
        self.security_group = security_group
        sg = QGridLayout(security_group)
        security_desc = QLabel("检查默认管理员密码、账号角色分布和 token 状态；用于无人值守上线前验收。")
        security_desc.setWordWrap(True)
        security_desc.setStyleSheet(f"color:#8b949e; font-size:{APP_FONT['caption']}px;")
        sg.addWidget(security_desc, 0, 0, 1, 4)
        self.security_status = QLabel("安全自检：未加载")
        self.security_status.setWordWrap(True)
        self.security_status.setStyleSheet(f"color:#94a3b8; font-size:{APP_FONT['caption']}px;")
        sg.addWidget(self.security_status, 1, 0, 1, 4)
        self.security_roles = QLabel("角色分布：-")
        self.security_roles.setStyleSheet(f"color:#4fc3f7; font-size:{APP_FONT['caption']}px;")
        sg.addWidget(self.security_roles, 2, 0, 1, 2)
        self.security_tokens = QLabel("Token：-")
        self.security_tokens.setStyleSheet(f"color:#4fc3f7; font-size:{APP_FONT['caption']}px;")
        sg.addWidget(self.security_tokens, 2, 2, 1, 2)
        self.btn_refresh_security_check = QPushButton("🔍 刷新安全自检")
        sg.addWidget(self.btn_refresh_security_check, 3, 0, 1, 2)
        self.btn_cleanup_expired_tokens = QPushButton("🧹 清理过期/异常 Token")
        sg.addWidget(self.btn_cleanup_expired_tokens, 3, 2, 1, 2)
        layout.addWidget(security_group)

        # ═══════════════════════════════════════════════════
        # 7. 数据 + 外观
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
        self._group_base_styles = {
            "sched": self.sched_group.styleSheet(),
            "push": self.push_group.styleSheet(),
            "ai": self.ai_group.styleSheet(),
            "policy": self.policy_group.styleSheet(),
            "trade_guard": self.trade_guard_group.styleSheet(),
            "openclaw_daemon": self.openclaw_daemon_group.styleSheet(),
            "security": self.security_group.styleSheet(),
        }
        self._highlight_timer = QTimer(self)
        self._highlight_timer.setSingleShot(True)
        self._highlight_timer.timeout.connect(self._restore_group_styles)

    def set_schedule_time(self, task_key: str, time_text: str):
        label = self.sched_time_labels.get(task_key)
        if label:
            label.setText(time_text or self.sched_time_defaults.get(task_key, "-"))

    def focus_section(self, section: str):
        section_key = str(section or "").strip().lower()
        target = None
        section_name = ""
        if section_key in {"push", "settings_push"}:
            target = self.push_group
            section_name = "push"
            self.push_key.setFocus()
        elif section_key in {"schedule", "settings_schedule"}:
            target = self.sched_group
            section_name = "sched"
            self.sched_engine.setFocus()
        elif section_key in {"ai", "settings_ai"}:
            target = self.ai_group
            section_name = "ai"
            self.ai_provider.setFocus()
        elif section_key in {"policy", "coordinator_policy", "settings_policy"}:
            target = self.policy_group
            section_name = "policy"
            self.coord_observe_blocked_ratio.setFocus()
        elif section_key in {"trade_guard", "unattended_trade_guard", "settings_trade_guard"}:
            target = self.trade_guard_group
            section_name = "trade_guard"
            self.trade_guard_buy_enabled.setFocus()
        elif section_key in {"openclaw_daemon", "settings_openclaw_daemon"}:
            target = self.openclaw_daemon_group
            section_name = "openclaw_daemon"
            self.openclaw_daemon_time.setFocus()
        elif section_key in {"security", "api_security", "settings_security"}:
            target = self.security_group
            section_name = "security"
            self.btn_refresh_security_check.setFocus()
        if target is not None:
            self.scroll.ensureWidgetVisible(target, 0, 24)
            self._highlight_group(section_name, target)

    def _highlight_group(self, section_name: str, target):
        self._restore_group_styles()
        base = self._group_base_styles.get(section_name, "") or ""
        highlight = (
            "QGroupBox{border:2px solid #4fc3f7; border-radius:8px;"
            "margin-top:10px; padding-top:6px;}"
        )
        target.setStyleSheet(f"{base}\n{highlight}".strip())
        self._highlight_timer.start(3000)

    def _restore_group_styles(self):
        self.sched_group.setStyleSheet(self._group_base_styles.get("sched", ""))
        self.push_group.setStyleSheet(self._group_base_styles.get("push", ""))
        self.ai_group.setStyleSheet(self._group_base_styles.get("ai", ""))
        self.policy_group.setStyleSheet(self._group_base_styles.get("policy", ""))
        self.trade_guard_group.setStyleSheet(self._group_base_styles.get("trade_guard", ""))
        self.openclaw_daemon_group.setStyleSheet(self._group_base_styles.get("openclaw_daemon", ""))
        self.security_group.setStyleSheet(self._group_base_styles.get("security", ""))
