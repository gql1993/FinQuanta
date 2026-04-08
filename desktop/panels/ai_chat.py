"""AI 助手面板 — 参考豆包/Kimi 风格设计"""
import os
import re
from datetime import datetime

from desktop.assistant_audit import get_action, list_action_logs, list_recent_actions

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QLineEdit, QComboBox, QSplitter, QListWidget,
    QListWidgetItem, QAbstractItemView, QFrame, QGridLayout,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

from api_server.config import settings

from desktop.data_access import RepoCompatConnection


def _init_chat_table():
    if settings.db_backend == "postgres":
        return
    conn = RepoCompatConnection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ai_chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT, role TEXT, content TEXT, created_at TEXT
        )
    """)
    conn.commit()
    conn.close()


_init_chat_table()


def save_chat_msg(session_id: str, role: str, content: str):
    conn = RepoCompatConnection()
    conn.execute(
        "INSERT INTO ai_chat_history (session_id, role, content, created_at) VALUES (?,?,?,?)",
        (session_id, role, content, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_sessions(limit: int = 50) -> list[dict]:
    conn = RepoCompatConnection()
    cur = conn.execute("""
        SELECT session_id, MIN(created_at), MAX(created_at), COUNT(*),
               (SELECT content FROM ai_chat_history h2
                WHERE h2.session_id=h1.session_id AND h2.role='user'
                ORDER BY h2.id LIMIT 1)
        FROM ai_chat_history h1 GROUP BY session_id ORDER BY MAX(created_at) DESC LIMIT ?
    """, (limit,))
    sessions = [
        {"session_id": r[0], "first_time": r[1], "last_time": r[2],
         "msg_count": r[3], "first_question": (r[4] or "")[:35]}
        for r in cur.fetchall()
    ]
    conn.close()
    return sessions


def get_session_messages(session_id: str) -> list[dict]:
    conn = RepoCompatConnection()
    cur = conn.execute(
        "SELECT role, content, created_at FROM ai_chat_history WHERE session_id=? ORDER BY id",
        (session_id,),
    )
    msgs = [{"role": r[0], "content": r[1], "time": r[2]} for r in cur.fetchall()]
    conn.close()
    return msgs


def _md_to_html(text: str) -> str:
    """Markdown → Manus 风格 HTML：卡片分区 + 步骤编号 + 结构化表格。"""
    lines = text.split("\n")
    out = []
    in_table = False
    in_code = False
    step_counter = [0]

    _card_open = (
        '<div style="background:#161b22;border:1px solid #21262d;border-radius:10px;'
        'padding:14px 18px;margin:10px 0;">'
    )
    _card_close = '</div>'

    for line in lines:
        s = line.strip()

        # 代码块
        if s.startswith("```"):
            in_code = not in_code
            if in_code:
                out.append(
                    '<div style="margin:8px 0;border-radius:8px;overflow:hidden;border:1px solid #30363d;">'
                    '<div style="background:#21262d;padding:4px 12px;font-size:10px;color:#8b949e;">代码</div>'
                    '<pre style="background:#0d1117;padding:12px;font-size:12px;margin:0;overflow-x:auto;color:#c9d1d9;">'
                )
            else:
                out.append('</pre></div>')
            continue
        if in_code:
            out.append(line.replace("<", "&lt;").replace(">", "&gt;") + "\n")
            continue

        # 表格
        if s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s.split("|")[1:-1]]
            if all(set(c) <= {"-", ":", " "} for c in cells):
                continue
            if not in_table:
                out.append(
                    '<div style="margin:8px 0;border-radius:8px;overflow:hidden;border:1px solid #21262d;">'
                    '<table style="border-collapse:collapse;width:100%;font-size:12px;">'
                )
                tag = "th"
                in_table = True
            else:
                tag = "td"
            if tag == "th":
                cell_style = "padding:8px 12px;background:#161b22;color:#58a6ff;font-weight:bold;border-bottom:2px solid #30363d;"
            else:
                cell_style = "padding:7px 12px;border-bottom:1px solid #21262d;"
            out.append("<tr>" + "".join(f'<{tag} style="{cell_style}">{c}</{tag}>' for c in cells) + "</tr>")
            continue
        if in_table and not s.startswith("|"):
            out.append('</table></div>')
            in_table = False

        # H1 → 大标题卡片（Manus 的 section header）
        if s.startswith("# ") and not s.startswith("## "):
            title = s[2:]
            out.append(
                f'<div style="margin:16px 0 8px;padding:10px 16px;background:linear-gradient(90deg,#1a1f35,#0d1117);'
                f'border-left:4px solid #58a6ff;border-radius:6px;">'
                f'<span style="color:#58a6ff;font-size:16px;font-weight:bold;">{title}</span></div>'
            )
            continue

        # H2 → 步骤卡片（Manus 风格的分步展示）
        if s.startswith("## "):
            title = s[3:]
            step_counter[0] += 1
            out.append(
                f'<div style="display:flex;align-items:center;margin:14px 0 6px;gap:8px;">'
                f'<span style="background:#238636;color:#fff;border-radius:50%;width:22px;height:22px;'
                f'display:inline-flex;align-items:center;justify-content:center;font-size:11px;font-weight:bold;">'
                f'{step_counter[0]}</span>'
                f'<span style="color:#f0883e;font-size:14px;font-weight:bold;">{title}</span></div>'
            )
            continue

        # H3 → 小节标题
        if s.startswith("### "):
            out.append(
                f'<div style="color:#d29922;font-size:13px;font-weight:bold;margin:10px 0 4px;'
                f'padding-left:4px;border-left:3px solid #d29922;">&nbsp;{s[4:]}</div>'
            )
            continue

        # 加粗
        line = re.sub(r'\*\*(.+?)\*\*', r'<b style="color:#e6edf3;">\1</b>', line)

        # 无序列表 → 带图标
        if s.startswith("- ") or s.startswith("* "):
            content = s[2:]
            # 自动识别红绿信号
            if any(kw in content for kw in ["买入", "加仓", "看涨", "利好", "上涨", "强烈"]):
                dot = '<span style="color:#3fb950;">▲</span>'
            elif any(kw in content for kw in ["卖出", "止损", "看跌", "利空", "下跌", "减仓"]):
                dot = '<span style="color:#f85149;">▼</span>'
            else:
                dot = '<span style="color:#58a6ff;">●</span>'
            line = f'<div style="padding:3px 0 3px 14px;">{dot} {content}</div>'
            out.append(line)
            continue

        # 有序列表
        m = re.match(r'^(\d+)\.\s+(.+)', s)
        if m:
            num = m.group(1)
            content = m.group(2)
            line = (
                f'<div style="padding:3px 0 3px 8px;display:flex;gap:6px;">'
                f'<span style="color:#58a6ff;font-weight:bold;min-width:18px;">{num}.</span>'
                f'<span>{content}</span></div>'
            )
            out.append(line)
            continue

        # 分割线
        if s in ("---", "***", "___"):
            out.append('<hr style="border:none;border-top:1px solid #21262d;margin:12px 0;">')
            continue

        # 引用块 → Manus 的 insight 卡片
        if s.startswith("> "):
            content = s[2:]
            out.append(
                f'<div style="background:#1c2128;border-left:3px solid #d29922;border-radius:0 6px 6px 0;'
                f'padding:10px 14px;margin:8px 0;color:#d2a8ff;font-size:13px;">'
                f'💡 {content}</div>'
            )
            continue

        # 普通段落
        if s:
            out.append(f'<div style="padding:2px 0;line-height:1.7;">{line}</div>')
        else:
            out.append('<div style="height:6px;"></div>')

    if in_table:
        out.append('</table></div>')
    if in_code:
        out.append('</pre></div>')
    return "".join(out)


# 快捷问题
_QUICK_QUESTIONS = [
    ("📊 分析我的持仓", "帮我分析手动仓和AI仓的持仓，哪些该持有，哪些该卖出？"),
    ("🏆 AI仓 vs 手动仓", "对比AI自主仓和手动仓的表现，谁做得更好？分析原因。"),
    ("📈 今日操作建议", "基于我当前持仓和最新市场数据，给出今天的操作建议。"),
    ("🔍 策略诊断", "分析最近回测结果，评估策略的有效性和改进方向。"),
    ("🏦 基金跟买", "基金重仓股里哪些值得跟买？结合持仓变动和股价走势分析。"),
    ("⚡ 事件解读", "解读最近的事件选股结果，有哪些值得关注的机会？"),
]

_CHAT_MODES = [
    ("自动判断", "auto"),
    ("查询", "query"),
    ("执行", "run"),
    ("修改", "update"),
]


class AIChatPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        header = QFrame()
        header.setStyleSheet(
            "QFrame { background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #111827, stop:1 #0f3460); "
            "border:1px solid #22304a; border-radius:16px; }"
        )
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 18, 20, 18)
        header_layout.setSpacing(12)

        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title = QLabel("FinQuanta AI 助手")
        title.setFont(QFont("", 18, QFont.Weight.Bold))
        title.setStyleSheet("color:#e6edf3;")
        title_box.addWidget(title)

        subtitle = QLabel("应用内直接查询系统状态、解释异常、执行白名单任务，并对修改类动作进行确认。")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color:#9fb3c8; font-size:12px;")
        title_box.addWidget(subtitle)
        header_layout.addLayout(title_box, 1)

        badge_wrap = QHBoxLayout()
        badge_wrap.setSpacing(8)
        for text, color in [
            ("系统查询", "#1f6feb"),
            ("任务执行", "#8b5cf6"),
            ("变更确认", "#238636"),
        ]:
            chip = QLabel(text)
            chip.setStyleSheet(
                f"background:{color}; color:white; border-radius:12px; padding:6px 12px; font-size:11px; font-weight:bold;"
            )
            badge_wrap.addWidget(chip)
        header_layout.addLayout(badge_wrap)
        layout.addWidget(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(10)
        self._splitter = splitter

        # ===== 左侧边栏 =====
        sidebar = QFrame()
        sidebar.setStyleSheet("QFrame { background: #0f172a; border:1px solid #1f2937; border-radius:16px; }")
        sidebar.setMinimumWidth(160)
        sidebar.setMaximumWidth(260)
        self._sidebar = sidebar
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(14, 14, 14, 14)
        sb_layout.setSpacing(10)

        side_title = QLabel("对话管理")
        side_title.setStyleSheet("color:#e6edf3; font-size:14px; font-weight:bold;")
        sb_layout.addWidget(side_title)

        side_desc = QLabel("查看历史会话、切换模型，管理当前系统助手会话。")
        side_desc.setWordWrap(True)
        side_desc.setStyleSheet("color:#8b949e; font-size:11px;")
        sb_layout.addWidget(side_desc)

        self.btn_new_session = QPushButton("＋  新对话")
        self.btn_new_session.setStyleSheet(
            "QPushButton { background:#1f6feb; color:#ffffff; border:1px solid #3b82f6; "
            "border-radius:10px; padding:10px; font-size:13px; font-weight:bold; }"
            "QPushButton:hover { background:#3b82f6; }"
        )
        sb_layout.addWidget(self.btn_new_session)

        sb_layout.addWidget(self._make_divider())

        hist_label = QLabel("历史对话")
        hist_label.setStyleSheet("color:#8b949e; font-size:11px; padding:4px 2px;")
        sb_layout.addWidget(hist_label)

        self.session_list = QListWidget()
        self.session_list.setStyleSheet("""
            QListWidget { background:#0b1220; border:1px solid #1f2937; border-radius:12px; padding:4px; }
            QListWidget::item {
                color:#c9d1d9; padding:10px 8px; border-radius:10px; margin:3px 0;
                font-size:12px;
            }
            QListWidget::item:selected { background:#1d4ed8; color:#ffffff; }
            QListWidget::item:hover { background:#111827; }
        """)
        self.session_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        sb_layout.addWidget(self.session_list)

        self.btn_delete_session = QPushButton("删除选中对话")
        self.btn_delete_session.setStyleSheet(
            "QPushButton { background:#111827; color:#9ca3af; border:1px solid #1f2937; "
            "border-radius:8px; padding:7px; font-size:11px; }"
            "QPushButton:hover { background:#1f2937; color:#f87171; border-color:#f87171; }"
        )
        sb_layout.addWidget(self.btn_delete_session)

        # 模型选择
        sb_layout.addWidget(self._make_divider())
        model_label = QLabel("模型")
        model_label.setStyleSheet("color:#8b949e; font-size:11px; padding:4px 2px;")
        sb_layout.addWidget(model_label)

        self.combo_provider = QComboBox()
        self.combo_provider.addItems(["DeepSeek", "OpenAI", "Gemini", "Claude", "通义千问", "Kimi"])
        self.combo_provider.setStyleSheet(
            "QComboBox { background:#0b1220; color:#c9d1d9; border:1px solid #1f2937; "
            "border-radius:8px; padding:8px 10px; font-size:12px; }"
        )
        sb_layout.addWidget(self.combo_provider)

        self.combo_model = QComboBox()
        self.combo_model.addItems(["deepseek-chat", "gpt-4o", "gemini-pro", "claude-3-sonnet", "qwen-max", "moonshot-v1-8k"])
        self.combo_model.setStyleSheet(self.combo_provider.styleSheet())
        sb_layout.addWidget(self.combo_model)

        sb_layout.addWidget(self._make_divider())
        action_hist_header = QHBoxLayout()
        action_hist_title = QLabel("最近系统动作")
        action_hist_title.setStyleSheet("color:#8b949e; font-size:11px; padding:4px 2px;")
        action_hist_header.addWidget(action_hist_title)
        action_hist_header.addStretch()
        self.btn_refresh_actions = QPushButton("刷新")
        self.btn_refresh_actions.setStyleSheet(
            "QPushButton { background:#111827; color:#9ca3af; border:1px solid #1f2937; border-radius:8px; padding:5px 10px; font-size:11px; }"
            "QPushButton:hover { color:#58a6ff; border-color:#58a6ff; }"
        )
        action_hist_header.addWidget(self.btn_refresh_actions)
        sb_layout.addLayout(action_hist_header)

        self.action_list = QListWidget()
        self.action_list.setStyleSheet("""
            QListWidget { background:#0b1220; border:1px solid #1f2937; border-radius:12px; padding:4px; }
            QListWidget::item {
                color:#cbd5e1; padding:9px 8px; border-radius:10px; margin:3px 0;
                font-size:11px;
            }
            QListWidget::item:selected { background:#172554; color:#ffffff; }
            QListWidget::item:hover { background:#111827; }
        """)
        self.action_list.setMaximumHeight(210)
        self.action_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        sb_layout.addWidget(self.action_list)

        self.action_detail_box = QLabel("点击上方系统动作可查看详情")
        self.action_detail_box.setWordWrap(True)
        self.action_detail_box.setStyleSheet(
            "background:#0b1220; color:#94a3b8; border:1px solid #1f2937; border-radius:12px; padding:10px; font-size:11px;"
        )
        self.action_detail_box.setMinimumHeight(88)
        sb_layout.addWidget(self.action_detail_box)

        sb_layout.addStretch()

        splitter.addWidget(sidebar)

        # ===== 右侧主区 =====
        main_area = QFrame()
        main_area.setStyleSheet("QFrame { background: #0b1220; border:1px solid #1f2937; border-radius:16px; }")
        main_layout = QVBoxLayout(main_area)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        toolbar = QFrame()
        toolbar.setStyleSheet("QFrame { background:#0f172a; border:1px solid #1f2937; border-radius:12px; }")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(14, 10, 14, 10)
        toolbar_layout.setSpacing(10)
        self.chat_mode_label = QLabel("模式:")
        self.chat_mode_label.setStyleSheet("color:#e6edf3; font-size:13px; font-weight:bold;")
        toolbar_layout.addWidget(self.chat_mode_label)
        self.combo_chat_mode = QComboBox()
        for label, value in _CHAT_MODES:
            self.combo_chat_mode.addItem(label, value)
        self.combo_chat_mode.setCurrentIndex(0)
        self.combo_chat_mode.setStyleSheet(
            "QComboBox { background:#111827; color:#e6edf3; border:1px solid #253246; border-radius:10px; padding:8px 12px; min-width:110px; }"
        )
        toolbar_layout.addWidget(self.combo_chat_mode)
        mode_desc = QLabel("系统类请求会先走本地执行链路，普通投研问题自动回退到大模型。")
        mode_desc.setStyleSheet("color:#8b949e; font-size:11px;")
        toolbar_layout.addWidget(mode_desc, 1)
        main_layout.addWidget(toolbar)

        # 聊天展示区
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setFrameShape(QFrame.Shape.NoFrame)
        self.chat_display.setStyleSheet("")
        self._show_welcome()
        main_layout.addWidget(self.chat_display)

        # 快捷问题栏
        self.quick_bar = QFrame()
        self.quick_bar.setStyleSheet("QFrame { background:#0f172a; border:1px solid #1f2937; border-radius:12px; }")
        qb_layout = QGridLayout(self.quick_bar)
        qb_layout.setContentsMargins(12, 12, 12, 12)
        qb_layout.setHorizontalSpacing(8)
        qb_layout.setVerticalSpacing(8)
        self._quick_layout = qb_layout
        self._quick_buttons = []
        for idx, (label, question) in enumerate(_QUICK_QUESTIONS):
            btn = QPushButton(label)
            btn.setStyleSheet(
                "QPushButton { background:#111827; color:#cbd5e1; border:1px solid #253246; "
                "border-radius:16px; padding:8px 12px; font-size:11px; text-align:left; }"
                "QPushButton:hover { background:#172033; color:#58a6ff; border-color:#58a6ff; }"
            )
            btn.setProperty("question", question)
            btn.clicked.connect(self._on_quick_click)
            btn.setMinimumHeight(36)
            self._quick_buttons.append(btn)
        self._reflow_quick_buttons(3)
        main_layout.addWidget(self.quick_bar)

        # 系统助手动作卡片
        self.action_card = QFrame()
        self.action_card.setVisible(False)
        self.action_card.setStyleSheet(
            "QFrame { background:#111827; border:1px solid #253246; border-radius:12px; }"
        )
        action_layout = QVBoxLayout(self.action_card)
        action_layout.setContentsMargins(18, 14, 18, 14)
        action_layout.setSpacing(8)

        self.action_title = QLabel("待确认操作")
        self.action_title.setStyleSheet("color:#58a6ff; font-size:13px; font-weight:bold;")
        action_layout.addWidget(self.action_title)

        self.action_risk_badge = QLabel("")
        self.action_risk_badge.setVisible(False)
        self.action_risk_badge.setStyleSheet(
            "background:#1d4ed8; color:#ffffff; border-radius:10px; padding:4px 10px; font-size:11px; font-weight:bold;"
        )
        action_layout.addWidget(self.action_risk_badge, alignment=Qt.AlignmentFlag.AlignLeft)

        self.action_summary = QLabel("")
        self.action_summary.setWordWrap(True)
        self.action_summary.setStyleSheet("color:#c9d1d9; font-size:12px;")
        action_layout.addWidget(self.action_summary)

        self.action_detail = QLabel("")
        self.action_detail.setWordWrap(True)
        self.action_detail.setStyleSheet("color:#8b949e; font-size:11px;")
        action_layout.addWidget(self.action_detail)

        action_btn_row = QHBoxLayout()
        action_btn_row.setContentsMargins(0, 4, 0, 0)
        self.btn_confirm_action = QPushButton("确认执行")
        self.btn_confirm_action.setStyleSheet(
            "QPushButton { background:#238636; color:#fff; border:none; border-radius:8px; padding:8px 16px; font-size:12px; font-weight:bold; }"
            "QPushButton:hover { background:#2ea043; }"
            "QPushButton:disabled { background:#21262d; color:#484f58; }"
        )
        action_btn_row.addWidget(self.btn_confirm_action)
        self.btn_cancel_action = QPushButton("取消")
        self.btn_cancel_action.setStyleSheet(
            "QPushButton { background:#21262d; color:#c9d1d9; border:1px solid #30363d; border-radius:8px; padding:8px 16px; font-size:12px; }"
            "QPushButton:hover { border-color:#f85149; color:#f85149; }"
        )
        action_btn_row.addWidget(self.btn_cancel_action)
        action_btn_row.addStretch()
        action_layout.addLayout(action_btn_row)
        main_layout.addWidget(self.action_card)

        # 输入区
        input_frame = QFrame()
        input_frame.setStyleSheet("QFrame { background:#0f172a; border:1px solid #1f2937; border-radius:14px; }")
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(14, 12, 14, 12)
        input_layout.setSpacing(10)

        self.msg_input = QLineEdit()
        self.msg_input.setPlaceholderText("输入系统问题、异常解释、执行指令，或继续普通 AI 对话...")
        self.msg_input.setStyleSheet(
            "QLineEdit { background:#0b1220; color:#c9d1d9; border:1px solid #253246; "
            "border-radius:12px; padding:12px 16px; font-size:14px; }"
            "QLineEdit:focus { border-color:#58a6ff; }"
        )
        input_layout.addWidget(self.msg_input)

        self.btn_send = QPushButton("➤")
        self.btn_send.setStyleSheet(
            "QPushButton { background:#238636; color:white; border:none; border-radius:12px; "
            "padding:12px 18px; font-size:16px; font-weight:bold; min-width:48px; }"
            "QPushButton:hover { background:#2ea043; }"
            "QPushButton:disabled { background:#21262d; color:#484f58; }"
        )
        input_layout.addWidget(self.btn_send)
        main_layout.addWidget(input_frame)

        splitter.addWidget(main_area)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([220, 980])
        layout.addWidget(splitter)

        self._current_session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._has_messages = False
        self._pending_action_id = ""

        self.btn_new_session.clicked.connect(self._new_session)
        self.session_list.currentItemChanged.connect(self._on_session_selected)
        self.btn_delete_session.clicked.connect(self._delete_session)
        self.btn_refresh_actions.clicked.connect(self.refresh_action_history)
        self.action_list.currentItemChanged.connect(self._on_action_selected)

        self._apply_chat_display_style(28)
        self.refresh_sessions()
        self.refresh_action_history()

    @staticmethod
    def _make_divider() -> QFrame:
        d = QFrame()
        d.setFixedHeight(1)
        d.setStyleSheet("background:#21262d; margin:4px 0;")
        return d

    def _show_welcome(self):
        self.chat_display.setHtml("""
        <div style="padding:24px 8px 36px 8px;">
            <div style="background:linear-gradient(180deg,#111827,#0f172a); border:1px solid #253246; border-radius:18px; padding:28px 24px;">
                <div style="font-size:44px; margin-bottom:10px;">🤖</div>
                <div style="font-size:24px; font-weight:bold; color:#58a6ff; margin-bottom:8px;">
                    FinQuanta 系统助手
                </div>
                <div style="font-size:13px; color:#94a3b8; line-height:1.9;">
                    我可以读取持仓、任务、走势验证、运行中心和系统快照数据，<br>
                    也可以在白名单范围内帮你执行系统动作，并在执行前要求你确认。
                </div>
                <div style="margin-top:18px; font-size:12px; color:#64748b;">
                    示例：为什么走势验证很多为空 / 刷新系统快照 / 重新跑一次走势验证校准
                </div>
            </div>
        </div>
        """)

    def _on_quick_click(self):
        btn = self.sender()
        if btn:
            q = btn.property("question")
            if q:
                self.msg_input.setText(q)
                self.btn_send.click()

    def _new_session(self):
        self._current_session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._has_messages = False
        self._show_welcome()
        self.quick_bar.setVisible(True)
        self.clear_pending_action()

    def _on_session_selected(self, current, previous):
        if not current:
            return
        sid = current.data(Qt.ItemDataRole.UserRole)
        if not sid:
            return
        self._current_session_id = sid
        msgs = get_session_messages(sid)
        self.chat_display.clear()
        self._has_messages = bool(msgs)
        self.quick_bar.setVisible(not self._has_messages)
        self.clear_pending_action()
        for m in msgs:
            self.append_message(m["role"], m["content"], save=False)

    def _delete_session(self):
        item = self.session_list.currentItem()
        if not item:
            return
        sid = item.data(Qt.ItemDataRole.UserRole)
        if not sid:
            return
        conn = RepoCompatConnection()
        conn.execute("DELETE FROM ai_chat_history WHERE session_id=?", (sid,))
        conn.commit()
        conn.close()
        if sid == self._current_session_id:
            self._new_session()
        self.refresh_sessions()

    def refresh_sessions(self):
        self.session_list.clear()
        for s in get_sessions(50):
            q = s["first_question"] or "新对话"
            ts = s["last_time"][:10] if s["last_time"] else ""
            item = QListWidgetItem(f"💬  {q}\n       {ts} · {s['msg_count']}条")
            item.setData(Qt.ItemDataRole.UserRole, s["session_id"])
            self.session_list.addItem(item)

    def refresh_action_history(self):
        self.action_list.clear()
        for item_data in list_recent_actions(8):
            status = self._format_action_status(item_data.get("status", "pending"))
            title = item_data.get("action_key") or item_data.get("intent") or "-"
            user_text = (item_data.get("user_text") or "")[:26]
            ts = (item_data.get("created_at") or "")[11:16]
            item = QListWidgetItem(f"{status} {title}\n{user_text}\n{ts}")
            item.setData(Qt.ItemDataRole.UserRole, item_data.get("id", ""))
            self.action_list.addItem(item)
        if self.action_list.count() == 0:
            self.action_detail_box.setText("暂无系统动作记录")

    def _on_action_selected(self, current, previous):
        if not current:
            return
        action_id = current.data(Qt.ItemDataRole.UserRole)
        if not action_id:
            return
        action = get_action(action_id)
        logs = list_action_logs(action_id)
        if not action:
            self.action_detail_box.setText("动作详情读取失败")
            return
        lines = [
            f"动作: {action.get('action_key', '-')}",
            f"状态: {action.get('status', '-')}",
            f"风险: {action.get('risk_level', '-')}",
            f"时间: {(action.get('created_at') or '')[:16]}",
            f"输入: {(action.get('user_text') or '')[:36]}",
        ]
        if action.get("error_text"):
            lines.append(f"错误: {action['error_text'][:60]}")
        if logs:
            lines.append(f"最后日志: {(logs[-1].get('message') or '')[:60]}")
        self.action_detail_box.setText("\n".join(lines))

    @property
    def session_id(self) -> str:
        return self._current_session_id

    def append_message(self, role: str, text: str, save: bool = True):
        if not self._has_messages:
            self.chat_display.clear()
            self._has_messages = True
            self.quick_bar.setVisible(False)

        ts = datetime.now().strftime("%H:%M")

        if role == "user":
            html = (
                f'<div style="margin:16px 12px 4px 88px;">'
                f'<div style="text-align:right;color:#8b949e;font-size:10px;margin-bottom:3px;">你 · {ts}</div>'
                f'<div style="background:linear-gradient(90deg,#1d4ed8,#1f6feb);color:#fff;border-radius:18px 18px 4px 18px;'
                f'padding:12px 18px;font-size:14px;line-height:1.6;text-align:left;">'
                f'{text}</div></div>'
            )
        elif role == "assistant":
            content = _md_to_html(text)
            # Manus 风格：带头像 + 标签 + 结构化卡片
            html = (
                f'<div style="margin:16px 24px 4px 8px;">'
                # 头部：avatar + name + timestamp
                f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;">'
                f'<span style="background:#238636;color:#fff;border-radius:6px;padding:2px 6px;'
                f'font-size:10px;font-weight:bold;">AI</span>'
                f'<span style="color:#58a6ff;font-size:12px;font-weight:bold;">量化助手</span>'
                f'<span style="color:#484f58;font-size:10px;">{ts}</span></div>'
                # 内容卡片
                f'<div style="background:#0f172a;color:#c9d1d9;border-radius:8px 16px 16px 16px;'
                f'padding:16px 20px;font-size:13px;line-height:1.7;'
                f'border:1px solid #253246;box-shadow:0 6px 16px rgba(0,0,0,0.18);">'
                f'{content}</div></div>'
            )
        elif role == "thinking":
            # Manus 风格：思考过程
            html = (
                f'<div style="margin:8px 24px 4px 8px;">'
                f'<div style="background:#111827;border:1px solid #253246;border-radius:10px;'
                f'padding:10px 14px;color:#8b949e;font-size:12px;">'
                f'<span style="color:#d29922;">⏳ 思考中...</span> {text}</div></div>'
            )
        else:
            html = (
                f'<div style="text-align:center;margin:10px 24px;">'
                f'<div style="display:inline-block;background:#111827;border:1px solid #253246;'
                f'border-radius:20px;padding:5px 16px;">'
                f'<span style="color:#d29922;font-size:11px;">⚙️ {text}</span></div></div>'
            )

        self.chat_display.append(html)
        sb = self.chat_display.verticalScrollBar()
        sb.setValue(sb.maximum())

        if save and role != "thinking":
            save_chat_msg(self._current_session_id, role, text)

    def clear_input(self):
        self.msg_input.clear()

    def show_pending_action(self, action_id: str, preview: dict | None = None, intent: dict | None = None):
        preview = preview or {}
        intent = intent or {}
        self._pending_action_id = action_id or ""
        risk_level = intent.get("risk_level", "low")
        risk_style = self._risk_style(risk_level)
        self.action_card.setStyleSheet(
            f"QFrame {{ background:{risk_style['bg']}; border:1px solid {risk_style['border']}; border-radius:12px; }}"
        )
        self.action_title.setText(preview.get("title", "待确认操作"))
        self.action_title.setStyleSheet(
            f"color:{risk_style['title']}; font-size:13px; font-weight:bold;"
        )
        self.action_risk_badge.setText(f"{risk_style['label']} 风险")
        self.action_risk_badge.setStyleSheet(
            f"background:{risk_style['badge_bg']}; color:#ffffff; border-radius:10px; padding:4px 10px; font-size:11px; font-weight:bold;"
        )
        self.action_risk_badge.setVisible(True)
        self.action_summary.setText(
            f"动作: {intent.get('action_key', '-')}\n说明: {preview.get('title', '请确认是否执行该系统动作。')}"
        )
        before = preview.get("before", {})
        after = preview.get("after", {})
        lines = []
        if before:
            lines.append(f"变更前: {before}")
        if after:
            lines.append(f"变更后: {after}")
        if intent.get("requires_confirmation"):
            lines.append("执行前需要你的确认，完成后会写入系统动作审计日志。")
        self.action_detail.setText("\n".join(lines) if lines else "请确认是否执行该系统动作。")
        self.action_card.setVisible(True)
        self.refresh_action_history()

    def clear_pending_action(self):
        self._pending_action_id = ""
        self.action_card.setStyleSheet(
            "QFrame { background:#111827; border:1px solid #253246; border-radius:12px; }"
        )
        self.action_title.setText("待确认操作")
        self.action_title.setStyleSheet("color:#58a6ff; font-size:13px; font-weight:bold;")
        self.action_risk_badge.setText("")
        self.action_risk_badge.setVisible(False)
        self.action_summary.setText("")
        self.action_detail.setText("")
        self.action_card.setVisible(False)

    @property
    def pending_action_id(self) -> str:
        return self._pending_action_id

    def _apply_chat_display_style(self, horizontal_padding: int):
        self.chat_display.setStyleSheet(
            "QTextEdit { "
            "background:#0b1220; color:#c9d1d9; border:1px solid #1f2937; border-radius:16px; "
            f"padding:20px {horizontal_padding}px; font-size:14px; selection-background-color:#264f78; "
            "}"
        )

    @property
    def current_mode(self) -> str:
        return self.combo_chat_mode.currentData() or "auto"

    @staticmethod
    def _risk_style(level: str) -> dict:
        styles = {
            "low": {
                "label": "低",
                "bg": "#0f172a",
                "border": "#1d4ed8",
                "title": "#60a5fa",
                "badge_bg": "#1d4ed8",
            },
            "medium": {
                "label": "中",
                "bg": "#1c1917",
                "border": "#d97706",
                "title": "#f59e0b",
                "badge_bg": "#d97706",
            },
            "high": {
                "label": "高",
                "bg": "#1f1315",
                "border": "#dc2626",
                "title": "#f87171",
                "badge_bg": "#dc2626",
            },
        }
        return styles.get(level, styles["low"])

    @staticmethod
    def _format_action_status(status: str) -> str:
        mapping = {
            "pending": "⏳",
            "confirmed": "🟡",
            "executed": "✅",
            "failed": "❌",
            "cancelled": "⛔",
        }
        return mapping.get(status, "•")

    def _reflow_quick_buttons(self, columns: int):
        while self._quick_layout.count():
            item = self._quick_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(self.quick_bar)
        for idx, btn in enumerate(self._quick_buttons):
            self._quick_layout.addWidget(btn, idx // columns, idx % columns)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        width = self.width()
        if width < 1100:
            sidebar_w = 170
            chat_pad = 16
            quick_cols = 1
        elif width < 1500:
            sidebar_w = 190
            chat_pad = 22
            quick_cols = 2
        else:
            sidebar_w = 220
            chat_pad = 28
            quick_cols = 3
        self._sidebar.setMinimumWidth(sidebar_w)
        self._sidebar.setMaximumWidth(sidebar_w + 40)
        self._apply_chat_display_style(chat_pad)
        self._reflow_quick_buttons(quick_cols)
