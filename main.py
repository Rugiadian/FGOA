"""
FGOA - Windows Auto Input & Color Detection Automation Tool
Entry Point
"""
import sys
import os
import ctypes

# 1. Prevent Python from creating or locking .pyc bytecode files
# This allows modifying code freely while the application is running without file-lock issues.
sys.dont_write_bytecode = True

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPalette, QColor
from ui.main_window import MainWindow


def configure_high_dpi():
    """Ensure Windows high-DPI awareness so pixel coordinates match 1:1 on scaled displays."""
    try:
        # Per-monitor DPI aware (Windows 8.1+)
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            # System DPI aware fallback (Windows Vista+)
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)


def main():
    from core.window_manager import WindowManager
    WindowManager.ensure_input_desktop()

    configure_high_dpi()

    app = QApplication(sys.argv)
    app.setApplicationName("FGOA")
    app.setOrganizationName("Rugiadian")

    # Use Fusion style to prevent Windows OS Dark Mode DWM surface from leaking black backgrounds
    app.setStyle("Fusion")

    # Set light-safe default fallback palette
    base_palette = app.palette()
    base_palette.setColor(QPalette.Window, QColor("#f1f5f9"))
    base_palette.setColor(QPalette.WindowText, QColor("#1e293b"))
    base_palette.setColor(QPalette.Base, QColor("#ffffff"))
    base_palette.setColor(QPalette.AlternateBase, QColor("#f8fafc"))
    base_palette.setColor(QPalette.Text, QColor("#1e293b"))
    base_palette.setColor(QPalette.Button, QColor("#ffffff"))
    base_palette.setColor(QPalette.ButtonText, QColor("#1e293b"))
    app.setPalette(base_palette)

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
