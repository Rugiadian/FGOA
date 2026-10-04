"""
Popup Play Bar for FGOA.
A floating, always-on-top, draggable mini control bar featuring:
- Start, Pause, Stop, Single-step controls
- Status indicator and runner detail label
- Scenario Quick Preset buttons for fast single-click scenario playback
"""
from typing import List, Optional, Tuple
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QComboBox, QScrollArea, QSizePolicy, QMenu, QAction, QApplication
)
from PyQt5.QtCore import Qt, QPoint, QRect, pyqtSignal
from PyQt5.QtGui import QFont, QColor
import win32gui
from core.models import Scenario


def calculate_playbar_target_position(
    target_rect: Tuple[int, int, int, int],
    screen_rect: Tuple[int, int, int, int],
    bar_size: Tuple[int, int]
) -> Tuple[int, int]:
    """
    Calculates play bar position (x, y) relative to target window:
    1. Initial position: bottom of target window, not covering target app.
    2. If bottom position overflows monitor screen boundary, place on top of target window.
    3. If target window is too large and both top and bottom overflow screen,
       place overlapping on top-left of target window.
    """
    t_left, t_top, t_right, t_bottom = target_rect
    s_left, s_top, s_right, s_bottom = screen_rect
    bar_w, bar_h = bar_size

    # Candidate 1: Bottom placement (just below target window)
    cand_bottom_y = t_bottom
    bottom_overflow = (cand_bottom_y + bar_h > s_bottom)

    # Candidate 2: Top placement (just above target window)
    cand_top_y = t_top - bar_h
    top_overflow = (cand_top_y < s_top)

    if not bottom_overflow:
        # Case 1: Bottom placement
        pos_y = cand_bottom_y
        pos_x = t_left
    elif not top_overflow:
        # Case 2: Top placement
        pos_y = cand_top_y
        pos_x = t_left
    else:
        # Case 3: Both overflow -> Overlap on top-left of target window
        pos_x = t_left
        pos_y = t_top

    # Boundary safety clamp inside available screen area
    if pos_x + bar_w > s_right:
        pos_x = max(s_left, s_right - bar_w)
    if pos_x < s_left:
        pos_x = s_left

    if pos_y + bar_h > s_bottom:
        pos_y = max(s_top, s_bottom - bar_h)
    if pos_y < s_top:
        pos_y = s_top

    return pos_x, pos_y


class PopupPlayBar(QWidget):
    """
    Floating, always-on-top, draggable mini play bar.
    Provides execution controls and dynamic scenario preset quick-launch buttons.
    """
    # Signals emitted to parent / controller
    sig_start_requested = pyqtSignal(object)       # Optional[str] scenario_id
    sig_pause_requested = pyqtSignal()
    sig_stop_requested = pyqtSignal()
    sig_step_requested = pyqtSignal(object)        # Optional[str] scenario_id
    sig_select_scenario_requested = pyqtSignal(str) # scenario_id

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.Window
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._drag_pos: Optional[QPoint] = None
        self._user_moved: bool = False
        self.target_hwnd: int = 0
        self._is_collapsed: bool = False
        self._scenarios: List[Scenario] = []
        self._runner_state: str = "stopped"  # "stopped", "running", "paused", "stepping"

        self._init_ui()
        self.resize(320, 100)

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(6, 6, 6, 6)
        root_layout.setSpacing(0)

        # Main background container frame
        self.card = QFrame()
        self.card.setObjectName("playbar_card")
        self.card.setStyleSheet("""
            QFrame#playbar_card {
                background-color: #1e1e2e;
                border: 1px solid #434461;
                border-radius: 10px;
            }
            QLabel {
                color: #cdd6f4;
            }
            QPushButton {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #45475a;
                border-color: #585b70;
            }
            QPushButton:pressed {
                background-color: #585b70;
            }
            QPushButton:disabled {
                background-color: #181825;
                color: #6c7086;
                border-color: #313244;
            }
        """)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(10, 8, 10, 8)
        card_layout.setSpacing(6)

        # ----------------------------------------------------
        # 1. Header (Draggable Title & Controls)
        # ----------------------------------------------------
        hdr_layout = QHBoxLayout()
        hdr_layout.setSpacing(6)

        self.lbl_drag_handle = QLabel("🎮 FGOA")
        font_hdr = QFont()
        font_hdr.setBold(True)
        font_hdr.setPointSize(9)
        self.lbl_drag_handle.setFont(font_hdr)
        self.lbl_drag_handle.setStyleSheet("color: #89b4fa; font-weight: bold;")
        hdr_layout.addWidget(self.lbl_drag_handle)

        self.lbl_state_badge = QLabel("⚪ 대기 중")
        self.lbl_state_badge.setStyleSheet("color: #a6adc8; font-size: 8pt; background: #313244; padding: 2px 6px; border-radius: 4px;")
        hdr_layout.addWidget(self.lbl_state_badge)

        hdr_layout.addStretch()

        # Close button
        btn_close = QPushButton("✕")
        btn_close.setFixedSize(22, 22)
        btn_close.setToolTip("플레이바 닫기 (메인 윈도우에서 다시 열 수 있습니다)")
        btn_close.clicked.connect(self.hide)
        hdr_layout.addWidget(btn_close)

        card_layout.addLayout(hdr_layout)

        # ----------------------------------------------------
        # 2. Main Playback Controls: 재생, 일시 정지, 정지
        # ----------------------------------------------------
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setSpacing(6)

        self.btn_play = QPushButton("▶ 재생 (F5)")
        self.btn_play.setStyleSheet("""
            QPushButton {
                background-color: #166534;
                color: #dcfce7;
                font-weight: bold;
                border: 1px solid #22c55e;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background-color: #15803d;
            }
            QPushButton:disabled {
                background-color: #143521;
                color: #4ade80;
                border-color: #166534;
            }
        """)
        self.btn_play.clicked.connect(self._on_play_clicked)
        ctrl_layout.addWidget(self.btn_play, 1)

        self.btn_pause = QPushButton("⏸ 일시 정지")
        self.btn_pause.setStyleSheet("""
            QPushButton {
                background-color: #854d0e;
                color: #fef9c3;
                font-weight: bold;
                border: 1px solid #eab308;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #a16207;
            }
            QPushButton:disabled {
                background-color: #3b2809;
                color: #715525;
                border-color: #4a350d;
            }
        """)
        self.btn_pause.setEnabled(False)
        self.btn_pause.clicked.connect(self._on_pause_clicked)
        ctrl_layout.addWidget(self.btn_pause, 1)

        self.btn_stop = QPushButton("⏹ 정지 (F6)")
        self.btn_stop.setStyleSheet("""
            QPushButton {
                background-color: #991b1b;
                color: #fee2e2;
                font-weight: bold;
                border: 1px solid #ef4444;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #b91c1c;
            }
            QPushButton:disabled {
                background-color: #451313;
                color: #7f2e2e;
                border-color: #581c1c;
            }
        """)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._on_stop_clicked)
        ctrl_layout.addWidget(self.btn_stop, 1)

        card_layout.addLayout(ctrl_layout)

        # ----------------------------------------------------
        # 3. Status Detail Label
        # ----------------------------------------------------
        self.lbl_status_detail = QLabel("타겟 대기 중")
        self.lbl_status_detail.setStyleSheet("color: #9399b2; font-size: 8pt; padding: 1px 2px;")
        self.lbl_status_detail.setWordWrap(True)
        card_layout.addWidget(self.lbl_status_detail)

        root_layout.addWidget(self.card)

    # ----------------------------------------------------
    # Drag & Move Event Overrides
    # ----------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self._user_moved = True
            self.move(event.globalPos() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._user_moved = False
            self.position_relative_to_target(force=True)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def set_target_hwnd(self, hwnd: int):
        """Updates target window handle and resets position lock if target changed."""
        if self.target_hwnd != hwnd:
            self.target_hwnd = hwnd
            self._user_moved = False
            if self.isVisible():
                self.position_relative_to_target(force=True)

    def position_relative_to_target(
        self,
        target_hwnd: Optional[int] = None,
        fallback_geo: Optional[QRect] = None,
        force: bool = False
    ):
        """
        Positions play bar relative to the target window according to placement rules:
        1. Default initial position: below the target app window (not covering it).
        2. If bottom placement overflows monitor screen boundary, place on top.
        3. If target window is too large and both top/bottom overflow, place overlapping on top-left.
        """
        if self._user_moved and not force:
            return

        if target_hwnd is not None:
            if self.target_hwnd != target_hwnd:
                self.target_hwnd = target_hwnd
                self._user_moved = False

        hwnd = self.target_hwnd
        target_rect = None

        if hwnd and win32gui.IsWindow(hwnd) and not win32gui.IsIconic(hwnd):
            try:
                rect = win32gui.GetWindowRect(hwnd)
                # rect is (left, top, right, bottom)
                if (rect[2] - rect[0] > 50) and (rect[3] - rect[1] > 50):
                    target_rect = rect
            except Exception:
                target_rect = None

        self.adjustSize()
        bar_w = self.width()
        bar_h = self.height()
        if bar_w <= 0 or bar_h <= 0:
            hint = self.sizeHint()
            bar_w = max(bar_w, hint.width(), 320)
            bar_h = max(bar_h, hint.height(), 100)

        if target_rect:
            t_left, t_top, t_right, t_bottom = target_rect
            center_x = (t_left + t_right) // 2
            center_y = (t_top + t_bottom) // 2
            screen = QApplication.screenAt(QPoint(center_x, center_y))
            if not screen:
                screen = QApplication.screenAt(QPoint(t_left, t_top))
            if not screen:
                screen = QApplication.primaryScreen()

            if screen:
                ag = screen.availableGeometry()
                s_rect = (ag.x(), ag.y(), ag.x() + ag.width(), ag.y() + ag.height())
            else:
                s_rect = (0, 0, 1920, 1080)

            pos_x, pos_y = calculate_playbar_target_position(
                target_rect=target_rect,
                screen_rect=s_rect,
                bar_size=(bar_w, bar_h)
            )
            self.move(pos_x, pos_y)
        else:
            if fallback_geo:
                self.move(
                    max(0, fallback_geo.x() + fallback_geo.width() - 480),
                    max(0, fallback_geo.y() + 60)
                )
            else:
                self.move(100, 100)


    # ----------------------------------------------------
    # ----------------------------------------------------
    # UI State & Actions
    # ----------------------------------------------------
    def _toggle_collapse(self):
        pass

    def _on_play_clicked(self):
        self.sig_start_requested.emit(None)

    def _on_pause_clicked(self):
        self.sig_pause_requested.emit()

    def _on_stop_clicked(self):
        self.sig_stop_requested.emit()

    def _on_step_clicked(self):
        self.sig_step_requested.emit(None)

    def _on_run_selected_preset(self):
        pass

    # ----------------------------------------------------
    # External Controller Synchronization
    # ----------------------------------------------------
    def set_runner_state(self, state: str, detail_text: str = ""):
        """
        Updates the play bar buttons and badge according to the runner's lifecycle:
        'running', 'paused', 'stopped', 'stepping'
        """
        self._runner_state = state
        self.lbl_status_detail.setStyleSheet("color: #9399b2; font-size: 8pt; padding: 1px 2px;")

        if state == "running":
            self.btn_play.setEnabled(False)
            self.btn_play.setText("▶ 실행 중")
            self.btn_play.setToolTip("오토가 실행 중입니다.")
            self.btn_pause.setEnabled(True)
            self.btn_pause.setText("⏸ 일시 정지")
            self.btn_pause.setToolTip("오토 실행을 일시정지합니다.")
            self.btn_stop.setEnabled(True)
            self.lbl_state_badge.setText("🟢 실행 중")
            self.lbl_state_badge.setStyleSheet("color: #a6e3a1; font-size: 8pt; background: #143521; padding: 2px 6px; border-radius: 4px; font-weight: bold;")
        elif state == "paused":
            self.btn_play.setEnabled(True)
            self.btn_play.setText("▶ 재개")
            self.btn_play.setToolTip("일시정지된 위치부터 실행을 재개합니다.")
            self.btn_pause.setEnabled(False)
            self.btn_pause.setText("⏸ 일시 정지")
            self.btn_stop.setEnabled(True)
            self.lbl_state_badge.setText("🟡 일시정지")
            self.lbl_state_badge.setStyleSheet("color: #f9e2af; font-size: 8pt; background: #3b2809; padding: 2px 6px; border-radius: 4px; font-weight: bold;")
        elif state == "stepping":
            self.btn_play.setEnabled(True)
            self.btn_play.setText("▶ 계속")
            self.btn_play.setToolTip("연속 실행으로 전환합니다.")
            self.btn_pause.setEnabled(False)
            self.btn_stop.setEnabled(True)
            self.lbl_state_badge.setText("🔵 1스텝")
            self.lbl_state_badge.setStyleSheet("color: #89b4fa; font-size: 8pt; background: #0c3349; padding: 2px 6px; border-radius: 4px; font-weight: bold;")
        else:  # "stopped"
            self.btn_play.setEnabled(True)
            self.btn_play.setText("▶ 재생 (F5)")
            self.btn_play.setToolTip("처음부터 순차적으로 실행합니다. (F5)")
            self.btn_pause.setEnabled(False)
            self.btn_pause.setText("⏸ 일시 정지")
            self.btn_pause.setToolTip("실행 중일 때 일시정지합니다.")
            self.btn_stop.setEnabled(False)
            self.lbl_state_badge.setText("⚪ 대기 중")
            self.lbl_state_badge.setStyleSheet("color: #a6adc8; font-size: 8pt; background: #313244; padding: 2px 6px; border-radius: 4px;")

        if detail_text:
            self._current_scenario_text = detail_text
            self.lbl_status_detail.setText(detail_text)

    def set_action_status(self, action, index: int, total: int, scenario_info: str = ""):
        """Displays real-time action sequence execution progress in playbar status label."""
        prefix = f"{scenario_info} ▶ " if scenario_info else (f"{self._current_scenario_text} ▶ " if getattr(self, "_current_scenario_text", "") else "")
        act_type = getattr(action, "action_type", "")
        if act_type == "mouse_click":
            desc = f"#{index}/{total} 🖱️ 클릭 ({action.x}, {action.y})"
        elif act_type == "mouse_drag":
            desc = f"#{index}/{total} ↔️ 드래그 ({action.x}, {action.y})➔({action.end_x}, {action.end_y})"
        elif act_type == "delay":
            desc = f"#{index}/{total} ⏱️ {action.delay_seconds:.1f}초 대기 진행 중..."
        elif act_type == "key_press":
            desc = f"#{index}/{total} ⌨️ 키 입력 [{action.key_name}]"
        elif act_type == "text_type":
            desc = f"#{index}/{total} ✍️ 텍스트 입력 '{action.text_content}'"
        else:
            summary = action.get_summary() if hasattr(action, "get_summary") else ""
            desc = f"#{index}/{total} {summary}"

        self.lbl_status_detail.setText(f"{prefix}{desc}")
        self.lbl_status_detail.setStyleSheet("color: #74c7ec; font-size: 8.5pt; font-weight: bold; padding: 1px 2px;")

    def refresh_scenarios(self, scenarios: List[Scenario]):
        """Caches scenario list for runner reference."""
        self._scenarios = scenarios

    def _show_chip_context_menu(self, button: QPushButton, pos: QPoint, scenario_id: str):
        pass
