"""
Modern UI styling and stylesheet constants for FGOA.
Supports both Light Mode and Dark Mode with Fusion-based professional styling.
Completely eliminates dark/black background leakage under Windows dark system settings.
"""
import os

_ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
CHECK_ICON_PATH = os.path.join(_ASSETS_DIR, "check_white.png").replace("\\", "/")


LIGHT_STYLESHEET = f"""
QMainWindow, QWidget#central_widget {{
    background-color: #f1f5f9;
    color: #1e293b;
    font-family: "Segoe UI", "Malgun Gothic", sans-serif;
    font-size: 9.5pt;
}}

QWidget {{
    color: #1e293b;
    font-family: "Segoe UI", "Malgun Gothic", sans-serif;
}}

QSplitter, QSplitter#main_h_splitter, QSplitter#inspector_v_splitter {{
    background-color: #f1f5f9;
}}

QSplitter::handle {{
    background-color: #e2e8f0;
}}

QSplitter::handle:hover {{
    background-color: #3b82f6;
}}

QSplitter::handle:vertical {{
    height: 5px;
}}

QSplitter::handle:horizontal {{
    width: 5px;
}}

QScrollArea {{
    background-color: #f8fafc;
    border: none;
}}

QScrollArea > QWidget > QWidget {{
    background-color: #f8fafc;
}}

QToolBar {{
    background-color: #ffffff;
    border-bottom: 1px solid #e2e8f0;
    padding: 4px;
    spacing: 4px;
}}

QToolButton {{
    background-color: #ffffff;
    color: #1e293b;
    border: 1px solid #d1d5db;
    border-radius: 4px;
    padding: 3px 8px;
    font-weight: 500;
}}

QToolButton:hover {{
    background-color: #f1f5f9;
    border-color: #94a3b8;
}}

QToolButton:pressed {{
    background-color: #e2e8f0;
}}

QPushButton {{
    background-color: #ffffff;
    color: #1e293b;
    border: 1px solid #d1d5db;
    border-radius: 4px;
    padding: 3px 8px;
    font-weight: 600;
    min-height: 20px;
    font-size: 9pt;
}}

QPushButton:hover {{
    background-color: #f8fafc;
    border-color: #94a3b8;
}}

QPushButton:pressed {{
    background-color: #e2e8f0;
}}

QPushButton:disabled,
QPushButton#btn_run:disabled,
QPushButton#btn_stop:disabled,
QPushButton#btn_pause:disabled,
QPushButton#btn_primary:disabled {{
    background-color: #f1f5f9;
    color: #94a3b8;
    border: 1px solid #e2e8f0;
}}

QPushButton#btn_run {{
    background-color: #16a34a;
    color: #ffffff;
    border: 1px solid #15803d;
    font-size: 9.5pt;
    font-weight: bold;
}}
QPushButton#btn_run:hover {{
    background-color: #15803d;
}}

QPushButton#btn_stop {{
    background-color: #dc2626;
    color: #ffffff;
    border: 1px solid #b91c1c;
    font-size: 9.5pt;
    font-weight: bold;
}}
QPushButton#btn_stop:hover {{
    background-color: #b91c1c;
}}

QPushButton#btn_pause {{
    background-color: #ea580c;
    color: #ffffff;
    border: 1px solid #c2410c;
    font-weight: bold;
}}
QPushButton#btn_pause:hover {{
    background-color: #c2410c;
}}

QPushButton#btn_primary {{
    background-color: #2563eb;
    color: #ffffff;
    border: 1px solid #1d4ed8;
    font-weight: bold;
}}
QPushButton#btn_primary:hover {{
    background-color: #1d4ed8;
}}

QPushButton#btn_theme {{
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    color: #334155;
    font-weight: bold;
    padding: 3px 8px;
}}
QPushButton#btn_theme:hover {{
    background-color: #f1f5f9;
    border-color: #94a3b8;
}}

/* Card Frames */
QFrame#card_frame {{
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
}}

QFrame#inspector_card {{
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
}}

QFrame#section_card {{
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 4px;
}}

/* Spreadsheet Table Styling */
QTableWidget {{
    background-color: #ffffff;
    alternate-background-color: #f8fafc;
    gridline-color: #f1f5f9;
    color: #1e293b;
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    selection-background-color: #dbeafe;
    selection-color: #1e3a8a;
    font-size: 9pt;
}}

QTableWidget::item {{
    padding: 2px 4px;
    border-bottom: 1px solid #f1f5f9;
}}

QTableWidget::item:selected {{
    background-color: #dbeafe;
    color: #1e3a8a;
}}

QHeaderView::section {{
    background-color: #f8fafc;
    color: #334155;
    padding: 4px 6px;
    border: 1px solid #e2e8f0;
    font-weight: bold;
    font-size: 8.5pt;
}}

QHeaderView::section:checked {{
    background-color: #e2e8f0;
    color: #0f172a;
}}

QTableCornerButton::section {{
    background-color: #f8fafc;
    border: 1px solid #e2e8f0;
}}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: #ffffff;
    color: #0f172a;
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    padding: 2px 6px;
    min-height: 20px;
    font-size: 9pt;
}}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid #2563eb;
}}

QComboBox QAbstractItemView {{
    background-color: #ffffff;
    color: #0f172a;
    selection-background-color: #dbeafe;
    selection-color: #1e3a8a;
    border: 1px solid #cbd5e1;
}}

QGroupBox {{
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 10px;
    font-weight: bold;
    color: #1e40af;
    font-size: 9pt;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 8px;
    padding: 0 4px;
    background-color: #ffffff;
}}

QScrollBar:vertical {{
    background: #f8fafc;
    width: 10px;
    margin: 0px;
}}

QScrollBar::handle:vertical {{
    background: #cbd5e1;
    min-height: 24px;
    border-radius: 4px;
    margin: 2px;
}}

QScrollBar::handle:vertical:hover {{
    background: #94a3b8;
}}

QScrollBar:horizontal {{
    background: #f8fafc;
    height: 10px;
    margin: 0px;
}}

QScrollBar::handle:horizontal {{
    background: #cbd5e1;
    min-width: 24px;
    border-radius: 4px;
    margin: 2px;
}}

QStatusBar {{
    background-color: #ffffff;
    color: #64748b;
    border-top: 1px solid #e2e8f0;
}}

QTextEdit, QPlainTextEdit {{
    background-color: #ffffff;
    color: #1e293b;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    font-family: "Consolas", "Cascadia Code", monospace;
    font-size: 9pt;
}}

QLabel {{
    color: #1e293b;
}}

QCheckBox {{
    color: #1e293b;
    spacing: 6px;
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid #94a3b8;
    border-radius: 3px;
    background-color: #ffffff;
}}

QCheckBox::indicator:checked {{
    background-color: #2563eb;
    border-color: #2563eb;
    image: url("{CHECK_ICON_PATH}");
}}

QSplitter::handle:horizontal {{
    background-color: #e2e8f0;
    width: 6px;
}}
QSplitter::handle:horizontal:hover {{
    background-color: #94a3b8;
}}
QSplitter::handle:vertical {{
    background-color: #e2e8f0;
    height: 6px;
}}
QSplitter::handle:vertical:hover {{
    background-color: #94a3b8;
}}
"""

DARK_STYLESHEET = f"""
QMainWindow, QWidget#central_widget {{
    background-color: #1a1a20;
    color: #e0e0e6;
    font-family: "Segoe UI", "Malgun Gothic", sans-serif;
    font-size: 9.5pt;
}}

QWidget {{
    color: #e0e0e6;
    font-family: "Segoe UI", "Malgun Gothic", sans-serif;
}}

QSplitter, QSplitter#main_h_splitter, QSplitter#inspector_v_splitter {{
    background-color: #1a1a22;
}}

QSplitter::handle {{
    background-color: #363644;
}}

QSplitter::handle:hover {{
    background-color: #60a5fa;
}}

QSplitter::handle:vertical {{
    height: 5px;
}}

QSplitter::handle:horizontal {{
    width: 5px;
}}

QScrollArea {{
    background-color: #18181f;
    border: none;
}}

QScrollArea > QWidget > QWidget {{
    background-color: #18181f;
}}

QToolBar {{
    background-color: #22222b;
    border-bottom: 1px solid #363644;
    padding: 4px;
    spacing: 4px;
}}

QToolButton {{
    background-color: #2d2d37;
    color: #f0f0f5;
    border: 1px solid #3d3d4b;
    border-radius: 4px;
    padding: 3px 8px;
    font-weight: 500;
}}

QToolButton:hover {{
    background-color: #383845;
    border-color: #4f4f60;
}}

QToolButton:pressed {{
    background-color: #1f1f26;
}}

QPushButton {{
    background-color: #2b2b36;
    color: #f0f0f5;
    border: 1px solid #3d3d4b;
    border-radius: 4px;
    padding: 3px 8px;
    font-weight: 600;
    min-height: 20px;
    font-size: 9pt;
}}

QPushButton:hover {{
    background-color: #383847;
    border-color: #555569;
}}

QPushButton:pressed {{
    background-color: #1d1d24;
}}

QPushButton:disabled,
QPushButton#btn_run:disabled,
QPushButton#btn_stop:disabled,
QPushButton#btn_pause:disabled,
QPushButton#btn_primary:disabled {{
    background-color: #23232b;
    color: #555566;
    border: 1px solid #2e2e38;
}}

QPushButton#btn_run {{
    background-color: #1b5e20;
    color: #ffffff;
    border: 1px solid #2e7d32;
    font-size: 9.5pt;
    font-weight: bold;
}}
QPushButton#btn_run:hover {{
    background-color: #2e7d32;
}}

QPushButton#btn_stop {{
    background-color: #b71c1c;
    color: #ffffff;
    border: 1px solid #c62828;
    font-size: 9.5pt;
    font-weight: bold;
}}
QPushButton#btn_stop:hover {{
    background-color: #c62828;
}}

QPushButton#btn_pause {{
    background-color: #e65100;
    color: #ffffff;
    border: 1px solid #ef6c00;
    font-weight: bold;
}}
QPushButton#btn_pause:hover {{
    background-color: #ef6c00;
}}

QPushButton#btn_primary {{
    background-color: #1976d2;
    color: #ffffff;
    border: 1px solid #1565c0;
    font-weight: bold;
}}
QPushButton#btn_primary:hover {{
    background-color: #1565c0;
}}

QPushButton#btn_theme {{
    background-color: #2b2b36;
    border: 1px solid #4a4a5a;
    color: #f0f0f5;
    font-weight: bold;
    padding: 3px 8px;
}}
QPushButton#btn_theme:hover {{
    background-color: #383847;
    border-color: #66667d;
}}

/* Card Frames */
QFrame#card_frame {{
    background-color: #24242d;
    border: 1px solid #383847;
    border-radius: 6px;
}}

QFrame#inspector_card {{
    background-color: #22222a;
    border: 1px solid #363644;
    border-radius: 6px;
}}

QFrame#section_card {{
    background-color: #262632;
    border: 1px solid #3b3b4a;
    border-radius: 6px;
    padding: 4px;
}}

/* Spreadsheet Table Styling */
QTableWidget {{
    background-color: #17171d;
    alternate-background-color: #202028;
    gridline-color: #2c2c36;
    color: #e2e2e8;
    border: 1px solid #363644;
    border-radius: 4px;
    selection-background-color: #294066;
    selection-color: #ffffff;
    font-size: 9pt;
}}

QTableWidget::item {{
    padding: 2px 4px;
    border-bottom: 1px solid #24242e;
}}

QTableWidget::item:selected {{
    background-color: #294066;
    color: #ffffff;
}}

QHeaderView::section {{
    background-color: #272731;
    color: #b0b0be;
    padding: 4px 6px;
    border: 1px solid #353544;
    font-weight: bold;
    font-size: 8.5pt;
}}

QHeaderView::section:checked {{
    background-color: #333340;
    color: #ffffff;
}}

QTableCornerButton::section {{
    background-color: #272731;
    border: 1px solid #353544;
}}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: #282833;
    color: #ffffff;
    border: 1px solid #3e3e4f;
    border-radius: 4px;
    padding: 2px 6px;
    min-height: 20px;
    font-size: 9pt;
}}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid #4d8bf0;
}}

QComboBox QAbstractItemView {{
    background-color: #22222b;
    color: #ffffff;
    selection-background-color: #3b5998;
    border: 1px solid #3e3e4f;
}}

QGroupBox {{
    background-color: #22222a;
    border: 1px solid #363644;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 10px;
    font-weight: bold;
    color: #8da4c4;
    font-size: 9pt;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 8px;
    padding: 0 4px;
    background-color: #22222a;
}}

QScrollBar:vertical {{
    background: #18181f;
    width: 10px;
    margin: 0px;
}}

QScrollBar::handle:vertical {{
    background: #383847;
    min-height: 24px;
    border-radius: 4px;
    margin: 2px;
}}

QScrollBar::handle:vertical:hover {{
    background: #4f4f63;
}}

QScrollBar:horizontal {{
    background: #18181f;
    height: 10px;
    margin: 0px;
}}

QScrollBar::handle:horizontal {{
    background: #383847;
    min-width: 24px;
    border-radius: 4px;
    margin: 2px;
}}

QStatusBar {{
    background-color: #16161c;
    color: #9e9eb0;
    border-top: 1px solid #2e2e38;
}}

QTextEdit, QPlainTextEdit {{
    background-color: #141418;
    color: #d8d8e2;
    border: 1px solid #2f2f3c;
    border-radius: 6px;
    font-family: "Consolas", "Cascadia Code", monospace;
    font-size: 9pt;
}}

QLabel {{
    color: #dcdce6;
}}

QCheckBox {{
    color: #dcdce6;
    spacing: 6px;
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid #444456;
    border-radius: 3px;
    background-color: #252530;
}}

QCheckBox::indicator:checked {{
    background-color: #2979ff;
    border-color: #2979ff;
    image: url("{CHECK_ICON_PATH}");
}}

QSplitter::handle:horizontal {{
    background-color: #2a2a35;
    width: 6px;
}}
QSplitter::handle:horizontal:hover {{
    background-color: #3d3d4d;
}}
QSplitter::handle:vertical {{
    background-color: #2a2a35;
    height: 6px;
}}
QSplitter::handle:vertical:hover {{
    background-color: #3d3d4d;
}}
"""


def get_stylesheet(theme: str) -> str:
    """Returns the CSS stylesheet string for requested theme ('light' or 'dark')."""
    if theme.lower() == "light":
        return LIGHT_STYLESHEET
    return DARK_STYLESHEET


def get_theme_colors(theme: str) -> dict:
    """Returns a dictionary of semantic UI colors for the active theme."""
    is_light = (theme.lower() == "light")
    return {
        "is_light": is_light,
        "text_primary": "#1e293b" if is_light else "#e0e0e6",
        "text_secondary": "#64748b" if is_light else "#8da4c4",
        "bg_card": "#ffffff" if is_light else "#24242d",
        "border": "#e2e8f0" if is_light else "#383847",
        "row_highlight": "#dbeafe" if is_light else "#233c5f",
        "row_normal": "#ffffff" if is_light else "#18181c",
        "row_alt": "#f8fafc" if is_light else "#202028",
        "success": "#16a34a" if is_light else "#66bb6a",
        "warning": "#d97706" if is_light else "#ffa726",
        "danger": "#dc2626" if is_light else "#ef5350",
        "info": "#2563eb" if is_light else "#4fc3f7",
        "log_info": "#0284c7" if is_light else "#90caf9",
        "log_action": "#7c3aed" if is_light else "#ce93d8",
        "log_success": "#15803d" if is_light else "#a5d6a7",
        "log_warn": "#b45309" if is_light else "#ffe082",
        "log_error": "#b91c1c" if is_light else "#ef9a9a",
        "log_user": "#0f766e" if is_light else "#80deea"
    }
