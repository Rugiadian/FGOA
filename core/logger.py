"""
Logging and Crash Reporting Module for FGOA.
Captures all unhandled exceptions, writes persistent crash logs to disk,
redirects stderr/stdout safely for pythonw, and provides user-facing error dialogs.
"""
import sys
import os
import traceback
import datetime
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CRASH_LOG_PATH = os.path.join(BASE_DIR, "fgoa_crash.log")
DEBUG_LOG_PATH = os.path.join(BASE_DIR, "fgoa_debug.log")


class DualStream:
    """Redirects writes to both a file and the original stream (stdout/stderr)."""
    def __init__(self, file_path: str, original_stream=None):
        self.file_path = file_path
        self.original_stream = original_stream

    def write(self, message):
        if self.original_stream:
            try:
                self.original_stream.write(message)
                self.original_stream.flush()
            except Exception:
                pass
        if message and message.strip():
            try:
                with open(self.file_path, "a", encoding="utf-8") as f:
                    f.write(message)
                    if not message.endswith("\n"):
                        f.write("\n")
                    f.flush()
            except Exception:
                pass

    def flush(self):
        if self.original_stream:
            try:
                self.original_stream.flush()
            except Exception:
                pass


def setup_logging():
    """Configure system-wide rotating debug logging and stream redirection."""
    # Ensure logs dir / files are accessible
    logger = logging.getLogger("FGOA")
    logger.setLevel(logging.DEBUG)

    # Avoid duplicate handlers
    if not logger.handlers:
        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        try:
            rfh = RotatingFileHandler(
                DEBUG_LOG_PATH, maxBytes=3 * 1024 * 1024, backupCount=2, encoding="utf-8"
            )
            rfh.setLevel(logging.DEBUG)
            rfh.setFormatter(formatter)
            logger.addHandler(rfh)
        except Exception:
            pass

        # Also add console handler if stdout exists
        if sys.stdout:
            ch = logging.StreamHandler(sys.stdout)
            ch.setLevel(logging.INFO)
            ch.setFormatter(formatter)
            logger.addHandler(ch)

    # Redirect stderr so uncaught errors in threads or C extensions are captured
    try:
        sys.stderr = DualStream(DEBUG_LOG_PATH, sys.stderr)
    except Exception:
        pass

    return logger


def log_crash(exc_type, exc_value, exc_tb) -> str:
    """Format and write full crash details to fgoa_crash.log."""
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))

    try:
        from core.version import __version__
        version_str = __version__
    except Exception:
        version_str = "Unknown"

    report = (
        f"\n{'='*70}\n"
        f"[FGOA CRASH REPORT - {now_str}]\n"
        f"FGOA Version: {version_str}\n"
        f"Python: {sys.version}\n"
        f"Executable: {sys.executable}\n"
        f"Base Dir: {BASE_DIR}\n"
        f"Error Type: {exc_type.__name__}\n"
        f"Error Message: {exc_value}\n"
        f"{'-'*70}\n"
        f"Stack Trace:\n{tb_str}"
        f"{'='*70}\n"
    )

    try:
        with open(CRASH_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(report)
            f.flush()
    except Exception:
        pass

    try:
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"\n[CRASH] {now_str} - {exc_type.__name__}: {exc_value}\n{tb_str}\n")
            f.flush()
    except Exception:
        pass

    return report


def show_crash_dialog(report: str, exc_type, exc_value):
    """Display an interactive dialog allowing user to view and copy the crash report."""
    try:
        from PyQt5.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
            QPushButton, QApplication
        )
        from PyQt5.QtCore import Qt

        app = QApplication.instance()
        if not app:
            return

        dlg = QDialog()
        dlg.setWindowTitle("⚠️ FGOA 오류 발생 (크래시 감지)")
        dlg.resize(680, 440)

        layout = QVBoxLayout(dlg)
        layout.setSpacing(10)

        lbl_msg = QLabel(
            f"<b>프로그램 실행 중 예기치 않은 오류가 발생했습니다.</b><br>"
            f"<span style='color: #dc2626; font-weight: bold;'>{exc_type.__name__}: {exc_value}</span><br>"
            f"<span style='color: #64748b; font-size: 8.5pt;'>아래 상세 내용을 복사하여 제보해 주시면 즉시 해결할 수 있습니다. "
            f"(로그 파일: <code>fgoa_crash.log</code>)</span>"
        )
        lbl_msg.setWordWrap(True)
        layout.addWidget(lbl_msg)

        txt_details = QTextEdit()
        txt_details.setReadOnly(True)
        txt_details.setPlainText(report)
        txt_details.setStyleSheet(
            "background-color: #0f172a; color: #f8fafc; font-family: Consolas, monospace; font-size: 8.5pt;"
        )
        layout.addWidget(txt_details, 1)

        btn_bar = QHBoxLayout()
        btn_copy = QPushButton("📋 오류 내용 복사")
        btn_copy.setStyleSheet("background-color: #2563eb; color: white; font-weight: bold; padding: 6px 14px;")
        def on_copy():
            clipboard = QApplication.clipboard()
            clipboard.setText(report)
            btn_copy.setText("✅ 복사 완료!")
        btn_copy.clicked.connect(on_copy)
        btn_bar.addWidget(btn_copy)

        btn_open_file = QPushButton("📂 로그 파일 열기")
        def on_open_file():
            open_log_file()
        btn_open_file.clicked.connect(on_open_file)
        btn_bar.addWidget(btn_open_file)

        btn_bar.addStretch()

        btn_close = QPushButton("닫기")
        btn_close.clicked.connect(dlg.accept)
        btn_bar.addWidget(btn_close)

        layout.addLayout(btn_bar)

        dlg.exec_()
    except Exception:
        pass


def install_crash_handler():
    """Install global unhandled exception hook."""
    setup_logging()

    def excepthook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return

        report = log_crash(exc_type, exc_value, exc_tb)
        show_crash_dialog(report, exc_type, exc_value)

    sys.excepthook = excepthook


def open_log_file():
    """Open crash log in Windows Notepad or default editor."""
    target = CRASH_LOG_PATH if os.path.exists(CRASH_LOG_PATH) else DEBUG_LOG_PATH
    if not os.path.exists(target):
        try:
            with open(target, "w", encoding="utf-8") as f:
                f.write("[FGOA Log Initialized]\n")
        except Exception:
            pass

    try:
        os.startfile(target)
    except Exception:
        import subprocess
        subprocess.Popen(["notepad.exe", target])
