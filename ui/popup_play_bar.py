"""
Popup Play Bar for FGOA.
A floating, always-on-top, draggable mini control bar featuring:
- Start, Pause, Stop, Single-step controls
- Status indicator and runner detail label
- Scenario Quick Preset buttons for fast single-click scenario playback
"""
from typing import List, Optional
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QComboBox, QScrollArea, QSizePolicy, QMenu, QAction
)
from PyQt5.QtCore import Qt, QPoint, pyqtSignal
from PyQt5.QtGui import QFont, QColor
from core.models import Scenario


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
        self._is_collapsed: bool = False
        self._scenarios: List[Scenario] = []
        self._runner_state: str = "stopped"  # "stopped", "running", "paused", "stepping"

        self._init_ui()
        self.resize(460, 160)

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

        self.lbl_drag_handle = QLabel("🎮 FGOA 플레이바")
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

        # Fold / Unfold toggle button
        self.btn_fold = QPushButton("▲")
        self.btn_fold.setFixedSize(22, 22)
        self.btn_fold.setToolTip("시나리오 프리셋 접기 / 펼치기")
        self.btn_fold.clicked.connect(self._toggle_collapse)
        hdr_layout.addWidget(self.btn_fold)

        # Close button
        btn_close = QPushButton("✕")
        btn_close.setFixedSize(22, 22)
        btn_close.setToolTip("플레이바 닫기 (메인 윈도우에서 다시 열 수 있습니다)")
        btn_close.clicked.connect(self.hide)
        hdr_layout.addWidget(btn_close)

        card_layout.addLayout(hdr_layout)

        # ----------------------------------------------------
        # 2. Main Playback Controls
        # ----------------------------------------------------
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setSpacing(6)

        self.btn_play = QPushButton("▶ 시작 (F5)")
        self.btn_play.setStyleSheet("""
            QPushButton {
                background-color: #166534;
                color: #dcfce7;
                font-weight: bold;
                border: 1px solid #22c55e;
                padding: 6px 12px;
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
        ctrl_layout.addWidget(self.btn_play)

        self.btn_pause = QPushButton("⏸ 일시정지")
        self.btn_pause.setStyleSheet("""
            QPushButton {
                background-color: #854d0e;
                color: #fef9c3;
                font-weight: bold;
                border: 1px solid #eab308;
                padding: 6px 10px;
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
        ctrl_layout.addWidget(self.btn_pause)

        self.btn_stop = QPushButton("⏹ 정지 (F6)")
        self.btn_stop.setStyleSheet("""
            QPushButton {
                background-color: #991b1b;
                color: #fee2e2;
                font-weight: bold;
                border: 1px solid #ef4444;
                padding: 6px 10px;
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
        ctrl_layout.addWidget(self.btn_stop)

        self.btn_step = QPushButton("⏭ 1스텝 (F7)")
        self.btn_step.setStyleSheet("""
            QPushButton {
                background-color: #075985;
                color: #e0f2fe;
                font-weight: bold;
                border: 1px solid #0284c7;
                padding: 6px 10px;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
            QPushButton:disabled {
                background-color: #0c3349;
                color: #386f91;
                border-color: #12425e;
            }
        """)
        self.btn_step.clicked.connect(self._on_step_clicked)
        ctrl_layout.addWidget(self.btn_step)

        card_layout.addLayout(ctrl_layout)

        # ----------------------------------------------------
        # 3. Status Detail Label
        # ----------------------------------------------------
        self.lbl_status_detail = QLabel("타겟 대기 중")
        self.lbl_status_detail.setStyleSheet("color: #9399b2; font-size: 8pt; padding: 1px 2px;")
        self.lbl_status_detail.setWordWrap(True)
        card_layout.addWidget(self.lbl_status_detail)

        # ----------------------------------------------------
        # 4. Scenario Quick Presets Section (Collapsible)
        # ----------------------------------------------------
        self.preset_section = QWidget()
        sec_layout = QVBoxLayout(self.preset_section)
        sec_layout.setContentsMargins(0, 4, 0, 0)
        sec_layout.setSpacing(4)

        preset_hdr = QHBoxLayout()
        lbl_preset_title = QLabel("⚡ 시나리오 프리셋 (클릭 시 즉시 실행):")
        lbl_preset_title.setStyleSheet("font-size: 8.5pt; font-weight: bold; color: #f9e2af;")
        preset_hdr.addWidget(lbl_preset_title)
        preset_hdr.addStretch()

        # Quick selector dropdown
        self.combo_presets = QComboBox()
        self.combo_presets.setStyleSheet("""
            QComboBox {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 8.5pt;
                min-width: 140px;
            }
            QComboBox QAbstractItemView {
                background-color: #1e1e2e;
                color: #cdd6f4;
                selection-background-color: #45475a;
            }
        """)
        preset_hdr.addWidget(self.combo_presets)

        btn_run_selected = QPushButton("▶")
        btn_run_selected.setToolTip("선택한 시나리오부터 실행")
        btn_run_selected.setFixedSize(24, 22)
        btn_run_selected.clicked.connect(self._on_run_selected_preset)
        preset_hdr.addWidget(btn_run_selected)

        sec_layout.addLayout(preset_hdr)

        # Scrollable horizontal chip buttons container
        self.scroll_presets = QScrollArea()
        self.scroll_presets.setWidgetResizable(True)
        self.scroll_presets.setFixedHeight(44)
        self.scroll_presets.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_presets.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_presets.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:horizontal {
                height: 4px;
                background: #181825;
            }
            QScrollBar::handle:horizontal {
                background: #45475a;
                border-radius: 2px;
            }
        """)

        self.preset_chips_widget = QWidget()
        self.preset_chips_layout = QHBoxLayout(self.preset_chips_widget)
        self.preset_chips_layout.setContentsMargins(0, 2, 0, 2)
        self.preset_chips_layout.setSpacing(5)
        self.preset_chips_layout.addStretch()
        self.scroll_presets.setWidget(self.preset_chips_widget)

        sec_layout.addWidget(self.scroll_presets)
        card_layout.addWidget(self.preset_section)

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
            self.move(event.globalPos() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    # ----------------------------------------------------
    # UI State & Actions
    # ----------------------------------------------------
    def _toggle_collapse(self):
        self._is_collapsed = not self._is_collapsed
        self.preset_section.setVisible(not self._is_collapsed)
        self.btn_fold.setText("▼" if self._is_collapsed else "▲")
        self.adjustSize()

    def _on_play_clicked(self):
        if self._runner_state == "paused":
            scen_id = self.combo_presets.currentData()
            self.sig_start_requested.emit(scen_id)
        else:
            self.sig_start_requested.emit(None)

    def _on_pause_clicked(self):
        self.sig_pause_requested.emit()

    def _on_stop_clicked(self):
        self.sig_stop_requested.emit()

    def _on_step_clicked(self):
        self.sig_step_requested.emit(None)

    def _on_run_selected_preset(self):
        scen_id = self.combo_presets.currentData()
        if scen_id:
            self.sig_start_requested.emit(scen_id)

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
            self.btn_pause.setText("⏸ 일시정지")
            self.btn_pause.setToolTip("오토 실행을 일시정지합니다.")
            self.btn_stop.setEnabled(True)
            self.btn_step.setEnabled(True)
            self.lbl_state_badge.setText("🟢 실행 중")
            self.lbl_state_badge.setStyleSheet("color: #a6e3a1; font-size: 8pt; background: #143521; padding: 2px 6px; border-radius: 4px; font-weight: bold;")
        elif state == "paused":
            self.btn_play.setEnabled(True)
            self.btn_play.setText("▶ 선택 노드 재개")
            self.btn_play.setToolTip("선택한 시나리오 노드부터 이어서 재개합니다.")
            self.btn_pause.setEnabled(True)
            self.btn_pause.setText("▶ 전역 재개")
            self.btn_pause.setToolTip("현재 멈춘 위치에서 전체 시나리오를 이어서 재개합니다.")
            self.btn_stop.setEnabled(True)
            self.btn_step.setEnabled(True)
            self.lbl_state_badge.setText("🟡 일시정지")
            self.lbl_state_badge.setStyleSheet("color: #f9e2af; font-size: 8pt; background: #3b2809; padding: 2px 6px; border-radius: 4px; font-weight: bold;")
        elif state == "stepping":
            self.btn_play.setEnabled(True)
            self.btn_play.setText("▶ 계속")
            self.btn_play.setToolTip("전체 연속 실행으로 전환합니다.")
            self.btn_pause.setEnabled(False)
            self.btn_stop.setEnabled(True)
            self.btn_step.setEnabled(True)
            self.lbl_state_badge.setText("🔵 1스텝")
            self.lbl_state_badge.setStyleSheet("color: #89b4fa; font-size: 8pt; background: #0c3349; padding: 2px 6px; border-radius: 4px; font-weight: bold;")
        else:  # "stopped"
            self.btn_play.setEnabled(True)
            self.btn_play.setText("▶ 시작 (F5)")
            self.btn_play.setToolTip("처음부터 순차적으로 실행합니다. (F5)")
            self.btn_pause.setEnabled(False)
            self.btn_pause.setText("⏸ 일시정지")
            self.btn_pause.setToolTip("실행 중일 때 일시정지합니다.")
            self.btn_stop.setEnabled(False)
            self.btn_step.setEnabled(True)
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
        """Populates scenario preset buttons and dropdown."""
        self._scenarios = scenarios

        # 1. Update dropdown
        cur_id = self.combo_presets.currentData()
        self.combo_presets.blockSignals(True)
        self.combo_presets.clear()
        for s in scenarios:
            prefix = "🔁 " if s.node_type.startswith("loop") else ""
            self.combo_presets.addItem(f"{prefix}s{s.scenario_number} {s.name}", s.id)
        if cur_id:
            idx = self.combo_presets.findData(cur_id)
            if idx >= 0:
                self.combo_presets.setCurrentIndex(idx)
        self.combo_presets.blockSignals(False)

        # 2. Rebuild chip buttons in scroll area
        # Clear existing layout items
        while self.preset_chips_layout.count() > 0:
            item = self.preset_chips_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        for s in scenarios:
            btn = QPushButton(f"s{s.scenario_number} {s.name}")
            btn.setToolTip(f"클릭: s{s.scenario_number}부터 즉시 시작\n우클릭: 상세 메뉴 (1스텝 실행 등)")
            
            # Subtle styling for chips
            if s.node_type == "loop_start":
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #2e304f;
                        color: #cba6f7;
                        border: 1px solid #74c7ec;
                        border-radius: 4px;
                        padding: 3px 8px;
                        font-size: 8.5pt;
                    }
                    QPushButton:hover {
                        background-color: #3e426f;
                    }
                """)
            elif s.node_type == "loop_end":
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #252636;
                        color: #a6adc8;
                        border: 1px dashed #6c7086;
                        border-radius: 4px;
                        padding: 3px 8px;
                        font-size: 8.5pt;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #313244;
                        color: #cdd6f4;
                        border: 1px solid #45475a;
                        border-radius: 4px;
                        padding: 3px 8px;
                        font-size: 8.5pt;
                    }
                    QPushButton:hover {
                        background-color: #45475a;
                        border-color: #89b4fa;
                    }
                """)

            # Connect left click to run from this scenario
            scen_id = s.id
            btn.clicked.connect(lambda checked, sid=scen_id: self.sig_start_requested.emit(sid))
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(lambda pos, b=btn, sid=scen_id: self._show_chip_context_menu(b, pos, sid))
            self.preset_chips_layout.addWidget(btn)

        self.preset_chips_layout.addStretch()

    def _show_chip_context_menu(self, button: QPushButton, pos: QPoint, scenario_id: str):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1e1e2e;
                color: #cdd6f4;
                border: 1px solid #45475a;
            }
            QMenu::item:selected {
                background-color: #45475a;
            }
        """)

        act_run = menu.addAction("▶ 이 시나리오부터 시작")
        act_run.triggered.connect(lambda: self.sig_start_requested.emit(scenario_id))

        act_step = menu.addAction("⏭ 이 시나리오 1스텝 실행")
        act_step.triggered.connect(lambda: self.sig_step_requested.emit(scenario_id))

        act_select = menu.addAction("🔍 편집기에서 선택")
        act_select.triggered.connect(lambda: self.sig_select_scenario_requested.emit(scenario_id))

        menu.exec_(button.mapToGlobal(pos))
