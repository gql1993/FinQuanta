"""AI 助手面板 — 参考豆包/Kimi 风格设计"""
import os
import re
from datetime import datetime

from desktop.assistant_audit import get_action, list_action_logs, list_recent_actions

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QLineEdit, QComboBox, QSplitter, QListWidget,
    QListWidgetItem, QAbstractItemView, QFrame, QGridLayout, QBoxLayout, QFileDialog, QSizePolicy,
    QMenu, QInputDialog,
)
from PyQt6.QtCore import Qt, pyqtSignal, QEvent, QTimer, QPoint
from PyQt6.QtGui import QFont, QColor, QAction

from api_server.config import settings

from desktop.data_access import RepoCompatConnection
from desktop.ui_tokens import APP_FONT


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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ai_chat_sessions_meta (
            session_id TEXT PRIMARY KEY,
            title TEXT DEFAULT '',
            favorite INTEGER DEFAULT 0,
            updated_at TEXT
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
    meta_rows = conn.execute(
        "SELECT session_id, title, favorite FROM ai_chat_sessions_meta"
    ).fetchall()
    meta_map = {
        str(r[0]): {"title": str(r[1] or ""), "favorite": bool(int(r[2] or 0))}
        for r in meta_rows
    }
    conn.close()
    for session in sessions:
        meta = meta_map.get(session["session_id"], {})
        session["title"] = meta.get("title", "")
        session["favorite"] = bool(meta.get("favorite", False))
    sessions.sort(
        key=lambda item: (
            0 if bool(item.get("favorite", False)) else 1,
            str(item.get("last_time", "")),
        ),
        reverse=False,
    )
    sessions.sort(key=lambda item: str(item.get("last_time", "")), reverse=True)
    sessions.sort(key=lambda item: 0 if bool(item.get("favorite", False)) else 1)
    return sessions


def save_session_meta(session_id: str, *, title: str | None = None, favorite: bool | None = None):
    if settings.db_backend == "postgres":
        return
    conn = RepoCompatConnection()
    row = conn.execute(
        "SELECT title, favorite FROM ai_chat_sessions_meta WHERE session_id=?",
        (session_id,),
    ).fetchone()
    current_title = str(row[0] or "") if row else ""
    current_favorite = bool(int(row[1] or 0)) if row else False
    next_title = current_title if title is None else str(title or "").strip()
    next_favorite = current_favorite if favorite is None else bool(favorite)
    conn.execute(
        "INSERT OR REPLACE INTO ai_chat_sessions_meta (session_id, title, favorite, updated_at) VALUES (?,?,?,?)",
        (session_id, next_title, 1 if next_favorite else 0, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def delete_session_meta(session_id: str):
    if settings.db_backend == "postgres":
        return
    conn = RepoCompatConnection()
    conn.execute("DELETE FROM ai_chat_sessions_meta WHERE session_id=?", (session_id,))
    conn.commit()
    conn.close()


class _SessionItemWidget(QFrame):
    clicked = pyqtSignal()
    menu_requested = pyqtSignal()

    def __init__(self, title: str, meta: str, favorite: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("sessionItemWidget")
        self._selected = False
        self._hovered = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 6, 6)
        layout.setSpacing(8)

        icon = QLabel("⭐" if favorite else "📁")
        icon.setStyleSheet(
            f"color:#f59e0b; font-size:12px; background:transparent; border:none;"
        )
        layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(1)
        self.title_label = QLabel(title)
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet(
            f"color:{_AI_DARK['text']}; font-size:12px; font-weight:400; background:transparent; border:none; margin:0; padding:0;"
        )
        text_col.addWidget(self.title_label)
        self.meta_label = QLabel(meta)
        self.meta_label.setStyleSheet(
            f"color:{_AI_DARK['muted']}; font-size:11px; background:transparent; border:none; margin:0; padding:0;"
        )
        text_col.addWidget(self.meta_label)
        layout.addLayout(text_col, 1)

        self.menu_btn = QPushButton("⋯")
        self.menu_btn.setFixedSize(24, 24)
        self.menu_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{_AI_DARK['subtle']}; border:none; border-radius:12px; font-size:16px; }}"
            f"QPushButton:hover {{ background:{_AI_DARK['surface_alt']}; color:{_AI_DARK['text']}; }}"
        )
        self.menu_btn.clicked.connect(self.menu_requested.emit)
        layout.addWidget(self.menu_btn, 0, Qt.AlignmentFlag.AlignTop)
        self._refresh_style()

    def set_selected(self, selected: bool):
        self._selected = bool(selected)
        self._refresh_style()

    def enterEvent(self, event):
        self._hovered = True
        self._refresh_style()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._refresh_style()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)

    def _refresh_style(self):
        if self._selected:
            bg = _AI_DARK["selected"]
            border = _AI_DARK["selected_border"]
        elif self._hovered:
            bg = _AI_DARK["surface_alt"]
            border = "transparent"
        else:
            bg = "transparent"
            border = "transparent"
        self.setStyleSheet(
            "QFrame#sessionItemWidget { background:%s; border:1px solid %s; border-radius:10px; }"
            % (bg, border)
        )


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

_SIDEBAR_TOKENS = {
    "btn_height": 34,
    "btn_radius": 10,
    "btn_font": APP_FONT["body"],
    "section_font": APP_FONT["body"],
    "section_gap": 10,
    "list_radius": 12,
    "list_item_radius": 10,
    "list_item_font": APP_FONT["emphasis"],
    "list_item_vpad": 10,
    "list_item_hpad": 9,
    "list_item_gap": 2,
}

_SURFACE_TOKENS = {
    "control_height": 32,
    "control_radius": 10,
    "control_font": APP_FONT["body"],
    "toolbar_radius": 12,
    "input_radius": 12,
    "send_btn_radius": 10,
    "send_btn_height": 40,
}

_AI_DARK = {
    "base": "#1a1a2e",
    "surface": "#16213e",
    "surface_alt": "#1a2744",
    "border": "#33384d",
    "text": "#e0e0e0",
    "muted": "#aab4c3",
    "subtle": "#8b949e",
    "accent": "#0f3460",
    "accent_hover": "#1a4a8e",
    "selected": "#0f3460",
    "selected_border": "#24508d",
    "scroll": "#4b5563",
}

_AI_DARK_BASE = dict(_AI_DARK)
_AI_LIGHT = {
    "base": "#fafafa",
    "surface": "#ffffff",
    "surface_alt": "#f0f0f0",
    "border": "#dddddd",
    "text": "#333333",
    "muted": "#666666",
    "subtle": "#888888",
    "accent": "#1976d2",
    "accent_hover": "#1565c0",
    "selected": "#e3f2fd",
    "selected_border": "#bbdefb",
    "scroll": "#cccccc",
}


class AIChatPanel(QWidget):
    open_settings_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme = "dark"
        self._ultra_compact_mode = True
        self._welcome_title_cap_mode = "steady"
        self._welcome_title_caps = {"steady": 64, "impact": 68}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        header = QFrame()
        header.setStyleSheet(
            "QFrame { background:#ffffff; border:1px solid #f0f2f5; border-radius:10px; }"
        )
        self._header_frame = header
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 5, 10, 5)
        header_layout.setSpacing(8)
        self._header_layout = header_layout

        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        title = QLabel("FinQuanta 1.0")
        title.setFont(QFont("", APP_FONT["section"], QFont.Weight.Bold))
        title.setStyleSheet("color:#111827;")
        title_box.addWidget(title)
        self._header_title = title

        subtitle = QLabel("Agent 工作台")
        subtitle.setWordWrap(False)
        subtitle.setStyleSheet(f"color:#6b7280; font-size:{APP_FONT['caption']}px;")
        title_box.addWidget(subtitle)
        self._header_subtitle = subtitle
        self._header_subtitle_full = "应用内直接查询系统状态、解释异常、执行白名单任务，并对修改类动作进行确认。"
        self._header_subtitle_compact = "查询状态 / 解释异常 / 执行白名单任务（修改动作需确认）"
        self._header_frame.setToolTip(self._header_subtitle_full)
        header_layout.addLayout(title_box, 1)

        self._header_status_full = "查询 · 执行 · 变更确认"
        self._header_status_compact = "查询 · 执行"
        status_strip = QLabel(self._header_status_full)
        status_strip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_strip.setStyleSheet(
            "QLabel { background:#ffffff; color:#6b7280; border:1px solid #e5e7eb; "
            f"border-radius:999px; padding:2px 10px; font-size:{APP_FONT['caption']}px; font-weight:600; }}"
        )
        status_strip.setFixedHeight(22)
        header_icon_host = QFrame()
        header_icon_host.setStyleSheet("QFrame { background:transparent; border:none; }")
        header_icon_layout = QHBoxLayout(header_icon_host)
        header_icon_layout.setContentsMargins(0, 0, 0, 0)
        header_icon_layout.setSpacing(6)
        self.btn_header_notice = QPushButton("🔔")
        self.btn_header_notice.setToolTip("通知（预留）")
        self.btn_header_notice.setStyleSheet(
            "QPushButton { background:#ffffff; color:#6b7280; border:1px solid #e5e7eb; "
            "border-radius:11px; font-size:11px; padding:0; }"
            "QPushButton:hover { background:#f3f4f6; color:#111827; }"
        )
        self.btn_header_notice.setFixedSize(22, 22)
        header_icon_layout.addWidget(self.btn_header_notice)
        self.btn_header_settings = QPushButton("⚙")
        self.btn_header_settings.setToolTip("设置（预留）")
        self.btn_header_settings.setStyleSheet(
            "QPushButton { background:#ffffff; color:#6b7280; border:1px solid #e5e7eb; "
            "border-radius:11px; font-size:11px; padding:0; }"
            "QPushButton:hover { background:#f3f4f6; color:#111827; }"
        )
        self.btn_header_settings.setFixedSize(22, 22)
        header_icon_layout.addWidget(self.btn_header_settings)
        header_layout.addWidget(header_icon_host, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._badge_host = status_strip
        self._header_status_strip = status_strip
        header_layout.addWidget(status_strip, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.btn_title_cap_toggle = QPushButton("标题:稳重")
        self.btn_title_cap_toggle.setToolTip("切换欢迎区标题上限：64/68")
        self.btn_title_cap_toggle.setStyleSheet(
            "QPushButton { background:#ffffff; color:#6b7280; border:1px solid #e5e7eb; "
            "border-radius:999px; padding:2px 10px; font-size:11px; font-weight:600; }"
            "QPushButton:hover { background:#f9fafb; color:#111827; border-color:#d1d5db; }"
        )
        self.btn_title_cap_toggle.setFixedHeight(22)
        self.btn_title_cap_toggle.clicked.connect(self._toggle_welcome_title_cap)
        header_layout.addWidget(self.btn_title_cap_toggle, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header.setVisible(False)
        layout.addWidget(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(8)
        splitter.setChildrenCollapsible(False)
        splitter.setStyleSheet(
            "QSplitter::handle:horizontal {"
            "background:#f8fafc; border-left:1px solid #eef2f7; border-right:1px solid #ffffff;"
            "}"
            "QSplitter::handle:horizontal:hover { background:#e5e7eb; }"
        )
        self._splitter = splitter

        # ===== 左侧边栏 =====
        sidebar = QFrame()
        sidebar.setStyleSheet(
            f"QFrame {{ background:{_AI_DARK['surface']}; border:none; border-radius:14px; }}"
        )
        sidebar.setMinimumWidth(240)
        sidebar.setMaximumWidth(480)
        self._sidebar = sidebar
        self._sidebar_collapsed = False
        self._sidebar_auto_collapsed = False
        self._sidebar_user_resized = False
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(12, 12, 12, 12)
        sb_layout.setSpacing(8)

        brand_row = QHBoxLayout()
        self.sidebar_brand = QLabel("✍ FinQuanta")
        self.sidebar_brand.setStyleSheet(
            f"color:{_AI_DARK['text']}; font-size:22px; font-weight:700;"
        )
        brand_row.addWidget(self.sidebar_brand)
        brand_row.addStretch()
        self.btn_sidebar_menu = QPushButton("⌂")
        self.btn_sidebar_menu.setToolTip("折叠/展开侧栏")
        self.btn_sidebar_menu.setStyleSheet(
            f"QPushButton {{ background:{_AI_DARK['surface_alt']}; color:{_AI_DARK['muted']}; border:1px solid {_AI_DARK['border']}; "
            "border-radius:12px; padding:2px 8px; font-size:12px; }"
            f"QPushButton:hover {{ background:{_AI_DARK['accent']}; color:{_AI_DARK['text']}; }}"
        )
        self.btn_sidebar_menu.setFixedSize(30, 24)
        brand_row.addWidget(self.btn_sidebar_menu)
        sb_layout.addLayout(brand_row)

        side_title = QLabel("Agent")
        self._side_title = side_title
        side_title.setStyleSheet(
            f"color:{_AI_DARK['text']}; font-size:{APP_FONT['section']}px; font-weight:bold;"
        )
        sb_layout.addWidget(side_title)

        side_desc = QLabel("任务历史与系统动作，按项目化方式统一管理。")
        self._side_desc = side_desc
        side_desc.setWordWrap(True)
        side_desc.setStyleSheet(f"color:{_AI_DARK['muted']}; font-size:{APP_FONT['caption']}px;")
        sb_layout.addWidget(side_desc)

        self.btn_new_session = QPushButton("✎  新建任务")
        self.btn_new_session.setStyleSheet(
            f"QPushButton {{ background:{_AI_DARK['accent']}; color:#ffffff; border:1px solid {_AI_DARK['selected_border']}; "
            f"border-radius:{_SIDEBAR_TOKENS['btn_radius']}px; padding:8px 12px; "
            f"font-size:{_SIDEBAR_TOKENS['btn_font']}px; font-weight:bold; }}"
            f"QPushButton:hover {{ background:{_AI_DARK['accent_hover']}; }}"
        )
        self.btn_new_session.setMinimumHeight(_SIDEBAR_TOKENS["btn_height"] + 4)
        sb_layout.addWidget(self.btn_new_session)

        sb_layout.addWidget(self._make_divider())

        project_label = QLabel("项目")
        self._project_label = project_label
        project_label.setStyleSheet(
            f"color:{_AI_DARK['subtle']}; font-size:{APP_FONT['caption']}px; padding:2px 2px; font-weight:bold;"
        )
        sb_layout.addWidget(project_label)

        hist_label = QLabel("历史对话")
        self._hist_label = hist_label
        hist_label.setStyleSheet(
            f"color:{_AI_DARK['text']}; font-size:{_SIDEBAR_TOKENS['section_font']}px; padding:4px 2px; font-weight:bold;"
        )
        sb_layout.addWidget(hist_label)

        self.session_list = QListWidget()
        self.session_list.setStyleSheet("""
            QListWidget { background:transparent; border:none; border-radius:%dpx; padding:6px; color:%s; }
            QListWidget::item {
                color:%s; padding:%dpx %dpx; border-radius:%dpx; margin:%dpx 0;
                font-size:%dpx;
            }
            QListWidget::item:selected { background:transparent; color:%s; }
            QListWidget::item:hover { background:transparent; }
            QScrollBar:vertical { background:transparent; width:8px; margin:4px 0 4px 0; }
            QScrollBar::handle:vertical { background:%s; border-radius:4px; min-height:28px; }
            QScrollBar::handle:vertical:hover { background:%s; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0px; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:transparent; }
        """ % (
            _SIDEBAR_TOKENS["list_radius"],
            _AI_DARK["text"],
            _AI_DARK["text"],
            2,
            _SIDEBAR_TOKENS["list_item_hpad"],
            _SIDEBAR_TOKENS["list_item_radius"],
            2,
            _SIDEBAR_TOKENS["list_item_font"],
            _AI_DARK["text"],
            _AI_DARK["scroll"],
            _AI_DARK["muted"],
        ))
        self.session_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.session_list.setSpacing(2)
        sb_layout.addWidget(self.session_list)

        self.btn_delete_session = QPushButton("删除选中对话")
        self.btn_delete_session.setStyleSheet(
            f"QPushButton {{ background:{_AI_DARK['surface_alt']}; color:{_AI_DARK['muted']}; border:1px solid {_AI_DARK['border']}; "
            f"border-radius:{_SIDEBAR_TOKENS['btn_radius']}px; padding:7px 10px; "
            f"font-size:{_SIDEBAR_TOKENS['btn_font']}px; }}"
            "QPushButton:hover { background:#3a1f24; color:#f87171; border-color:#7f1d1d; }"
        )
        self.btn_delete_session.setMinimumHeight(_SIDEBAR_TOKENS["btn_height"])
        sb_layout.addWidget(self.btn_delete_session)
        self.btn_delete_session.setVisible(False)

        # 模型来源提示（全局配置迁移到设置页）
        self._model_divider = self._make_divider()
        sb_layout.addWidget(self._model_divider)
        model_label = QLabel("当前模型")
        model_label.setStyleSheet(
            f"color:{_AI_DARK['text']}; font-size:{_SIDEBAR_TOKENS['section_font']}px; padding:4px 2px; font-weight:bold;"
        )
        self._model_label = model_label
        sb_layout.addWidget(model_label)

        self.model_summary = QLabel("未配置（请前往设置）")
        self.model_summary.setWordWrap(True)
        self.model_summary.setStyleSheet(
            f"background:{_AI_DARK['surface_alt']}; color:{_AI_DARK['text']}; border:1px solid {_AI_DARK['border']}; "
            f"border-radius:8px; padding:9px 11px; font-size:{APP_FONT['body']}px; line-height:1.5;"
        )
        sb_layout.addWidget(self.model_summary)
        self.btn_open_settings = QPushButton("前往设置")
        self.btn_open_settings.setStyleSheet(
            f"QPushButton {{ background:{_AI_DARK['surface_alt']}; color:#58a6ff; border:1px solid {_AI_DARK['border']}; "
            f"border-radius:{_SIDEBAR_TOKENS['btn_radius']}px; padding:7px 10px; "
            f"font-size:{_SIDEBAR_TOKENS['btn_font']}px; font-weight:bold; }}"
            f"QPushButton:hover {{ border-color:#58a6ff; background:{_AI_DARK['accent']}; }}"
        )
        self.btn_open_settings.setMinimumHeight(_SIDEBAR_TOKENS["btn_height"])
        sb_layout.addWidget(self.btn_open_settings)
        self._model_divider.setVisible(False)
        self._model_label.setVisible(False)
        self.model_summary.setVisible(False)
        self.btn_open_settings.setVisible(False)

        sb_layout.addWidget(self._make_divider())
        task_label = QLabel("所有任务")
        self._task_label = task_label
        task_label.setStyleSheet(
            f"color:{_AI_DARK['subtle']}; font-size:{APP_FONT['caption']}px; padding:2px 2px; font-weight:bold;"
        )
        sb_layout.addWidget(task_label)
        action_hist_header = QHBoxLayout()
        action_hist_title = QLabel("任务队列")
        self._action_hist_title = action_hist_title
        action_hist_title.setStyleSheet(
            f"color:{_AI_DARK['text']}; font-size:{_SIDEBAR_TOKENS['section_font']}px; padding:4px 2px; font-weight:bold;"
        )
        action_hist_header.addWidget(action_hist_title)
        action_hist_header.addStretch()
        self.btn_refresh_actions = QPushButton("刷新")
        self.btn_refresh_actions.setStyleSheet(
            "QPushButton { background:#ffffff; color:#6b7280; border:1px solid #e5e7eb; "
            f"border-radius:{_SIDEBAR_TOKENS['btn_radius']}px; padding:6px 10px; font-size:{_SIDEBAR_TOKENS['btn_font']}px; }}"
            "QPushButton:hover { color:#2563eb; border-color:#93c5fd; background:#eff6ff; }"
        )
        self.btn_refresh_actions.setMinimumHeight(_SIDEBAR_TOKENS["btn_height"])
        action_hist_header.addWidget(self.btn_refresh_actions)
        sb_layout.addLayout(action_hist_header)

        self.action_list = QListWidget()
        self.action_list.setStyleSheet("""
            QListWidget { background:transparent; border:none; border-radius:%dpx; padding:4px; color:%s; }
            QListWidget::item {
                color:%s; padding:%dpx %dpx; border-radius:%dpx; margin:%dpx 0;
                font-size:%dpx;
            }
            QListWidget::item:selected { background:transparent; color:%s; }
            QListWidget::item:hover { background:transparent; }
            QScrollBar:vertical { background:transparent; width:8px; margin:4px 0 4px 0; }
            QScrollBar::handle:vertical { background:%s; border-radius:4px; min-height:28px; }
            QScrollBar::handle:vertical:hover { background:%s; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0px; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:transparent; }
        """ % (
            _SIDEBAR_TOKENS["list_radius"],
            _AI_DARK["text"],
            _AI_DARK["text"],
            _SIDEBAR_TOKENS["list_item_vpad"],
            _SIDEBAR_TOKENS["list_item_hpad"],
            _SIDEBAR_TOKENS["list_item_radius"],
            _SIDEBAR_TOKENS["list_item_gap"],
            _SIDEBAR_TOKENS["list_item_font"] - 1,
            _AI_DARK["text"],
            _AI_DARK["scroll"],
            _AI_DARK["muted"],
        ))
        self.action_list.setMaximumHeight(210)
        self.action_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        sb_layout.addWidget(self.action_list)

        self.action_detail_box = QLabel("点击上方系统动作可查看详情")
        self.action_detail_box.setWordWrap(True)
        self.action_detail_box.setStyleSheet(
            f"background:{_AI_DARK['surface_alt']}; color:{_AI_DARK['muted']}; border:1px solid {_AI_DARK['border']}; "
            f"border-radius:12px; padding:10px; font-size:{APP_FONT['body']}px;"
        )
        self.action_detail_box.setMinimumHeight(88)
        sb_layout.addWidget(self.action_detail_box)

        sb_layout.addStretch()

        splitter.addWidget(sidebar)

        # ===== 右侧主区 =====
        main_area = QFrame()
        self._main_area = main_area
        main_area.setStyleSheet(
            f"QFrame {{ background:{_AI_DARK['base']}; border:1px solid {_AI_DARK['border']}; border-radius:14px; }}"
        )
        main_layout = QVBoxLayout(main_area)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)
        self._main_layout = main_layout

        toolbar = QFrame()
        self._toolbar = toolbar
        toolbar.setStyleSheet(
            f"QFrame {{ background:{_AI_DARK['surface']}; border:1px solid {_AI_DARK['border']}; border-radius:{_SURFACE_TOKENS['toolbar_radius']}px; }}"
        )
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(8, 4, 8, 4)
        toolbar_layout.setSpacing(6)
        self.btn_toggle_sidebar = QPushButton("☰ 对话列表")
        self.btn_toggle_sidebar.setStyleSheet(
            f"QPushButton {{ background:{_AI_DARK['surface_alt']}; color:{_AI_DARK['text']}; border:1px solid {_AI_DARK['border']}; "
            f"border-radius:{_SURFACE_TOKENS['control_radius']}px; padding:7px 10px; font-size:{_SURFACE_TOKENS['control_font']}px; }}"
            f"QPushButton:hover {{ border-color:#58a6ff; color:#58a6ff; background:{_AI_DARK['accent']}; }}"
        )
        self.btn_toggle_sidebar.setMinimumHeight(_SURFACE_TOKENS["control_height"])
        toolbar_layout.addWidget(self.btn_toggle_sidebar)
        self.chat_mode_label = QLabel("模式:")
        self.chat_mode_label.setStyleSheet(
            f"color:{_AI_DARK['text']}; font-size:{APP_FONT['emphasis']}px; font-weight:bold;"
        )
        toolbar_layout.addWidget(self.chat_mode_label)
        self.chat_mode_label.setVisible(False)
        self.combo_chat_mode = QComboBox()
        for label, value in _CHAT_MODES:
            self.combo_chat_mode.addItem(label, value)
        self.combo_chat_mode.setCurrentIndex(0)
        self.combo_chat_mode.setStyleSheet(
            f"QComboBox {{ background:{_AI_DARK['surface_alt']}; color:{_AI_DARK['text']}; border:1px solid {_AI_DARK['border']}; "
            f"border-radius:{_SURFACE_TOKENS['control_radius']}px; padding:8px 12px; min-width:110px; font-size:{_SURFACE_TOKENS['control_font']}px; }}"
        )
        self.combo_chat_mode.setMinimumHeight(_SURFACE_TOKENS["control_height"])
        toolbar_layout.addWidget(self.combo_chat_mode)
        mode_desc = QLabel("系统类请求会先走本地执行链路，普通投研问题自动回退到大模型。")
        self._mode_desc = mode_desc
        mode_desc.setStyleSheet(f"color:#6b7280; font-size:{APP_FONT['caption']}px;")
        toolbar_layout.addWidget(mode_desc, 1)
        mode_desc.setVisible(False)
        main_layout.addWidget(toolbar)

        self.welcome_panel = QFrame()
        self.welcome_panel.setStyleSheet("QFrame { background:transparent; border:none; }")
        self.welcome_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        welcome_shell = QVBoxLayout(self.welcome_panel)
        welcome_shell.setContentsMargins(0, 0, 0, 0)
        welcome_shell.setSpacing(0)
        welcome_shell.addStretch(1)

        self.welcome_content = QFrame()
        self.welcome_content.setStyleSheet("QFrame { background:transparent; border:none; }")
        self.welcome_content.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        welcome_layout = QVBoxLayout(self.welcome_content)
        welcome_layout.setContentsMargins(24, 12, 24, 12)
        welcome_layout.setSpacing(14)
        welcome_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._welcome_layout = welcome_layout

        self.welcome_eyebrow = QLabel("FinQuanta Assistant")
        self.welcome_eyebrow.setStyleSheet(f"color:{_AI_DARK['muted']}; font-size:12px;")
        self.welcome_eyebrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_layout.addWidget(self.welcome_eyebrow, 0, Qt.AlignmentFlag.AlignHCenter)

        self.welcome_title = QLabel("我能为你做什么？")
        self.welcome_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.welcome_title.setStyleSheet(
            f"color:{_AI_DARK['text']}; font-weight:500; font-family:'Songti SC','STSong','SimSun',serif;"
        )
        welcome_layout.addWidget(self.welcome_title, 0, Qt.AlignmentFlag.AlignHCenter)

        self.welcome_subtitle = QLabel("分配任务、查询状态、触发执行并获得可审计反馈")
        self.welcome_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.welcome_subtitle.setStyleSheet(f"color:{_AI_DARK['muted']}; font-size:13px;")
        welcome_layout.addWidget(self.welcome_subtitle, 0, Qt.AlignmentFlag.AlignHCenter)

        welcome_action_row = QHBoxLayout()
        welcome_action_row.setSpacing(10)
        welcome_action_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._welcome_action_buttons = []
        for label, question in [
            ("👜 分析我的持仓", "帮我分析手动仓和AI仓的持仓，哪些该持有，哪些该卖出？"),
            ("💡 今日操作建议", "基于我当前持仓和最新市场数据，给出今天的操作建议。"),
            ("🩺 系统诊断", "请检查 daemon 与推送链路状态，并输出自检结果。"),
        ]:
            btn = QPushButton(label)
            btn.setProperty("question", question)
            btn.clicked.connect(self._on_quick_click)
            btn.setStyleSheet(
                f"QPushButton {{ background:{_AI_DARK['surface_alt']}; color:{_AI_DARK['text']}; border:1px solid {_AI_DARK['border']}; "
                "border-radius:18px; padding:6px 14px; font-size:12px; }"
                f"QPushButton:hover {{ background:{_AI_DARK['accent']}; color:#58a6ff; border-color:#58a6ff; }}"
            )
            self._welcome_action_buttons.append(btn)
            welcome_action_row.addWidget(btn)
        welcome_layout.addLayout(welcome_action_row)
        welcome_shell.addWidget(self.welcome_content, 0, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        welcome_shell.addStretch(1)
        main_layout.addWidget(self.welcome_panel, 1)

        # 聊天展示区
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setFrameShape(QFrame.Shape.NoFrame)
        self.chat_display.setStyleSheet("")
        main_layout.addWidget(self.chat_display)

        # 快捷问题栏
        self.quick_bar = QFrame()
        self.quick_bar.setStyleSheet(
            f"QFrame {{ background:{_AI_DARK['surface']}; border:1px solid {_AI_DARK['border']}; border-radius:12px; }}"
        )
        qb_layout = QGridLayout(self.quick_bar)
        qb_layout.setContentsMargins(12, 12, 12, 12)
        qb_layout.setHorizontalSpacing(8)
        qb_layout.setVerticalSpacing(8)
        self._quick_layout = qb_layout
        self._quick_buttons = []
        for idx, (label, question) in enumerate(_QUICK_QUESTIONS):
            btn = QPushButton(label)
            btn.setStyleSheet(
                f"QPushButton {{ background:{_AI_DARK['surface_alt']}; color:{_AI_DARK['text']}; border:1px solid {_AI_DARK['border']}; "
                f"border-radius:17px; padding:8px 14px; font-size:{APP_FONT['body']}px; text-align:left; }}"
                f"QPushButton:hover {{ background:{_AI_DARK['accent']}; color:#58a6ff; border-color:#58a6ff; }}"
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
            f"QFrame {{ background:{_AI_DARK['surface']}; border:1px solid {_AI_DARK['border']}; border-radius:12px; }}"
        )
        action_layout = QVBoxLayout(self.action_card)
        action_layout.setContentsMargins(18, 14, 18, 14)
        action_layout.setSpacing(8)

        self.action_title = QLabel("待确认操作")
        self.action_title.setStyleSheet(
            f"color:#58a6ff; font-size:{APP_FONT['emphasis']}px; font-weight:bold;"
        )
        action_layout.addWidget(self.action_title)

        self.action_risk_badge = QLabel("")
        self.action_risk_badge.setVisible(False)
        self.action_risk_badge.setStyleSheet(
            "background:#1d4ed8; color:#ffffff; border-radius:10px; "
            f"padding:4px 10px; font-size:{APP_FONT['caption']}px; font-weight:bold;"
        )
        action_layout.addWidget(self.action_risk_badge, alignment=Qt.AlignmentFlag.AlignLeft)

        self.action_summary = QLabel("")
        self.action_summary.setWordWrap(True)
        self.action_summary.setStyleSheet(f"color:{_AI_DARK['text']}; font-size:{APP_FONT['body']}px;")
        action_layout.addWidget(self.action_summary)

        self.action_detail = QLabel("")
        self.action_detail.setWordWrap(True)
        self.action_detail.setStyleSheet(f"color:{_AI_DARK['muted']}; font-size:{APP_FONT['caption']}px;")
        action_layout.addWidget(self.action_detail)

        action_btn_row = QHBoxLayout()
        action_btn_row.setContentsMargins(0, 4, 0, 0)
        self.btn_confirm_action = QPushButton("确认执行")
        self.btn_confirm_action.setStyleSheet(
            "QPushButton { background:#238636; color:#fff; border:none; border-radius:8px; "
            f"padding:8px 16px; font-size:{APP_FONT['body']}px; font-weight:bold; }}"
            "QPushButton:hover { background:#2ea043; }"
            "QPushButton:disabled { background:#21262d; color:#484f58; }"
        )
        action_btn_row.addWidget(self.btn_confirm_action)
        self.btn_cancel_action = QPushButton("取消")
        self.btn_cancel_action.setStyleSheet(
            "QPushButton { background:#21262d; color:#c9d1d9; border:1px solid #30363d; "
            f"border-radius:8px; padding:8px 16px; font-size:{APP_FONT['body']}px; }}"
            "QPushButton:hover { border-color:#f85149; color:#f85149; }"
        )
        action_btn_row.addWidget(self.btn_cancel_action)
        action_btn_row.addStretch()
        action_layout.addLayout(action_btn_row)
        main_layout.addWidget(self.action_card)

        # 输入区
        input_frame = QFrame()
        input_frame.setStyleSheet(
            "QFrame { background:transparent; border:none; }"
        )
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(10)
        self.btn_input_attach = QPushButton("＋")
        self.btn_input_attach.setStyleSheet(
            f"QPushButton {{ background:{_AI_DARK['surface_alt']}; color:{_AI_DARK['text']}; border:1px solid {_AI_DARK['border']}; "
            "border-radius:16px; padding:0; "
            f"font-size:{APP_FONT['section']}px; font-weight:bold; }}"
            f"QPushButton:hover {{ border-color:#58a6ff; color:#58a6ff; background:{_AI_DARK['accent']}; }}"
        )
        self.btn_input_attach.setFixedSize(32, 32)
        input_layout.addWidget(self.btn_input_attach)
        self.btn_input_tool = QPushButton("🧰")
        self.btn_input_tool.setStyleSheet(
            f"QPushButton {{ background:{_AI_DARK['surface_alt']}; color:{_AI_DARK['text']}; border:1px solid {_AI_DARK['border']}; "
            "border-radius:16px; padding:0; "
            f"font-size:{APP_FONT['body']}px; }}"
            f"QPushButton:hover {{ border-color:#58a6ff; color:#58a6ff; background:{_AI_DARK['accent']}; }}"
        )
        self.btn_input_tool.setFixedSize(32, 32)
        input_layout.addWidget(self.btn_input_tool)

        self.msg_input = QLineEdit()
        self.msg_input.setPlaceholderText("分配一个任务或提问任何问题")
        self.msg_input.setStyleSheet(
            f"QLineEdit {{ background:{_AI_DARK['surface_alt']}; color:{_AI_DARK['text']}; border:1px solid {_AI_DARK['border']}; "
            "border-radius:16px; padding:11px 14px; "
            f"font-size:{APP_FONT['emphasis']}px; }}"
            f"QLineEdit:focus {{ border-color:#58a6ff; background:{_AI_DARK['surface']}; }}"
        )
        self.msg_input.setMinimumHeight(_SURFACE_TOKENS["send_btn_height"])
        input_layout.addWidget(self.msg_input)

        self.btn_send = QPushButton("➤")
        self.btn_send.setStyleSheet(
            f"QPushButton {{ background:{_AI_DARK['surface_alt']}; color:{_AI_DARK['muted']}; border:1px solid {_AI_DARK['border']}; "
            "border-radius:18px; padding:0; "
            f"font-size:{APP_FONT['emphasis']}px; font-weight:bold; }}"
            f"QPushButton:hover {{ background:{_AI_DARK['accent']}; color:{_AI_DARK['text']}; }}"
            f"QPushButton:disabled {{ background:{_AI_DARK['surface']}; color:{_AI_DARK['subtle']}; }}"
        )
        self.btn_send.setText("↑")
        self.btn_send.setFixedSize(36, 36)
        input_layout.addWidget(self.btn_send)
        self._input_frame = input_frame
        main_layout.addWidget(input_frame)
        self._input_in_welcome = False

        splitter.addWidget(main_area)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([340, 900])
        splitter.splitterMoved.connect(self._on_splitter_moved)
        layout.addWidget(splitter)

        self._current_session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._has_messages = False
        self._pending_action_id = ""
        self._session_item_widgets = {}

        self.btn_new_session.clicked.connect(self._new_session)
        self.session_list.currentItemChanged.connect(self._on_session_selected)
        self.btn_refresh_actions.clicked.connect(self.refresh_action_history)
        self.action_list.currentItemChanged.connect(self._on_action_selected)
        self.btn_open_settings.clicked.connect(self.open_settings_requested.emit)
        self.btn_sidebar_menu.clicked.connect(self._toggle_sidebar)
        self.btn_toggle_sidebar.clicked.connect(self._toggle_sidebar)
        self.btn_input_attach.clicked.connect(self._on_input_attach)
        self.btn_input_tool.clicked.connect(self._on_input_tool_template)
        self.btn_input_attach.installEventFilter(self)
        self.btn_input_tool.installEventFilter(self)

        self._input_hint_card = QLabel(self)
        self._input_hint_card.setVisible(False)
        self._input_hint_card.setWordWrap(True)
        self._input_hint_card.setStyleSheet(
            f"QLabel {{ background:{_AI_DARK['surface']}; color:{_AI_DARK['text']}; border:1px solid {_AI_DARK['selected_border']}; "
            "border-radius:10px; padding:8px 10px; font-size:11px; }"
        )
        self._input_hint_card.resize(220, 56)
        self._input_hint_hide_timer = QTimer(self)
        self._input_hint_hide_timer.setSingleShot(True)
        self._input_hint_hide_timer.timeout.connect(self._input_hint_card.hide)

        self._apply_chat_display_style(28)
        theme_fn = getattr(self, "_apply_theme_styles", None)
        if callable(theme_fn):
            theme_fn()
        self._apply_header_responsive(self.width())
        self._apply_welcome_layout_state(self.width())
        self.refresh_sessions()
        self.refresh_action_history()

    @staticmethod
    def _make_divider() -> QFrame:
        d = QFrame()
        d.setFixedHeight(1)
        d.setStyleSheet(f"background:{_AI_DARK['border']}; margin:4px 0;")
        return d

    def _show_welcome(self):
        width = max(980, self.width())
        if width >= 2400:
            title_size = 74
            content_width = 1180
            pill_font = 13
        elif width >= 1800:
            title_size = 68
            content_width = 980
            pill_font = 12
        elif width >= 1400:
            title_size = 60
            content_width = 860
            pill_font = 12
        else:
            title_size = 50
            content_width = 760
            pill_font = 11
        title_cap = int(self._welcome_title_caps.get(self._welcome_title_cap_mode, 64))
        title_size = min(title_size, title_cap)
        self.welcome_title.setStyleSheet(
            f"color:{_AI_DARK['text']}; font-size:{title_size}px; font-weight:500; "
            "font-family:'Songti SC','STSong','SimSun',serif;"
        )
        self.welcome_content.setMaximumWidth(content_width)
        for btn in self._welcome_action_buttons:
            btn.setStyleSheet(
                "QPushButton { background:#ffffff; color:#374151; border:1px solid #e5e7eb; "
                f"border-radius:18px; padding:6px 14px; font-size:{pill_font}px; }}"
                "QPushButton:hover { background:#f9fafb; color:#2563eb; border-color:#bfdbfe; }"
            )

    def set_theme(self, theme: str):
        self._theme = "light" if str(theme).lower() == "light" else "dark"
        _AI_DARK.clear()
        _AI_DARK.update(_AI_LIGHT if self._theme == "light" else _AI_DARK_BASE)
        theme_fn = getattr(self, "_apply_theme_styles", None)
        if callable(theme_fn):
            theme_fn()
        self.refresh_sessions()
        self.refresh_action_history()
        self.clear_pending_action()
        if self._has_messages:
            msgs = get_session_messages(self._current_session_id)
            self.chat_display.clear()
            for m in msgs:
                self.append_message(m["role"], m["content"], save=False)
        else:
            self._show_welcome()
            self._apply_welcome_layout_state(self.width())

    def _apply_theme_styles(self):
        self._sidebar.setStyleSheet(
            f"QFrame {{ background:{_AI_DARK['surface']}; border:none; border-radius:14px; }}"
        )
        self.sidebar_brand.setStyleSheet(
            f"color:{_AI_DARK['text']}; font-size:22px; font-weight:700;"
        )
        self.btn_sidebar_menu.setStyleSheet(
            f"QPushButton {{ background:{_AI_DARK['surface_alt']}; color:{_AI_DARK['muted']}; border:1px solid {_AI_DARK['border']}; "
            "border-radius:12px; padding:2px 8px; font-size:12px; }"
            f"QPushButton:hover {{ background:{_AI_DARK['accent']}; color:{_AI_DARK['text']}; }}"
        )
        self._side_title.setStyleSheet(
            f"color:{_AI_DARK['text']}; font-size:{APP_FONT['section']}px; font-weight:bold;"
        )
        self._side_desc.setStyleSheet(f"color:{_AI_DARK['muted']}; font-size:{APP_FONT['caption']}px;")
        self._project_label.setStyleSheet(
            f"color:{_AI_DARK['subtle']}; font-size:{APP_FONT['caption']}px; padding:2px 2px; font-weight:bold;"
        )
        self._hist_label.setStyleSheet(
            f"color:{_AI_DARK['text']}; font-size:{_SIDEBAR_TOKENS['section_font']}px; padding:4px 2px; font-weight:bold;"
        )
        self._task_label.setStyleSheet(
            f"color:{_AI_DARK['subtle']}; font-size:{APP_FONT['caption']}px; padding:2px 2px; font-weight:bold;"
        )
        self._action_hist_title.setStyleSheet(
            f"color:{_AI_DARK['text']}; font-size:{_SIDEBAR_TOKENS['section_font']}px; padding:4px 2px; font-weight:bold;"
        )
        self.btn_new_session.setStyleSheet(
            f"QPushButton {{ background:{_AI_DARK['accent']}; color:#ffffff; border:1px solid {_AI_DARK['selected_border']}; "
            f"border-radius:{_SIDEBAR_TOKENS['btn_radius']}px; padding:8px 12px; font-size:{_SIDEBAR_TOKENS['btn_font']}px; font-weight:bold; }}"
            f"QPushButton:hover {{ background:{_AI_DARK['accent_hover']}; }}"
        )
        self.btn_refresh_actions.setStyleSheet(
            f"QPushButton {{ background:{_AI_DARK['surface_alt']}; color:{_AI_DARK['muted']}; border:1px solid {_AI_DARK['border']}; "
            f"border-radius:{_SIDEBAR_TOKENS['btn_radius']}px; padding:6px 10px; font-size:{_SIDEBAR_TOKENS['btn_font']}px; }}"
            f"QPushButton:hover {{ color:#58a6ff; border-color:#58a6ff; background:{_AI_DARK['accent']}; }}"
        )
        self.action_detail_box.setStyleSheet(
            f"background:{_AI_DARK['surface_alt']}; color:{_AI_DARK['muted']}; border:1px solid {_AI_DARK['border']}; "
            f"border-radius:12px; padding:10px; font-size:{APP_FONT['body']}px;"
        )
        self._main_area.setStyleSheet(
            f"QFrame {{ background:{_AI_DARK['base']}; border:1px solid {_AI_DARK['border']}; border-radius:14px; }}"
        )
        self._toolbar.setStyleSheet(
            f"QFrame {{ background:{_AI_DARK['surface']}; border:1px solid {_AI_DARK['border']}; border-radius:{_SURFACE_TOKENS['toolbar_radius']}px; }}"
        )
        self.btn_toggle_sidebar.setStyleSheet(
            f"QPushButton {{ background:{_AI_DARK['surface_alt']}; color:{_AI_DARK['text']}; border:1px solid {_AI_DARK['border']}; "
            f"border-radius:{_SURFACE_TOKENS['control_radius']}px; padding:7px 10px; font-size:{_SURFACE_TOKENS['control_font']}px; }}"
            f"QPushButton:hover {{ border-color:#58a6ff; color:#58a6ff; background:{_AI_DARK['accent']}; }}"
        )
        self.chat_mode_label.setStyleSheet(
            f"color:{_AI_DARK['text']}; font-size:{APP_FONT['emphasis']}px; font-weight:bold;"
        )
        self.combo_chat_mode.setStyleSheet(
            f"QComboBox {{ background:{_AI_DARK['surface_alt']}; color:{_AI_DARK['text']}; border:1px solid {_AI_DARK['border']}; "
            f"border-radius:{_SURFACE_TOKENS['control_radius']}px; padding:8px 12px; min-width:110px; font-size:{_SURFACE_TOKENS['control_font']}px; }}"
        )
        self._mode_desc.setStyleSheet(f"color:{_AI_DARK['muted']}; font-size:{APP_FONT['caption']}px;")
        self.quick_bar.setStyleSheet(
            f"QFrame {{ background:{_AI_DARK['surface']}; border:1px solid {_AI_DARK['border']}; border-radius:12px; }}"
        )
        self.welcome_eyebrow.setStyleSheet(f"color:{_AI_DARK['muted']}; font-size:12px;")
        self.welcome_subtitle.setStyleSheet(f"color:{_AI_DARK['muted']}; font-size:13px;")
        self.action_card.setStyleSheet(
            f"QFrame {{ background:{_AI_DARK['surface']}; border:1px solid {_AI_DARK['border']}; border-radius:12px; }}"
        )
        self.action_title.setStyleSheet(
            f"color:#58a6ff; font-size:{APP_FONT['emphasis']}px; font-weight:bold;"
        )
        self.action_summary.setStyleSheet(f"color:{_AI_DARK['text']}; font-size:{APP_FONT['body']}px;")
        self.action_detail.setStyleSheet(f"color:{_AI_DARK['muted']}; font-size:{APP_FONT['caption']}px;")
        self.btn_input_attach.setStyleSheet(
            f"QPushButton {{ background:{_AI_DARK['surface_alt']}; color:{_AI_DARK['text']}; border:1px solid {_AI_DARK['border']}; "
            f"border-radius:16px; padding:0; font-size:{APP_FONT['section']}px; font-weight:bold; }}"
            f"QPushButton:hover {{ border-color:#58a6ff; color:#58a6ff; background:{_AI_DARK['accent']}; }}"
        )
        self.btn_input_tool.setStyleSheet(
            f"QPushButton {{ background:{_AI_DARK['surface_alt']}; color:{_AI_DARK['text']}; border:1px solid {_AI_DARK['border']}; "
            f"border-radius:16px; padding:0; font-size:{APP_FONT['body']}px; }}"
            f"QPushButton:hover {{ border-color:#58a6ff; color:#58a6ff; background:{_AI_DARK['accent']}; }}"
        )
        self.msg_input.setStyleSheet(
            f"QLineEdit {{ background:{_AI_DARK['surface_alt']}; color:{_AI_DARK['text']}; border:1px solid {_AI_DARK['border']}; "
            f"border-radius:16px; padding:11px 14px; font-size:{APP_FONT['emphasis']}px; }}"
            f"QLineEdit:focus {{ border-color:#58a6ff; background:{_AI_DARK['surface']}; }}"
        )
        self.btn_send.setStyleSheet(
            f"QPushButton {{ background:{_AI_DARK['surface_alt']}; color:{_AI_DARK['muted']}; border:1px solid {_AI_DARK['border']}; "
            f"border-radius:18px; padding:0; font-size:{APP_FONT['emphasis']}px; font-weight:bold; }}"
            f"QPushButton:hover {{ background:{_AI_DARK['accent']}; color:{_AI_DARK['text']}; }}"
            f"QPushButton:disabled {{ background:{_AI_DARK['surface']}; color:{_AI_DARK['subtle']}; }}"
        )
        self._input_hint_card.setStyleSheet(
            f"QLabel {{ background:{_AI_DARK['surface']}; color:{_AI_DARK['text']}; border:1px solid {_AI_DARK['selected_border']}; "
            "border-radius:10px; padding:8px 10px; font-size:11px; }"
        )
        self._apply_chat_display_style(28)

    def _apply_welcome_layout_state(self, width: int):
        w = max(980, int(width or self.width() or 980))
        if not self._has_messages:
            if w >= 2200:
                input_w = 1320
            elif w >= 1700:
                input_w = 1120
            elif w >= 1300:
                input_w = 940
            else:
                input_w = max(760, w - 320)
            self.welcome_panel.setVisible(True)
            self.chat_display.setVisible(False)
            self.welcome_panel.setMaximumHeight(16777215)
            self.welcome_panel.setMinimumHeight(0)
            self.quick_bar.setVisible(False)
            self.action_card.setVisible(False)
            self._mount_input_frame_in_welcome(True)
            self._input_frame.setMaximumWidth(input_w)
            self.msg_input.setMinimumWidth(max(420, input_w - 170))
            self._welcome_layout.setAlignment(self._input_frame, Qt.AlignmentFlag.AlignHCenter)
        else:
            self.welcome_panel.setVisible(False)
            self.chat_display.setVisible(True)
            self.chat_display.setMaximumHeight(16777215)
            self.chat_display.setMinimumHeight(0)
            self._mount_input_frame_in_welcome(False)
            self._input_frame.setMaximumWidth(16777215)
            self.msg_input.setMinimumWidth(0)
            self._main_layout.setAlignment(self._input_frame, Qt.AlignmentFlag(0))

    def _mount_input_frame_in_welcome(self, in_welcome: bool):
        target = bool(in_welcome)
        if target and not self._input_in_welcome:
            self._main_layout.removeWidget(self._input_frame)
            self._welcome_layout.insertWidget(3, self._input_frame, 0, Qt.AlignmentFlag.AlignHCenter)
            self._input_in_welcome = True
        elif (not target) and self._input_in_welcome:
            self._welcome_layout.removeWidget(self._input_frame)
            self._main_layout.addWidget(self._input_frame)
            self._input_in_welcome = False

    def _toggle_welcome_title_cap(self):
        self._welcome_title_cap_mode = "impact" if self._welcome_title_cap_mode == "steady" else "steady"
        if self._welcome_title_cap_mode == "impact":
            self.btn_title_cap_toggle.setText("标题:冲击")
        else:
            self.btn_title_cap_toggle.setText("标题:稳重")
        if not self._has_messages:
            self._show_welcome()

    def set_model_summary(self, provider: str, model: str, source_hint: str = "默认模型来自设置"):
        provider_text = (provider or "未设置").strip()
        model_text = (model or "未设置").strip()
        self.model_summary.setText(f"{provider_text} / {model_text}\n{source_hint}")

    def _on_quick_click(self):
        btn = self.sender()
        if btn:
            q = btn.property("question")
            if q:
                self.msg_input.setText(q)
                self.btn_send.click()

    def _on_input_attach(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择附件", "", "All Files (*.*)")
        if not path:
            return
        filename = os.path.basename(path)
        existing = self.msg_input.text().strip()
        prefix = f"[附件:{filename}] {path}"
        self.msg_input.setText(f"{prefix}\n{existing}" if existing else f"{prefix}\n请结合附件分析。")
        self.msg_input.setFocus()

    def _on_input_tool_template(self):
        templates = [
            "请读取运行中心并给出今日异常摘要与修复建议。",
            "请分析当前持仓风险并给出三条可执行建议。",
            "请检查 daemon 与推送链路状态，并输出自检结果。",
        ]
        current = self.msg_input.text().strip()
        idx = 0
        if current in templates:
            idx = (templates.index(current) + 1) % len(templates)
        self.msg_input.setText(templates[idx])
        self.msg_input.setFocus()

    def eventFilter(self, obj, event):
        if obj in (getattr(self, "btn_input_attach", None), getattr(self, "btn_input_tool", None)):
            if event.type() == QEvent.Type.Enter:
                self._input_hint_hide_timer.stop()
                if obj is self.btn_input_attach:
                    self._show_input_hint_card(
                        obj,
                        "附件入口\n选择本地文件并自动插入路径到输入框。"
                    )
                else:
                    self._show_input_hint_card(
                        obj,
                        "工具入口\n快速插入常用任务模板，点击可轮换。"
                    )
            elif event.type() == QEvent.Type.Leave:
                self._input_hint_hide_timer.start(120)
        return super().eventFilter(obj, event)

    def _show_input_hint_card(self, anchor_btn: QPushButton, text: str):
        self._input_hint_card.setText(text)
        self._input_hint_card.adjustSize()
        anchor = anchor_btn.mapTo(self, QPoint(anchor_btn.width() // 2, 0))
        x = max(8, min(self.width() - self._input_hint_card.width() - 8, anchor.x() - self._input_hint_card.width() // 2))
        y = max(8, anchor.y() - self._input_hint_card.height() - 8)
        self._input_hint_card.move(x, y)
        self._input_hint_card.raise_()
        self._input_hint_card.show()

    def _new_session(self):
        self._current_session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._has_messages = False
        self._apply_welcome_layout_state(self.width())
        self.clear_pending_action()

    def _on_session_selected(self, current, previous):
        self._sync_session_item_styles()
        if not current:
            return
        sid = current.data(Qt.ItemDataRole.UserRole)
        if not sid:
            return
        self._current_session_id = sid
        msgs = get_session_messages(sid)
        self.chat_display.clear()
        self._has_messages = bool(msgs)
        self._apply_welcome_layout_state(self.width())
        self.clear_pending_action()
        for m in msgs:
            self.append_message(m["role"], m["content"], save=False)

    def _delete_session(self, session_id: str | None = None):
        item = self.session_list.currentItem()
        sid = session_id or (item.data(Qt.ItemDataRole.UserRole) if item else "")
        if not sid:
            return
        conn = RepoCompatConnection()
        conn.execute("DELETE FROM ai_chat_history WHERE session_id=?", (sid,))
        conn.commit()
        conn.close()
        delete_session_meta(sid)
        if sid == self._current_session_id:
            self._new_session()
        self.refresh_sessions()

    def refresh_sessions(self):
        current_sid = self._current_session_id
        self.session_list.clear()
        self._session_item_widgets = {}
        for s in get_sessions(50):
            q = (s.get("title") or s.get("first_question") or "新对话").strip()
            ts = s["last_time"][:10] if s["last_time"] else ""
            favorite = bool(s.get("favorite", False))
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, s["session_id"])
            item.setSizeHint(self.session_list.sizeHintForIndex(self.session_list.model().index(0, 0)).expandedTo(item.sizeHint()))
            self.session_list.addItem(item)
            widget = _SessionItemWidget(
                q,
                f"{ts} · {s['msg_count']}条",
                favorite=favorite,
                parent=self.session_list,
            )
            widget.clicked.connect(lambda sid=s["session_id"]: self._select_session_by_id(sid))
            widget.menu_requested.connect(lambda sid=s["session_id"]: self._show_session_menu(sid))
            self.session_list.setItemWidget(item, widget)
            item.setSizeHint(widget.sizeHint())
            self._session_item_widgets[s["session_id"]] = widget
            if s["session_id"] == current_sid:
                self.session_list.setCurrentItem(item)
        self._sync_session_item_styles()

    def _select_session_by_id(self, session_id: str):
        for idx in range(self.session_list.count()):
            item = self.session_list.item(idx)
            if item and item.data(Qt.ItemDataRole.UserRole) == session_id:
                self.session_list.setCurrentItem(item)
                break

    def _sync_session_item_styles(self):
        current = self.session_list.currentItem()
        current_sid = current.data(Qt.ItemDataRole.UserRole) if current else ""
        for sid, widget in self._session_item_widgets.items():
            widget.set_selected(sid == current_sid)

    def _show_session_menu(self, session_id: str):
        self._select_session_by_id(session_id)
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background:{_AI_DARK['surface']}; color:{_AI_DARK['text']}; border:1px solid {_AI_DARK['border']}; border-radius:12px; padding:6px; }}"
            "QMenu::item { padding:8px 14px; border-radius:8px; }"
            f"QMenu::item:selected {{ background:{_AI_DARK['accent']}; color:#58a6ff; }}"
        )
        rename_action = QAction("重命名", self)
        rename_action.triggered.connect(lambda: self._rename_session(session_id))
        menu.addAction(rename_action)

        sessions = {s["session_id"]: s for s in get_sessions(200)}
        current_meta = sessions.get(session_id, {})
        favorite = bool(current_meta.get("favorite", False))
        favorite_action = QAction("取消收藏" if favorite else "添加到收藏", self)
        favorite_action.triggered.connect(lambda fav=not favorite: self._toggle_session_favorite(session_id, fav))
        menu.addAction(favorite_action)

        delete_action = QAction("删除", self)
        delete_action.triggered.connect(lambda: self._delete_session(session_id))
        menu.addAction(delete_action)

        widget = self._session_item_widgets.get(session_id)
        anchor = widget.menu_btn.mapToGlobal(QPoint(widget.menu_btn.width() // 2, widget.menu_btn.height()))
        menu.exec(anchor)

    def _rename_session(self, session_id: str):
        sessions = {s["session_id"]: s for s in get_sessions(200)}
        current_title = (sessions.get(session_id, {}).get("title") or sessions.get(session_id, {}).get("first_question") or "").strip()
        text, ok = QInputDialog.getText(self, "重命名对话", "新的对话名称：", text=current_title[:80])
        if not ok:
            return
        save_session_meta(session_id, title=text)
        self.refresh_sessions()

    def _toggle_session_favorite(self, session_id: str, favorite: bool):
        save_session_meta(session_id, favorite=favorite)
        self.refresh_sessions()

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
            self._apply_welcome_layout_state(self.width())

        ts = datetime.now().strftime("%H:%M")

        if role == "user":
            html = (
                f'<div style="margin:16px 12px 4px 88px;">'
                f'<div style="text-align:right;color:#9ca3af;font-size:10px;margin-bottom:3px;">你 · {ts}</div>'
                f'<div style="background:#0f3460;color:#ffffff;border:1px solid #24508d;border-radius:18px 18px 4px 18px;'
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
                f'<span style="background:#111827;color:#fff;border-radius:6px;padding:2px 6px;'
                f'font-size:10px;font-weight:bold;">AI</span>'
                f'<span style="color:#e0e0e0;font-size:12px;font-weight:bold;">FinQuanta 助手</span>'
                f'<span style="color:#9ca3af;font-size:10px;">{ts}</span></div>'
                # 内容卡片
                f'<div style="background:#16213e;color:#e0e0e0;border-radius:8px 16px 16px 16px;'
                f'padding:16px 20px;font-size:13px;line-height:1.7;'
                f'border:1px solid #33384d;box-shadow:0 4px 12px rgba(0,0,0,0.18);">'
                f'{content}</div></div>'
            )
        elif role == "thinking":
            # Manus 风格：思考过程
            html = (
                f'<div style="margin:8px 24px 4px 8px;">'
                f'<div style="background:#fffbeb;border:1px solid #fde68a;border-radius:10px;'
                f'padding:10px 14px;color:#92400e;font-size:12px;">'
                f'<span style="color:#b45309;">⏳ 思考中...</span> {text}</div></div>'
            )
        else:
            html = (
                f'<div style="text-align:center;margin:10px 24px;">'
                f'<div style="display:inline-block;background:#16213e;border:1px solid #33384d;'
                f'border-radius:20px;padding:5px 16px;">'
                f'<span style="color:#aab4c3;font-size:11px;">⚙️ {text}</span></div></div>'
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
            f"background:{_AI_DARK['base']}; color:{_AI_DARK['text']}; border:1px solid {_AI_DARK['border']}; border-radius:16px; "
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
                "bg": "#eff6ff",
                "border": "#93c5fd",
                "title": "#1d4ed8",
                "badge_bg": "#2563eb",
            },
            "medium": {
                "label": "中",
                "bg": "#fffbeb",
                "border": "#fcd34d",
                "title": "#b45309",
                "badge_bg": "#d97706",
            },
            "high": {
                "label": "高",
                "bg": "#fef2f2",
                "border": "#fca5a5",
                "title": "#dc2626",
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
        self._apply_header_responsive(width)
        self._apply_sidebar_responsive(width)
        if width < 1100:
            chat_pad = 16
            quick_cols = 1
        elif width < 1500:
            chat_pad = 22
            quick_cols = 2
        else:
            chat_pad = 28
            quick_cols = 3
        if width < 1100:
            self._sidebar.setMinimumWidth(220)
        elif width < 1500:
            self._sidebar.setMinimumWidth(250)
        elif width < 2100:
            self._sidebar.setMinimumWidth(280)
        else:
            self._sidebar.setMinimumWidth(340)
        self._sidebar.setMaximumWidth(620 if width >= 2100 else 520)
        if (not self._sidebar_collapsed) and (not self._sidebar_user_resized):
            if width >= 2400:
                default_sidebar = 460
            elif width >= 2100:
                default_sidebar = 420
            elif width >= 1500:
                default_sidebar = 340
            elif width >= 1200:
                default_sidebar = 300
            else:
                default_sidebar = 260
            self._splitter.setSizes([default_sidebar, max(720, width - default_sidebar - 40)])
        self._apply_chat_display_style(chat_pad)
        self._reflow_quick_buttons(quick_cols)
        self._apply_compact_spacing(width)
        self._apply_welcome_layout_state(width)

    def _apply_header_responsive(self, width: int):
        very_narrow = width < 980
        medium = width < 1500
        if self._ultra_compact_mode:
            if width < 1100:
                self._header_layout.setContentsMargins(8, 4, 8, 4)
            else:
                self._header_layout.setContentsMargins(10, 5, 10, 5)
        elif width < 1100:
            self._header_layout.setContentsMargins(12, 8, 12, 8)
        else:
            self._header_layout.setContentsMargins(14, 10, 14, 10)
        self._header_layout.setDirection(QBoxLayout.Direction.LeftToRight)
        self._header_layout.setAlignment(
            self._badge_host, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        if self._ultra_compact_mode:
            self._header_subtitle.setVisible(False)
            if very_narrow:
                self._header_title.setStyleSheet(
                    f"color:#111827; font-size:{APP_FONT['body']}px; font-weight:700;"
                )
            elif medium:
                self._header_title.setStyleSheet(
                    f"color:#111827; font-size:{APP_FONT['emphasis']}px; font-weight:700;"
                )
            else:
                self._header_title.setStyleSheet(
                    f"color:#111827; font-size:{APP_FONT['section']}px; font-weight:700;"
                )
            self._header_status_strip.setText(
                self._header_status_compact if width < 1200 else self._header_status_full
            )
            self._header_status_strip.setStyleSheet(
                "QLabel { background:#f8fafc; color:#4b5563; border:1px solid #e2e8f0; "
                f"border-radius:999px; padding:2px 10px; font-size:{APP_FONT['caption']}px; font-weight:600; }}"
            )
            self._header_status_strip.setFixedHeight(22)
        elif very_narrow:
            self._header_title.setStyleSheet(
                f"color:#111827; font-size:{APP_FONT['emphasis']}px; font-weight:700;"
            )
            self._header_subtitle.setVisible(False)
            self._header_status_strip.setText(self._header_status_compact)
            self._header_status_strip.setStyleSheet(
                "QLabel { background:#eff6ff; color:#2563eb; border:1px solid #bfdbfe; "
                f"border-radius:999px; padding:2px 10px; font-size:{APP_FONT['caption']}px; font-weight:600; }}"
            )
            self._header_status_strip.setFixedHeight(22)
        elif medium:
            self._header_title.setStyleSheet(
                f"color:#111827; font-size:{APP_FONT['section']}px; font-weight:700;"
            )
            self._header_subtitle.setVisible(False)
            self._header_status_strip.setText(self._header_status_full)
            self._header_status_strip.setStyleSheet(
                "QLabel { background:#f8fafc; color:#4b5563; border:1px solid #e2e8f0; "
                f"border-radius:999px; padding:2px 10px; font-size:{APP_FONT['caption']}px; font-weight:600; }}"
            )
            self._header_status_strip.setFixedHeight(22)
        else:
            self._header_title.setStyleSheet(
                f"color:#111827; font-size:{APP_FONT['section']}px; font-weight:700;"
            )
            self._header_subtitle.setVisible(False)
            self._header_status_strip.setText(self._header_status_full)
            self._header_status_strip.setStyleSheet(
                "QLabel { background:#f8fafc; color:#4b5563; border:1px solid #e2e8f0; "
                f"border-radius:999px; padding:2px 10px; font-size:{APP_FONT['caption']}px; font-weight:600; }}"
            )
            self._header_status_strip.setFixedHeight(22)

    def _apply_sidebar_responsive(self, width: int):
        if width < 980 and not self._sidebar_collapsed:
            self._set_sidebar_collapsed(True, auto=True)
        elif width >= 1220 and self._sidebar_collapsed and self._sidebar_auto_collapsed:
            self._set_sidebar_collapsed(False, auto=True)

    def _toggle_sidebar(self):
        self._set_sidebar_collapsed(not self._sidebar_collapsed, auto=False)
        self._sidebar_user_resized = False

    def _on_splitter_moved(self, pos: int, index: int):
        if not self._sidebar_collapsed:
            self._sidebar_user_resized = True

    def _set_sidebar_collapsed(self, collapsed: bool, *, auto: bool):
        self._sidebar_collapsed = bool(collapsed)
        self._sidebar_auto_collapsed = bool(auto and collapsed)
        self._sidebar.setVisible(not collapsed)
        if collapsed:
            self.btn_toggle_sidebar.setText("☰ 展开侧栏")
            self.btn_toggle_sidebar.setToolTip("展开历史会话与系统动作侧栏")
            self._splitter.setSizes([0, max(1000, self.width())])
        else:
            self.btn_toggle_sidebar.setText("☰ 对话列表")
            self.btn_toggle_sidebar.setToolTip("收起历史会话与系统动作侧栏")
            if self.width() >= 2400:
                default_sidebar = 460
            elif self.width() >= 2100:
                default_sidebar = 420
            elif self.width() >= 1500:
                default_sidebar = 340
            elif self.width() >= 1200:
                default_sidebar = 300
            else:
                default_sidebar = 260
            self._splitter.setSizes([default_sidebar, max(720, self.width() - default_sidebar - 40)])

    def _apply_compact_spacing(self, width: int):
        if width < 980:
            self.layout().setContentsMargins(6, 6, 6, 6)
            self.layout().setSpacing(6)
            self.quick_bar.setVisible(False if not self._has_messages else False)
        else:
            if width >= 2100:
                self.layout().setContentsMargins(10, 10, 10, 10)
                self.layout().setSpacing(8)
            else:
                self.layout().setContentsMargins(6, 6, 6, 6)
                self.layout().setSpacing(6)
            if not self._has_messages:
                self.quick_bar.setVisible(True)
