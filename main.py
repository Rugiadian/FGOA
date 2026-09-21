"""
FGOA - Windows Auto Input & Color Detection Automation Tool
Entry Point
"""
import sys
import ctypes
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
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
    configure_high_dpi()

    app = QApplication(sys.argv)
    app.setApplicationName("FGOA")
    app.setOrganizationName("Rugiadian")

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
