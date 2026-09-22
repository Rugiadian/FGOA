"""
Scenario Property Editor Dialog for FGOA.
Allows editing scenario branch behavior, jump targets, retries, and launching sub-editors.
"""
import copy
from typing import Optional
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox,
    QGroupBox, QFormLayout, QMessageBox
)
from core.models import Scenario, Project
from ui.condition_editor_dialog import ConditionEditorDialog
from ui.action_editor_dialog import ActionEditorDialog


class ScenarioEditorDialog(QDialog):
    """Detailed Scenario Editor Dialog."""

    def __init__(self, scenario: Scenario, project: Project, target_hwnd: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"시나리오 편집 - #{scenario.step_number} [{scenario.name}]")
        self.resize(560, 520)

        self.scenario = copy.deepcopy(scenario)
        self.project = project
        self.target_hwnd = target_hwnd

        self._init_ui()
        self._load_data()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()
        form.setSpacing(10)

        # Name
        self.txt_name = QLineEdit()
        form.addRow("시나리오 이름:", self.txt_name)

        # ID
        self.lbl_id = QLabel()
        self.lbl_id.setStyleSheet("color: #8da4c4; font-family: monospace;")
        form.addRow("고유 ID:", self.lbl_id)

        # Enabled Checkbox
        self.chk_enabled = QCheckBox("시나리오 활성화 (On/Off)")
        form.addRow("활성 여부:", self.chk_enabled)

        layout.addLayout(form)

        # Branching Group
        grp_branch = QGroupBox("실행 분기 처리 (Brain)")
        l_branch = QFormLayout(grp_branch)

        # On Match
        self.combo_on_match = QComboBox()
        self.combo_on_match.addItem("액션 실행 후 다음 단계 (Execute)", "execute")
        self.combo_on_match.addItem("다른 시나리오로 점프 (Jump)", "jump")
        self.combo_on_match.addItem("실행 정지 (Stop)", "stop")
        self.combo_on_match.currentIndexChanged.connect(self._on_branch_mode_changed)

        self.combo_target_match = QComboBox()
        self._populate_scenario_targets(self.combo_target_match)

        l_branch.addRow("조건 일치 시:", self.combo_on_match)
        self.row_target_match = l_branch.addRow("일치 점프 대상:", self.combo_target_match)

        # On Mismatch
        self.combo_on_mismatch = QComboBox()
        self.combo_on_mismatch.addItem("다음 시나리오로 진행 (Next)", "next")
        self.combo_on_mismatch.addItem("다른 시나리오로 점프 (Jump)", "jump")
        self.combo_on_mismatch.addItem("실행 정지 (Stop)", "stop")
        self.combo_on_mismatch.addItem("대기 후 조건 재시도 (Retry)", "retry")
        self.combo_on_mismatch.currentIndexChanged.connect(self._on_branch_mode_changed)

        self.combo_target_mismatch = QComboBox()
        self._populate_scenario_targets(self.combo_target_mismatch)

        l_branch.addRow("조건 불일치 시:", self.combo_on_mismatch)
        self.row_target_mismatch = l_branch.addRow("불일치 점프 대상:", self.combo_target_mismatch)

        # Retry settings
        retry_box = QHBoxLayout()
        self.spin_retries = QSpinBox()
        self.spin_retries.setRange(1, 100)
        self.spin_retry_sec = QDoubleSpinBox()
        self.spin_retry_sec.setRange(0.1, 60.0)
        self.spin_retry_sec.setSingleStep(0.5)
        self.spin_retry_sec.setSuffix(" 초")
        retry_box.addWidget(QLabel("최대 횟수:"))
        retry_box.addWidget(self.spin_retries)
        retry_box.addWidget(QLabel("간격:"))
        retry_box.addWidget(self.spin_retry_sec)
        l_branch.addRow("재시도 설정:", retry_box)

        layout.addWidget(grp_branch)

        # Quick Sub-editors Buttons
        grp_sub = QGroupBox("조건 및 액션 세부 설정")
        l_sub = QVBoxLayout(grp_sub)

        h_cond = QHBoxLayout()
        self.lbl_cond_summary = QLabel()
        btn_edit_cond = QPushButton("🎨 컬러 조건 & 피커 설정...")
        btn_edit_cond.clicked.connect(self._on_edit_condition)
        h_cond.addWidget(self.lbl_cond_summary, 1)
        h_cond.addWidget(btn_edit_cond)
        l_sub.addLayout(h_cond)

        h_act = QHBoxLayout()
        self.lbl_act_summary = QLabel()
        btn_edit_act = QPushButton("⚡ 액션 시퀀스 설정...")
        btn_edit_act.clicked.connect(self._on_edit_actions)
        h_act.addWidget(self.lbl_act_summary, 1)
        h_act.addWidget(btn_edit_act)
        l_sub.addLayout(h_act)

        layout.addWidget(grp_sub)

        # Post delay
        delay_layout = QHBoxLayout()
        delay_layout.addWidget(QLabel("시나리오 완료 후 후행 대기:"))
        self.spin_post_delay = QDoubleSpinBox()
        self.spin_post_delay.setRange(0.0, 60.0)
        self.spin_post_delay.setSingleStep(0.2)
        self.spin_post_delay.setSuffix(" 초")
        delay_layout.addWidget(self.spin_post_delay)
        delay_layout.addStretch()
        layout.addLayout(delay_layout)

        # Action Custom Log
        log_layout = QHBoxLayout()
        log_layout.addWidget(QLabel("액션 실행 시 로그 출력:"))
        self.txt_custom_log = QLineEdit()
        self.txt_custom_log.setPlaceholderText("원하는 로그 문장을 입력하세요 (선택 사항)")
        log_layout.addWidget(self.txt_custom_log)
        layout.addLayout(log_layout)

        # Bottom Buttons
        bottom_bar = QHBoxLayout()
        bottom_bar.addStretch()

        btn_cancel = QPushButton("취소")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("💾 시나리오 저장")
        btn_save.setStyleSheet("background-color: #1b5e20; color: white; font-weight: bold; padding: 6px 18px;")
        btn_save.clicked.connect(self._on_save)
        bottom_bar.addWidget(btn_cancel)
        bottom_bar.addWidget(btn_save)

        layout.addLayout(bottom_bar)

    def _populate_scenario_targets(self, combo: QComboBox):
        combo.clear()
        combo.addItem("(선택 안 함)", "")
        for s in self.project.scenarios:
            if s.id != self.scenario.id:
                combo.addItem(f"#{s.step_number} [{s.name}] (ID: {s.id})", s.id)

    def _load_data(self):
        self.txt_name.setText(self.scenario.name)
        self.lbl_id.setText(self.scenario.id)
        self.chk_enabled.setChecked(self.scenario.enabled)

        # Match combo
        idx_match = self.combo_on_match.findData(self.scenario.on_match)
        if idx_match >= 0:
            self.combo_on_match.setCurrentIndex(idx_match)
        idx_tm = self.combo_target_match.findData(self.scenario.jump_target_on_match)
        if idx_tm >= 0:
            self.combo_target_match.setCurrentIndex(idx_tm)

        # Mismatch combo
        idx_mismatch = self.combo_on_mismatch.findData(self.scenario.on_mismatch)
        if idx_mismatch >= 0:
            self.combo_on_mismatch.setCurrentIndex(idx_mismatch)
        idx_tmm = self.combo_target_mismatch.findData(self.scenario.jump_target_on_mismatch)
        if idx_tmm >= 0:
            self.combo_target_mismatch.setCurrentIndex(idx_tmm)

        self.spin_retries.setValue(self.scenario.retry_max_count)
        self.spin_retry_sec.setValue(self.scenario.retry_interval_sec)
        self.spin_post_delay.setValue(self.scenario.post_delay_seconds)
        self.txt_custom_log.setText(getattr(self.scenario, "custom_log", ""))

        self._update_summaries()
        self._on_branch_mode_changed()

    def _update_summaries(self):
        self.lbl_cond_summary.setText(f"조건: {self.scenario.get_condition_summary()}")
        self.lbl_act_summary.setText(f"액션: {self.scenario.get_actions_summary()}")

    def _on_branch_mode_changed(self):
        self.combo_target_match.setEnabled(self.combo_on_match.currentData() == "jump")
        self.combo_target_mismatch.setEnabled(self.combo_on_mismatch.currentData() == "jump")
        self.spin_retries.setEnabled(self.combo_on_mismatch.currentData() == "retry")
        self.spin_retry_sec.setEnabled(self.combo_on_mismatch.currentData() == "retry")

    def _on_edit_condition(self):
        dlg = ConditionEditorDialog(
            condition=self.scenario.condition,
            project=self.project,
            current_scenario_id=self.scenario.id,
            target_hwnd=self.target_hwnd,
            parent=self
        )
        if dlg.exec_() == QDialog.Accepted:
            self.scenario.condition = dlg.get_condition()
            self._update_summaries()

    def _on_edit_actions(self):
        ref_path = getattr(self.scenario, "last_action_image_path", None) or (
            self.scenario.condition.reference_image_path if self.scenario.condition else None
        )
        dlg = ActionEditorDialog(
            actions=self.scenario.actions,
            target_hwnd=self.target_hwnd,
            reference_image_path=ref_path,
            scenario=self.scenario,
            parent=self
        )
        if dlg.exec_() == QDialog.Accepted:
            self.scenario.actions = dlg.get_actions()
            self._update_summaries()

    def _on_save(self):
        self.scenario.name = self.txt_name.text().strip() or "시나리오"
        self.scenario.enabled = self.chk_enabled.isChecked()
        self.scenario.on_match = self.combo_on_match.currentData()
        self.scenario.jump_target_on_match = self.combo_target_match.currentData() or ""
        self.scenario.on_mismatch = self.combo_on_mismatch.currentData()
        self.scenario.jump_target_on_mismatch = self.combo_target_mismatch.currentData() or ""
        self.scenario.retry_max_count = self.spin_retries.value()
        self.scenario.retry_interval_sec = self.spin_retry_sec.value()
        self.scenario.post_delay_seconds = self.spin_post_delay.value()
        self.scenario.custom_log = self.txt_custom_log.text().strip()
        self.accept()
