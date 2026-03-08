"""设置面板"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QGroupBox, QGridLayout, QComboBox, QCheckBox,
)
from PyQt6.QtGui import QFont


class SettingsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        title = QLabel("⚙️ 设置")
        title.setFont(QFont("", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        push_group = QGroupBox("📤 微信推送（Server酱）")
        pg = QGridLayout(push_group)
        pg.addWidget(QLabel("SendKey:"), 0, 0)
        self.push_key = QLineEdit()
        self.push_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.push_key.setPlaceholderText("SCTxxxxxxxxxxxxx")
        pg.addWidget(self.push_key, 0, 1)
        self.btn_save_push = QPushButton("💾 保存")
        pg.addWidget(self.btn_save_push, 0, 2)
        self.btn_test_push = QPushButton("🔔 测试推送")
        pg.addWidget(self.btn_test_push, 0, 3)
        self.push_status = QLabel("")
        pg.addWidget(self.push_status, 1, 0, 1, 4)
        layout.addWidget(push_group)

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
