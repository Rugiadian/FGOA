"""
Floating Emergency Stop Widget for FGOA.
An always-on-top, draggable mini floating bar that provides immediate stop
and pause controls regardless of which window is active on screen.
"""
from typing import Optional
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QGraphicsDropShadowEffect
)
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtCore import Qt, pyqtSignal, QPoint


class GlobalFloatingStopWidget(QWidget):
    """
    Compact always-on-top floating emergency stop widget.
    Draggable anywhere on the desktop and clearly indicates running state.
    """
    sig_stop_requested = pyqtSignal()
    sig_pause_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        self._drag_pos = QPoint()
        self._init_ui()

    def _init_ui(self):
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(8, 8, 8, 8)

        # Container Frame with dark red styled border & shadow
        self.container = QWidget()
        self.container.setObjectName("floating_stop_container")
        self.container.setStyleSheet("""
            QWidget#floating_stop_container {
                background-color: #18181b;
                border: 2px solid #ef4444;
                border-radius: 8px;
            }
        """)

        # Drop shadow effect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 4)
        self.container.setGraphicsEffect(shadow)

        c_layout = QHBoxLayout(self.container)
        c_layout.setContentsMargins(10, 6, 10, 6)
        c_layout.setSpacing(8)

        # Drag handle icon
        lbl_drag = QLabel("⠿")
        lbl_drag.setToolTip("마우스로 드래그하여 원하는 위치로 이동할 수 있습니다.")
        lbl_drag.setStyleSheet("color: #a1a1aa; font-size: 14pt; font-weight: bold;")
        lbl_drag.setCursor(Qt.SizeAllCursor)
        c_layout.addWidget(lbl_drag)

        # Title & Status Label
        self.lbl_status = QLabel("오토 실행 중...")
        self.lbl_status.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 9pt;")
        self.lbl_status.setMaximumWidth(220)
        c_layout.addWidget(self.lbl_status)

        # Pause Button
        self.btn_pause = QPushButton("⏸ 일시정지")
        self.btn_pause.setStyleSheet("""
            QPushButton {
                background-color: #ea580c;
                color: #ffffff;
                font-weight: bold;
                font-size: 9pt;
                padding: 4px 10px;
                border: 1px solid #c2410c;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #c2410c;
            }
        """)
        self.btn_pause.clicked.connect(self._on_pause_clicked)
        c_layout.addWidget(self.btn_pause)

        # Big Red Emergency Stop Button
        self.btn_stop = QPushButton("⏹ 정지 (F6)")
        self.btn_stop.setStyleSheet("""
            QPushButton {
                background-color: #dc2626;
                color: #ffffff;
                font-weight: bold;
                font-size: 9.5pt;
                padding: 5px 14px;
                border: 1px solid #b91c1c;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #b91c1c;
            }
        """)
        self.btn_stop.clicked.connect(self._on_stop_clicked)
        c_layout.addWidget(self.btn_stop)

        # Close/Hide button
        btn_close = QPushButton("✕")
        btn_close.setToolTip("이 플로팅 바를 닫습니다 (FGOA 창에서 다시 켤 수 있습니다).")
        btn_close.setFixedSize(20, 20)
        btn_close.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #71717a;
                font-weight: bold;
                border: none;
                font-size: 9pt;
            }
            QPushButton:hover {
                color: #ffffff;
                background-color: #3f3f46;
                border-radius: 10px;
            }
        """)
        btn_close.clicked.connect(self.hide)
        c_layout.addWidget(btn_close)

        root_layout.addWidget(self.container)
        self.adjustSize()

    def set_status(self, text: str):
        """Updates the status text label."""
        self.lbl_status.setText(text)

    def set_paused_state(self, is_paused: bool):
        """Updates the pause button label according to state."""
        if is_paused:
            self.btn_pause.setText("▶ 재개")
            self.btn_pause.setStyleSheet("""
                QPushButton {
                    background-color: #16a34a;
                    color: #ffffff;
                    font-weight: bold;
                    font-size: 9pt;
                    padding: 4px 10px;
                    border: 1px solid #15803d;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #15803d;
                }
            """)
        else:
            self.btn_pause.setText("⏸ 일시정지")
            self.btn_pause.setStyleSheet("""
                QPushButton {
                    background-color: #ea580c;
                    color: #ffffff;
                    font-weight: bold;
                    font-size: 9pt;
                    padding: 4px 10px;
                    border: 1px solid #c2410c;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #c2410c;
                }
            """)

    def _on_pause_clicked(self):
        self.sig_pause_requested.emit()

    def _on_stop_clicked(self):
        self.sig_stop_requested.emit()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and not self._drag_pos.isNull():
            self.move(event.globalPos() - self._drag_pos)
            event.accept()
