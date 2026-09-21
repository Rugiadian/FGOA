"""
Modern UI styling and stylesheet constants for FGOA.
Dark / Modern professional spreadsheet theme.
"""

DARK_STYLESHEET = """
QMainWindow {
    background-color: #1e1e24;
    color: #e0e0e6;
    font-family: "Segoe UI", "Malgun Gothic", sans-serif;
    font-size: 10pt;
}

QWidget {
    background-color: #1e1e24;
    color: #e0e0e6;
    font-family: "Segoe UI", "Malgun Gothic", sans-serif;
}

QToolBar {
    background-color: #25252d;
    border-bottom: 1px solid #363642;
    padding: 6px;
    spacing: 6px;
}

QToolButton {
    background-color: #2d2d37;
    color: #f0f0f5;
    border: 1px solid #3d3d4b;
    border-radius: 4px;
    padding: 5px 10px;
    font-weight: 500;
}

QToolButton:hover {
    background-color: #383845;
    border-color: #4f4f60;
}

QToolButton:pressed {
    background-color: #1f1f26;
}

QPushButton {
    background-color: #2b2b36;
    color: #f0f0f5;
    border: 1px solid #3d3d4b;
    border-radius: 5px;
    padding: 6px 14px;
    font-weight: bold;
    min-height: 20px;
}

QPushButton:hover {
    background-color: #383847;
    border-color: #555569;
}

QPushButton:pressed {
    background-color: #1d1d24;
}

QPushButton#btn_run {
    background-color: #1b5e20;
    color: #ffffff;
    border: 1px solid #2e7d32;
    font-size: 11pt;
}
QPushButton#btn_run:hover {
    background-color: #2e7d32;
}

QPushButton#btn_stop {
    background-color: #b71c1c;
    color: #ffffff;
    border: 1px solid #c62828;
    font-size: 11pt;
}
QPushButton#btn_stop:hover {
    background-color: #c62828;
}

QPushButton#btn_pause {
    background-color: #e65100;
    color: #ffffff;
    border: 1px solid #ef6c00;
}
QPushButton#btn_pause:hover {
    background-color: #ef6c00;
}

/* Spreadsheet Table Styling */
QTableWidget {
    background-color: #18181c;
    alternate-background-color: #212127;
    gridline-color: #2e2e38;
    color: #e2e2e8;
    border: 1px solid #363644;
    selection-background-color: #2b3a55;
    selection-color: #ffffff;
    font-size: 9.5pt;
}

QTableWidget::item {
    padding: 6px;
    border-bottom: 1px solid #282833;
}

QTableWidget::item:selected {
    background-color: #294066;
}

QHeaderView::section {
    background-color: #272731;
    color: #b0b0be;
    padding: 6px;
    border: 1px solid #353544;
    font-weight: bold;
    font-size: 9.5pt;
}

QHeaderView::section:checked {
    background-color: #333340;
    color: #ffffff;
}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #282833;
    color: #ffffff;
    border: 1px solid #3e3e4f;
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 22px;
}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #4d8bf0;
}

QComboBox QAbstractItemView {
    background-color: #22222b;
    color: #ffffff;
    selection-background-color: #3b5998;
    border: 1px solid #3e3e4f;
}

QGroupBox {
    border: 1px solid #363644;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 14px;
    font-weight: bold;
    color: #8da4c4;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 4px;
}

QScrollBar:vertical {
    background: #1a1a20;
    width: 12px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #383847;
    min-height: 25px;
    border-radius: 4px;
    margin: 2px;
}

QScrollBar::handle:vertical:hover {
    background: #4f4f63;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    background: #1a1a20;
    height: 12px;
    margin: 0px;
}

QScrollBar::handle:horizontal {
    background: #383847;
    min-width: 25px;
    border-radius: 4px;
    margin: 2px;
}

QStatusBar {
    background-color: #17171c;
    color: #9e9eb0;
    border-top: 1px solid #2e2e38;
}

QTextEdit, QPlainTextEdit {
    background-color: #141418;
    color: #d8d8e2;
    border: 1px solid #2f2f3c;
    font-family: "Consolas", "Cascadia Code", monospace;
    font-size: 9pt;
}

QLabel {
    color: #dcdce6;
}

QCheckBox {
    color: #dcdce6;
    spacing: 6px;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 1px solid #444456;
    border-radius: 3px;
    background-color: #252530;
}

QCheckBox::indicator:checked {
    background-color: #2979ff;
    border-color: #2979ff;
}
"""
