"""深色/浅色主题样式"""

DARK_STYLE = """
QMainWindow, QWidget { background-color: #1a1a2e; color: #e0e0e0; }
QTabWidget::pane { border: 1px solid #333; background: #1a1a2e; }
QTabBar::tab { background: #16213e; color: #aaa; padding: 8px 18px; margin-right: 2px; border-top-left-radius: 4px; border-top-right-radius: 4px; }
QTabBar::tab:selected { background: #0f3460; color: #fff; font-weight: bold; }
QTabBar::tab:hover { background: #1a3a6e; }
QTableWidget { background: #16213e; gridline-color: #333; color: #e0e0e0; alternate-background-color: #1a2744; }
QTableWidget::item:selected { background: #0f3460; }
QHeaderView::section { background: #0f3460; color: #fff; padding: 6px; border: 1px solid #333; font-weight: bold; }
QPushButton { background: #0f3460; color: #fff; border: none; padding: 8px 16px; border-radius: 4px; font-weight: bold; }
QPushButton:hover { background: #1a4a8e; }
QPushButton:pressed { background: #0a2a4a; }
QPushButton[cssClass="danger"] { background: #d32f2f; }
QPushButton[cssClass="success"] { background: #388e3c; }
QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background: #16213e; color: #e0e0e0; border: 1px solid #333; padding: 6px; border-radius: 3px;
}
QLabel { color: #e0e0e0; }
QGroupBox { border: 1px solid #333; border-radius: 4px; margin-top: 12px; padding-top: 16px; color: #aaa; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; color: #4fc3f7; }
QSplitter::handle { background: #333; }
QScrollBar:vertical { background: #1a1a2e; width: 10px; }
QScrollBar::handle:vertical { background: #333; border-radius: 5px; min-height: 20px; }
QStatusBar { background: #0f3460; color: #ccc; }
QMenuBar { background: #0f3460; color: #ddd; }
QMenuBar::item:selected { background: #1a4a8e; }
QMenu { background: #16213e; color: #ddd; border: 1px solid #333; }
QMenu::item:selected { background: #0f3460; }
QProgressBar { border: 1px solid #333; border-radius: 3px; text-align: center; color: #fff; }
QProgressBar::chunk { background: #4fc3f7; }
"""

LIGHT_STYLE = """
QMainWindow, QWidget { background-color: #fafafa; color: #333; }
QTabWidget::pane { border: 1px solid #ddd; background: #fff; }
QTabBar::tab { background: #f0f0f0; color: #666; padding: 8px 18px; margin-right: 2px; border-top-left-radius: 4px; border-top-right-radius: 4px; }
QTabBar::tab:selected { background: #1976d2; color: #fff; font-weight: bold; }
QTabBar::tab:hover { background: #e0e0e0; }
QTableWidget { background: #fff; gridline-color: #eee; color: #333; alternate-background-color: #f9f9f9; }
QTableWidget::item:selected { background: #bbdefb; }
QHeaderView::section { background: #1976d2; color: #fff; padding: 6px; border: 1px solid #ddd; font-weight: bold; }
QPushButton { background: #1976d2; color: #fff; border: none; padding: 8px 16px; border-radius: 4px; font-weight: bold; }
QPushButton:hover { background: #1565c0; }
QPushButton:pressed { background: #0d47a1; }
QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background: #fff; color: #333; border: 1px solid #ddd; padding: 6px; border-radius: 3px;
}
QGroupBox { border: 1px solid #ddd; border-radius: 4px; margin-top: 12px; padding-top: 16px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; color: #1976d2; }
QStatusBar { background: #1976d2; color: #fff; }
QMenuBar { background: #1976d2; color: #fff; }
QMenuBar::item:selected { background: #1565c0; }
QMenu { background: #fff; color: #333; border: 1px solid #ddd; }
QMenu::item:selected { background: #e3f2fd; }
QProgressBar { border: 1px solid #ddd; border-radius: 3px; text-align: center; }
QProgressBar::chunk { background: #1976d2; }
"""
