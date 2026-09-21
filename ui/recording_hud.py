"""
Floating HUD overlay for Action Sequence Recording.
Floats on top of all windows while recording user actions on the target game window.
"""
from typing import List, Optional
from PyQt5.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QGraphicsDropShadowEffect
)
from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QTimer
from PyQt5.QtGui import QColor, QFont

from core.models import Action
from core.recorder import ActionRecorder


class RecordingHud(QDialog):
    """
    Compact, draggable, always-on-top HUD toolbar
    displayed during action sequence recording.
    """
    sig_recording_finished = pyqtSignal(list)  # List[Action]

    def __init__(self, target_hwnd: int = 0, parent=None):
        super().__init__(parent, Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.target_hwnd = target_hwnd
        self.drag_position = QPoint()

        self.recorder = ActionRecorder(target_hwnd=self.target_hwnd, parent=self)
        self.recorder.sig_action_recorded.connect(self._on_action_recorded)
        self.recorder.sig_recording_finished.connect(self._on_recorder_finished)
        self.recorder.sig_status_msg.connect(self._on_status_msg)

        self._init_ui()

        # Start recording immediately when HUD is shown
        self.recorder.start()

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)

        # Card container with shadow
        card = QFrame()
        card.setObjectName("recording_card")
        card.setStyleSheet("""
            QFrame#recording_card {
                background-color: #1e293b;
                border: 2px solid #ef4444;
                border-radius: 10px;
            }
            QLabel {
                color: #f8fafc;
            }
        """)

        # Drop shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 160))
        shadow.setOffset(0, 4)
        card.setGraphicsEffect(shadow)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)

        # 1. Header row (Draggable title + dot + counter)
        hdr_layout = QHBoxLayout()
        self.lbl_dot = QLabel("🔴")
        self.lbl_dot.setStyleSheet("font-size: 11pt;")
        hdr_layout.addWidget(self.lbl_dot)

        lbl_title = QLabel("조작 녹화 중 (타겟 창을 클릭하세요)")
        lbl_title.setStyleSheet("font-weight: bold; font-size: 9.5pt; color: #f8fafc;")
        hdr_layout.addWidget(lbl_title)

        hdr_layout.addStretch()

        self.lbl_count = QLabel("0개 기록됨")
        self.lbl_count.setStyleSheet(
            "background-color: #ef4444; color: white; font-weight: bold; "
            "padding: 2px 8px; border-radius: 4px; font-size: 8.5pt;"
        )
        hdr_layout.addWidget(self.lbl_count)
        layout.addLayout(hdr_layout)

        # 2. Last Action info label
        self.lbl_last_action = QLabel("타겟 창에서 마우스 클릭 또는 드래그를 수행하세요. (단축키: F9 종료)")
        self.lbl_last_action.setStyleSheet("color: #94a3b8; font-size: 8.5pt;")
        layout.addWidget(self.lbl_last_action)

        # 3. Action Buttons Row
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.btn_finish = QPushButton("⏹️ 녹화 완료 (F9)")
        self.btn_finish.setStyleSheet("""
            QPushButton {
                background-color: #16a34a;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 5px;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background-color: #15803d;
            }
        """)
        self.btn_finish.clicked.connect(self._finish_recording)
        btn_layout.addWidget(self.btn_finish)

        self.btn_add_delay = QPushButton("⏳ 1초 대기 삽입")
        self.btn_add_delay.setStyleSheet("""
            QPushButton {
                background-color: #334155;
                color: #e2e8f0;
                border: 1px solid #475569;
                border-radius: 5px;
                padding: 6px 10px;
            }
            QPushButton:hover {
                background-color: #475569;
            }
        """)
        self.btn_add_delay.clicked.connect(lambda: self.recorder.insert_delay(1.0))
        btn_layout.addWidget(self.btn_add_delay)

        self.btn_cancel = QPushButton("❌ 취소")
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #334155;
                color: #ef4444;
                border: 1px solid #475569;
                border-radius: 5px;
                padding: 6px 10px;
            }
            QPushButton:hover {
                background-color: #475569;
            }
        """)
        self.btn_cancel.clicked.connect(self._cancel_recording)
        btn_layout.addWidget(self.btn_cancel)

        layout.addLayout(btn_layout)
        root_layout.addWidget(card)

        # Blink timer for the red recording dot
        self.blink_state = True
        self.blink_timer = QTimer(self)
        self.blink_timer.setInterval(600)
        self.blink_timer.timeout.connect(self._toggle_blink)
        self.blink_timer.start()

        self.adjustSize()

    def _toggle_blink(self):
        self.blink_state = not self.blink_state
        self.lbl_dot.setText("🔴" if self.blink_state else "⭕")

    def _on_action_recorded(self, action: Action):
        cnt = len(self.recorder.recorded_actions)
        self.lbl_count.setText(f"{cnt}개 기록됨")
        self.lbl_last_action.setText(f"최근 기록: {action.get_summary()} ({action.delay_seconds:.1f}s)")

    def _on_status_msg(self, msg: str):
        self.lbl_last_action.setText(msg)

    def _finish_recording(self):
        self.recorder.stop_recording()
        self.recorder.wait()
        self.sig_recording_finished.emit(self.recorder.recorded_actions)
        self.accept()

    def _cancel_recording(self):
        self.recorder.stop_recording()
        self.recorder.wait()
        self.reject()

    def _on_recorder_finished(self, actions: List[Action]):
        self.sig_recording_finished.emit(actions)
        self.accept()

    # Drag window handling
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and not self.drag_position.isNull():
            self.move(event.globalPos() - self.drag_position)
            event.accept()
