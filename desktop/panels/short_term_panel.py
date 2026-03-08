"""短期选股面板 —— 将事件选股与基金持仓合并为一个入口。"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTabWidget
from PyQt6.QtGui import QFont

from desktop.panels.event_panel import EventPanel
from desktop.panels.fund_panel import FundPanel


class ShortTermPanel(QWidget):
    """包含"⚡ 事件选股"和"🏦 基金持仓"两个子标签页。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.inner_tabs = QTabWidget()
        self.inner_tabs.setFont(QFont("", 11))

        self.event_panel = EventPanel()
        self.fund_panel = FundPanel()

        self.inner_tabs.addTab(self.event_panel, "⚡ 事件选股")
        self.inner_tabs.addTab(self.fund_panel, "🏦 基金持仓")

        layout.addWidget(self.inner_tabs)
