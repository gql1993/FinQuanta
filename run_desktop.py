"""
AI 驱动量化客户端 - 启动入口
"""
import sys
import os
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.runtime.mode import LOCAL_MODE, resolve_runtime_mode_context

LOG_FILE = os.path.join("data_cache", "desktop_crash.log")


def main():
    try:
        runtime = resolve_runtime_mode_context()
        if "FINQUANTA_RUNTIME_MODE" not in os.environ:
            os.environ["FINQUANTA_RUNTIME_MODE"] = LOCAL_MODE
        if runtime.is_platform_mode:
            print(
                "FinQuanta desktop is starting in platform mode "
                f"(db_backend={runtime.db_backend}).",
                file=sys.stderr,
            )

        os.environ["QT_OPENGL"] = "software"
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu"

        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtGui import QFont, QIcon

        # WebEngine 必须在 QApplication 之前初始化
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
        except ImportError:
            pass

        app = QApplication(sys.argv)
        app.setApplicationName("FinQuanta")
        app.setFont(QFont("Microsoft YaHei", 10))
        _icon = os.path.join(os.path.dirname(__file__), "desktop", "resources", "finquanta.ico")
        if os.path.isfile(_icon):
            app.setWindowIcon(QIcon(_icon))

        from desktop.main_window import MainWindow
        window = MainWindow()
        window.show()

        sys.exit(app.exec())
    except Exception as e:
        msg = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        print(msg, file=sys.stderr)
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write(msg)
        sys.exit(1)


if __name__ == "__main__":
    main()
