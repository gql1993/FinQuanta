"""
OpenClaw 智能体执行网关面板
全流程自动化中枢：数据采集 → 策略研判 → 交易执行 → 监控反馈
"""
import json

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QGroupBox, QGridLayout, QComboBox, QCheckBox,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QTextEdit, QSpinBox, QScrollArea, QProgressBar,
)
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtCore import Qt
from desktop.ui_tokens import APP_FONT


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
        title.setFont(QFont("", APP_FONT["page_title"], QFont.Weight.Bold))
        title.setStyleSheet("color:#FF6D00;")
        header.addWidget(title)
        header.addStretch()

        self.status_indicator = QLabel("● 未连接")
        self.status_indicator.setStyleSheet(
            f"color:#ef5350; font-size:{APP_FONT['emphasis']}px; font-weight:bold;"
        )
        header.addWidget(self.status_indicator)
        layout.addLayout(header)

        subtitle = QLabel(
            "开源 AI 智能体执行网关 — 连接 LLM、数据源、策略引擎与交易 API 的全流程自动化中枢"
        )
        subtitle.setStyleSheet(
            f"color:#8b949e; font-size:{APP_FONT['caption']}px; padding:0 0 6px 0;"
        )
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
        self.btn_connect.setStyleSheet(
            f"font-size:{APP_FONT['emphasis']}px; padding:8px 20px; background:#E65100; color:white;"
        )
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
        desc.setStyleSheet(f"color:#8b949e; font-size:{APP_FONT['caption']}px;")
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
        self.btn_fetch_all.setStyleSheet(f"font-size:{APP_FONT['body']}px; padding:6px 14px;")
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
        self.monitor_log.setStyleSheet(
            f"font-size:{APP_FONT['caption']}px; background:#0d1117;"
        )
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
        desc.setStyleSheet(f"color:#8b949e; font-size:{APP_FONT['caption']}px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # 自然语言策略输入
        nl_row = QHBoxLayout()
        self.strategy_input = QLineEdit()
        self.strategy_input.setPlaceholderText(
            "用自然语言描述策略，如：「选出近5日放量突破MA50且RSI<70的半导体股票」"
        )
        self.strategy_input.setMinimumHeight(36)
        self.strategy_input.setStyleSheet(
            f"font-size:{APP_FONT['emphasis']}px; padding:6px;"
        )
        nl_row.addWidget(self.strategy_input)
        self.btn_nl_run = QPushButton("🧠 AI 研判")
        self.btn_nl_run.setStyleSheet(
            f"font-size:{APP_FONT['emphasis']}px; padding:8px 16px; background:#1565C0;"
        )
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
            btn.setStyleSheet(f"font-size:{APP_FONT['caption']}px; padding:4px 10px;")
            btn.setProperty("strategy_key", key)
            quick_row.addWidget(btn)
            self.quick_btns[key] = btn
        quick_row.addStretch()
        layout.addLayout(quick_row)

        # 研判结果表
        self.decision_result_table = QTableWidget()
        self.decision_result_table.setColumnCount(11)
        self.decision_result_table.setHorizontalHeaderLabels([
            "代码", "名称", "信号", "方向", "置信度", "因子得分", "建议仓位", "验证", "验证分", "风险级别", "理由",
        ])
        self.decision_result_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.decision_result_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.decision_result_table.setAlternatingRowColors(True)
        layout.addWidget(self.decision_result_table)

        self.decision_guard_label = QLabel("验证层状态：待运行")
        self.decision_guard_label.setWordWrap(True)
        self.decision_guard_label.setStyleSheet(
            f"color:#8b949e; font-size:{APP_FONT['caption']}px; padding:4px 0;"
        )
        layout.addWidget(self.decision_guard_label)

        self.decision_compare_text = QTextEdit()
        self.decision_compare_text.setReadOnly(True)
        self.decision_compare_text.setMaximumHeight(120)
        self.decision_compare_text.setPlaceholderText("这里会显示原始决策与守门后决策的差异对照。")
        self.decision_compare_text.setStyleSheet(
            f"font-size:{APP_FONT['caption']}px; background:#0d1117;"
        )
        layout.addWidget(self.decision_compare_text)

        # AI 分析输出
        self.ai_analysis_output = QTextEdit()
        self.ai_analysis_output.setReadOnly(True)
        self.ai_analysis_output.setMaximumHeight(150)
        self.ai_analysis_output.setPlaceholderText("AI 综合研判分析结果...")
        self.ai_analysis_output.setStyleSheet(
            f"font-size:{APP_FONT['body']}px; background:#0d1117;"
        )
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
        desc.setStyleSheet(f"color:#8b949e; font-size:{APP_FONT['caption']}px;")
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

        self.execution_plan_label = QLabel("策略分流：待运行")
        self.execution_plan_label.setWordWrap(True)
        self.execution_plan_label.setStyleSheet(
            f"color:#8b949e; font-size:{APP_FONT['caption']}px; padding:4px 0;"
        )
        layout.addWidget(self.execution_plan_label)

        self.execution_block_table = QTableWidget()
        self.execution_block_table.setColumnCount(4)
        self.execution_block_table.setHorizontalHeaderLabels([
            "动作", "代码", "名称", "分流原因",
        ])
        self.execution_block_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.execution_block_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.execution_block_table.setAlternatingRowColors(True)
        self.execution_block_table.setMaximumHeight(120)
        layout.addWidget(self.execution_block_table)

        # 执行按钮
        exec_btn_row = QHBoxLayout()
        self.btn_exec_all = QPushButton("▶ 执行全部待办")
        self.btn_exec_all.setStyleSheet(
            f"font-size:{APP_FONT['emphasis']}px; padding:8px 16px; background:#2E7D32;"
        )
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
        desc.setStyleSheet(f"color:#8b949e; font-size:{APP_FONT['caption']}px;")
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
            t.setStyleSheet(f"color:{color}; font-size:{APP_FONT['caption']}px; border:none;")
            cl.addWidget(t)
            v = QLabel("-")
            v.setFont(QFont("", APP_FONT["section"], QFont.Weight.Bold))
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
        self.btn_generate_report.setStyleSheet(
            f"font-size:{APP_FONT['body']}px; padding:6px 14px;"
        )
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
        self.feedback_output.setStyleSheet(
            f"font-size:{APP_FONT['body']}px; background:#0d1117;"
        )
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
        desc.setStyleSheet(f"color:#8b949e; font-size:{APP_FONT['body']}px;")
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
            f"font-size:{APP_FONT['section']}px; padding:10px 28px; background:#E65100; color:white; font-weight:bold;"
        )
        btn_row.addWidget(self.btn_run_pipeline)
        self.btn_schedule_pipeline = QPushButton("⏰ 定时执行")
        self.btn_schedule_pipeline.setStyleSheet(
            f"font-size:{APP_FONT['body']}px; padding:8px 16px;"
        )
        btn_row.addWidget(self.btn_schedule_pipeline)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # 执行日志
        self.pipeline_log = QTextEdit()
        self.pipeline_log.setReadOnly(True)
        self.pipeline_log.setMaximumHeight(180)
        self.pipeline_log.setPlaceholderText("全流程执行日志...")
        self.pipeline_log.setStyleSheet(
            f"font-size:{APP_FONT['caption']}px; background:#0d1117;"
        )
        layout.addWidget(self.pipeline_log)

        orch_group = QGroupBox("🧭 Coordinator 编排轨迹")
        ol = QVBoxLayout(orch_group)
        self.coordinator_orch_label = QLabel("Coordinator 编排：等待流水线执行")
        self.coordinator_orch_label.setWordWrap(True)
        self.coordinator_orch_label.setStyleSheet(
            f"color:#cbd5e1; font-size:{APP_FONT['caption']}px; padding:4px 0;"
        )
        ol.addWidget(self.coordinator_orch_label)

        self.coordinator_orch_table = QTableWidget()
        self.coordinator_orch_table.setColumnCount(6)
        self.coordinator_orch_table.setHorizontalHeaderLabels([
            "阶段", "Ready", "模式", "动作数", "执行动作", "原因",
        ])
        self.coordinator_orch_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.coordinator_orch_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.coordinator_orch_table.setAlternatingRowColors(True)
        self.coordinator_orch_table.setMaximumHeight(160)
        self.coordinator_orch_table.cellClicked.connect(self._on_coordinator_orch_row_clicked)
        ol.addWidget(self.coordinator_orch_table)

        self.coordinator_orch_detail = QTextEdit()
        self.coordinator_orch_detail.setReadOnly(True)
        self.coordinator_orch_detail.setMaximumHeight(140)
        self.coordinator_orch_detail.setPlaceholderText("点击上方编排记录查看动作详情。")
        self.coordinator_orch_detail.setStyleSheet(
            f"font-size:{APP_FONT['caption']}px; background:#0d1117;"
        )
        ol.addWidget(self.coordinator_orch_detail)
        layout.addWidget(orch_group)

        trace_group = QGroupBox("🔎 Agent Trace 明细")
        tl = QVBoxLayout(trace_group)
        self.agent_trace_label = QLabel("Agent Trace：等待流水线执行")
        self.agent_trace_label.setWordWrap(True)
        self.agent_trace_label.setStyleSheet(
            f"color:#cbd5e1; font-size:{APP_FONT['caption']}px; padding:4px 0;"
        )
        tl.addWidget(self.agent_trace_label)

        self.agent_trace_table = QTableWidget()
        self.agent_trace_table.setColumnCount(6)
        self.agent_trace_table.setHorizontalHeaderLabels([
            "Agent", "阶段", "状态", "耗时(ms)", "Span", "摘要",
        ])
        self.agent_trace_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.agent_trace_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.agent_trace_table.setAlternatingRowColors(True)
        self.agent_trace_table.setMaximumHeight(180)
        self.agent_trace_table.cellClicked.connect(self._on_agent_trace_row_clicked)
        tl.addWidget(self.agent_trace_table)

        self.agent_trace_detail = QTextEdit()
        self.agent_trace_detail.setReadOnly(True)
        self.agent_trace_detail.setMaximumHeight(160)
        self.agent_trace_detail.setPlaceholderText("点击上方 span 查看输入/输出摘要。")
        self.agent_trace_detail.setStyleSheet(
            f"font-size:{APP_FONT['caption']}px; background:#0d1117;"
        )
        tl.addWidget(self.agent_trace_detail)
        layout.addWidget(trace_group)

        self._agent_trace_items: list[dict] = []
        self._coordinator_orch_items: list[dict] = []

        return w

    # ═══════════════════════════════════════════
    #  公共更新方法
    # ═══════════════════════════════════════════
    def set_connected(self, connected: bool):
        if connected:
            self.status_indicator.setText("● 已连接")
            self.status_indicator.setStyleSheet(
                f"color:#66bb6a; font-size:{APP_FONT['emphasis']}px; font-weight:bold;"
            )
        else:
            self.status_indicator.setText("● 未连接")
            self.status_indicator.setStyleSheet(
                f"color:#ef5350; font-size:{APP_FONT['emphasis']}px; font-weight:bold;"
            )

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
        desc.setStyleSheet(f"color:#8b949e; font-size:{APP_FONT['caption']}px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # 定时任务配置
        sched_row = QHBoxLayout()
        sched_row.addWidget(QLabel("学习频率:"))
        self.evolve_freq = QComboBox()
        self.evolve_freq.addItems(["每日收盘后(15:35)", "每2小时", "每次全流程后", "手动"])
        sched_row.addWidget(self.evolve_freq)

        self.btn_learn_now = QPushButton("🧠 立即学习")
        self.btn_learn_now.setStyleSheet(
            f"font-size:{APP_FONT['emphasis']}px; padding:8px 18px; background:#E65100; color:white;"
        )
        sched_row.addWidget(self.btn_learn_now)

        self.btn_evolve_advice = QPushButton("💡 AI进化建议")
        self.btn_evolve_advice.setStyleSheet(
            f"font-size:{APP_FONT['emphasis']}px; padding:8px 18px; background:#1565C0;"
        )
        sched_row.addWidget(self.btn_evolve_advice)

        self.btn_apply_weights = QPushButton("✅ 应用权重到自主仓")
        self.btn_apply_weights.setStyleSheet(
            f"font-size:{APP_FONT['emphasis']}px; padding:8px 18px; background:#2E7D32;"
        )
        sched_row.addWidget(self.btn_apply_weights)
        sched_row.addStretch()
        layout.addLayout(sched_row)

        self.evolve_status = QLabel("等待学习...")
        self.evolve_status.setStyleSheet(
            f"color:#4fc3f7; font-size:{APP_FONT['body']}px; padding:4px;"
        )
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

        verify_group = QGroupBox("🛂 验证守门效果")
        vl = QVBoxLayout(verify_group)
        self.verification_effect_label = QLabel("等待学习结果...")
        self.verification_effect_label.setStyleSheet(
            f"color:#cbd5e1; font-size:{APP_FONT['body']}px; padding:4px 0;"
        )
        self.verification_effect_label.setWordWrap(True)
        vl.addWidget(self.verification_effect_label)
        self.verification_effect_text = QTextEdit()
        self.verification_effect_text.setReadOnly(True)
        self.verification_effect_text.setMaximumHeight(120)
        self.verification_effect_text.setPlaceholderText("这里会展示验证通过/存疑/拦截买入的后验效果。")
        self.verification_effect_text.setStyleSheet(
            f"font-size:{APP_FONT['caption']}px; background:#0d1117;"
        )
        vl.addWidget(self.verification_effect_text)
        layout.addWidget(verify_group)

        coordinator_group = QGroupBox("🧭 协调者分流效果")
        cl = QVBoxLayout(coordinator_group)
        self.coordinator_effect_label = QLabel("等待学习结果...")
        self.coordinator_effect_label.setStyleSheet(
            f"color:#cbd5e1; font-size:{APP_FONT['body']}px; padding:4px 0;"
        )
        self.coordinator_effect_label.setWordWrap(True)
        cl.addWidget(self.coordinator_effect_label)
        self.coordinator_effect_text = QTextEdit()
        self.coordinator_effect_text.setReadOnly(True)
        self.coordinator_effect_text.setMaximumHeight(120)
        self.coordinator_effect_text.setPlaceholderText("这里会展示 sell_only / limit_buy / observe_only 的后验效果与当前参数。")
        self.coordinator_effect_text.setStyleSheet(
            f"font-size:{APP_FONT['caption']}px; background:#0d1117;"
        )
        cl.addWidget(self.coordinator_effect_text)
        layout.addWidget(coordinator_group)

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
        self.evolve_output.setStyleSheet(
            f"font-size:{APP_FONT['body']}px; background:#0d1117;"
        )
        layout.addWidget(self.evolve_output)

        # 学习历史
        self.learning_log = QTextEdit()
        self.learning_log.setReadOnly(True)
        self.learning_log.setMaximumHeight(120)
        self.learning_log.setPlaceholderText("学习历史记录...")
        self.learning_log.setStyleSheet(
            f"font-size:{APP_FONT['caption']}px; background:#0d1117;"
        )
        layout.addWidget(self.learning_log)

        return w

    def _build_ops_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        desc = QLabel("统一查看最近任务运行、系统事件与运营状态。")
        desc.setStyleSheet(f"color:#8b949e; font-size:{APP_FONT['caption']}px;")
        layout.addWidget(desc)

        row = QHBoxLayout()
        self.btn_refresh_ops = QPushButton("🔄 刷新运行中心")
        self.btn_refresh_ops.setStyleSheet(
            f"font-size:{APP_FONT['body']}px; padding:6px 14px;"
        )
        row.addWidget(self.btn_refresh_ops)
        self.ops_status = QLabel("等待刷新...")
        self.ops_status.setStyleSheet(f"color:#4fc3f7; font-size:{APP_FONT['body']}px;")
        row.addWidget(self.ops_status)
        row.addStretch()
        layout.addLayout(row)

        daemon_row = QHBoxLayout()
        self.daemon_status_label = QLabel("Daemon: -")
        self.daemon_status_label.setStyleSheet(
            f"color:#cbd5e1; font-size:{APP_FONT['body']}px;"
        )
        daemon_row.addWidget(self.daemon_status_label)
        self.daemon_next_task_label = QLabel("下一任务: -")
        self.daemon_next_task_label.setStyleSheet(
            f"color:#94a3b8; font-size:{APP_FONT['body']}px;"
        )
        daemon_row.addWidget(self.daemon_next_task_label)
        daemon_row.addStretch()
        layout.addLayout(daemon_row)

        oc_daemon_group = QGroupBox("🦀 后台 OpenClaw")
        odl = QVBoxLayout(oc_daemon_group)
        self.openclaw_daemon_summary = QLabel("等待刷新后台 OpenClaw 状态...")
        self.openclaw_daemon_summary.setWordWrap(True)
        self.openclaw_daemon_summary.setStyleSheet(
            f"color:#cbd5e1; font-size:{APP_FONT['caption']}px; padding:4px 0;"
        )
        odl.addWidget(self.openclaw_daemon_summary)

        status_grid = QGridLayout()
        self.openclaw_daemon_config_label = QLabel("配置: -")
        self.openclaw_daemon_last_run_label = QLabel("上次执行: -")
        self.openclaw_daemon_alert_label = QLabel("告警: -")
        self.openclaw_daemon_guard_label = QLabel("安全闸: -")
        for idx, widget in enumerate([
            self.openclaw_daemon_config_label,
            self.openclaw_daemon_last_run_label,
            self.openclaw_daemon_alert_label,
            self.openclaw_daemon_guard_label,
        ]):
            widget.setWordWrap(True)
            widget.setStyleSheet(f"color:#94a3b8; font-size:{APP_FONT['caption']}px;")
            status_grid.addWidget(widget, idx // 2, idx % 2)
        odl.addLayout(status_grid)

        self.openclaw_daemon_history_table = QTableWidget()
        self.openclaw_daemon_history_table.setColumnCount(8)
        self.openclaw_daemon_history_table.setHorizontalHeaderLabels([
            "时间", "状态", "模式", "拦截", "Trace", "编排", "仿真", "摘要",
        ])
        self.openclaw_daemon_history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.openclaw_daemon_history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.openclaw_daemon_history_table.setAlternatingRowColors(True)
        self.openclaw_daemon_history_table.setMaximumHeight(150)
        odl.addWidget(self.openclaw_daemon_history_table)
        self.openclaw_guard_replay_label = QLabel("安全闸回放：暂无记录")
        self.openclaw_guard_replay_label.setWordWrap(True)
        self.openclaw_guard_replay_label.setStyleSheet(
            f"color:#94a3b8; font-size:{APP_FONT['caption']}px; padding:4px 0;"
        )
        odl.addWidget(self.openclaw_guard_replay_label)
        replay_btn_row = QHBoxLayout()
        self.btn_run_guard_replay = QPushButton("🧪 运行安全闸回放")
        self.btn_run_guard_replay.setStyleSheet(
            f"font-size:{APP_FONT['caption']}px; padding:5px 12px; background:#0f766e;"
        )
        replay_btn_row.addWidget(self.btn_run_guard_replay)
        self.openclaw_guard_replay_status = QLabel("")
        self.openclaw_guard_replay_status.setStyleSheet(
            f"color:#94a3b8; font-size:{APP_FONT['caption']}px;"
        )
        replay_btn_row.addWidget(self.openclaw_guard_replay_status)
        replay_btn_row.addStretch()
        odl.addLayout(replay_btn_row)
        self.openclaw_guard_replay_table = QTableWidget()
        self.openclaw_guard_replay_table.setColumnCount(7)
        self.openclaw_guard_replay_table.setHorizontalHeaderLabels([
            "时间", "来源", "模式", "输入", "通过", "拒绝", "结果",
        ])
        self.openclaw_guard_replay_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.openclaw_guard_replay_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.openclaw_guard_replay_table.setAlternatingRowColors(True)
        self.openclaw_guard_replay_table.setMaximumHeight(120)
        odl.addWidget(self.openclaw_guard_replay_table)
        self.openclaw_config_audit_label = QLabel("配置审计：暂无记录")
        self.openclaw_config_audit_label.setWordWrap(True)
        self.openclaw_config_audit_label.setStyleSheet(
            f"color:#94a3b8; font-size:{APP_FONT['caption']}px; padding:4px 0;"
        )
        odl.addWidget(self.openclaw_config_audit_label)
        audit_btn_row = QHBoxLayout()
        self.btn_rollback_config_audit = QPushButton("↩ 回滚最近配置变更")
        self.btn_rollback_config_audit.setStyleSheet(
            f"font-size:{APP_FONT['caption']}px; padding:5px 12px; background:#7c3aed;"
        )
        audit_btn_row.addWidget(self.btn_rollback_config_audit)
        self.openclaw_config_rollback_status = QLabel("")
        self.openclaw_config_rollback_status.setStyleSheet(
            f"color:#94a3b8; font-size:{APP_FONT['caption']}px;"
        )
        audit_btn_row.addWidget(self.openclaw_config_rollback_status)
        audit_btn_row.addStretch()
        odl.addLayout(audit_btn_row)
        self.openclaw_config_audit_table = QTableWidget()
        self.openclaw_config_audit_table.setColumnCount(5)
        self.openclaw_config_audit_table.setHorizontalHeaderLabels(["时间", "配置域", "动作", "变更字段", "操作者"])
        self.openclaw_config_audit_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.openclaw_config_audit_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.openclaw_config_audit_table.setAlternatingRowColors(True)
        self.openclaw_config_audit_table.setMaximumHeight(120)
        odl.addWidget(self.openclaw_config_audit_table)
        layout.addWidget(oc_daemon_group)

        agent_group = QGroupBox("🤖 Agent Registry / 智能体能力")
        al = QVBoxLayout(agent_group)
        self.agent_registry_label = QLabel("等待刷新运行中心...")
        self.agent_registry_label.setWordWrap(True)
        self.agent_registry_label.setStyleSheet(
            f"color:#cbd5e1; font-size:{APP_FONT['caption']}px; padding:4px 0;"
        )
        al.addWidget(self.agent_registry_label)
        self.agent_registry_table = QTableWidget()
        self.agent_registry_table.setColumnCount(6)
        self.agent_registry_table.setHorizontalHeaderLabels([
            "Key", "名称", "阶段", "安全级别", "能力", "入口",
        ])
        self.agent_registry_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.agent_registry_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.agent_registry_table.setAlternatingRowColors(True)
        self.agent_registry_table.setMaximumHeight(190)
        al.addWidget(self.agent_registry_table)
        layout.addWidget(agent_group)

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
                    item.setFont(QFont("", APP_FONT["caption"], QFont.Weight.Bold))
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

    def update_verification_effectiveness(self, payload: dict):
        eff = payload or {}
        blocked = int(eff.get("blocked_buy_count", 0) or 0)
        avoided = int(eff.get("avoided_losses", 0) or 0)
        missed = int(eff.get("missed_gains", 0) or 0)
        annotated = int(eff.get("annotated_buy_count", 0) or 0)
        verified = int(eff.get("verified_candidates", 0) or 0)
        questionable = int(eff.get("questionable_candidates", 0) or 0)
        rejected = int(eff.get("rejected_candidates", 0) or 0)
        avoided_rate = float(eff.get("avoided_loss_rate", 0) or 0)

        self.verification_effect_label.setText(
            "验证守门效果："
            f"通过候选 {verified} | 存疑候选 {questionable} | 高风险候选 {rejected} | "
            f"拦截买入 {blocked} | 避免亏损 {avoided} | 错过上涨 {missed}"
        )

        lines = [
            f"避免亏损率: {avoided_rate:.1f}%",
            f"存疑放行次数: {annotated}",
        ]
        if blocked > 0:
            lines.append("说明: 被拦截买入会做后验校准，用来判断验证层是否过严或过松。")
        else:
            lines.append("说明: 暂无被拦截买入样本，继续积累数据后再评估守门质量。")
        self.verification_effect_text.setText("\n".join(lines))

    def update_coordinator_effectiveness(self, payload: dict, config: dict | None = None):
        eff = payload or {}
        cfg = config or {}
        routed = int(eff.get("routed_blocked_count", 0) or 0)
        avoided = int(eff.get("avoided_losses", 0) or 0)
        missed = int(eff.get("missed_gains", 0) or 0)
        avoided_rate = float(eff.get("avoided_loss_rate", 0) or 0)
        sell_only = int(eff.get("sell_only_count", 0) or 0)
        limit_buy = int(eff.get("limit_buy_count", 0) or 0)
        observe_only = int(eff.get("observe_only_count", 0) or 0)

        self.coordinator_effect_label.setText(
            "协调者分流效果："
            f"分流拦截 {routed} | 避免亏损 {avoided} | 错过上涨 {missed} | "
            f"避免亏损率 {avoided_rate:.1f}%"
        )

        lines = [
            f"触发次数: sell_only {sell_only} | limit_buy {limit_buy} | observe_only {observe_only}",
            (
                "当前参数: "
                f"sell_only舆情<{float(cfg.get('sell_only_sentiment_ratio', 0) or 0):.2f} | "
                f"limit_buy舆情<{float(cfg.get('limit_buy_sentiment_ratio', 0) or 0):.2f} | "
                f"限买 {int(cfg.get('limit_buy_max_count', 0) or 0)} 条 | "
                f"观察模式守门拦截率>={float(cfg.get('observe_blocked_ratio', 0) or 0):.2f}"
            ),
        ]
        note = str(cfg.get("last_learning_note", "") or "")
        if note:
            lines.append(f"最近调参: {note}")
        elif routed > 0:
            lines.append("说明: 分流样本已进入后验校准，用来判断协调者是否过严或过松。")
        else:
            lines.append("说明: 暂无分流拦截样本，继续积累数据后再评估调参。")
        self.coordinator_effect_text.setText("\n".join(lines))

    def update_coordinator_orchestration(self, orchestration: list[dict]):
        self._coordinator_orch_items = list(orchestration or [])
        if self._coordinator_orch_items:
            action_total = sum(
                len((item.get("actions_done", item.get("actions", [])) or []))
                for item in self._coordinator_orch_items
                if isinstance(item, dict)
            )
            self.coordinator_orch_label.setText(
                f"Coordinator 编排：{len(self._coordinator_orch_items)} 个阶段检查 | 动作 {action_total} 个"
            )
        else:
            self.coordinator_orch_label.setText("Coordinator 编排：暂无记录，运行全流程后展示")
            self.coordinator_orch_detail.clear()

        self.coordinator_orch_table.setRowCount(len(self._coordinator_orch_items))
        for i, item in enumerate(self._coordinator_orch_items):
            actions = item.get("actions_done", item.get("actions", [])) or []
            action_names = [
                str(action.get("type", ""))
                + (f"/{action.get('status')}" if action.get("status") else "")
                for action in actions
                if isinstance(action, dict)
            ]
            vals = [
                item.get("stage", ""),
                "是" if bool(item.get("ready", True)) else "否",
                item.get("mode", ""),
                str(len(actions)),
                ", ".join(action_names[:2]) + ("..." if len(action_names) > 2 else ""),
                item.get("reason", ""),
            ]
            for j, v in enumerate(vals):
                table_item = QTableWidgetItem(str(v))
                table_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 1:
                    table_item.setForeground(QColor("#66bb6a" if v == "是" else "#ffb74d"))
                if j == 2 and str(v) not in {"normal", ""}:
                    table_item.setForeground(QColor("#4fc3f7"))
                self.coordinator_orch_table.setItem(i, j, table_item)
        if self._coordinator_orch_items:
            self._render_coordinator_orch_detail(0)

    def _on_coordinator_orch_row_clicked(self, row: int, col: int):
        self._render_coordinator_orch_detail(row)

    def _render_coordinator_orch_detail(self, row: int):
        if row < 0 or row >= len(self._coordinator_orch_items):
            return
        item = self._coordinator_orch_items[row]
        payload = {
            "stage": item.get("stage", ""),
            "ready": bool(item.get("ready", True)),
            "mode": item.get("mode", ""),
            "reason": item.get("reason", ""),
            "actions": item.get("actions", []),
            "actions_done": item.get("actions_done", []),
            "timestamp": item.get("timestamp", ""),
        }
        self.coordinator_orch_detail.setText(json.dumps(payload, ensure_ascii=False, indent=2, default=str))

    def update_agent_trace(self, trace_items: list[dict], trace_context: dict | None = None):
        self._agent_trace_items = list(trace_items or [])
        ctx = trace_context or {}
        trace_id = str(ctx.get("trace_id_hex", "") or ctx.get("trace_id", "") or "")
        status = str(ctx.get("status", "") or "-")
        duration = ctx.get("duration_ms", "-")
        if self._agent_trace_items:
            self.agent_trace_label.setText(
                f"Agent Trace：{len(self._agent_trace_items)} spans | "
                f"trace={trace_id[:24] or '-'} | status={status} | duration={duration}ms"
            )
        else:
            self.agent_trace_label.setText("Agent Trace：暂无 span，运行全流程后展示")
            self.agent_trace_detail.clear()

        self.agent_trace_table.setRowCount(len(self._agent_trace_items))
        for i, span in enumerate(self._agent_trace_items):
            output_summary = span.get("output_summary", {}) or {}
            summary = self._short_trace_summary(output_summary)
            vals = [
                span.get("agent_key", ""),
                span.get("stage", ""),
                span.get("status", ""),
                str(span.get("duration_ms", "")),
                str(span.get("span_id", ""))[:10],
                summary,
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(str(v))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 2:
                    color = "#66bb6a" if v == "ok" else "#ef5350" if v == "error" else "#ffb74d"
                    item.setForeground(QColor(color))
                self.agent_trace_table.setItem(i, j, item)
        if self._agent_trace_items:
            self._render_agent_trace_detail(0)

    def _short_trace_summary(self, summary: dict) -> str:
        if not isinstance(summary, dict) or not summary:
            return "-"
        parts = []
        for key, value in list(summary.items())[:3]:
            if isinstance(value, dict):
                if "count" in value:
                    parts.append(f"{key}:{value.get('count')}")
                elif "keys" in value:
                    parts.append(f"{key}:dict")
                else:
                    parts.append(f"{key}:obj")
            else:
                text = str(value).replace("\n", " ")
                parts.append(f"{key}:{text[:18]}")
        return " | ".join(parts) if parts else "-"

    def _on_agent_trace_row_clicked(self, row: int, col: int):
        self._render_agent_trace_detail(row)

    def _render_agent_trace_detail(self, row: int):
        if row < 0 or row >= len(self._agent_trace_items):
            return
        span = self._agent_trace_items[row]
        payload = {
            "agent": span.get("agent_key", ""),
            "stage": span.get("stage", ""),
            "status": span.get("status", ""),
            "duration_ms": span.get("duration_ms", 0),
            "trace_id_hex": span.get("trace_id_hex", ""),
            "span_id": span.get("span_id", ""),
            "parent_span_id": span.get("parent_span_id", ""),
            "input_summary": span.get("input_summary", {}),
            "output_summary": span.get("output_summary", {}),
        }
        if span.get("error"):
            payload["error"] = span.get("error", "")
        self.agent_trace_detail.setText(json.dumps(payload, ensure_ascii=False, indent=2, default=str))

    def update_ops_center(
        self,
        task_runs: list[dict],
        events: list[dict],
        daemon: dict | None = None,
        registry: dict | None = None,
        openclaw_status: dict | None = None,
    ):
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
        daemon = daemon or {}
        active = bool(daemon.get("active", False))
        pid = int(daemon.get("leader_pid", 0) or 0)
        hb = str(daemon.get("heartbeat_at", "") or "-")
        self.daemon_status_label.setText(f"Daemon: {'🟢 运行中' if active else '🔴 未运行'}  PID:{pid or '-'}  心跳:{hb}")
        self.daemon_status_label.setStyleSheet(
            (
                f"color:#66bb6a; font-size:{APP_FONT['body']}px;"
                if active
                else f"color:#ef5350; font-size:{APP_FONT['body']}px;"
            )
        )
        next_task = daemon.get("next_task", {}) or {}
        next_name = str(next_task.get("task_name", "") or "-")
        next_time = str(next_task.get("scheduled_at", "") or "-")
        self.daemon_next_task_label.setText(f"下一任务: {next_name} @ {next_time}")
        self.update_openclaw_daemon_status(openclaw_status or {})
        self.update_agent_registry(registry or {})

    def update_openclaw_daemon_status(self, payload: dict):
        daemon = (payload or {}).get("daemon", {}) or {}
        openclaw = (payload or {}).get("openclaw", {}) or {}
        guard = (payload or {}).get("trade_guard", {}) or {}
        config = openclaw.get("config", {}) or {}
        config_audit = openclaw.get("config_audit", {}) or {}
        readiness = openclaw.get("readiness", {}) or {}
        last_run = openclaw.get("last_run", {}) or {}
        alert_state = openclaw.get("alert_state", {}) or {}
        alert_policy = openclaw.get("alert_policy", {}) or {}
        guard_cfg = guard.get("config", {}) or {}
        usage = guard.get("usage", {}) or {}
        simulation = guard.get("simulation", {}) or {}
        replay = guard.get("replay", {}) or {}
        trace = last_run.get("agent_trace", {}) or {}
        orchestration = last_run.get("coordinator_orchestration", {}) or {}

        active = bool(daemon.get("active", False))
        enabled = bool(config.get("enabled", False))
        time_text = str(config.get("time", "-") or "-")
        boards = "、".join([str(x) for x in config.get("boards", [])][:5]) or "-"
        self.openclaw_daemon_config_label.setText(
            f"配置: {'启用' if enabled else '停用'} | {time_text} | 板块 {boards}"
        )

        status = str(last_run.get("status", "") or "-")
        status_text = {"success": "成功", "warning": "告警", "error": "失败"}.get(status, status)
        summary = str(last_run.get("summary", "") or "-")
        ts = str(last_run.get("timestamp", "") or "-")[:19]
        self.openclaw_daemon_last_run_label.setText(
            f"上次执行: {status_text} | {ts} | {summary[:80]}"
        )
        last_color = "#66bb6a" if status == "success" else "#ef5350" if status == "error" else "#ffb74d"
        self.openclaw_daemon_last_run_label.setStyleSheet(
            f"color:{last_color}; font-size:{APP_FONT['caption']}px;"
        )

        consecutive = int(alert_state.get("consecutive_errors", 0) or 0)
        suppressed = int(alert_state.get("suppressed_count", 0) or 0)
        escalated = bool(alert_state.get("escalated", False))
        self.openclaw_daemon_alert_label.setText(
            f"告警: {'启用' if alert_policy.get('enabled', True) else '停用'} | "
            f"静默 {alert_policy.get('suppress_seconds', '-')}s | 升级 {alert_policy.get('escalate_after', '-')}次 | "
            f"连续失败 {consecutive} | 抑制 {suppressed} | {'已升级' if escalated else '未升级'}"
        )

        buy_enabled = bool(guard_cfg.get("unattended_buy_enabled", False))
        buy_count = int(usage.get("buy_count", 0) or 0)
        buy_amount = float(usage.get("buy_amount", 0) or 0)
        sim_passed = bool(simulation.get("passed", False))
        sim_runs = int(simulation.get("consecutive_success_runs", 0) or 0)
        sim_required = int(simulation.get("required_runs", 0) or 0)
        self.openclaw_daemon_guard_label.setText(
            f"安全闸: 无人买入 {'开启' if buy_enabled else '关闭'} | 今日 {buy_count}笔/{buy_amount:.0f} | "
            f"仿真 {'通过' if sim_passed else '未通过'} {sim_runs}/{sim_required}"
        )
        self.openclaw_daemon_summary.setText(
            f"就绪度 {readiness.get('status', '-')} | "
            f"{str(readiness.get('summary', '') or '')[:80]} | "
            f"Daemon {'运行中' if active else '未运行'} | OpenClaw {'启用' if enabled else '停用'} | "
            f"最近状态 {status_text} | Trace {int(trace.get('span_count', 0) or 0)} spans | "
            f"编排 {int(orchestration.get('stage_count', 0) or 0)} 阶段"
        )
        readiness_color = {
            "ready": "#66bb6a",
            "warning": "#ffb74d",
            "error": "#ef5350",
        }.get(str(readiness.get("status", "")), "#cbd5e1")
        self.openclaw_daemon_summary.setStyleSheet(
            f"color:{readiness_color}; font-size:{APP_FONT['caption']}px; padding:4px 0;"
        )

        history = list(openclaw.get("history", []) or [])[:10]
        self.openclaw_daemon_history_table.setRowCount(len(history))
        for i, item in enumerate(history):
            sim = item.get("simulation", {}) or {}
            vals = [
                str(item.get("timestamp", "") or "")[:19],
                str(item.get("status", "") or ""),
                str(item.get("mode", "") or ""),
                str(item.get("blocked_count", 0) or 0),
                str(item.get("trace_span_count", 0) or 0),
                f"{item.get('orchestration_stage_count', 0) or 0}/{item.get('orchestration_action_count', 0) or 0}",
                f"{'通过' if sim.get('passed') else '未过'} {sim.get('consecutive_success_runs', 0)}/{sim.get('required_runs', 0)}",
                str(item.get("summary", "") or "")[:80],
            ]
            for j, v in enumerate(vals):
                table_item = QTableWidgetItem(str(v))
                table_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 1:
                    color = "#66bb6a" if v == "success" else "#ef5350" if v == "error" else "#ffb74d"
                    table_item.setForeground(QColor(color))
                self.openclaw_daemon_history_table.setItem(i, j, table_item)

        replay_last = replay.get("last", {}) or {}
        replay_history = list(replay.get("history", []) or [])[:10]
        if replay_last:
            self.openclaw_guard_replay_label.setText(
                "安全闸回放："
                f"{str(replay_last.get('timestamp', '') or '-')[:19]} | "
                f"输入 {replay_last.get('input_count', 0)} | "
                f"通过 {replay_last.get('approved_count', 0)} | "
                f"拒绝 {replay_last.get('rejected_count', 0)}"
            )
        else:
            self.openclaw_guard_replay_label.setText("安全闸回放：暂无记录")
        self.openclaw_guard_replay_table.setRowCount(len(replay_history))
        for i, item in enumerate(replay_history):
            ok = bool(item.get("ok", False))
            vals = [
                str(item.get("timestamp", "") or "")[:19],
                str(item.get("source", "") or ""),
                str(item.get("mode", "") or ""),
                str(item.get("input_count", 0) or 0),
                str(item.get("approved_count", 0) or 0),
                str(item.get("rejected_count", 0) or 0),
                "OK" if ok else str(item.get("message", "FAIL") or "FAIL")[:30],
            ]
            for j, v in enumerate(vals):
                table_item = QTableWidgetItem(str(v))
                table_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 6:
                    table_item.setForeground(QColor("#66bb6a" if ok else "#ef5350"))
                self.openclaw_guard_replay_table.setItem(i, j, table_item)

        audit_history = list(config_audit.get("history", []) or [])[:10]
        if audit_history:
            latest = audit_history[0]
            self.openclaw_config_audit_label.setText(
                "配置审计："
                f"{str(latest.get('timestamp', '') or '-')[:19]} | "
                f"{latest.get('domain', '')}/{latest.get('action', '')} | "
                f"{', '.join(latest.get('changed_keys', [])[:4])}"
            )
        else:
            self.openclaw_config_audit_label.setText("配置审计：暂无记录")
        self.openclaw_config_audit_table.setRowCount(len(audit_history))
        for i, item in enumerate(audit_history):
            vals = [
                str(item.get("timestamp", "") or "")[:19],
                str(item.get("domain", "") or ""),
                str(item.get("action", "") or ""),
                ", ".join([str(x) for x in item.get("changed_keys", [])[:5]]),
                str(item.get("actor", "") or ""),
            ]
            for j, v in enumerate(vals):
                table_item = QTableWidgetItem(str(v))
                table_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.openclaw_config_audit_table.setItem(i, j, table_item)

    def update_agent_registry(self, registry: dict):
        agents = list((registry or {}).get("agents", []) or [])
        agent_count = int((registry or {}).get("agent_count", len(agents)) or 0)
        meta = (registry or {}).get("meta", {}) or {}
        token = str(meta.get("change_token", "") or "")[:12]
        payload_mode = "full" if agents else "compact/empty"
        self.agent_registry_label.setText(
            f"已注册智能体 {agent_count} 个 | payload={payload_mode} | token={token or '-'}"
        )
        self.agent_registry_table.setRowCount(len(agents))
        for i, agent in enumerate(agents):
            capabilities = "、".join([str(x) for x in agent.get("capabilities", [])][:4])
            if len(agent.get("capabilities", []) or []) > 4:
                capabilities += "..."
            vals = [
                agent.get("key", ""),
                agent.get("display_name", ""),
                agent.get("stage", ""),
                agent.get("safety_level", ""),
                capabilities,
                agent.get("entrypoint", ""),
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(str(v))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 3:
                    color = "#66bb6a" if v == "read_only" else "#ffb74d" if v == "approval_required" else "#4fc3f7"
                    item.setForeground(QColor(color))
                self.agent_registry_table.setItem(i, j, item)

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
