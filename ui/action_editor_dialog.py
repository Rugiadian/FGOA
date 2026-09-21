"""
Action Sequence Editor Dialog for FGOA.
Allows editing mouse clicks, drags, delays, keystrokes, and text inputs for a scenario.
"""
import copy
from typing import List, Optional
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QSpinBox, QDoubleSpinBox, QLineEdit, QGroupBox, QMessageBox,
    QFormLayout
)
from PyQt5.QtCore import Qt
from core.models import Action
from core.input_controller import InputController


class SingleActionDialog(QDialog):
    """Dialog to create or edit a single action."""

    def __init__(self, action: Optional[Action] = None, target_hwnd: int = 0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("액션 속성 설정")
        self.resize(420, 360)
        self.action = copy.deepcopy(action) if action else Action()
        self.target_hwnd = target_hwnd
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()
        form.setSpacing(10)

        # Action Type
        self.combo_type = QComboBox()
        self.combo_type.addItem("마우스 클릭 (좌/우/더블)", "mouse_click")
        self.combo_type.addItem("마우스 드래그 앤 드롭", "mouse_drag")
        self.combo_type.addItem("키보드 단축키/키 입력", "key_press")
        self.combo_type.addItem("텍스트 타이핑", "text_type")
        self.combo_type.addItem("대기 (Sleep/Delay)", "delay")
        self.combo_type.addItem("비프 사운드", "sound_beep")
        self.combo_type.addItem("로그 메시지", "log_message")

        idx = self.combo_type.findData(self.action.action_type)
        if idx >= 0:
            self.combo_type.setCurrentIndex(idx)
        self.combo_type.currentIndexChanged.connect(self._on_type_changed)
        form.addRow("액션 유형:", self.combo_type)

        # Dynamic containers
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

        # 5. Delay fields
        self.grp_delay = QGroupBox("대기 시간 설정")
        l_delay = QFormLayout(self.grp_delay)
        self.spin_delay = QDoubleSpinBox()
        self.spin_delay.setRange(0.01, 3600.0)
        self.spin_delay.setValue(self.action.delay_seconds)
        self.spin_delay.setSuffix(" 초")
        l_delay.addRow("대기 시간:", self.spin_delay)
        form.addRow(self.grp_delay)

        layout.addLayout(form)
        self._update_visibility()

        # Dialog buttons
        btns = QHBoxLayout()
        btns.addStretch()
        btn_cancel = QPushButton("취소")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("확인")
        btn_ok.setStyleSheet("background-color: #1b5e20; color: white; font-weight: bold;")
        btn_ok.clicked.connect(self._on_ok)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        layout.addLayout(btns)

    def _on_type_changed(self):
        self._update_visibility()

    def _update_visibility(self):
        current_type = self.combo_type.currentData()
        self.grp_click.setVisible(current_type in ("mouse_click", "mouse_drag"))
        self.grp_drag.setVisible(current_type == "mouse_drag")
        self.grp_key.setVisible(current_type == "key_press")
        self.grp_text.setVisible(current_type == "text_type")
        self.grp_delay.setVisible(current_type == "delay")

    def _on_ok(self):
        self.action.action_type = self.combo_type.currentData()
        if self.action.action_type in ("mouse_click", "mouse_drag"):
            self.action.x = self.spin_x.value()
            self.action.y = self.spin_y.value()
            btn_map = {0: "left", 1: "right", 2: "middle"}
            self.action.mouse_button = btn_map.get(self.combo_btn.currentIndex(), "left")
            self.action.click_type = "double" if self.combo_click_type.currentIndex() == 1 else "single"
            self.action.repeat_count = self.spin_repeat.value()

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

        elif self.action.action_type == "delay":
            self.action.delay_seconds = self.spin_delay.value()

        self.accept()


class ActionEditorDialog(QDialog):
    """Sequence Editor for Scenario Actions."""

    def __init__(self, actions: List[Action], target_hwnd: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("액션 시퀀스 편집기")
        self.resize(680, 520)
        self.actions = [copy.deepcopy(a) for a in actions]
        self.target_hwnd = target_hwnd

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

        # Toolbar buttons
        btn_bar = QHBoxLayout()

        btn_add = QPushButton("➕ 액션 추가")
        btn_add.clicked.connect(self._on_add_action)
        btn_bar.addWidget(btn_add)

        btn_edit = QPushButton("✏️ 액션 수정")
        btn_edit.clicked.connect(self._on_edit_action)
        btn_bar.addWidget(btn_edit)

        btn_del = QPushButton("🗑️ 삭제")
        btn_del.clicked.connect(self._on_delete_action)
        btn_bar.addWidget(btn_del)

        btn_bar.addSpacing(15)

        btn_up = QPushButton("⬆️ 위로")
        btn_up.clicked.connect(self._on_move_up)
        btn_bar.addWidget(btn_up)

        btn_down = QPushButton("⬇️ 아래로")
        btn_down.clicked.connect(self._on_move_down)
        btn_bar.addWidget(btn_down)

        btn_bar.addStretch()

        btn_test = QPushButton("▶ 단일 액션 테스트")
        btn_test.setStyleSheet("background-color: #2e7d32; color: white;")
        btn_test.clicked.connect(self._on_test_action)
        btn_bar.addWidget(btn_test)

        layout.addLayout(btn_bar)

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
        dlg = SingleActionDialog(target_hwnd=self.target_hwnd, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self.actions.append(dlg.action)
            self._refresh_table()

    def _on_edit_action(self):
        rows = self.tbl_actions.selectionModel().selectedRows()
        if not rows:
            return
        idx = rows[0].row()
        dlg = SingleActionDialog(action=self.actions[idx], target_hwnd=self.target_hwnd, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self.actions[idx] = dlg.action
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

        if act.action_type == "mouse_click":
            InputController.click_at(self.target_hwnd, act.x, act.y, act.mouse_button, act.click_type, act.repeat_count)
        elif act.action_type == "key_press":
            InputController.send_key_combination(act.key, act.modifiers)
        elif act.action_type == "sound_beep":
            InputController.beep()
        QMessageBox.information(self, "완료", f"액션 '{act.get_summary()}' 테스트를 실행했습니다.")

    def get_actions(self) -> List[Action]:
        return self.actions
