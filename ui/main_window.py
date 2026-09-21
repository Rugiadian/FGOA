"""
Main Window for FGOA (Windows Auto Input & Color Automation Tool).
Tall vertical layout with spreadsheet-style scenario management,
real-time target window tracking, and execution controls.
"""
import os
import json
from typing import Optional, Dict, List
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox, QToolBar,
    QFileDialog, QMessageBox, QSplitter, QTextEdit, QStatusBar,
    QFrame, QAbstractItemView
)
from PyQt5.QtGui import QColor, QFont, QIcon, QKeySequence
from PyQt5.QtCore import Qt, QTimer

from core.models import Project, Scenario, Condition, Action, ColorPoint
from core.window_manager import WindowManager, WindowInfo
from core.evaluator import ConditionEvaluator
from core.runner import WorkflowRunner
from ui.theme import DARK_STYLESHEET
from ui.window_picker_dialog import WindowPickerDialog
from ui.scenario_editor_dialog import ScenarioEditorDialog
from ui.condition_editor_dialog import ConditionEditorDialog
from ui.action_editor_dialog import ActionEditorDialog
from ui.widgets.color_badge import WarningBadge


class MainWindow(QMainWindow):
    """Tall vertical spreadsheet-style main application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("FGOA - 화면 인식 스마트 윈도우 오토 툴")
        # Tall vertical aspect ratio
        self.resize(920, 1020)
        self.setMinimumSize(780, 700)

        self.project = Project()
        self.target_hwnd: int = 0
        self.runner: Optional[WorkflowRunner] = None
        self.current_project_path: Optional[str] = None

        # Sample initial scenario if empty
        self._init_sample_project()

        self._init_ui()
        self._apply_theme()
        self._refresh_scenario_table()
        self._start_target_monitor_timer()

    def _init_sample_project(self):
        """Create sample scenario sequence so the user sees immediate example usage."""
        if not self.project.scenarios:
            s1 = Scenario(
                step_number=1,
                name="전투 진입 확인",
                enabled=True,
                condition=Condition(
                    name="전투 화면 인식",
                    logic_operator="AND",
                    points=[
                        ColorPoint(x=100, y=100, r=220, g=20, b=60, tolerance=20),
                        ColorPoint(x=350, y=120, r=255, g=255, b=255, tolerance=15)
                    ]
                ),
                on_match="execute",
                on_mismatch="retry",
                retry_max_count=5,
                retry_interval_sec=1.0,
                actions=[
                    Action(action_type="mouse_click", x=450, y=550, mouse_button="left", repeat_count=1),
                    Action(action_type="delay", delay_seconds=2.0)
                ]
            )
            s2 = Scenario(
                step_number=2,
                name="스킬 1 발동",
                enabled=True,
                condition=None,  # Unconditional
                on_match="execute",
                actions=[
                    Action(action_type="mouse_click", x=120, y=620, mouse_button="left"),
                    Action(action_type="delay", delay_seconds=1.5)
                ]
            )
            s3 = Scenario(
                step_number=3,
                name="결과 대기 및 복귀",
                enabled=True,
                condition=Condition(
                    name="클리어 화면 인식",
                    points=[
                        ColorPoint(x=640, y=360, r=255, g=215, b=0, tolerance=25)
                    ]
                ),
                on_match="jump",
                jump_target_on_match=s1.id,  # Loop back to s1
                on_mismatch="next",
                actions=[
                    Action(action_type="mouse_click", x=640, y=680, mouse_button="left"),
                    Action(action_type="delay", delay_seconds=3.0)
                ]
            )
            self.project.scenarios = [s1, s2, s3]
            self.project.renumber_steps()

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # 1. Top Target Window Selector Bar
        target_frame = QFrame()
        target_frame.setStyleSheet("background-color: #24242d; border: 1px solid #383847; border-radius: 6px; padding: 4px;")
        t_layout = QHBoxLayout(target_frame)
        t_layout.setContentsMargins(8, 4, 8, 4)

        t_layout.addWidget(QLabel("🎯 타겟 창 (상대 좌표 기준):"))
        self.lbl_target_info = QLabel("선택된 창 없음 (창을 선택해주세요)")
        self.lbl_target_info.setStyleSheet("font-weight: bold; color: #ffb74d;")
        t_layout.addWidget(self.lbl_target_info, 1)

        btn_select_win = QPushButton("창 선택...")
        btn_select_win.clicked.connect(self._on_select_target_window)
        t_layout.addWidget(btn_select_win)

        btn_focus_win = QPushButton("창 활성화")
        btn_focus_win.clicked.connect(self._on_focus_target_window)
        t_layout.addWidget(btn_focus_win)

        main_layout.addWidget(target_frame)

        # 2. Project & Scenario Management Toolbar
        tb_layout = QHBoxLayout()
        tb_layout.setSpacing(6)

        btn_add = QPushButton("➕ 시나리오 추가")
        btn_add.clicked.connect(self._on_add_scenario)
        tb_layout.addWidget(btn_add)

        btn_edit = QPushButton("✏️ 편집")
        btn_edit.clicked.connect(self._on_edit_selected_scenario)
        tb_layout.addWidget(btn_edit)

        btn_dup = QPushButton("📋 복제")
        btn_dup.clicked.connect(self._on_duplicate_scenario)
        tb_layout.addWidget(btn_dup)

        btn_del = QPushButton("🗑️ 삭제")
        btn_del.clicked.connect(self._on_delete_scenario)
        tb_layout.addWidget(btn_del)

        tb_layout.addSpacing(10)

        btn_up = QPushButton("⬆️ 위로")
        btn_up.clicked.connect(self._on_move_up)
        tb_layout.addWidget(btn_up)

        btn_down = QPushButton("⬇️ 아래로")
        btn_down.clicked.connect(self._on_move_down)
        tb_layout.addWidget(btn_down)

        tb_layout.addStretch()

        btn_save_proj = QPushButton("💾 저장")
        btn_save_proj.clicked.connect(self._on_save_project)
        tb_layout.addWidget(btn_save_proj)

        btn_open_proj = QPushButton("📂 열기")
        btn_open_proj.clicked.connect(self._on_open_project)
        tb_layout.addWidget(btn_open_proj)

        main_layout.addLayout(tb_layout)

        # 3. Spreadsheet Table for Scenarios (Vertical stretch)
        splitter = QSplitter(Qt.Vertical)

        self.tbl_scenarios = QTableWidget()
        self.tbl_scenarios.setColumnCount(9)
        self.tbl_scenarios.setHorizontalHeaderLabels([
            "#", "활성", "ID", "시나리오 이름", "실행 조건 (Eye)",
            "일치 시 (Match)", "불일치 시 (Mismatch)", "액션 요약 (Hand)", "상태"
        ])
        self.tbl_scenarios.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tbl_scenarios.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)  # Name stretches
        self.tbl_scenarios.horizontalHeader().setSectionResizeMode(7, QHeaderView.Stretch)  # Actions stretch
        self.tbl_scenarios.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_scenarios.setAlternatingRowColors(True)
        self.tbl_scenarios.cellDoubleClicked.connect(self._on_cell_double_clicked)
        splitter.addWidget(self.tbl_scenarios)

        # 4. Bottom Collapsible Log & Execution Monitor
        log_widget = QWidget()
        l_log = QVBoxLayout(log_widget)
        l_log.setContentsMargins(0, 4, 0, 0)
        l_log.setSpacing(4)

        log_hdr = QHBoxLayout()
        log_hdr.addWidget(QLabel("📋 실시간 실행 로그 & 진단"))
        log_hdr.addStretch()
        btn_clear_log = QPushButton("로그 비우기")
        btn_clear_log.setFixedHeight(22)
        btn_clear_log.clicked.connect(lambda: self.txt_log.clear())
        log_hdr.addWidget(btn_clear_log)
        l_log.addLayout(log_hdr)

        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        l_log.addWidget(self.txt_log)
        splitter.addWidget(log_widget)

        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        main_layout.addWidget(splitter, 1)

        # 5. Execution Controller Bottom Bar
        ctrl_frame = QFrame()
        ctrl_frame.setStyleSheet("background-color: #24242d; border: 1px solid #383847; border-radius: 6px; padding: 6px;")
        c_layout = QHBoxLayout(ctrl_frame)
        c_layout.setContentsMargins(8, 6, 8, 6)

        # Run Buttons
        self.btn_run = QPushButton("▶ 시작 (F5)")
        self.btn_run.setObjectName("btn_run")
        self.btn_run.clicked.connect(self._on_start_execution)
        c_layout.addWidget(self.btn_run)

        self.btn_pause = QPushButton("⏸ 일시정지")
        self.btn_pause.setObjectName("btn_pause")
        self.btn_pause.setEnabled(False)
        self.btn_pause.clicked.connect(self._on_pause_execution)
        c_layout.addWidget(self.btn_pause)

        self.btn_stop = QPushButton("⏹ 정지 (F6)")
        self.btn_stop.setObjectName("btn_stop")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._on_stop_execution)
        c_layout.addWidget(self.btn_stop)

        self.btn_step = QPushButton("⏭ 단일 스텝")
        self.btn_step.clicked.connect(self._on_step_execution)
        c_layout.addWidget(self.btn_step)

        c_layout.addSpacing(20)

        # Loop Controls
        c_layout.addWidget(QLabel("반복 횟수:"))
        self.spin_loops = QSpinBox()
        self.spin_loops.setRange(0, 99999)
        self.spin_loops.setValue(self.project.loop_count)
        self.spin_loops.setSpecialValueText("무한 반복 (∞)")
        self.spin_loops.valueChanged.connect(self._on_loop_count_changed)
        c_layout.addWidget(self.spin_loops)

        c_layout.addWidget(QLabel("루프 간격:"))
        self.spin_loop_delay = QDoubleSpinBox()
        self.spin_loop_delay.setRange(0.0, 3600.0)
        self.spin_loop_delay.setValue(self.project.loop_delay_seconds)
        self.spin_loop_delay.setSuffix(" 초")
        self.spin_loop_delay.valueChanged.connect(self._on_loop_delay_changed)
        c_layout.addWidget(self.spin_loop_delay)

        c_layout.addStretch()

        self.lbl_run_status = QLabel("대기 중")
        self.lbl_run_status.setStyleSheet("font-weight: bold; color: #a9b1d6; font-size: 10.5pt;")
        c_layout.addWidget(self.lbl_run_status)

        main_layout.addWidget(ctrl_frame)

        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("준비 완료 - FGOA 오토 툴")

    def _apply_theme(self):
        self.setStyleSheet(DARK_STYLESHEET)

    # Spreadsheet Rendering
    def _refresh_scenario_table(self):
        self.project.renumber_steps()
        warnings_map = ConditionEvaluator.check_project_uniqueness(self.project)

        self.tbl_scenarios.setRowCount(len(self.project.scenarios))

        for row, scen in enumerate(self.project.scenarios):
            # 1. Step #
            it_num = QTableWidgetItem(str(scen.step_number))
            it_num.setTextAlignment(Qt.AlignCenter)
            it_num.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.tbl_scenarios.setItem(row, 0, it_num)

            # 2. Enabled Checkbox
            chk_widget = QWidget()
            chk_layout = QHBoxLayout(chk_widget)
            chk_layout.setContentsMargins(0, 0, 0, 0)
            chk_layout.setAlignment(Qt.AlignCenter)
            chk = QCheckBox()
            chk.setChecked(scen.enabled)
            chk.stateChanged.connect(lambda state, s=scen: self._on_scenario_toggle(s, state))
            chk_layout.addWidget(chk)
            self.tbl_scenarios.setCellWidget(row, 1, chk_widget)

            # 3. Scenario ID
            it_id = QTableWidgetItem(scen.id)
            it_id.setTextAlignment(Qt.AlignCenter)
            it_id.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            it_id.setForeground(QColor(140, 160, 190))
            self.tbl_scenarios.setItem(row, 2, it_id)

            # 4. Name
            it_name = QTableWidgetItem(scen.name)
            it_name.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.tbl_scenarios.setItem(row, 3, it_name)

            # 5. Condition Summary + Uniqueness Warning
            cond_summary = scen.get_condition_summary()
            if scen.id in warnings_map:
                w_widget = QWidget()
                w_layout = QHBoxLayout(w_widget)
                w_layout.setContentsMargins(4, 0, 4, 0)
                w_layout.addWidget(QLabel(cond_summary))
                w_badge = WarningBadge("\n".join(warnings_map[scen.id]))
                w_layout.addWidget(w_badge)
                w_layout.addStretch()
                self.tbl_scenarios.setCellWidget(row, 4, w_widget)
            else:
                it_cond = QTableWidgetItem(cond_summary)
                it_cond.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.tbl_scenarios.setItem(row, 4, it_cond)

            # 6. On Match
            match_str = "액션 실행" if scen.on_match == "execute" else (
                f"점프 → {self._get_jump_display(scen.jump_target_on_match)}" if scen.on_match == "jump" else "정지"
            )
            it_match = QTableWidgetItem(match_str)
            it_match.setTextAlignment(Qt.AlignCenter)
            it_match.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            it_match.setForeground(QColor(100, 220, 130))
            self.tbl_scenarios.setItem(row, 5, it_match)

            # 7. On Mismatch
            if scen.on_mismatch == "next":
                mismatch_str = "다음 단계"
            elif scen.on_mismatch == "jump":
                mismatch_str = f"점프 → {self._get_jump_display(scen.jump_target_on_mismatch)}"
            elif scen.on_mismatch == "retry":
                mismatch_str = f"재시도 ({scen.retry_max_count}회)"
            else:
                mismatch_str = "정지"
            it_mismatch = QTableWidgetItem(mismatch_str)
            it_mismatch.setTextAlignment(Qt.AlignCenter)
            it_mismatch.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            it_mismatch.setForeground(QColor(255, 180, 80))
            self.tbl_scenarios.setItem(row, 6, it_mismatch)

            # 8. Action Summary
            it_act = QTableWidgetItem(scen.get_actions_summary())
            it_act.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.tbl_scenarios.setItem(row, 7, it_act)

            # 9. Status
            it_status = QTableWidgetItem("대기")
            it_status.setTextAlignment(Qt.AlignCenter)
            it_status.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            it_status.setForeground(QColor(160, 160, 170))
            self.tbl_scenarios.setItem(row, 8, it_status)

    def _get_jump_display(self, target_id: str) -> str:
        if not target_id:
            return "(미지정)"
        target_scen = self.project.find_scenario_by_id(target_id)
        if target_scen:
            return f"#{target_scen.step_number} [{target_scen.name}]"
        return target_id

    def _on_scenario_toggle(self, scenario: Scenario, state: int):
        scenario.enabled = (state == Qt.Checked)

    def _on_cell_double_clicked(self, row: int, col: int):
        if row < 0 or row >= len(self.project.scenarios):
            return
        scen = self.project.scenarios[row]

        if col == 4:  # Condition column clicked
            dlg = ConditionEditorDialog(
                condition=scen.condition,
                project=self.project,
                current_scenario_id=scen.id,
                target_hwnd=self.target_hwnd,
                parent=self
            )
            if dlg.exec_() == ConditionEditorDialog.Accepted:
                scen.condition = dlg.get_condition()
                self._refresh_scenario_table()

        elif col == 7:  # Actions column clicked
            dlg = ActionEditorDialog(actions=scen.actions, target_hwnd=self.target_hwnd, parent=self)
            if dlg.exec_() == ActionEditorDialog.Accepted:
                scen.actions = dlg.get_actions()
                self._refresh_scenario_table()

        else:  # Open full scenario editor
            dlg = ScenarioEditorDialog(scenario=scen, project=self.project, target_hwnd=self.target_hwnd, parent=self)
            if dlg.exec_() == ScenarioEditorDialog.Accepted:
                self.project.scenarios[row] = dlg.scenario
                self._refresh_scenario_table()

    # Toolbar Actions
    def _on_add_scenario(self):
        new_step_num = len(self.project.scenarios) + 1
        new_scen = Scenario(
            step_number=new_step_num,
            name=f"시나리오 {new_step_num}",
            enabled=True
        )
        self.project.scenarios.append(new_scen)
        self._refresh_scenario_table()
        self.tbl_scenarios.selectRow(len(self.project.scenarios) - 1)

    def _on_edit_selected_scenario(self):
        rows = self.tbl_scenarios.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "안내", "편집할 시나리오를 표에서 선택해주세요.")
            return
        row = rows[0].row()
        scen = self.project.scenarios[row]
        dlg = ScenarioEditorDialog(scenario=scen, project=self.project, target_hwnd=self.target_hwnd, parent=self)
        if dlg.exec_() == ScenarioEditorDialog.Accepted:
            self.project.scenarios[row] = dlg.scenario
            self._refresh_scenario_table()

    def _on_duplicate_scenario(self):
        rows = self.tbl_scenarios.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        import copy
        cloned = copy.deepcopy(self.project.scenarios[row])
        import uuid
        cloned.id = f"scen_{uuid.uuid4().hex[:6]}"
        cloned.name = f"{cloned.name} (복제)"
        self.project.scenarios.insert(row + 1, cloned)
        self._refresh_scenario_table()
        self.tbl_scenarios.selectRow(row + 1)

    def _on_delete_scenario(self):
        rows = self.tbl_scenarios.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        scen = self.project.scenarios[row]
        res = QMessageBox.question(self, "삭제 확인", f"시나리오 #{scen.step_number} [{scen.name}]를 삭제하시겠습니까?")
        if res == QMessageBox.Yes:
            del self.project.scenarios[row]
            self._refresh_scenario_table()

    def _on_move_up(self):
        rows = self.tbl_scenarios.selectionModel().selectedRows()
        if not rows or rows[0].row() == 0:
            return
        row = rows[0].row()
        self.project.scenarios[row - 1], self.project.scenarios[row] = (
            self.project.scenarios[row], self.project.scenarios[row - 1]
        )
        self._refresh_scenario_table()
        self.tbl_scenarios.selectRow(row - 1)

    def _on_move_down(self):
        rows = self.tbl_scenarios.selectionModel().selectedRows()
        if not rows or rows[0].row() >= len(self.project.scenarios) - 1:
            return
        row = rows[0].row()
        self.project.scenarios[row + 1], self.project.scenarios[row] = (
            self.project.scenarios[row], self.project.scenarios[row + 1]
        )
        self._refresh_scenario_table()
        self.tbl_scenarios.selectRow(row + 1)

    # Window Selection & Monitoring
    def _on_select_target_window(self):
        dlg = WindowPickerDialog(current_hwnd=self.target_hwnd, parent=self)
        if dlg.exec_() == WindowPickerDialog.Accepted and dlg.selected_window:
            self.target_hwnd = dlg.selected_window.hwnd
            self.project.target_window_title = dlg.selected_window.title
            self._update_target_label(dlg.selected_window)

    def _on_focus_target_window(self):
        if self.target_hwnd:
            WindowManager.bring_to_foreground(self.target_hwnd)

    def _update_target_label(self, win: Optional[WindowInfo]):
        if win:
            self.lbl_target_info.setText(
                f"'{win.title}' (HWND: 0x{win.hwnd:X}, 클라이언트: {win.client_width}×{win.client_height})"
            )
            self.lbl_target_info.setStyleSheet("font-weight: bold; color: #4fc3f7;")
        else:
            self.lbl_target_info.setText("선택된 창 없음 (창을 선택해주세요)")
            self.lbl_target_info.setStyleSheet("font-weight: bold; color: #ffb74d;")

    def _start_target_monitor_timer(self):
        self.timer_monitor = QTimer(self)
        self.timer_monitor.setInterval(1500)
        self.timer_monitor.timeout.connect(self._check_target_alive)
        self.timer_monitor.start()

    def _check_target_alive(self):
        if self.target_hwnd:
            win_info = WindowManager.get_window_info(self.target_hwnd)
            if not win_info:
                self.lbl_target_info.setText("⚠️ 타겟 창이 닫혔거나 감지되지 않습니다!")
                self.lbl_target_info.setStyleSheet("font-weight: bold; color: #ef5350;")
            else:
                self._update_target_label(win_info)

    # Execution Engine Control
    def _on_start_execution(self):
        if not self.target_hwnd:
            QMessageBox.warning(self, "타겟 창 필요", "먼저 상단에서 오토 입력을 수행할 타겟 창을 선택해주세요.")
            return

        if self.runner and self.runner.isRunning():
            if self.runner._is_paused:
                self.runner.resume()
                self.lbl_run_status.setText("실행 중...")
                self.lbl_run_status.setStyleSheet("color: #66bb6a; font-weight: bold;")
                self.btn_pause.setText("⏸ 일시정지")
                return

        # Start fresh runner
        self.runner = WorkflowRunner(self.project, self.target_hwnd, parent=self)
        self.runner.sig_log.connect(self._append_log)
        self.runner.sig_scenario_started.connect(self._on_scenario_started)
        self.runner.sig_scenario_completed.connect(self._on_scenario_completed)
        self.runner.sig_finished.connect(self._on_runner_finished)

        self.btn_run.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_stop.setEnabled(True)
        self.lbl_run_status.setText("실행 중 (F5/F6)")
        self.lbl_run_status.setStyleSheet("color: #66bb6a; font-weight: bold;")

        self.runner.start()

    def _on_pause_execution(self):
        if self.runner and self.runner.isRunning():
            if self.runner._is_paused:
                self.runner.resume()
                self.btn_pause.setText("⏸ 일시정지")
                self.lbl_run_status.setText("실행 중...")
                self.lbl_run_status.setStyleSheet("color: #66bb6a; font-weight: bold;")
            else:
                self.runner.pause()
                self.btn_pause.setText("▶ 재개")
                self.lbl_run_status.setText("일시정지됨")
                self.lbl_run_status.setStyleSheet("color: #ffa726; font-weight: bold;")

    def _on_stop_execution(self):
        if self.runner:
            self.runner.stop()
            self.lbl_run_status.setText("정지 요청 중...")
            self.lbl_run_status.setStyleSheet("color: #ef5350; font-weight: bold;")

    def _on_step_execution(self):
        if not self.target_hwnd:
            QMessageBox.warning(self, "타겟 창 필요", "타겟 창을 먼저 선택해주세요.")
            return
        if not self.runner or not self.runner.isRunning():
            self._on_start_execution()
            if self.runner:
                self.runner.step_forward()
        else:
            self.runner.step_forward()

    def _on_scenario_started(self, scenario_id: str):
        for row, s in enumerate(self.project.scenarios):
            if s.id == scenario_id:
                it = self.tbl_scenarios.item(row, 8)
                if it:
                    it.setText("⚡ 검사 중")
                    it.setForeground(QColor(79, 195, 247))
                # Highlight row background
                for col in range(self.tbl_scenarios.columnCount()):
                    item = self.tbl_scenarios.item(row, col)
                    if item:
                        item.setBackground(QColor(35, 60, 95))
            else:
                for col in range(self.tbl_scenarios.columnCount()):
                    item = self.tbl_scenarios.item(row, col)
                    if item:
                        item.setBackground(QColor(24, 24, 28))

    def _on_scenario_completed(self, scenario_id: str, result: str):
        for row, s in enumerate(self.project.scenarios):
            if s.id == scenario_id:
                it = self.tbl_scenarios.item(row, 8)
                if it:
                    if result == "matched":
                        it.setText("✓ 일치")
                        it.setForeground(QColor(102, 187, 106))
                    elif result == "mismatch":
                        it.setText("✗ 불일치")
                        it.setForeground(QColor(255, 167, 38))
                    elif result == "skipped":
                        it.setText("- 건너뜀")
                        it.setForeground(QColor(120, 120, 130))

    def _on_runner_finished(self, reason: str):
        self.btn_run.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.btn_pause.setText("⏸ 일시정지")
        self.lbl_run_status.setText(f"완료 ({reason})")
        self.lbl_run_status.setStyleSheet("color: #a9b1d6; font-weight: bold;")

    def _append_log(self, level: str, msg: str):
        color_map = {
            "INFO": "#90caf9",
            "ACTION": "#ce93d8",
            "SUCCESS": "#a5d6a7",
            "WARN": "#ffe082",
            "ERROR": "#ef9a9a",
            "USER": "#80deea"
        }
        color = color_map.get(level, "#ffffff")
        html = f"<span style='color: #757575;'>[{level}]</span> <span style='color: {color};'>{msg}</span>"
        self.txt_log.append(html)

    def _on_loop_count_changed(self, val: int):
        self.project.loop_count = val

    def _on_loop_delay_changed(self, val: float):
        self.project.loop_delay_seconds = val

    # Save & Open Project
    def _on_save_project(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "프로젝트 저장", self.current_project_path or "fgoa_project.json", "FGOA Project (*.json)"
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(self.project.to_dict(), f, indent=2, ensure_ascii=False)
                self.current_project_path = path
                self.status_bar.showMessage(f"프로젝트 저장 완료: {path}", 4000)
            except Exception as e:
                QMessageBox.critical(self, "저장 오류", f"프로젝트를 저장할 수 없습니다:\n{e}")

    def _on_open_project(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "프로젝트 열기", "", "FGOA Project (*.json)"
        )
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.project = Project.from_dict(data)
                self.current_project_path = path
                self.spin_loops.setValue(self.project.loop_count)
                self.spin_loop_delay.setValue(self.project.loop_delay_seconds)
                self._refresh_scenario_table()
                self.status_bar.showMessage(f"프로젝트 불러오기 완료: {path}", 4000)
            except Exception as e:
                QMessageBox.critical(self, "열기 오류", f"프로젝트를 불러올 수 없습니다:\n{e}")

    # Hotkey support
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F5:
            if not self.runner or not self.runner.isRunning():
                self._on_start_execution()
            else:
                self._on_pause_execution()
            event.accept()
        elif event.key() == Qt.Key_F6:
            self._on_stop_execution()
            event.accept()
        elif event.key() == Qt.Key_F7:
            self._on_step_execution()
            event.accept()
        else:
            super().keyPressEvent(event)
