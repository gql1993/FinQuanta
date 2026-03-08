"""AI 助手面板 — 参考豆包/Kimi 风格设计"""
import os
import re
import sqlite3
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QLineEdit, QComboBox, QSplitter, QListWidget,
    QListWidgetItem, QAbstractItemView, QFrame, QScrollArea,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

DB_PATH = os.path.join("data_cache", "quant.db")


def _init_chat_table():
    conn = sqlite3.connect(DB_PATH, timeout=5)
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
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.execute(
        "INSERT INTO ai_chat_history (session_id, role, content, created_at) VALUES (?,?,?,?)",
        (session_id, role, content, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_sessions(limit: int = 50) -> list[dict]:
    conn = sqlite3.connect(DB_PATH, timeout=5)
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
    conn = sqlite3.connect(DB_PATH, timeout=5)
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


class AIChatPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ===== 左侧边栏 =====
        sidebar = QFrame()
        sidebar.setStyleSheet("background: #0d1117;")
        sidebar.setMinimumWidth(200)
        sidebar.setMaximumWidth(280)
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(10, 12, 10, 10)
        sb_layout.setSpacing(8)

        self.btn_new_session = QPushButton("＋  新对话")
        self.btn_new_session.setStyleSheet(
            "QPushButton { background:#21262d; color:#c9d1d9; border:1px solid #30363d; "
            "border-radius:8px; padding:10px; font-size:13px; font-weight:bold; }"
            "QPushButton:hover { background:#30363d; border-color:#58a6ff; }"
        )
        sb_layout.addWidget(self.btn_new_session)

        sb_layout.addWidget(self._make_divider())

        hist_label = QLabel("历史对话")
        hist_label.setStyleSheet("color:#8b949e; font-size:11px; padding:4px 2px;")
        sb_layout.addWidget(hist_label)

        self.session_list = QListWidget()
        self.session_list.setStyleSheet("""
            QListWidget { background:transparent; border:none; }
            QListWidget::item {
                color:#c9d1d9; padding:10px 8px; border-radius:8px; margin:1px 0;
                font-size:12px;
            }
            QListWidget::item:selected { background:#1f2937; }
            QListWidget::item:hover { background:#161b22; }
        """)
        self.session_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        sb_layout.addWidget(self.session_list)

        self.btn_delete_session = QPushButton("删除选中对话")
        self.btn_delete_session.setStyleSheet(
            "QPushButton { background:transparent; color:#8b949e; border:1px solid #21262d; "
            "border-radius:6px; padding:6px; font-size:11px; }"
            "QPushButton:hover { background:#21262d; color:#f85149; border-color:#f85149; }"
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
            "QComboBox { background:#161b22; color:#c9d1d9; border:1px solid #30363d; "
            "border-radius:6px; padding:6px 10px; font-size:12px; }"
        )
        sb_layout.addWidget(self.combo_provider)

        self.combo_model = QComboBox()
        self.combo_model.addItems(["deepseek-chat", "gpt-4o", "gemini-pro", "claude-3-sonnet", "qwen-max", "moonshot-v1-8k"])
        self.combo_model.setStyleSheet(self.combo_provider.styleSheet())
        sb_layout.addWidget(self.combo_model)

        splitter.addWidget(sidebar)

        # ===== 右侧主区 =====
        main_area = QFrame()
        main_area.setStyleSheet("background: #0d1117;")
        main_layout = QVBoxLayout(main_area)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 聊天展示区
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setStyleSheet(
            "QTextEdit { background:#0d1117; border:none; padding:20px 40px; "
            "font-size:14px; color:#c9d1d9; selection-background-color:#264f78; }"
        )
        self._show_welcome()
        main_layout.addWidget(self.chat_display)

        # 快捷问题栏
        self.quick_bar = QFrame()
        self.quick_bar.setStyleSheet("background:#0d1117; padding:4px 30px;")
        qb_layout = QHBoxLayout(self.quick_bar)
        qb_layout.setContentsMargins(10, 0, 10, 0)
        qb_layout.setSpacing(8)
        self._quick_buttons = []
        for label, question in _QUICK_QUESTIONS:
            btn = QPushButton(label)
            btn.setStyleSheet(
                "QPushButton { background:#161b22; color:#8b949e; border:1px solid #30363d; "
                "border-radius:16px; padding:6px 14px; font-size:11px; }"
                "QPushButton:hover { background:#21262d; color:#58a6ff; border-color:#58a6ff; }"
            )
            btn.setProperty("question", question)
            btn.clicked.connect(self._on_quick_click)
            qb_layout.addWidget(btn)
            self._quick_buttons.append(btn)
        qb_layout.addStretch()
        main_layout.addWidget(self.quick_bar)

        # 输入区
        input_frame = QFrame()
        input_frame.setStyleSheet("background:#161b22; border-top:1px solid #21262d; padding:12px 30px;")
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(10, 8, 10, 8)
        input_layout.setSpacing(10)

        self.msg_input = QLineEdit()
        self.msg_input.setPlaceholderText("给 AI 助手发消息...")
        self.msg_input.setStyleSheet(
            "QLineEdit { background:#0d1117; color:#c9d1d9; border:1px solid #30363d; "
            "border-radius:12px; padding:12px 18px; font-size:14px; }"
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
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([230, 700])
        layout.addWidget(splitter)

        self._current_session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._has_messages = False

        self.btn_new_session.clicked.connect(self._new_session)
        self.session_list.currentItemChanged.connect(self._on_session_selected)
        self.btn_delete_session.clicked.connect(self._delete_session)

        self.refresh_sessions()

    @staticmethod
    def _make_divider() -> QFrame:
        d = QFrame()
        d.setFixedHeight(1)
        d.setStyleSheet("background:#21262d; margin:4px 0;")
        return d

    def _show_welcome(self):
        self.chat_display.setHtml("""
        <div style="text-align:center; padding:60px 20px;">
            <div style="font-size:48px;">🤖</div>
            <div style="font-size:22px; font-weight:bold; color:#58a6ff; margin:16px 0 8px;">
                AetherQuant AI
            </div>
            <div style="font-size:13px; color:#8b949e; line-height:1.8;">
                我可以读取你的持仓、策略、回测、事件选股等全部数据<br>
                帮你分析实操表现、优化策略参数、研判市场机会
            </div>
            <div style="margin-top:30px; color:#484f58; font-size:12px;">
                点击下方快捷按钮或直接输入问题开始对话
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
        for m in msgs:
            self.append_message(m["role"], m["content"], save=False)

    def _delete_session(self):
        item = self.session_list.currentItem()
        if not item:
            return
        sid = item.data(Qt.ItemDataRole.UserRole)
        if not sid:
            return
        conn = sqlite3.connect(DB_PATH, timeout=5)
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
                f'<div style="margin:16px 16px 4px 120px;">'
                f'<div style="text-align:right;color:#8b949e;font-size:10px;margin-bottom:3px;">你 · {ts}</div>'
                f'<div style="background:#1f6feb;color:#fff;border-radius:16px 16px 4px 16px;'
                f'padding:12px 18px;font-size:14px;line-height:1.6;text-align:left;">'
                f'{text}</div></div>'
            )
        elif role == "assistant":
            content = _md_to_html(text)
            # Manus 风格：带头像 + 标签 + 结构化卡片
            html = (
                f'<div style="margin:16px 60px 4px 16px;">'
                # 头部：avatar + name + timestamp
                f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;">'
                f'<span style="background:#238636;color:#fff;border-radius:6px;padding:2px 6px;'
                f'font-size:10px;font-weight:bold;">AI</span>'
                f'<span style="color:#58a6ff;font-size:12px;font-weight:bold;">量化助手</span>'
                f'<span style="color:#484f58;font-size:10px;">{ts}</span></div>'
                # 内容卡片
                f'<div style="background:#0d1117;color:#c9d1d9;border-radius:4px 12px 12px 12px;'
                f'padding:16px 20px;font-size:13px;line-height:1.7;'
                f'border:1px solid #21262d;box-shadow:0 1px 3px rgba(0,0,0,0.3);">'
                f'{content}</div></div>'
            )
        elif role == "thinking":
            # Manus 风格：思考过程
            html = (
                f'<div style="margin:8px 60px 4px 16px;">'
                f'<div style="background:#1c2128;border:1px solid #30363d;border-radius:8px;'
                f'padding:10px 14px;color:#8b949e;font-size:12px;">'
                f'<span style="color:#d29922;">⏳ 思考中...</span> {text}</div></div>'
            )
        else:
            html = (
                f'<div style="text-align:center;margin:10px 60px;">'
                f'<div style="display:inline-block;background:#161b22;border:1px solid #30363d;'
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
