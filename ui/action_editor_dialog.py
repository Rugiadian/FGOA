"""
Action Sequence Editor Dialog for FGOA.
Allows editing mouse clicks, drags, delays, keystrokes, and text inputs for a scenario.
"""
import copy
import time
from typing import List, Optional, Any
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QSpinBox, QDoubleSpinBox, QLineEdit, QGroupBox, QMessageBox,
    QFormLayout, QApplication, QCheckBox, QButtonGroup, QGridLayout
)
from PyQt5.QtCore import Qt
from core.models import Action
from core.input_controller import InputController


class SingleActionDialog(QDialog):
    """Dialog to create or edit a single action."""

    def __init__(
        self,
        action: Optional[Action] = None,
        target_hwnd: int = 0,
        reference_image_path: Optional[str] = None,
        scenario: Optional[Any] = None,
        parent=None
    ):
        super().__init__(parent)
        self.setWindowTitle("액션 속성 설정")
        self.resize(520, 520)
        self.action = copy.deepcopy(action) if action else Action()
        self.target_hwnd = target_hwnd
        self.reference_image_path = reference_image_path
        self.scenario = scenario
        self.type_buttons = {}
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # 1. Action Type: Exposed as visible buttons instead of dropdown scroll menu
        grp_type = QGroupBox("📌 액션 유형 선택")
        type_grid = QGridLayout(grp_type)
        type_grid.setSpacing(6)

        self.btn_group_type = QButtonGroup(self)
        self.btn_group_type.setExclusive(True)

        action_types_def = [
            ("mouse_click", "🖱️ 클릭", 0, 0),
            ("mouse_drag", "↔️ 드래그", 0, 1),
            ("key_press", "⌨️ 키 입력", 0, 2),
            ("text_type", "📝 텍스트", 0, 3),
            ("delay", "⏳ 정밀 대기", 1, 0),
            ("sound_beep", "🔔 비프음", 1, 1),
            ("log_message", "📋 로그", 1, 2),
        ]

        btn_style = """
            QPushButton {
                padding: 7px 10px;
                font-size: 9.5pt;
                font-weight: 500;
                border: 1px solid #cbd5e1;
                border-radius: 5px;
                background-color: #f8fafc;
                color: #1e293b;
                min-height: 28px;
            }
            QPushButton:hover {
                background-color: #e2e8f0;
                border-color: #94a3b8;
            }
            QPushButton:checked {
                background-color: #2563eb;
                color: #ffffff;
                font-weight: bold;
                border: 1px solid #1d4ed8;
            }
        """

        cur_type = self.action.action_type or "mouse_click"
        for t_code, t_label, r, c in action_types_def:
            btn = QPushButton(t_label)
            btn.setCheckable(True)
            btn.setStyleSheet(btn_style)
            if t_code == cur_type:
                btn.setChecked(True)
            btn.clicked.connect(lambda checked, tc=t_code: self._on_type_button_clicked(tc))
            self.btn_group_type.addButton(btn)
            self.type_buttons[t_code] = btn
            type_grid.addWidget(btn, r, c)

        layout.addWidget(grp_type)

        # 2. Dynamic containers in form
        form = QFormLayout()
        form.setSpacing(10)

        # 1. Mouse Click fields
        self.grp_click = QGroupBox("마우스 클릭 설정")
        l_click = QFormLayout(self.grp_click)
        self.combo_btn = QComboBox()
        self.combo_btn.addItems(["좌클릭 (Left)", "우클릭 (Right)", "휠클릭 (Middle)"])
        self.combo_btn.setCurrentIndex({"left": 0, "right": 1, "middle": 2}.get(self.action.mouse_button, 0))

        self.combo_click_type = QComboBox()
        self.combo_click_type.addItems(["단일 클릭 (Single)", "더블 클릭 (Double)"])
        self.combo_click_type.setCurrentIndex(1 if self.action.click_type == "double" else 0)

        coord_layout = QHBoxLayout()
        self.spin_x = QSpinBox()
        self.spin_x.setRange(-9999, 9999)
        self.spin_x.setValue(self.action.x)
        self.spin_y = QSpinBox()
        self.spin_y.setRange(-9999, 9999)
        self.spin_y.setValue(self.action.y)
        coord_layout.addWidget(QLabel("X:"))
        coord_layout.addWidget(self.spin_x)
        coord_layout.addWidget(QLabel("Y:"))
        coord_layout.addWidget(self.spin_y)

        btn_pick_click = QPushButton("🎯 레퍼런스로 지정...")
        btn_pick_click.setToolTip("레퍼런스 이미지 또는 게임 화면에서 클릭 위치를 직접 선택합니다.")
        btn_pick_click.clicked.connect(lambda: self._on_pick_coordinates_from_image(drag_mode=False))
        coord_layout.addWidget(btn_pick_click)

        self.spin_repeat = QSpinBox()
        self.spin_repeat.setRange(1, 100)
        self.spin_repeat.setValue(self.action.repeat_count)

        l_click.addRow("버튼:", self.combo_btn)
        l_click.addRow("클릭 모드:", self.combo_click_type)
        l_click.addRow("상대 좌표:", coord_layout)
        l_click.addRow("반복 횟수:", self.spin_repeat)
        form.addRow(self.grp_click)

        # 2. Mouse Drag fields
        self.grp_drag = QGroupBox("드래그 앤 드롭 설정")
        l_drag = QFormLayout(self.grp_drag)
        self.spin_end_x = QSpinBox()
        self.spin_end_x.setRange(-9999, 9999)
        self.spin_end_x.setValue(self.action.end_x)
        self.spin_end_y = QSpinBox()
        self.spin_end_y.setRange(-9999, 9999)
        self.spin_end_y.setValue(self.action.end_y)
        end_layout = QHBoxLayout()
        end_layout.addWidget(QLabel("끝 X:"))
        end_layout.addWidget(self.spin_end_x)
        end_layout.addWidget(QLabel("끝 Y:"))
        end_layout.addWidget(self.spin_end_y)

        btn_pick_drag = QPushButton("🎯 레퍼런스로 시작/끝 지정...")
        btn_pick_drag.setToolTip("레퍼런스 이미지 또는 게임 화면에서 드래그 시작점과 종료점을 선택합니다.")
        btn_pick_drag.clicked.connect(lambda: self._on_pick_coordinates_from_image(drag_mode=True))
        end_layout.addWidget(btn_pick_drag)

        self.spin_drag_duration = QSpinBox()
        self.spin_drag_duration.setRange(50, 10000)
        self.spin_drag_duration.setValue(self.action.drag_duration_ms)
        self.spin_drag_duration.setSuffix(" ms")

        l_drag.addRow("종료 상대 좌표:", end_layout)
        l_drag.addRow("이동 시간:", self.spin_drag_duration)
        form.addRow(self.grp_drag)

        # 3. Keyboard fields
        self.grp_key = QGroupBox("키보드 입력 설정")
        l_key = QFormLayout(self.grp_key)
        self.txt_key = QLineEdit(self.action.key)
        self.combo_modifiers = QComboBox()
        self.combo_modifiers.addItems(["(없음)", "Ctrl", "Alt", "Shift", "Ctrl + Alt", "Ctrl + Shift"])
        if "Ctrl" in self.action.modifiers and "Alt" in self.action.modifiers:
            self.combo_modifiers.setCurrentIndex(4)
        elif "Ctrl" in self.action.modifiers:
            self.combo_modifiers.setCurrentIndex(1)
        elif "Alt" in self.action.modifiers:
            self.combo_modifiers.setCurrentIndex(2)
        elif "Shift" in self.action.modifiers:
            self.combo_modifiers.setCurrentIndex(3)

        l_key.addRow("주요 키 (예: Enter, Space, Esc, 1, A):", self.txt_key)
        l_key.addRow("조합 키 (Modifier):", self.combo_modifiers)
        form.addRow(self.grp_key)

        # 4. Text Type fields
        self.grp_text = QGroupBox("텍스트 입력 설정")
        l_text = QFormLayout(self.grp_text)
        self.txt_content = QLineEdit(self.action.text)
        l_text.addRow("입력할 문자열:", self.txt_content)
        form.addRow(self.grp_text)

        # 5. Delay fields: 누르기 쉬운 큰 -/+ 버튼 (0.5초, 1초 단위 제공)
        self.grp_delay = QGroupBox("⏳ 대기 시간 설정 (초)")
        v_delay = QVBoxLayout(self.grp_delay)
        v_delay.setSpacing(6)

        delay_btn_layout = QHBoxLayout()
        delay_btn_layout.setSpacing(6)

        btn_sub_1s = QPushButton("-1.0초")
        btn_sub_1s.setToolTip("1.0초 감소")
        btn_sub_1s.setStyleSheet("height: 36px; min-width: 60px; font-weight: bold; font-size: 10pt; color: #dc2626; background: #fef2f2; border: 1px solid #fca5a5; border-radius: 4px;")
        btn_sub_1s.clicked.connect(lambda: self._adjust_delay(-1.0))
        delay_btn_layout.addWidget(btn_sub_1s)

        btn_sub_05s = QPushButton("-0.5초")
        btn_sub_05s.setToolTip("0.5초 감소")
        btn_sub_05s.setStyleSheet("height: 36px; min-width: 60px; font-weight: bold; font-size: 10pt; color: #ea580c; background: #fff7ed; border: 1px solid #fdba74; border-radius: 4px;")
        btn_sub_05s.clicked.connect(lambda: self._adjust_delay(-0.5))
        delay_btn_layout.addWidget(btn_sub_05s)

        self.spin_delay = QDoubleSpinBox()
        self.spin_delay.setRange(0.0, 3600.0)
        self.spin_delay.setSingleStep(0.1)
        self.spin_delay.setDecimals(2)
        self.spin_delay.setValue(self.action.delay_seconds)
        self.spin_delay.setSuffix(" 초")
        self.spin_delay.setAlignment(Qt.AlignCenter)
        self.spin_delay.setStyleSheet("height: 36px; font-size: 11pt; font-weight: bold;")
        delay_btn_layout.addWidget(self.spin_delay, 1)

        btn_add_05s = QPushButton("+0.5초")
        btn_add_05s.setToolTip("0.5초 증가")
        btn_add_05s.setStyleSheet("height: 36px; min-width: 60px; font-weight: bold; font-size: 10pt; color: #16a34a; background: #f0fdf4; border: 1px solid #86efac; border-radius: 4px;")
        btn_add_05s.clicked.connect(lambda: self._adjust_delay(+0.5))
        delay_btn_layout.addWidget(btn_add_05s)

        btn_add_1s = QPushButton("+1.0초")
        btn_add_1s.setToolTip("1.0초 증가")
        btn_add_1s.setStyleSheet("height: 36px; min-width: 60px; font-weight: bold; font-size: 10pt; color: #15803d; background: #dcfce7; border: 1px solid #4ade80; border-radius: 4px;")
        btn_add_1s.clicked.connect(lambda: self._adjust_delay(+1.0))
        delay_btn_layout.addWidget(btn_add_1s)

        v_delay.addLayout(delay_btn_layout)
        form.addRow(self.grp_delay)

        # 6. Log Message fields (for log_message action type)
        self.grp_log = QGroupBox("로그 메시지 설정")
        l_log = QFormLayout(self.grp_log)
        self.txt_log = QLineEdit(self.action.log_text)
        self.txt_log.setPlaceholderText("출력할 로그 문장 입력 (예: 보구 사용 시작)")
        l_log.addRow("로그 문장:", self.txt_log)
        form.addRow(self.grp_log)

        # 7. Custom log output option: 활성화 체크 안해도 바로 입력 가능, 비어있으면 자동 오프
        self.grp_custom_log = QGroupBox("💬 액션 로그 출력 옵션")
        l_cl = QVBoxLayout(self.grp_custom_log)
        l_cl.setSpacing(4)
        lbl_cl_desc = QLabel("로그 문장 (비워두면 자동 꺼짐 / 입력 시 자동 활성화):")
        lbl_cl_desc.setStyleSheet("color: #475569; font-size: 8.5pt;")
        self.txt_custom_log = QLineEdit(getattr(self.action, "custom_log", ""))
        self.txt_custom_log.setPlaceholderText("원하는 로그 문장을 입력하세요 (예: 1라운드 스킬 발동, 비워두면 출력 안 함)")
        self.txt_custom_log.setEnabled(True)
        l_cl.addWidget(lbl_cl_desc)
        l_cl.addWidget(self.txt_custom_log)
        form.addRow(self.grp_custom_log)

        # 8. Coordinate anti-ban options (for mouse_click & mouse_drag)
        self.grp_coord_antiban = QGroupBox("🎯 안티밴: 좌표 설정")
        l_cab = QFormLayout(self.grp_coord_antiban)
        self.combo_coord_antiban = QComboBox()
        self.combo_coord_antiban.addItem("오프셋 약 (기본값)", "weak")
        self.combo_coord_antiban.addItem("오프셋 강", "strong")
        self.combo_coord_antiban.addItem("해제 (좌표 고정)", "none")

        cur_mode = getattr(self.action, "coord_anti_ban", "weak")
        idx_cab = self.combo_coord_antiban.findData(cur_mode)
        self.combo_coord_antiban.setCurrentIndex(idx_cab if idx_cab >= 0 else 0)
        self.combo_coord_antiban.setToolTip(
            "이 액션 실행 시 마우스 좌표에 무작위 오프셋을 적용합니다.\n"
            "- 오프셋 약: 좁은 오차 범위 분산 (기본값, 버튼 클릭용)\n"
            "- 오프셋 강: 넓은 오차 범위 분산 (넓은 영역 클릭용)\n"
            "- 해제: 오프셋 없이 지정한 좌표 정확히 클릭\n"
            "* 약/강의 세부 픽셀 수치는 시나리오 재생 창(전역 옵션)에서 조절합니다."
        )
        l_cab.addRow("좌표 오프셋 강도:", self.combo_coord_antiban)
        form.addRow(self.grp_coord_antiban)

        layout.addLayout(form)
        self._update_visibility()

        # Dialog buttons
        btns = QHBoxLayout()
        btns.addStretch()
        btn_cancel = QPushButton("취소")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("확인")
        btn_ok.setStyleSheet("background-color: #1b5e20; color: white; font-weight: bold; padding: 6px 16px;")
        btn_ok.clicked.connect(self._on_ok)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        layout.addLayout(btns)

    def _adjust_delay(self, delta: float):
        """Adjusts delay seconds by delta and clamps to [0.0, 3600.0]."""
        cur = self.spin_delay.value()
        new_val = max(0.0, min(3600.0, round(cur + delta, 2)))
        self.spin_delay.setValue(new_val)

    def _on_type_button_clicked(self, action_type: str):
        """Handles action type button click."""
        self.action.action_type = action_type
        self._update_visibility()

    def _update_visibility(self):
        current_type = self.action.action_type
        self.grp_click.setVisible(current_type in ("mouse_click", "mouse_drag"))
        self.grp_drag.setVisible(current_type == "mouse_drag")
        self.grp_key.setVisible(current_type == "key_press")
        self.grp_text.setVisible(current_type == "text_type")
        self.grp_log.setVisible(current_type == "log_message")
        self.grp_custom_log.setVisible(current_type != "log_message")
        self.grp_coord_antiban.setVisible(current_type in ("mouse_click", "mouse_drag"))

        # 대기 시간 설정: delay 액션일 때는 주 대기 시간, 기타 액션일 때는 실행 후 대기 시간으로 항상 제공
        if current_type == "delay":
            self.grp_delay.setTitle("⏳ 정밀 대기 시간 설정 (초)")
        else:
            self.grp_delay.setTitle("⏳ 액션 실행 후 대기 시간 (초)")
        self.grp_delay.setVisible(True)

    def _on_ok(self):
        # Action type is already set via type button
        if self.action.action_type in ("mouse_click", "mouse_drag"):
            self.action.x = self.spin_x.value()
            self.action.y = self.spin_y.value()
            btn_map = {0: "left", 1: "right", 2: "middle"}
            self.action.mouse_button = btn_map.get(self.combo_btn.currentIndex(), "left")
            self.action.click_type = "double" if self.combo_click_type.currentIndex() == 1 else "single"
            self.action.repeat_count = self.spin_repeat.value()
            self.action.coord_anti_ban = self.combo_coord_antiban.currentData()

        if self.action.action_type == "mouse_drag":
            self.action.end_x = self.spin_end_x.value()
            self.action.end_y = self.spin_end_y.value()
            self.action.drag_duration_ms = self.spin_drag_duration.value()

        elif self.action.action_type == "key_press":
            self.action.key = self.txt_key.text().strip()
            mod_idx = self.combo_modifiers.currentIndex()
            mod_map = {0: [], 1: ["Ctrl"], 2: ["Alt"], 3: ["Shift"], 4: ["Ctrl", "Alt"], 5: ["Ctrl", "Shift"]}
            self.action.modifiers = mod_map.get(mod_idx, [])

        elif self.action.action_type == "text_type":
            self.action.text = self.txt_content.text()

        elif self.action.action_type == "log_message":
            self.action.log_text = self.txt_log.text().strip()

        # 대기 시간: 모든 액션에서 설정된 값 저장
        self.action.delay_seconds = self.spin_delay.value()

        # 커스텀 로그: 비어있으면 자동으로 "" (Off로 인식)
        self.action.custom_log = self.txt_custom_log.text().strip()

        self.accept()

    def _on_pick_coordinates_from_image(self, drag_mode: bool = False):
        """Open CoordinatePickerDialog to pick coordinates interactively."""
        from ui.coordinate_picker_dialog import CoordinatePickerDialog
        ref_path = self.reference_image_path
        if not ref_path and hasattr(self, "scenario") and self.scenario:
            ref_path = getattr(self.scenario, "last_action_image_path", None) or (
                self.scenario.condition.reference_image_path if self.scenario.condition else None
            ) or CoordinatePickerDialog.get_last_used_image_path()
        elif not ref_path:
            ref_path = CoordinatePickerDialog.get_last_used_image_path()

        dlg = CoordinatePickerDialog(
            image_path=ref_path,
            target_hwnd=self.target_hwnd,
            initial_x=self.spin_x.value(),
            initial_y=self.spin_y.value(),
            drag_mode=drag_mode,
            initial_end_x=self.spin_end_x.value() if drag_mode else 0,
            initial_end_y=self.spin_end_y.value() if drag_mode else 0,
            scenario=getattr(self, "scenario", None),
            parent=self
        )
        if dlg.exec_() == CoordinatePickerDialog.Accepted:
            if dlg.current_image_path:
                self.reference_image_path = dlg.current_image_path
                CoordinatePickerDialog.set_last_used_image_path(dlg.current_image_path)
                if hasattr(self, "scenario") and self.scenario:
                    self.scenario.last_action_image_path = dlg.current_image_path
            x, y, ex, ey = dlg.get_coordinates()
            self.spin_x.setValue(x)
            self.spin_y.setValue(y)
            if drag_mode:
                self.spin_end_x.setValue(ex)
                self.spin_end_y.setValue(ey)

    def get_action(self) -> Action:
        """Returns the edited Action instance."""
        return self.action


class ActionEditorDialog(QDialog):
    """Sequence Editor for Scenario Actions."""

    def __init__(
        self,
        actions: List[Action],
        target_hwnd: int,
        reference_image_path: Optional[str] = None,
        scenario: Optional[Any] = None,
        parent=None
    ):
        super().__init__(parent)
        self.setWindowTitle("액션 시퀀스 편집기")
        self.resize(680, 520)
        self.actions = [copy.deepcopy(a) for a in actions]
        self.target_hwnd = target_hwnd
        self.reference_image_path = reference_image_path
        self.scenario = scenario

        self._init_ui()
        self._refresh_table()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Action Table
        self.tbl_actions = QTableWidget()
        self.tbl_actions.setColumnCount(4)
        self.tbl_actions.setHorizontalHeaderLabels(["#", "액션 유형", "상세 내용", "요약"])
        self.tbl_actions.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tbl_actions.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tbl_actions.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.tbl_actions)

        # Toolbar buttons - Row 1: Add, Edit, Del, Up, Down
        btn_bar1 = QHBoxLayout()
        btn_bar1.setSpacing(4)

        btn_add = QPushButton("➕ 액션 추가")
        btn_add.clicked.connect(self._on_add_action)
        btn_bar1.addWidget(btn_add)

        btn_edit = QPushButton("✏️ 액션 수정")
        btn_edit.clicked.connect(self._on_edit_action)
        btn_bar1.addWidget(btn_edit)

        btn_del = QPushButton("🗑️ 삭제")
        btn_del.clicked.connect(self._on_delete_action)
        btn_bar1.addWidget(btn_del)

        btn_bar1.addSpacing(10)

        btn_up = QPushButton("⬆️ 위로")
        btn_up.clicked.connect(self._on_move_up)
        btn_bar1.addWidget(btn_up)

        btn_down = QPushButton("⬇️ 아래로")
        btn_down.clicked.connect(self._on_move_down)
        btn_bar1.addWidget(btn_down)

        btn_bar1.addStretch()
        layout.addLayout(btn_bar1)

        # Toolbar buttons - Row 2: Tests
        btn_bar2 = QHBoxLayout()
        btn_bar2.setSpacing(4)

        btn_test = QPushButton("⚡ 선택 액션 테스트")
        btn_test.setStyleSheet("color: #2563eb; font-weight: bold;")
        btn_test.clicked.connect(self._on_test_action)
        btn_bar2.addWidget(btn_test)

        btn_test_all = QPushButton("▶ 전체 시퀀스 테스트")
        btn_test_all.setStyleSheet("color: #16a34a; font-weight: bold;")
        btn_test_all.clicked.connect(self._on_test_all_actions)
        btn_bar2.addWidget(btn_test_all)

        btn_bar2.addStretch()
        layout.addLayout(btn_bar2)

        # Bottom OK / Cancel
        bottom_bar = QHBoxLayout()
        bottom_bar.addStretch()
        btn_cancel = QPushButton("취소")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("💾 액션 저장")
        btn_save.setStyleSheet("background-color: #1b5e20; color: white; font-weight: bold; padding: 6px 18px;")
        btn_save.clicked.connect(self.accept)
        bottom_bar.addWidget(btn_cancel)
        bottom_bar.addWidget(btn_save)
        layout.addLayout(bottom_bar)

    def _refresh_table(self):
        self.tbl_actions.setRowCount(len(self.actions))
        for row, act in enumerate(self.actions):
            # Index
            it_idx = QTableWidgetItem(str(row + 1))
            it_idx.setTextAlignment(Qt.AlignCenter)
            self.tbl_actions.setItem(row, 0, it_idx)

            # Type
            type_names = {
                "mouse_click": "마우스 클릭",
                "mouse_drag": "마우스 드래그",
                "key_press": "키보드 입력",
                "text_type": "텍스트 입력",
                "delay": "대기 시간",
                "sound_beep": "비프음",
                "log_message": "로그"
            }
            self.tbl_actions.setItem(row, 1, QTableWidgetItem(type_names.get(act.action_type, act.action_type)))

            # Summary
            self.tbl_actions.setItem(row, 2, QTableWidgetItem(act.get_summary()))
            self.tbl_actions.setItem(row, 3, QTableWidgetItem(act.get_summary()))

    def _on_add_action(self):
        dlg = SingleActionDialog(
            target_hwnd=self.target_hwnd,
            reference_image_path=self.reference_image_path,
            scenario=self.scenario,
            parent=self
        )
        if dlg.exec_() == QDialog.Accepted:
            self.actions.append(dlg.action)
            if hasattr(dlg, "reference_image_path") and dlg.reference_image_path:
                self.reference_image_path = dlg.reference_image_path
            self._refresh_table()

    def _on_edit_action(self):
        rows = self.tbl_actions.selectionModel().selectedRows()
        if not rows:
            return
        idx = rows[0].row()
        dlg = SingleActionDialog(
            action=self.actions[idx],
            target_hwnd=self.target_hwnd,
            reference_image_path=self.reference_image_path,
            scenario=self.scenario,
            parent=self
        )
        if dlg.exec_() == QDialog.Accepted:
            self.actions[idx] = dlg.action
            if hasattr(dlg, "reference_image_path") and dlg.reference_image_path:
                self.reference_image_path = dlg.reference_image_path
            self._refresh_table()

    def _on_delete_action(self):
        rows = self.tbl_actions.selectionModel().selectedRows()
        if not rows:
            return
        idx = rows[0].row()
        del self.actions[idx]
        self._refresh_table()

    def _on_move_up(self):
        rows = self.tbl_actions.selectionModel().selectedRows()
        if not rows or rows[0].row() == 0:
            return
        idx = rows[0].row()
        self.actions[idx - 1], self.actions[idx] = self.actions[idx], self.actions[idx - 1]
        self._refresh_table()
        self.tbl_actions.selectRow(idx - 1)

    def _on_move_down(self):
        rows = self.tbl_actions.selectionModel().selectedRows()
        if not rows or rows[0].row() >= len(self.actions) - 1:
            return
        idx = rows[0].row()
        self.actions[idx + 1], self.actions[idx] = self.actions[idx], self.actions[idx + 1]
        self._refresh_table()
        self.tbl_actions.selectRow(idx + 1)

    def _on_test_action(self):
        rows = self.tbl_actions.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(self, "선택 필요", "테스트할 액션을 목록에서 선택해주세요.")
            return
        act = self.actions[rows[0].row()]
        if not self.target_hwnd:
            QMessageBox.warning(self, "경고", "타겟 창이 설정되어 있지 않습니다.")
            return

        try:
            InputController.execute_action(act, self.target_hwnd)
            QMessageBox.information(self, "완료", f"액션 '{act.get_summary()}' 테스트를 실행했습니다.")
        except Exception as e:
            QMessageBox.critical(self, "실행 오류", f"액션 실행 중 오류 발생:\n{e}")

    def _on_test_all_actions(self):
        if not self.actions:
            QMessageBox.warning(self, "경고", "실행할 액션이 없습니다.")
            return
        if not self.target_hwnd:
            QMessageBox.warning(self, "경고", "타겟 창이 설정되어 있지 않습니다.")
            return

        total = len(self.actions)
        try:
            for idx, act in enumerate(self.actions):
                self.tbl_actions.selectRow(idx)
                QApplication.processEvents()

                if act.action_type == "delay" and act.delay_seconds > 0.1:
                    remaining = act.delay_seconds
                    while remaining > 0:
                        step_sleep = min(0.1, remaining)
                        time.sleep(step_sleep)
                        remaining -= step_sleep
                        QApplication.processEvents()
                else:
                    InputController.execute_action(act, self.target_hwnd)

                time.sleep(0.05)
                QApplication.processEvents()

            QMessageBox.information(self, "완료", f"전체 액션 시퀀스({total}개) 테스트 실행을 완료했습니다.")
        except Exception as e:
            QMessageBox.critical(self, "실행 오류", f"액션 시퀀스 실행 중 오류 발생:\n{e}")

    def get_actions(self) -> List[Action]:
        return self.actions
