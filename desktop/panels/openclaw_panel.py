"""
OpenClaw 智能体执行网关面板
全流程自动化中枢：数据采集 → 策略研判 → 交易执行 → 监控反馈
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QGroupBox, QGridLayout, QComboBox, QCheckBox,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QTextEdit, QSpinBox, QScrollArea, QProgressBar,
)
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtCore import Qt


class OpenClawPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(8)

        # ── 标题 ──
        header = QHBoxLayout()
        title = QLabel("🦀 OpenClaw 智能体执行网关")
        title.setFont(QFont("", 16, QFont.Weight.Bold))
        title.setStyleSheet("color:#FF6D00;")
        header.addWidget(title)
        header.addStretch()

        self.status_indicator = QLabel("● 未连接")
        self.status_indicator.setStyleSheet("color:#ef5350; font-size:13px; font-weight:bold;")
        header.addWidget(self.status_indicator)
        layout.addLayout(header)

        subtitle = QLabel(
            "开源 AI 智能体执行网关 — 连接 LLM、数据源、策略引擎与交易 API 的全流程自动化中枢"
        )
        subtitle.setStyleSheet("color:#8b949e; font-size:11px; padding:0 0 6px 0;")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # ── 连接配置 ──
        cfg_group = QGroupBox("🔧 连接配置")
        cfg = QGridLayout(cfg_group)

        cfg.addWidget(QLabel("LLM 引擎:"), 0, 0)
        self.llm_engine = QComboBox()
        self.llm_engine.addItems([
            "DeepSeek (已配置)", "OpenAI GPT-4o", "Claude Sonnet",
            "Gemini Flash", "本地 Ollama", "自定义",
        ])
        cfg.addWidget(self.llm_engine, 0, 1)

        cfg.addWidget(QLabel("API Key:"), 0, 2)
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("使用「设置」中已配置的 Key，或单独填写")
        cfg.addWidget(self.api_key_input, 0, 3)

        cfg.addWidget(QLabel("执行模式:"), 1, 0)
        self.exec_mode = QComboBox()
        self.exec_mode.addItems(["模拟执行（推荐）", "半自动（需确认）", "全自动（谨慎）"])
        cfg.addWidget(self.exec_mode, 1, 1)

        cfg.addWidget(QLabel("运行频率:"), 1, 2)
        self.run_freq = QComboBox()
        self.run_freq.addItems(["每日2次(10:00/14:00)", "每日3次", "每小时", "实时(5min)"])
        cfg.addWidget(self.run_freq, 1, 3)

        self.btn_connect = QPushButton("🔌 连接并启动")
        self.btn_connect.setStyleSheet("font-size:13px; padding:8px 20px; background:#E65100; color:white;")
        cfg.addWidget(self.btn_connect, 2, 0, 1, 2)

        self.btn_save_cfg = QPushButton("💾 保存配置")
        cfg.addWidget(self.btn_save_cfg, 2, 2)

        self.btn_stop = QPushButton("⏹ 停止")
        self.btn_stop.setStyleSheet("background:#b71c1c;")
        cfg.addWidget(self.btn_stop, 2, 3)

        layout.addWidget(cfg_group)

        # ── 四层架构 Tabs ──
        self.layer_tabs = QTabWidget()
        self.layer_tabs.addTab(self._build_perception_layer(), "📡 感知层")
        self.layer_tabs.addTab(self._build_decision_layer(), "🧠 决策层")
        self.layer_tabs.addTab(self._build_execution_layer(), "⚡ 执行层")
        self.layer_tabs.addTab(self._build_feedback_layer(), "📊 反馈层")
        self.layer_tabs.addTab(self._build_pipeline_tab(), "🔄 全流程")
        self.layer_tabs.addTab(self._build_evolution_tab(), "🎯 自主进化")
        self.layer_tabs.addTab(self._build_ops_tab(), "🛰 运行中心")
        # AI 助手子tab由外部注入
        self._chat_tab_idx = -1
        layout.addWidget(self.layer_tabs)

        scroll.setWidget(container)
        outer.addWidget(scroll)

    def add_chat_tab(self, widget):
        """外部注入 AI 助手面板。"""
        self._chat_tab_idx = self.layer_tabs.addTab(widget, "💬 AI助手")

    # ═══════════════════════════════════════════
    #  感知层 — 数据采集与清洗
    # ═══════════════════════════════════════════
    def _build_perception_layer(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        desc = QLabel(
            "多源数据拉取 · 结构化处理 · 实时监控\n"
            "自动获取行情、财报、研报、公告、宏观数据、舆情，7×24 盯盘"
        )
        desc.setStyleSheet("color:#8b949e; font-size:11px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # 数据源状态表
        self.data_source_table = QTableWidget()
        self.data_source_table.setColumnCount(5)
        self.data_source_table.setHorizontalHeaderLabels([
            "数据源", "类型", "状态", "最后更新", "数据量",
        ])
        self.data_source_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.data_source_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.data_source_table.setAlternatingRowColors(True)
        layout.addWidget(self.data_source_table)

        # 操作按钮
        btn_row = QHBoxLayout()
        self.btn_fetch_all = QPushButton("📥 全量数据拉取")
        self.btn_fetch_all.setStyleSheet("font-size:12px; padding:6px 14px;")
        btn_row.addWidget(self.btn_fetch_all)
        self.btn_fetch_realtime = QPushButton("⚡ 实时行情刷新")
        btn_row.addWidget(self.btn_fetch_realtime)
        self.btn_fetch_news = QPushButton("📰 资讯舆情抓取")
        btn_row.addWidget(self.btn_fetch_news)
        self.btn_fetch_fund = QPushButton("📋 基金持仓更新")
        btn_row.addWidget(self.btn_fetch_fund)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # 监控事件流
        self.monitor_log = QTextEdit()
        self.monitor_log.setReadOnly(True)
        self.monitor_log.setMaximumHeight(120)
        self.monitor_log.setPlaceholderText("实时监控事件流...")
        self.monitor_log.setStyleSheet("font-size:11px; background:#0d1117;")
        layout.addWidget(self.monitor_log)

        return w

    # ═══════════════════════════════════════════
    #  决策层 — 多因子与策略研发
    # ═══════════════════════════════════════════
    def _build_decision_layer(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        desc = QLabel(
            "多因子筛选回测 · 跨维度信号生成 · 策略自动生成 · 行情模式识别\n"
            "融合技术面、基本面、情绪面、宏观面，LLM 综合判断多空与仓位"
        )
        desc.setStyleSheet("color:#8b949e; font-size:11px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # 自然语言策略输入
        nl_row = QHBoxLayout()
        self.strategy_input = QLineEdit()
        self.strategy_input.setPlaceholderText(
            "用自然语言描述策略，如：「选出近5日放量突破MA50且RSI<70的半导体股票」"
        )
        self.strategy_input.setMinimumHeight(36)
        self.strategy_input.setStyleSheet("font-size:13px; padding:6px;")
        nl_row.addWidget(self.strategy_input)
        self.btn_nl_run = QPushButton("🧠 AI 研判")
        self.btn_nl_run.setStyleSheet("font-size:13px; padding:8px 16px; background:#1565C0;")
        nl_row.addWidget(self.btn_nl_run)
        layout.addLayout(nl_row)

        # 内置策略快捷按钮
        quick_row = QHBoxLayout()
        quick_row.addWidget(QLabel("快捷策略:"))
        strategies = [
            ("趋势突破选股", "trend_breakout"),
            ("多因子综合", "multi_factor"),
            ("事件驱动", "event_driven"),
            ("资金流向", "money_flow"),
            ("舆情异动", "sentiment"),
            ("形态识别", "pattern"),
        ]
        self.quick_btns = {}
        for label, key in strategies:
            btn = QPushButton(label)
            btn.setStyleSheet("font-size:11px; padding:4px 10px;")
            btn.setProperty("strategy_key", key)
            quick_row.addWidget(btn)
            self.quick_btns[key] = btn
        quick_row.addStretch()
        layout.addLayout(quick_row)

        # 研判结果表
        self.decision_result_table = QTableWidget()
        self.decision_result_table.setColumnCount(8)
        self.decision_result_table.setHorizontalHeaderLabels([
            "代码", "名称", "信号", "方向", "置信度", "因子得分", "建议仓位", "理由",
        ])
        self.decision_result_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.decision_result_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.decision_result_table.setAlternatingRowColors(True)
        layout.addWidget(self.decision_result_table)

        # AI 分析输出
        self.ai_analysis_output = QTextEdit()
        self.ai_analysis_output.setReadOnly(True)
        self.ai_analysis_output.setMaximumHeight(150)
        self.ai_analysis_output.setPlaceholderText("AI 综合研判分析结果...")
        self.ai_analysis_output.setStyleSheet("font-size:12px; background:#0d1117;")
        layout.addWidget(self.ai_analysis_output)

        return w

    # ═══════════════════════════════════════════
    #  执行层 — 交易执行与风控
    # ═══════════════════════════════════════════
    def _build_execution_layer(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        desc = QLabel(
            "API 对接与自动下单 · 条件单与智能执行 · 实时风控 · 物理隔离安全\n"
            "支持分批、网格、止盈止损等执行逻辑，自动暂停/平仓/报警"
        )
        desc.setStyleSheet("color:#8b949e; font-size:11px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # 风控参数
        risk_row = QHBoxLayout()
        risk_row.addWidget(QLabel("最大单股仓位:"))
        self.max_single_pos = QSpinBox()
        self.max_single_pos.setRange(5, 50)
        self.max_single_pos.setValue(20)
        self.max_single_pos.setSuffix("%")
        risk_row.addWidget(self.max_single_pos)

        risk_row.addWidget(QLabel("最大回撤止损:"))
        self.max_drawdown = QSpinBox()
        self.max_drawdown.setRange(5, 30)
        self.max_drawdown.setValue(10)
        self.max_drawdown.setSuffix("%")
        risk_row.addWidget(self.max_drawdown)

        risk_row.addWidget(QLabel("单日亏损限制:"))
        self.daily_loss_limit = QSpinBox()
        self.daily_loss_limit.setRange(1, 20)
        self.daily_loss_limit.setValue(5)
        self.daily_loss_limit.setSuffix("%")
        risk_row.addWidget(self.daily_loss_limit)

        risk_row.addWidget(QLabel("最大持仓数:"))
        self.max_holdings = QSpinBox()
        self.max_holdings.setRange(1, 20)
        self.max_holdings.setValue(10)
        risk_row.addWidget(self.max_holdings)
        risk_row.addStretch()
        layout.addLayout(risk_row)

        # 执行队列
        self.exec_table = QTableWidget()
        self.exec_table.setColumnCount(8)
        self.exec_table.setHorizontalHeaderLabels([
            "时间", "操作", "代码", "名称", "价格", "数量", "状态", "备注",
        ])
        self.exec_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.exec_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.exec_table.setAlternatingRowColors(True)
        layout.addWidget(self.exec_table)

        # 执行按钮
        exec_btn_row = QHBoxLayout()
        self.btn_exec_all = QPushButton("▶ 执行全部待办")
        self.btn_exec_all.setStyleSheet("font-size:13px; padding:8px 16px; background:#2E7D32;")
        exec_btn_row.addWidget(self.btn_exec_all)
        self.btn_pause_exec = QPushButton("⏸ 暂停执行")
        exec_btn_row.addWidget(self.btn_pause_exec)
        self.btn_emergency_stop = QPushButton("🛑 紧急停止")
        self.btn_emergency_stop.setStyleSheet("background:#b71c1c; font-weight:bold;")
        exec_btn_row.addWidget(self.btn_emergency_stop)
        exec_btn_row.addStretch()
        layout.addLayout(exec_btn_row)

        return w

    # ═══════════════════════════════════════════
    #  反馈层 — 监控、预警与复盘
    # ═══════════════════════════════════════════
    def _build_feedback_layer(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        desc = QLabel(
            "主动式提醒 · 绩效归因 · 策略迭代\n"
            "关键价位突破、指标背离、风险超标时自动推送，定期归因分析与策略调优建议"
        )
        desc.setStyleSheet("color:#8b949e; font-size:11px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # 绩效概览卡片
        perf_row = QHBoxLayout()
        self.perf_cards = {}
        for key, label, color in [
            ("total_return", "累计收益", "#4fc3f7"),
            ("win_rate", "胜率", "#66bb6a"),
            ("sharpe", "夏普比率", "#ce93d8"),
            ("max_dd", "最大回撤", "#ef5350"),
            ("profit_factor", "盈亏比", "#ffb74d"),
            ("accuracy", "预测准确率", "#81c784"),
        ]:
            card = QWidget()
            card.setStyleSheet(
                f"background:rgba({int(color[1:3],16)},{int(color[3:5],16)},{int(color[5:7],16)},0.08);"
                f"border:1px solid {color}40; border-radius:6px; padding:4px;"
            )
            cl = QVBoxLayout(card)
            cl.setContentsMargins(8, 4, 8, 4)
            cl.setSpacing(1)
            t = QLabel(label)
            t.setStyleSheet(f"color:{color}; font-size:10px; border:none;")
            cl.addWidget(t)
            v = QLabel("-")
            v.setFont(QFont("", 14, QFont.Weight.Bold))
            v.setStyleSheet("color:#e0e0e0; border:none;")
            cl.addWidget(v)
            perf_row.addWidget(card)
            self.perf_cards[key] = v
        layout.addLayout(perf_row)

        # 预警日志
        self.alert_table = QTableWidget()
        self.alert_table.setColumnCount(5)
        self.alert_table.setHorizontalHeaderLabels([
            "时间", "类型", "代码", "内容", "状态",
        ])
        self.alert_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.alert_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.alert_table.setAlternatingRowColors(True)
        layout.addWidget(self.alert_table)

        # 策略迭代建议
        iter_row = QHBoxLayout()
        self.btn_generate_report = QPushButton("📊 生成绩效报告")
        self.btn_generate_report.setStyleSheet("font-size:12px; padding:6px 14px;")
        iter_row.addWidget(self.btn_generate_report)
        self.btn_suggest_optimize = QPushButton("🔧 AI 策略调优建议")
        iter_row.addWidget(self.btn_suggest_optimize)
        self.btn_export_report = QPushButton("📤 导出报告")
        iter_row.addWidget(self.btn_export_report)
        iter_row.addStretch()
        layout.addLayout(iter_row)

        self.feedback_output = QTextEdit()
        self.feedback_output.setReadOnly(True)
        self.feedback_output.setMaximumHeight(150)
        self.feedback_output.setPlaceholderText("绩效分析 / 策略调优建议...")
        self.feedback_output.setStyleSheet("font-size:12px; background:#0d1117;")
        layout.addWidget(self.feedback_output)

        return w

    # ═══════════════════════════════════════════
    #  全流程 — 一键执行完整量化管线
    # ═══════════════════════════════════════════
    def _build_pipeline_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        desc = QLabel(
            "一键执行完整量化流水线：数据采集 → 多因子筛选 → AI 研判 → 交易执行 → 风控监控 → 绩效复盘"
        )
        desc.setStyleSheet("color:#8b949e; font-size:12px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # 流水线步骤
        self.pipeline_table = QTableWidget()
        self.pipeline_table.setColumnCount(5)
        self.pipeline_table.setHorizontalHeaderLabels([
            "步骤", "任务", "状态", "耗时", "结果摘要",
        ])
        self.pipeline_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.pipeline_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        _steps = [
            ("1", "📡 数据采集与清洗", "待执行", "-", "-"),
            ("2", "📊 多因子计算与筛选", "待执行", "-", "-"),
            ("3", "🧠 AI 综合研判（多空/仓位）", "待执行", "-", "-"),
            ("4", "⚡ 生成交易指令", "待执行", "-", "-"),
            ("5", "🛡 风控检查", "待执行", "-", "-"),
            ("6", "▶ 执行交易", "待执行", "-", "-"),
            ("7", "📤 推送通知", "待执行", "-", "-"),
            ("8", "📊 记录并归因", "待执行", "-", "-"),
            ("9", "🎯 自主学习进化", "待执行", "-", "-"),
        ]
        self.pipeline_table.setRowCount(len(_steps))
        for i, (step, task, status, time_str, result) in enumerate(_steps):
            for j, v in enumerate([step, task, status, time_str, result]):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 2:
                    item.setForeground(QColor("#888"))
                self.pipeline_table.setItem(i, j, item)
        layout.addWidget(self.pipeline_table)

        # 进度条
        self.pipeline_progress = QProgressBar()
        self.pipeline_progress.setRange(0, 9)
        self.pipeline_progress.setValue(0)
        self.pipeline_progress.setTextVisible(True)
        self.pipeline_progress.setFormat("等待启动 %v/8")
        self.pipeline_progress.setStyleSheet(
            "QProgressBar{background:#1a1a2e; border-radius:4px; height:20px;}"
            "QProgressBar::chunk{background:#E65100; border-radius:4px;}"
        )
        layout.addWidget(self.pipeline_progress)

        # 按钮
        btn_row = QHBoxLayout()
        self.btn_run_pipeline = QPushButton("🚀 启动全流程")
        self.btn_run_pipeline.setStyleSheet(
            "font-size:14px; padding:10px 28px; background:#E65100; color:white; font-weight:bold;"
        )
        btn_row.addWidget(self.btn_run_pipeline)
        self.btn_schedule_pipeline = QPushButton("⏰ 定时执行")
        self.btn_schedule_pipeline.setStyleSheet("font-size:12px; padding:8px 16px;")
        btn_row.addWidget(self.btn_schedule_pipeline)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # 执行日志
        self.pipeline_log = QTextEdit()
        self.pipeline_log.setReadOnly(True)
        self.pipeline_log.setMaximumHeight(180)
        self.pipeline_log.setPlaceholderText("全流程执行日志...")
        self.pipeline_log.setStyleSheet("font-size:11px; background:#0d1117;")
        layout.addWidget(self.pipeline_log)

        return w

    # ═══════════════════════════════════════════
    #  公共更新方法
    # ═══════════════════════════════════════════
    def set_connected(self, connected: bool):
        if connected:
            self.status_indicator.setText("● 已连接")
            self.status_indicator.setStyleSheet("color:#66bb6a; font-size:13px; font-weight:bold;")
        else:
            self.status_indicator.setText("● 未连接")
            self.status_indicator.setStyleSheet("color:#ef5350; font-size:13px; font-weight:bold;")

    # ═══════════════════════════════════════════
    #  自主进化 — 学习 + 优化 + 赋能
    # ═══════════════════════════════════════════
    def _build_evolution_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        desc = QLabel(
            "OpenClaw 自主进化引擎：定时采集各模块执行结果 → 评估策略有效性 → "
            "学习规律调整权重 → 生成优化建议 → 赋能完全自主仓\n"
            "形成 数据→决策→执行→校准→学习→优化 的完整闭环"
        )
        desc.setStyleSheet("color:#8b949e; font-size:11px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # 定时任务配置
        sched_row = QHBoxLayout()
        sched_row.addWidget(QLabel("学习频率:"))
        self.evolve_freq = QComboBox()
        self.evolve_freq.addItems(["每日收盘后(15:35)", "每2小时", "每次全流程后", "手动"])
        sched_row.addWidget(self.evolve_freq)

        self.btn_learn_now = QPushButton("🧠 立即学习")
        self.btn_learn_now.setStyleSheet("font-size:13px; padding:8px 18px; background:#E65100; color:white;")
        sched_row.addWidget(self.btn_learn_now)

        self.btn_evolve_advice = QPushButton("💡 AI进化建议")
        self.btn_evolve_advice.setStyleSheet("font-size:13px; padding:8px 18px; background:#1565C0;")
        sched_row.addWidget(self.btn_evolve_advice)

        self.btn_apply_weights = QPushButton("✅ 应用权重到自主仓")
        self.btn_apply_weights.setStyleSheet("font-size:13px; padding:8px 18px; background:#2E7D32;")
        sched_row.addWidget(self.btn_apply_weights)
        sched_row.addStretch()
        layout.addLayout(sched_row)

        self.evolve_status = QLabel("等待学习...")
        self.evolve_status.setStyleSheet("color:#4fc3f7; font-size:12px; padding:4px;")
        layout.addWidget(self.evolve_status)

        # 策略权重表
        weight_group = QGroupBox("📊 策略权重（学习结果）")
        wl = QVBoxLayout(weight_group)
        self.weight_table = QTableWidget()
        self.weight_table.setColumnCount(5)
        self.weight_table.setHorizontalHeaderLabels([
            "策略", "权重", "准确率", "5日均涨%", "样本数",
        ])
        self.weight_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.weight_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.weight_table.setAlternatingRowColors(True)
        wl.addWidget(self.weight_table)
        layout.addWidget(weight_group)

        # 学习发现
        findings_group = QGroupBox("🔍 学习发现")
        fl = QVBoxLayout(findings_group)
        self.findings_table = QTableWidget()
        self.findings_table.setColumnCount(3)
        self.findings_table.setHorizontalHeaderLabels(["模块", "发现", "权重/建议"])
        self.findings_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.findings_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        fl.addWidget(self.findings_table)
        layout.addWidget(findings_group)

        # AI 进化建议输出
        self.evolve_output = QTextEdit()
        self.evolve_output.setReadOnly(True)
        self.evolve_output.setMaximumHeight(200)
        self.evolve_output.setPlaceholderText("AI 自主进化建议...")
        self.evolve_output.setStyleSheet("font-size:12px; background:#0d1117;")
        layout.addWidget(self.evolve_output)

        # 学习历史
        self.learning_log = QTextEdit()
        self.learning_log.setReadOnly(True)
        self.learning_log.setMaximumHeight(120)
        self.learning_log.setPlaceholderText("学习历史记录...")
        self.learning_log.setStyleSheet("font-size:11px; background:#0d1117;")
        layout.addWidget(self.learning_log)

        return w

    def _build_ops_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        desc = QLabel("统一查看最近任务运行、系统事件与运营状态。")
        desc.setStyleSheet("color:#8b949e; font-size:11px;")
        layout.addWidget(desc)

        row = QHBoxLayout()
        self.btn_refresh_ops = QPushButton("🔄 刷新运行中心")
        self.btn_refresh_ops.setStyleSheet("font-size:12px; padding:6px 14px;")
        row.addWidget(self.btn_refresh_ops)
        self.ops_status = QLabel("等待刷新...")
        self.ops_status.setStyleSheet("color:#4fc3f7; font-size:12px;")
        row.addWidget(self.ops_status)
        row.addStretch()
        layout.addLayout(row)

        task_group = QGroupBox("📋 最近任务运行")
        tl = QVBoxLayout(task_group)
        self.task_run_table = QTableWidget()
        self.task_run_table.setColumnCount(5)
        self.task_run_table.setHorizontalHeaderLabels(["时间", "任务", "来源", "状态", "摘要"])
        self.task_run_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.task_run_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.task_run_table.setAlternatingRowColors(True)
        tl.addWidget(self.task_run_table)
        layout.addWidget(task_group)

        event_group = QGroupBox("🧾 最近系统事件")
        el = QVBoxLayout(event_group)
        self.event_log_table = QTableWidget()
        self.event_log_table.setColumnCount(5)
        self.event_log_table.setHorizontalHeaderLabels(["时间", "来源", "分类", "级别", "标题"])
        self.event_log_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.event_log_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.event_log_table.setAlternatingRowColors(True)
        el.addWidget(self.event_log_table)
        layout.addWidget(event_group)
        return w

    def update_strategy_weights(self, weights: dict):
        """更新策略权重表。"""
        sorted_w = sorted(weights.items(), key=lambda x: x[1].get("weight", 0), reverse=True)
        self.weight_table.setRowCount(len(sorted_w))
        for i, (strat, w) in enumerate(sorted_w):
            vals = [
                strat, f"{w.get('weight', 1.0):.2f}",
                f"{w.get('accuracy', 0):.1f}%",
                f"{w.get('avg_pnl_5d', 0):+.2f}%",
                str(w.get("samples", 0)),
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 1:
                    wt = w.get("weight", 1.0)
                    color = "#66bb6a" if wt >= 1.5 else "#ef5350" if wt < 0.5 else "#4fc3f7"
                    item.setForeground(QColor(color))
                    item.setFont(QFont("", 11, QFont.Weight.Bold))
                self.weight_table.setItem(i, j, item)

    def update_findings(self, learnings: list[dict]):
        """更新学习发现表。"""
        self.findings_table.setRowCount(len(learnings))
        for i, l in enumerate(learnings):
            vals = [l.get("module", ""), l.get("finding", ""), str(l.get("weight", ""))]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.findings_table.setItem(i, j, item)

    def update_ops_center(self, task_runs: list[dict], events: list[dict]):
        self.task_run_table.setRowCount(len(task_runs))
        for i, r in enumerate(task_runs):
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
                    color = "#66bb6a" if v == "success" else "#ef5350" if v == "error" else "#ffb74d"
                    item.setForeground(QColor(color))
                self.task_run_table.setItem(i, j, item)

        self.event_log_table.setRowCount(len(events))
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
                    color = "#ef5350" if v == "error" else "#ffb74d" if v == "warning" else "#4fc3f7"
                    item.setForeground(QColor(color))
                self.event_log_table.setItem(i, j, item)

    # ═══════════════════════════════════════════
    #  公共更新方法
    # ═══════════════════════════════════════════
    def update_data_sources(self, sources: list[dict]):
        self.data_source_table.setRowCount(len(sources))
        for i, s in enumerate(sources):
            vals = [
                s.get("name", ""), s.get("type", ""), s.get("status", ""),
                s.get("last_update", ""), str(s.get("count", 0)),
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 2:
                    color = "#66bb6a" if "正常" in v else "#ef5350" if "异常" in v else "#ffb74d"
                    item.setForeground(QColor(color))
                self.data_source_table.setItem(i, j, item)

    def update_pipeline_step(self, step: int, status: str, elapsed: str, summary: str):
        if 0 <= step < self.pipeline_table.rowCount():
            colors = {"运行中": "#ffb74d", "完成": "#66bb6a", "失败": "#ef5350",
                      "跳过": "#888", "待执行": "#555"}
            self.pipeline_table.item(step, 2).setText(status)
            self.pipeline_table.item(step, 2).setForeground(QColor(colors.get(status, "#888")))
            self.pipeline_table.item(step, 3).setText(elapsed)
            self.pipeline_table.item(step, 4).setText(summary)
            self.pipeline_progress.setValue(step + 1)
            self.pipeline_progress.setFormat(f"步骤 {step+1}/8: {status}")

    def append_pipeline_log(self, text: str):
        self.pipeline_log.append(text)

    def update_perf_cards(self, data: dict):
        for key, lbl in self.perf_cards.items():
            val = data.get(key)
            if val is not None:
                lbl.setText(str(val))
