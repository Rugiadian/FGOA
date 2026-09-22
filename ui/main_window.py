"""
Main Window for FGOA (Windows Auto Input & Color Automation Tool).
3-Pane Professional Architecture:
- Left pane: Scenario List & Sequence Toolbar (QFrame card_frame)
- Center pane: Always-open Unity Inspector (Properties, Brain Branching, Eye Conditions, Hand Actions)
- Right pane: Real-time Execution Log & Diagnostics
- Themes: Full support for Light Mode and Dark Mode with Fusion-based clean backgrounds
- Live Code Reload: Automatically reloads when code is saved in editor without file-lock issues
"""
import os
import sys
import json
import copy
from typing import Optional, Dict, List
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox, QToolBar,
    QFileDialog, QMessageBox, QSplitter, QTextEdit, QStatusBar,
    QFrame, QAbstractItemView, QShortcut
)
from PyQt5.QtGui import QColor, QFont, QIcon, QKeySequence
from PyQt5.QtCore import Qt, QTimer, QFileSystemWatcher, QProcess

from core.models import Project, Scenario, Condition, Action, ColorPoint
from core.window_manager import WindowManager, WindowInfo
from core.evaluator import ConditionEvaluator
from core.runner import WorkflowRunner
from ui.theme import get_stylesheet, get_theme_colors
from ui.window_picker_dialog import WindowPickerDialog
from ui.inspector_widget import InspectorWidget
from ui.widgets.color_badge import WarningBadge


CONFIG_FILE = "fgoa_config.json"
TEMP_RELOAD_FILE = "_temp_reload_project.json"


class MainWindow(QMainWindow):
    """
    Main application window with 3-Pane (Scenario Table | Inspector | Realtime Log) layout
    and full Light/Dark mode support.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("FGOA - 화면 인식 스마트 윈도우 오토 툴")
        self.resize(1380, 880)
        self.setMinimumSize(1020, 650)

        self.project = Project()
        self.target_hwnd: int = 0
        self.runner: Optional[WorkflowRunner] = None
        self.current_project_path: Optional[str] = None
        self.current_theme: str = "light"  # Default to light mode

        # Load user settings
        self._load_app_config()

        # Check for reload state
        self._check_reload_state()

        # Sample initial scenario if empty
        self._init_sample_project()

        self._init_ui()
        self._apply_theme()
        self._refresh_scenario_table()
        self._update_target_label(None)
        self._start_target_monitor_timer()
        self._init_code_watcher()

        # Check if previous crash log exists
        from core.logger import CRASH_LOG_PATH
        if os.path.exists(CRASH_LOG_PATH) and os.path.getsize(CRASH_LOG_PATH) > 0:
            self.status_bar.showMessage("⚠️ 이전 크래시 로그가 기록되어 있습니다. 상단 [📋 에러 로그] 버튼으로 확인하세요.", 8000)

        # Initial selection to first scenario
        if self.project.scenarios:
            self.tbl_scenarios.selectRow(0)

    def _check_reload_state(self):
        """Restore project state if reloading after code modification."""
        if os.path.exists(TEMP_RELOAD_FILE):
            try:
                with open(TEMP_RELOAD_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.project = Project.from_dict(data)
                os.remove(TEMP_RELOAD_FILE)
            except Exception:
                pass

    def _load_app_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    self.current_theme = cfg.get("theme", "light")
                    if hasattr(self.project, "target_client_width"):
                        self.project.target_client_width = cfg.get("last_target_width", 1600)
                        self.project.target_client_height = cfg.get("last_target_height", 900)
                        self.project.target_window_title = cfg.get("last_target_title", "")
            except Exception:
                pass

    def _save_app_config(self):
        try:
            cfg = {
                "theme": self.current_theme,
                "window_width": self.width(),
                "window_height": self.height(),
                "last_target_title": getattr(self.project, "target_window_title", ""),
                "last_target_width": getattr(self.project, "target_client_width", 1600),
                "last_target_height": getattr(self.project, "target_client_height", 900),
            }
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def closeEvent(self, event):
        self._save_app_config()
        super().closeEvent(event)

    def _init_sample_project(self):
        """Create sample scenario sequence so the user sees immediate example usage."""
        if not self.project.scenarios:
            s1 = Scenario(
                step_number=1,
                scenario_number=1,
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
                scenario_number=2,
                name="스킬 1 발동",
                enabled=True,
                condition=None,
                on_match="execute",
                actions=[
                    Action(action_type="mouse_click", x=120, y=620, mouse_button="left"),
                    Action(action_type="delay", delay_seconds=1.5)
                ]
            )
            s3 = Scenario(
                step_number=3,
                scenario_number=3,
                name="결과 대기 및 복귀",
                enabled=True,
                condition=Condition(
                    name="클리어 화면 인식",
                    points=[
                        ColorPoint(x=640, y=360, r=255, g=215, b=0, tolerance=25)
                    ]
                ),
                on_match="jump",
                jump_target_on_match=s1.id,
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
        central_widget.setObjectName("central_widget")
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # 1. Top Target Window Selector Bar
        target_frame = QFrame()
        target_frame.setObjectName("card_frame")
        t_layout = QHBoxLayout(target_frame)
        t_layout.setContentsMargins(10, 6, 10, 6)

        t_layout.addWidget(QLabel("🎯 대상 게임 창:"))
        self.lbl_target_info = QLabel("선택된 창 없음 (창 선택 버튼을 클릭하세요)")
        self.lbl_target_info.setStyleSheet("font-weight: bold; color: #d97706;")
        t_layout.addWidget(self.lbl_target_info, 1)

        btn_select_win = QPushButton("창 선택...")
        btn_select_win.setObjectName("btn_primary")
        btn_select_win.clicked.connect(self._on_select_target_window)
        t_layout.addWidget(btn_select_win)

        btn_focus_win = QPushButton("창 활성화")
        btn_focus_win.clicked.connect(self._on_focus_target_window)
        t_layout.addWidget(btn_focus_win)

        btn_gallery = QPushButton("🖼️ 레퍼런스 갤러리")
        btn_gallery.setToolTip("참조 이미지 보관함 및 어느 조건/액션에서 사용 중인지 확인합니다.")
        btn_gallery.clicked.connect(self._on_open_reference_gallery)
        t_layout.addWidget(btn_gallery)

        t_layout.addSpacing(10)

        # Hot Reload Controls
        self.chk_hot_reload = QCheckBox("코드 자동 리로드")
        self.chk_hot_reload.setChecked(False)
        self.chk_hot_reload.setToolTip("코드(.py) 파일 수정 저장 시 프로그램을 즉시 자동 재시작합니다.")
        t_layout.addWidget(self.chk_hot_reload)

        btn_reload = QPushButton("🔄 리로드 (Ctrl+R)")
        btn_reload.setToolTip("프로그램을 즉시 리로드합니다. (단축키: Ctrl+R / F8)")
        btn_reload.clicked.connect(self._reload_application)
        t_layout.addWidget(btn_reload)

        btn_error_log = QPushButton("📋 에러 로그")
        btn_error_log.setToolTip("오류 발생 기록(fgoa_crash.log)을 텍스트 편집기로 엽니다.")
        btn_error_log.clicked.connect(self._on_open_crash_log)
        t_layout.addWidget(btn_error_log)

        t_layout.addSpacing(10)

        # Theme Toggle Button
        self.btn_theme_toggle = QPushButton()
        self.btn_theme_toggle.setObjectName("btn_theme")
        self.btn_theme_toggle.clicked.connect(self._toggle_theme)
        self._update_theme_toggle_btn()
        t_layout.addWidget(self.btn_theme_toggle)

        main_layout.addWidget(target_frame)

        # 2. Main 3-Pane Horizontal Splitter [Left: Table | Center: Inspector | Right: Log]
        self.main_h_splitter = QSplitter(Qt.Horizontal)
        self.main_h_splitter.setObjectName("main_h_splitter")

        # ==========================================
        # Pane 1: Left (Scenario Table & Sequence Toolbar)
        # Wrap in QFrame#card_frame to eliminate black OS background
        # ==========================================
        left_pane = QFrame()
        left_pane.setObjectName("card_frame")
        l_layout = QVBoxLayout(left_pane)
        l_layout.setContentsMargins(8, 8, 8, 8)
        l_layout.setSpacing(6)

        # Pane Header: 📜 시나리오 목록 (Scenarios)
        pane_hdr = QHBoxLayout()
        lbl_scen_title = QLabel("📜 시나리오 목록 (Scenarios)")
        lbl_scen_title.setStyleSheet("font-weight: bold; font-size: 9.5pt;")
        pane_hdr.addWidget(lbl_scen_title)
        pane_hdr.addStretch()
        self.lbl_scen_count = QLabel("총 0개")
        self.lbl_scen_count.setStyleSheet("color: #64748b; font-size: 8.5pt;")
        pane_hdr.addWidget(self.lbl_scen_count)
        l_layout.addLayout(pane_hdr)

        # Toolbar
        tb_layout = QHBoxLayout()
        tb_layout.setSpacing(5)

        btn_add = QPushButton("➕ 추가")
        btn_add.clicked.connect(self._on_add_scenario)
        tb_layout.addWidget(btn_add)

        btn_add_loop = QPushButton("🔁 루프 추가")
        btn_add_loop.setToolTip("루프 시작과 종료 노드로 구성된 루프 블록을 추가합니다.")
        btn_add_loop.clicked.connect(self._on_add_loop_block)
        tb_layout.addWidget(btn_add_loop)

        btn_dup = QPushButton("📋 복제")
        btn_dup.clicked.connect(self._on_duplicate_scenario)
        tb_layout.addWidget(btn_dup)

        btn_del = QPushButton("🗑️ 삭제")
        btn_del.clicked.connect(self._on_delete_scenario)
        tb_layout.addWidget(btn_del)

        tb_layout.addSpacing(4)

        btn_up = QPushButton("⬆️")
        btn_up.setToolTip("위로 이동")
        btn_up.clicked.connect(self._on_move_up)
        tb_layout.addWidget(btn_up)

        btn_down = QPushButton("⬇️")
        btn_down.setToolTip("아래로 이동")
        btn_down.clicked.connect(self._on_move_down)
        tb_layout.addWidget(btn_down)

        tb_layout.addStretch()

        btn_save_proj = QPushButton("💾 저장")
        btn_save_proj.clicked.connect(self._on_save_project)
        tb_layout.addWidget(btn_save_proj)

        btn_open_proj = QPushButton("📂 열기")
        btn_open_proj.clicked.connect(self._on_open_project)
        tb_layout.addWidget(btn_open_proj)

        l_layout.addLayout(tb_layout)

        # Scenario Table (Full height)
        self.tbl_scenarios = QTableWidget()
        self.tbl_scenarios.setColumnCount(7)
        self.tbl_scenarios.setHorizontalHeaderLabels([
            "순서", "고유 #", "활성", "시나리오 이름", "인식 조건 (Eye)", "분기 (일치/불일치)", "액션"
        ])
        
        # Responsive header resizing
        header = self.tbl_scenarios.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.resizeSection(0, 32)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.resizeSection(1, 46)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.resizeSection(2, 36)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        header.resizeSection(4, 115)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        header.resizeSection(5, 105)
        header.setSectionResizeMode(6, QHeaderView.Fixed)
        header.resizeSection(6, 42)
        self.tbl_scenarios.verticalHeader().setDefaultSectionSize(26)

        self.tbl_scenarios.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_scenarios.setAlternatingRowColors(True)
        self.tbl_scenarios.itemSelectionChanged.connect(self._on_table_selection_changed)
        l_layout.addWidget(self.tbl_scenarios, 1)

        self.main_h_splitter.addWidget(left_pane)

        # ==========================================
        # Pane 2: Center (Unity-Style Always-Open Inspector)
        # ==========================================
        self.inspector = InspectorWidget(self)
        self.inspector.sig_scenario_changed.connect(self._on_inspector_scenario_changed)
        self.inspector.sig_log.connect(self._append_log)
        self.main_h_splitter.addWidget(self.inspector)

        # ==========================================
        # Pane 3: Right (Real-time Log Window & Diagnostics)
        # ==========================================
        right_log_pane = QFrame()
        right_log_pane.setObjectName("card_frame")
        r_layout = QVBoxLayout(right_log_pane)
        r_layout.setContentsMargins(8, 8, 8, 8)
        r_layout.setSpacing(6)

        # Log Header
        log_header = QHBoxLayout()
        lbl_log_title = QLabel("📋 실시간 실행 로그 (Logs)")
        lbl_log_title.setStyleSheet("font-weight: bold; font-size: 9.5pt;")
        log_header.addWidget(lbl_log_title)
        log_header.addStretch()

        self.chk_autoscroll = QCheckBox("자동 스크롤")
        self.chk_autoscroll.setChecked(True)
        log_header.addWidget(self.chk_autoscroll)

        btn_clear_log = QPushButton("비우기")
        btn_clear_log.setFixedHeight(22)
        btn_clear_log.clicked.connect(lambda: self.txt_log.clear())
        log_header.addWidget(btn_clear_log)
        r_layout.addLayout(log_header)

        # Text Edit Log (Takes full height)
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        r_layout.addWidget(self.txt_log, 1)

        self.main_h_splitter.addWidget(right_log_pane)

        # Splitter sizing ratios: Left ~38%, Center ~42%, Right ~20%
        self.main_h_splitter.setStretchFactor(0, 38)
        self.main_h_splitter.setStretchFactor(1, 42)
        self.main_h_splitter.setStretchFactor(2, 20)
        self.main_h_splitter.setSizes([540, 560, 280])

        main_layout.addWidget(self.main_h_splitter, 1)

        # 3. Execution Controller Bottom Bar
        ctrl_frame = QFrame()
        ctrl_frame.setObjectName("card_frame")
        c_layout = QHBoxLayout(ctrl_frame)
        c_layout.setContentsMargins(10, 6, 10, 6)

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

        c_layout.addWidget(QLabel("반복:"))
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
        self.lbl_run_status.setStyleSheet("font-weight: bold; font-size: 10pt;")
        c_layout.addWidget(self.lbl_run_status)

        main_layout.addWidget(ctrl_frame)

        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("준비 완료 - FGOA 화면 인식 스마트 오토 툴")

        # Shortcuts
        self.sc_reload = QShortcut(QKeySequence("Ctrl+R"), self)
        self.sc_reload.activated.connect(self._reload_application)

        self.sc_f8 = QShortcut(QKeySequence("F8"), self)
        self.sc_f8.activated.connect(self._reload_application)

    # ==========================================
    # Code Watcher & Live Reload
    # ==========================================
    def _init_code_watcher(self):
        """Watches python source files for changes to support editing code while app runs."""
        self.code_watcher = QFileSystemWatcher(self)
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        main_py = os.path.join(base_dir, "main.py")
        if os.path.exists(main_py):
            self.code_watcher.addPath(main_py)

        for sub in ("ui", "core"):
            sub_dir = os.path.join(base_dir, sub)
            if os.path.isdir(sub_dir):
                for fname in os.listdir(sub_dir):
                    if fname.endswith(".py"):
                        self.code_watcher.addPath(os.path.join(sub_dir, fname))

        self.reload_timer = QTimer(self)
        self.reload_timer.setSingleShot(True)
        self.reload_timer.setInterval(600)  # 600ms debounce
        self.reload_timer.timeout.connect(self._on_code_changed_timeout)

        self.code_watcher.fileChanged.connect(self._on_code_file_changed)

    def _on_code_file_changed(self, path: str):
        if not path.endswith(".py"):
            return
        if getattr(self, "chk_hot_reload", None) and self.chk_hot_reload.isChecked():
            # Re-add path in case file was replaced atomically by editor
            if os.path.exists(path) and path not in self.code_watcher.files():
                self.code_watcher.addPath(path)
            self.reload_timer.start()

    def _on_code_changed_timeout(self):
        self.status_bar.showMessage("🔄 코드가 수정되어 프로그램을 자동 리로드합니다...", 3000)
        self._reload_application()

    def _reload_application(self):
        """Cleanly saves current project state and relaunches application."""
        try:
            with open(TEMP_RELOAD_FILE, "w", encoding="utf-8") as f:
                json.dump(self.project.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception:
            pass

        self._save_app_config()

        # Launch detached new process
        QProcess.startDetached(sys.executable, sys.argv)
        self.close()

    def _on_open_crash_log(self):
        from core.logger import open_log_file
        open_log_file()

    # ==========================================
    # Theme Support
    # ==========================================
    def _toggle_theme(self):
        self.current_theme = "dark" if self.current_theme == "light" else "light"
        self._apply_theme()
        self._refresh_scenario_table()
        self._save_app_config()

    def _update_theme_toggle_btn(self):
        if self.current_theme == "light":
            self.btn_theme_toggle.setText("🌙 다크 모드로 전환")
            self.btn_theme_toggle.setToolTip("클릭하여 다크 모드로 전환합니다.")
        else:
            self.btn_theme_toggle.setText("☀️ 라이트 모드로 전환")
            self.btn_theme_toggle.setToolTip("클릭하여 라이트 모드로 전환합니다.")

    def _apply_theme(self):
        self.setStyleSheet(get_stylesheet(self.current_theme))
        self._update_theme_toggle_btn()
        if self.target_hwnd:
            win_info = WindowManager.get_window_info(self.target_hwnd)
            self._update_target_label(win_info)
        else:
            self._update_target_label(None)

    # ==========================================
    # Selection & Inspector Binding
    # ==========================================
    def _on_table_selection_changed(self):
        rows = self.tbl_scenarios.selectionModel().selectedRows()
        if not rows:
            # 빈 공간 클릭 등으로 선택이 해제되어도 기존 인스펙터 창 내용을 비우지 않고 유지
            if self.inspector.current_scenario:
                for r, s in enumerate(self.project.scenarios):
                    if s.id == self.inspector.current_scenario.id:
                        self.tbl_scenarios.blockSignals(True)
                        self.tbl_scenarios.selectRow(r)
                        self.tbl_scenarios.blockSignals(False)
                        break
            return

        row = rows[0].row()
        if 0 <= row < len(self.project.scenarios):
            scen = self.project.scenarios[row]
            self.inspector.set_scenario(scen, self.target_hwnd, self.project)

    def _on_inspector_scenario_changed(self, modified_scen: Scenario):
        """Called when properties are edited inside the Inspector."""
        # Refresh full table to properly update hierarchy indentation if node_type changed
        self._refresh_scenario_table()

    # ==========================================
    # Table Rendering & Hierarchy UI
    # ==========================================
    def _refresh_scenario_table(self):
        self.project.renumber_steps()
        warnings_map = ConditionEvaluator.check_project_uniqueness(self.project)
        depths = self.project.compute_hierarchy_depths()

        if hasattr(self, "lbl_scen_count"):
            self.lbl_scen_count.setText(f"총 {len(self.project.scenarios)}개")

        selected_row = -1
        rows = self.tbl_scenarios.selectionModel().selectedRows()
        if rows:
            selected_row = rows[0].row()

        self.tbl_scenarios.blockSignals(True)
        self.tbl_scenarios.setRowCount(len(self.project.scenarios))

        for row, scen in enumerate(self.project.scenarios):
            depth = depths[row] if row < len(depths) else 0
            self._update_table_row(row, scen, warnings_map, depth)

        self.tbl_scenarios.blockSignals(False)

        # Restore selection
        if 0 <= selected_row < len(self.project.scenarios):
            self.tbl_scenarios.selectRow(selected_row)
        elif self.project.scenarios:
            self.tbl_scenarios.selectRow(0)

    def _update_table_row(self, row: int, scen: Scenario, warnings_map: Optional[dict] = None, depth: int = 0):
        if warnings_map is None:
            warnings_map = ConditionEvaluator.check_project_uniqueness(self.project)

        # 0. Step # (실행 순서 번호)
        it_num = QTableWidgetItem(str(scen.step_number))
        it_num.setTextAlignment(Qt.AlignCenter)
        it_num.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        self.tbl_scenarios.setItem(row, 0, it_num)

        # 1. Scenario # (시나리오 고유 번호)
        it_uid = QTableWidgetItem(f"#{scen.scenario_number}")
        it_uid.setTextAlignment(Qt.AlignCenter)
        it_uid.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        self.tbl_scenarios.setItem(row, 1, it_uid)

        # 2. Enabled Checkbox
        chk_widget = QWidget()
        chk_layout = QHBoxLayout(chk_widget)
        chk_layout.setContentsMargins(0, 0, 0, 0)
        chk_layout.setAlignment(Qt.AlignCenter)
        chk = QCheckBox()
        chk.setChecked(scen.enabled)
        chk.stateChanged.connect(lambda state, s=scen: self._on_scenario_toggle(s, state))
        chk_layout.addWidget(chk)
        self.tbl_scenarios.setCellWidget(row, 2, chk_widget)

        # 3. Name with Loop Hierarchy UI
        if scen.node_type == "loop_start":
            loop_desc = scen.get_loop_summary()
            it_name = QTableWidgetItem(f"{loop_desc} [{scen.name}]")
            it_name.setForeground(QColor("#2563eb" if self.current_theme == "light" else "#60a5fa"))
            f = it_name.font()
            f.setBold(True)
            it_name.setFont(f)
        elif scen.node_type == "loop_end":
            start_idx = self.project.find_matching_loop_start(row)
            start_num_str = f"#{self.project.scenarios[start_idx].scenario_number}" if start_idx is not None else ""
            it_name = QTableWidgetItem(f"🔁 [루프 종료] → 루프 {start_num_str} 복귀")
            it_name.setForeground(QColor("#7c3aed" if self.current_theme == "light" else "#c084fc"))
            f = it_name.font()
            f.setBold(True)
            it_name.setFont(f)
        else:
            if depth > 0:
                indent = ("    " * (depth - 1)) + "  │  ↳ "
                it_name = QTableWidgetItem(f"{indent}{scen.name}")
            else:
                it_name = QTableWidgetItem(scen.name)
        it_name.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        self.tbl_scenarios.setItem(row, 3, it_name)

        # 4. Condition Summary + Warning
        cond_summary = scen.get_condition_summary()
        if scen.node_type == "normal" and scen.id in warnings_map:
            w_widget = QWidget()
            w_layout = QHBoxLayout(w_widget)
            w_layout.setContentsMargins(4, 0, 4, 0)
            w_layout.addWidget(QLabel(cond_summary))
            w_badge = WarningBadge("\n".join(warnings_map[scen.id]))
            w_layout.addWidget(w_badge)
            w_layout.addStretch()
            self.tbl_scenarios.setCellWidget(row, 4, w_widget)
        else:
            self.tbl_scenarios.setCellWidget(row, 4, None)
            it_cond = QTableWidgetItem(cond_summary)
            if scen.node_type != "normal":
                it_cond.setForeground(QColor("#64748b"))
            it_cond.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.tbl_scenarios.setItem(row, 4, it_cond)

        # 5. Branch Summary (On Match / On Mismatch / Loop)
        if scen.node_type == "loop_start":
            it_branch = QTableWidgetItem("🔁 회차 반복 제어")
            it_branch.setForeground(QColor("#2563eb" if self.current_theme == "light" else "#60a5fa"))
        elif scen.node_type == "loop_end":
            it_branch = QTableWidgetItem("🔁 시작점 복귀")
            it_branch.setForeground(QColor("#7c3aed" if self.current_theme == "light" else "#c084fc"))
        else:
            m_str = "실행" if scen.on_match == "execute" else (
                "점프" if scen.on_match == "jump" else (
                    "루프탈출" if scen.on_match == "break_loop" else "정지"
                )
            )
            if scen.on_mismatch == "next":
                mm_str = "다음"
            elif scen.on_mismatch == "jump":
                mm_str = "점프"
            elif scen.on_mismatch == "retry":
                mm_str = f"재시도({scen.retry_max_count})"
            elif scen.on_mismatch == "break_loop":
                mm_str = "루프탈출"
            else:
                mm_str = "정지"
            it_branch = QTableWidgetItem(f"{m_str} / {mm_str}")

        it_branch.setTextAlignment(Qt.AlignCenter)
        it_branch.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        self.tbl_scenarios.setItem(row, 5, it_branch)

        # 6. Action count
        act_text = f"{len(scen.actions)}개" if scen.node_type != "loop_end" else "-"
        it_act = QTableWidgetItem(act_text)
        it_act.setTextAlignment(Qt.AlignCenter)
        it_act.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        self.tbl_scenarios.setItem(row, 6, it_act)

    def _get_jump_display(self, target_id: str) -> str:
        if not target_id:
            return "(미지정)"
        target_scen = self.project.find_scenario_by_id(target_id)
        if not target_scen:
            try:
                target_scen = self.project.find_scenario_by_number(int(target_id))
            except ValueError:
                pass
        if target_scen:
            return f"고유 #{target_scen.scenario_number} (실행 #{target_scen.step_number}) [{target_scen.name}]"
        return target_id

    def _on_scenario_toggle(self, scenario: Scenario, state: int):
        scenario.enabled = (state == Qt.Checked)
        if self.inspector.current_scenario and self.inspector.current_scenario.id == scenario.id:
            self.inspector.chk_enabled.blockSignals(True)
            self.inspector.chk_enabled.setChecked(scenario.enabled)
            self.inspector.chk_enabled.blockSignals(False)

    # ==========================================
    # Toolbar Actions
    # ==========================================
    def _on_add_scenario(self):
        new_step_num = len(self.project.scenarios) + 1
        new_scen_num = self.project.get_next_scenario_number()
        new_scen = Scenario(
            step_number=new_step_num,
            scenario_number=new_scen_num,
            name=f"시나리오 {new_scen_num}",
            enabled=True
        )
        self.project.scenarios.append(new_scen)
        self._refresh_scenario_table()
        self.tbl_scenarios.selectRow(len(self.project.scenarios) - 1)

    def _on_add_loop_block(self):
        """Create a complete loop block (Loop Start + inner child + Loop End)."""
        start_num = self.project.get_next_scenario_number()
        scen_start = Scenario(
            step_number=len(self.project.scenarios) + 1,
            scenario_number=start_num,
            name=f"루프 블록 {start_num}",
            node_type="loop_start",
            loop_mode="count",
            loop_count=5,
            enabled=True
        )
        child_num = start_num + 1
        scen_child = Scenario(
            step_number=len(self.project.scenarios) + 2,
            scenario_number=child_num,
            name="반복 실행 동작",
            node_type="normal",
            enabled=True
        )
        end_num = child_num + 1
        scen_end = Scenario(
            step_number=len(self.project.scenarios) + 3,
            scenario_number=end_num,
            name="루프 종료",
            node_type="loop_end",
            loop_target_id=scen_start.id,
            enabled=True
        )
        self.project.scenarios.extend([scen_start, scen_child, scen_end])
        self._refresh_scenario_table()
        # Select loop start
        self.tbl_scenarios.selectRow(len(self.project.scenarios) - 3)

    def _on_open_reference_gallery(self):
        """Open the Reference Gallery dialog."""
        from ui.reference_gallery_dialog import ReferenceGalleryDialog
        dlg = ReferenceGalleryDialog(project=self.project, target_hwnd=self.target_hwnd, parent=self)
        dlg.exec_()

    def _on_duplicate_scenario(self):
        rows = self.tbl_scenarios.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        cloned = copy.deepcopy(self.project.scenarios[row])
        import uuid
        cloned.id = f"scen_{uuid.uuid4().hex[:6]}"
        cloned.scenario_number = self.project.get_next_scenario_number()
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
        res = QMessageBox.question(self, "삭제 확인", f"시나리오 고유 #{scen.scenario_number} (실행 #{scen.step_number}) [{scen.name}]를 삭제하시겠습니까?")
        if res == QMessageBox.Yes:
            del self.project.scenarios[row]
            self._refresh_scenario_table()
            new_sel = min(row, len(self.project.scenarios) - 1)
            if new_sel >= 0:
                self.tbl_scenarios.selectRow(new_sel)

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

    # ==========================================
    # Target Window Management
    # ==========================================
    def _on_select_target_window(self):
        cur_w = getattr(self.project, "target_client_width", 1600)
        cur_h = getattr(self.project, "target_client_height", 900)
        cur_title = getattr(self.project, "target_window_title", "")
        dlg = WindowPickerDialog(
            current_hwnd=self.target_hwnd,
            current_width=cur_w,
            current_height=cur_h,
            current_title=cur_title,
            parent=self
        )
        if dlg.exec_() == WindowPickerDialog.Accepted and dlg.selected_window:
            self.target_hwnd = dlg.selected_window.hwnd
            self.project.target_window_title = dlg.selected_window.title
            self.project.target_client_width = dlg.selected_window.client_width
            self.project.target_client_height = dlg.selected_window.client_height
            self._save_app_config()
            self.inspector.set_target_hwnd(self.target_hwnd)
            self._update_target_label(dlg.selected_window)
            self._append_log("INFO", f"타겟 지정 완료: '{dlg.selected_window.title}' ({dlg.selected_window.client_width}×{dlg.selected_window.client_height})")

    def _on_focus_target_window(self):
        if self.target_hwnd:
            WindowManager.bring_to_foreground(self.target_hwnd)
        else:
            QMessageBox.information(
                self, "창 활성화 안내",
                "현재 실행 중인 특정 윈도우 창이 선택되지 않았습니다.\n(직접 지정 해상도 모드에서는 활성화할 윈도우가 없습니다.)"
            )

    def _update_target_label(self, win: Optional[WindowInfo]):
        pal = get_theme_colors(self.current_theme)
        if win:
            if win.hwnd:
                self.lbl_target_info.setText(
                    f"'{win.title}' (HWND: 0x{win.hwnd:X}, 해상도: {win.client_width}×{win.client_height})"
                )
            else:
                self.lbl_target_info.setText(
                    f"📐 직접 지정 해상도: {win.client_width}×{win.client_height} ('{win.title}')"
                )
            self.lbl_target_info.setStyleSheet(f"font-weight: bold; color: {pal['info']};")
        else:
            w = getattr(self.project, "target_client_width", 0)
            h = getattr(self.project, "target_client_height", 0)
            title = getattr(self.project, "target_window_title", "")
            if w > 0 and h > 0:
                self.lbl_target_info.setText(f"📐 기억된 해상도: {w}×{h} ('{title or '가상 타겟'}')")
                self.lbl_target_info.setStyleSheet(f"font-weight: bold; color: {pal['info']};")
            else:
                self.lbl_target_info.setText("선택된 창 없음 (창 선택 버튼을 클릭하세요)")
                self.lbl_target_info.setStyleSheet(f"font-weight: bold; color: {pal['warning']};")

    def _start_target_monitor_timer(self):
        self.timer_monitor = QTimer(self)
        self.timer_monitor.setInterval(1500)
        self.timer_monitor.timeout.connect(self._check_target_alive)
        self.timer_monitor.start()

    def _check_target_alive(self):
        if self.target_hwnd:
            win_info = WindowManager.get_window_info(self.target_hwnd)
            if not win_info:
                pal = get_theme_colors(self.current_theme)
                self.lbl_target_info.setText("⚠️ 타겟 창이 닫혔거나 감지되지 않습니다!")
                self.lbl_target_info.setStyleSheet(f"font-weight: bold; color: {pal['danger']};")
            else:
                self._update_target_label(win_info)

    # ==========================================
    # Execution Engine Control
    # ==========================================
    def _on_start_execution(self):
        if not self.target_hwnd:
            QMessageBox.warning(self, "타겟 창 필요", "먼저 상단에서 오토 입력을 수행할 타겟 게임 창을 선택해주세요.")
            return

        if self.runner and self.runner.isRunning():
            if self.runner._is_paused:
                self.runner.resume()
                self.lbl_run_status.setText("실행 중...")
                self.btn_pause.setText("⏸ 일시정지")
                return

        self.runner = WorkflowRunner(self.project, self.target_hwnd, parent=self)
        self.runner.sig_log.connect(self._append_log)
        self.runner.sig_scenario_started.connect(self._on_scenario_started)
        self.runner.sig_scenario_completed.connect(self._on_scenario_completed)
        self.runner.sig_finished.connect(self._on_runner_finished)

        self.btn_run.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_stop.setEnabled(True)
        self.lbl_run_status.setText("실행 중 (F5/F6)")
        self.lbl_run_status.setStyleSheet("color: #16a34a; font-weight: bold;")

        self.runner.start()

    def _on_pause_execution(self):
        if self.runner and self.runner.isRunning():
            if self.runner._is_paused:
                self.runner.resume()
                self.btn_pause.setText("⏸ 일시정지")
                self.lbl_run_status.setText("실행 중...")
                self.lbl_run_status.setStyleSheet("color: #16a34a; font-weight: bold;")
            else:
                self.runner.pause()
                self.btn_pause.setText("▶ 재개")
                self.lbl_run_status.setText("일시정지됨")
                self.lbl_run_status.setStyleSheet("color: #ea580c; font-weight: bold;")

    def _on_stop_execution(self):
        if self.runner:
            self.runner.stop()
            self.lbl_run_status.setText("정지 요청 중...")
            self.lbl_run_status.setStyleSheet("color: #dc2626; font-weight: bold;")

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
                self.tbl_scenarios.selectRow(row)
                break

    def _on_scenario_completed(self, scenario_id: str, result: str):
        pass

    def _on_runner_finished(self, reason: str):
        self.btn_run.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.btn_pause.setText("⏸ 일시정지")
        self.lbl_run_status.setText(f"완료 ({reason})")
        self.lbl_run_status.setStyleSheet("font-weight: bold;")

    def _append_log(self, level: str, msg: str):
        pal = get_theme_colors(self.current_theme)
        color_map = {
            "INFO": pal["log_info"],
            "ACTION": pal["log_action"],
            "SUCCESS": pal["log_success"],
            "WARN": pal["log_warn"],
            "ERROR": pal["log_error"],
            "USER": pal["log_user"]
        }
        color = color_map.get(level, pal["text_primary"])
        prefix_color = "#64748b" if pal["is_light"] else "#8da4c4"
        html = f"<span style='color: {prefix_color};'>[{level}]</span> <span style='color: {color};'>{msg}</span>"
        self.txt_log.append(html)
        if self.chk_autoscroll.isChecked():
            sb = self.txt_log.verticalScrollBar()
            sb.setValue(sb.maximum())

    def _on_loop_count_changed(self, val: int):
        self.project.loop_count = val

    def _on_loop_delay_changed(self, val: float):
        self.project.loop_delay_seconds = val

    # ==========================================
    # Save & Open Project
    # ==========================================
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
                if self.project.scenarios:
                    self.tbl_scenarios.selectRow(0)
                self.status_bar.showMessage(f"프로젝트 불러오기 완료: {path}", 4000)
            except Exception as e:
                QMessageBox.critical(self, "열기 오류", f"프로젝트를 불러올 수 없습니다:\n{e}")

    # ==========================================
    # Hotkeys
    # ==========================================
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
