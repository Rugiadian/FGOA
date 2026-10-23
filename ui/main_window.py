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
import re
import html
from typing import Optional, Dict, List, Tuple, Any
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox, QToolBar,
    QFileDialog, QMessageBox, QSplitter, QTextEdit, QTextBrowser, QStatusBar,
    QFrame, QAbstractItemView, QShortcut, QDockWidget, QMenu,
    QAction, QInputDialog, QSizePolicy, QApplication, QTabWidget, QStyle,
    QDialog, QColorDialog
)
from PyQt5.QtGui import QColor, QFont, QIcon, QKeySequence, QDrag, QCursor, QPixmap
from PyQt5.QtCore import Qt, QTimer, QFileSystemWatcher, QProcess, QByteArray, pyqtSignal, QMimeData, QSize, QPoint

from core.models import Project, Scenario, Condition, Action, ColorPoint, ActionSequence, make_block_palette
from core.window_manager import WindowManager, WindowInfo
from core.evaluator import ConditionEvaluator
from core.runner import WorkflowRunner
from core.preset_manager import PresetManager
from core.version import __version__
from ui.theme import get_stylesheet, get_theme_colors, CHECK_ICON_PATH
from ui.window_picker_dialog import WindowPickerDialog
from ui.inspector_widget import InspectorWidget
from ui.modules_manager_widget import ModulesManagerWidget
from ui.widgets.color_badge import WarningBadge
from ui.widgets.flow_layout import FlowLayout
from ui.preset_dialog import SavePresetDialog, PresetManagerDialog
from ui.action_overlay import ActionOverlayWindow
from ui.anti_ban_dialog import AntiBanDialog
from ui.virtual_canvas_window import VirtualCanvasWindow
from ui.anti_burn_in_overlay import AntiBurnInOverlay
from ui.image_preview_dialog import show_image_preview
from ui.custom_spinbox import NoWheelComboBox, NoWheelSpinBox
from core.global_hotkey import GlobalHotkeyListener
from ui.floating_stop_widget import GlobalFloatingStopWidget
from ui.custom_spinbox import CustomSpinBox
from core.path_utils import to_absolute_path, to_relative_path
from core.config import get_config_filepath
from ui.main_window_parts import (
    MainWindowLogMixin,
    MainWindowConfigLifecycleMixin,
    MainWindowPlaybackMixin,
    MainWindowTargetMixin,
    MainWindowLayoutThemeMixin,
    MainWindowTableMixin,
)


CONFIG_FILE = get_config_filepath()
TEMP_RELOAD_FILE = "_temp_reload_project.json"

# Modular components extracted for token optimization & clean architecture
from ui.scenario_table_widget import ScenarioVerticalHeader, DraggableScenarioTableWidget


class ResponsiveTabWidget(QTabWidget):
    """
    QTabWidget that reports its minimumSizeHint based on the current active tab
    rather than the maximum of all tabs, allowing parent dock/splitter containers
    to shrink when a compact tab is active.
    """
    def minimumSizeHint(self) -> QSize:
        cur = self.currentWidget()
        if cur:
            sz = cur.minimumSizeHint()
            tb = self.tabBar()
            tb_h = tb.height() if tb else 28
            return QSize(max(180, sz.width()), max(100, sz.height() + tb_h))
        return super().minimumSizeHint()

    def sizeHint(self) -> QSize:
        cur = self.currentWidget()
        if cur:
            return cur.sizeHint()
        return super().sizeHint()


class MainWindow(
    MainWindowConfigLifecycleMixin,
    MainWindowPlaybackMixin,
    MainWindowTargetMixin,
    MainWindowLayoutThemeMixin,
    MainWindowTableMixin,
    MainWindowLogMixin,
    QMainWindow,
):
    """
    Main application window with 3-Pane (Scenario Table | Inspector | Realtime Log) layout
    and full Light/Dark mode support.
    """

    def __init__(self):
        super().__init__()
        self.project = Project()
        self.target_hwnd: int = 0
        self.runner: Optional[WorkflowRunner] = None
        self._current_run_loop: int = 0
        self._last_loop_duration: float = 0.0
        self._last_config_target_title: str = ""
        self.current_project_path: Optional[str] = None
        self.last_project_path: Optional[str] = None
        self.virtual_canvas_window: Optional[VirtualCanvasWindow] = None
        self.anti_burn_overlay: AntiBurnInOverlay = AntiBurnInOverlay(self)
        self.current_theme: str = "light"  # Default to light mode

        self._update_window_title()
        self.resize(1380, 880)
        self.setMinimumSize(1020, 650)

        self.custom_layouts: Dict[str, str] = {}
        self.current_layout_name: str = "기본 3열 (Default)"
        self._saved_dock_state: Optional[str] = None

        # Scenario list Undo / Redo history
        self.scenario_undo_stack: List[Tuple[str, List[Dict[str, Any]]]] = []
        self.scenario_redo_stack: List[Tuple[str, List[Dict[str, Any]]]] = []
        self._is_undoing_redoing_scenario: bool = False
        self._current_running_row: Optional[int] = None
        self._paused_scenario_id: Optional[str] = None
        self._last_running_scenario_id: Optional[str] = None

        # Debounced auto-save timer for window geometry & position/size changes
        self._config_save_timer = QTimer(self)
        self._config_save_timer.setSingleShot(True)
        self._config_save_timer.setInterval(600)
        self._config_save_timer.timeout.connect(self._save_app_config)

        # Load user settings
        self._load_app_config()

        # Check for reload state or auto-restore last used project
        reloaded = self._check_reload_state()
        if not reloaded and self.last_project_path and os.path.isfile(self.last_project_path):
            try:
                with open(self.last_project_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.project = Project.from_dict(data)
                self.current_project_path = self.last_project_path
                self._update_window_title()
            except Exception:
                self.current_project_path = None

        # Sample initial scenario if empty
        self._init_sample_project()

        self._init_ui()
        self._init_layout_and_docks()
        self._apply_ui_config()
        self._apply_theme()
        self._refresh_scenario_table()
        self._update_target_label(None)
        self._auto_track_target_window()
        self._start_target_monitor_timer()
        self._init_code_watcher()

        if self.current_project_path:
            self.status_bar.showMessage(f"📂 마지막 사용 프로젝트 자동 복원 완료: {os.path.basename(self.current_project_path)}", 4000)

        # Check if previous crash log exists
        from core.logger import CRASH_LOG_PATH
        if os.path.exists(CRASH_LOG_PATH) and os.path.getsize(CRASH_LOG_PATH) > 0:
            self.status_bar.showMessage("⚠️ 이전 크래시 로그가 기록되어 있습니다. 상단 [📋 에러 로그] 버튼으로 확인하세요.", 8000)

        # Initial selection to first scenario
        if self.project.scenarios:
            self.tbl_scenarios.selectRow(0)

        # Global hotkey and floating emergency stop widget
        self._init_global_hotkey_and_floating_stop()

    # Configuration, Global Hotkeys & Window Lifecycle events are in MainWindowConfigLifecycleMixin (ui/main_window_parts/config_lifecycle.py)

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
        # 0. Setup Window Docking Features (Unity style)
        self.setDockNestingEnabled(True)
        self.setDockOptions(
            QMainWindow.AllowNestedDocks | QMainWindow.AllowTabbedDocks | QMainWindow.AnimatedDocks | QMainWindow.GroupedDragging
        )
        self.setCorner(Qt.TopLeftCorner, Qt.LeftDockWidgetArea)
        self.setCorner(Qt.BottomLeftCorner, Qt.LeftDockWidgetArea)
        self.setCorner(Qt.TopRightCorner, Qt.RightDockWidgetArea)
        self.setCorner(Qt.BottomRightCorner, Qt.RightDockWidgetArea)

        dummy_central = QWidget()
        dummy_central.setMaximumSize(0, 0)
        self.setCentralWidget(dummy_central)

        # 1. Top Target Window & Layout Selector Bar (2-Row Wrapped Layout)
        target_frame = QFrame()
        target_frame.setObjectName("card_frame")
        target_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        t_main_layout = QVBoxLayout(target_frame)
        t_main_layout.setContentsMargins(10, 6, 10, 6)
        t_main_layout.setSpacing(6)

        # ----------------------------------------------------
        # Row 1: Target Window & Authoring Resolution Settings
        # ----------------------------------------------------
        row1_layout = QHBoxLayout()
        row1_layout.setContentsMargins(0, 0, 0, 0)
        row1_layout.setSpacing(6)

        row1_layout.addWidget(QLabel("🎯 대상 게임 창:"))
        self.lbl_target_info = QLabel("선택된 창 없음 (창 선택 버튼을 클릭하세요)")
        self.lbl_target_info.setStyleSheet("font-weight: bold; color: #d97706;")
        row1_layout.addWidget(self.lbl_target_info, 1)

        btn_select_win = QPushButton("창 선택...")
        btn_select_win.setObjectName("btn_primary")
        btn_select_win.clicked.connect(self._on_select_target_window)
        row1_layout.addWidget(btn_select_win)

        btn_focus_win = QPushButton("창 활성화")
        btn_focus_win.clicked.connect(self._on_focus_target_window)
        row1_layout.addWidget(btn_focus_win)

        btn_virtual_canvas = QPushButton("🎨 가상 캔버스")
        btn_virtual_canvas.setToolTip("타깃 게임 창 없이 테스트/시뮬레이션을 수행할 수 있는 가상 캔버스 창을 띄웁니다.")
        btn_virtual_canvas.clicked.connect(self._on_open_virtual_canvas)
        row1_layout.addWidget(btn_virtual_canvas)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.VLine)
        sep1.setFrameShadow(QFrame.Sunken)
        sep1.setStyleSheet("color: #94a3b8; margin: 2px 4px;")
        row1_layout.addWidget(sep1)

        # Scenario Authoring Resolution Display
        self.lbl_authoring_res = QLabel()
        self.lbl_authoring_res.setObjectName("lbl_authoring_res")
        self.lbl_authoring_res.setContextMenuPolicy(Qt.CustomContextMenu)
        self.lbl_authoring_res.customContextMenuRequested.connect(self._on_authoring_res_context_menu)
        row1_layout.addWidget(self.lbl_authoring_res)

        # Register Authoring Reference Image Button (Menu dropdown)
        self.btn_register_ref_img = QPushButton("🖼️ 기준 이미지 등록 ▼")
        self.btn_register_ref_img.setToolTip(
            "시나리오 제작 기준 해상도를 추적/지정할 레퍼런스 이미지를 등록합니다.\n"
            "- 레퍼런스 갤러리 또는 파일 탐색기에서 선택 가능\n"
            "- 이미지 크기에 맞추어 제작 기준 해상도가 자동 설정됩니다."
        )
        self.btn_register_ref_img.clicked.connect(self._on_show_authoring_menu)
        self.btn_register_ref_img.setContextMenuPolicy(Qt.CustomContextMenu)
        self.btn_register_ref_img.customContextMenuRequested.connect(self._on_authoring_res_context_menu)
        row1_layout.addWidget(self.btn_register_ref_img)

        btn_gallery = QPushButton("🖼️ 레퍼런스 갤러리")
        btn_gallery.setToolTip("참조 이미지 보관함 및 어느 조건/액션에서 사용 중인지 확인합니다.")
        btn_gallery.clicked.connect(self._on_open_reference_gallery)
        row1_layout.addWidget(btn_gallery)

        t_main_layout.addLayout(row1_layout)

        # ----------------------------------------------------
        # Row 2: Layout, Tools, Reload & Quick Controls
        # ----------------------------------------------------
        row2_layout = QHBoxLayout()
        row2_layout.setContentsMargins(0, 0, 0, 0)
        row2_layout.setSpacing(6)

        # Unity-style Dynamic Layout Selector
        row2_layout.addWidget(QLabel("📐 레이아웃:"))
        self.combo_layout = NoWheelComboBox()
        self.combo_layout.setObjectName("combo_layout")
        self.combo_layout.setMinimumWidth(135)
        self.combo_layout.setToolTip("유니티 스타일 유동적 레이아웃 전환 (기본/와이드/세로/탭/인스펙터 전면 등)")
        self.combo_layout.currentTextChanged.connect(self._on_layout_combo_changed)
        row2_layout.addWidget(self.combo_layout)

        # Unity-style Window/Panels Menu
        self.btn_panels_menu = QPushButton("🪟 패널 표시 ▼")
        self.btn_panels_menu.setToolTip("패널(시나리오 목록, 인스펙터, 실행 로그) 표시/숨김 상태 제어")
        row2_layout.addWidget(self.btn_panels_menu)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.VLine)
        sep2.setFrameShadow(QFrame.Sunken)
        sep2.setStyleSheet("color: #94a3b8; margin: 2px 4px;")
        row2_layout.addWidget(sep2)

        # Hot Reload Controls
        self.chk_hot_reload = QCheckBox("코드 자동 리로드")
        self.chk_hot_reload.setChecked(False)
        self.chk_hot_reload.setToolTip("코드(.py) 파일 수정 저장 시 프로그램을 즉시 자동 재시작합니다.")
        self.chk_hot_reload.toggled.connect(lambda _: self._save_app_config())
        row2_layout.addWidget(self.chk_hot_reload)

        btn_reload = QPushButton("🔄 리로드 (Ctrl+R)")
        btn_reload.setToolTip("프로그램을 즉시 리로드합니다. (단축키: Ctrl+R / F8)")
        btn_reload.clicked.connect(self._reload_application)
        row2_layout.addWidget(btn_reload)

        btn_error_log = QPushButton("📋 에러 로그")
        btn_error_log.setToolTip("오류 발생 기록(fgoa_crash.log)을 텍스트 편집기로 엽니다.")
        btn_error_log.clicked.connect(self._on_open_crash_log)
        row2_layout.addWidget(btn_error_log)

        sep3 = QFrame()
        sep3.setFrameShape(QFrame.VLine)
        sep3.setFrameShadow(QFrame.Sunken)
        sep3.setStyleSheet("color: #94a3b8; margin: 2px 4px;")
        row2_layout.addWidget(sep3)

        self.btn_popup_playbar = QPushButton("🎮 플레이바 (F4)")
        self.btn_popup_playbar.setCheckable(True)
        self.btn_popup_playbar.setToolTip("항상 위에 떠 있는 미니 플레이바 창을 열거나 닫습니다. (단축키: F4)")
        self.btn_popup_playbar.clicked.connect(self._toggle_popup_playbar)
        row2_layout.addWidget(self.btn_popup_playbar)

        row2_layout.addStretch()

        # Theme Toggle Button
        self.btn_theme_toggle = QPushButton()
        self.btn_theme_toggle.setObjectName("btn_theme")
        self.btn_theme_toggle.clicked.connect(self._toggle_theme)
        self._update_theme_toggle_btn()
        row2_layout.addWidget(self.btn_theme_toggle)

        t_main_layout.addLayout(row2_layout)

        # Initial authoring resolution display update
        self._update_authoring_resolution_display()

        # Top ToolBar
        self.top_toolbar = QToolBar("Target & Tools", self)
        self.top_toolbar.setObjectName("TopToolBar")
        self.top_toolbar.setMovable(False)
        self.top_toolbar.setFloatable(False)
        self.top_toolbar.setStyleSheet("border: none; padding: 0px; margin: 2px 4px;")
        self.top_toolbar.addWidget(target_frame)
        self.addToolBar(Qt.TopToolBarArea, self.top_toolbar)

        # ==========================================
        # Pane 1: Left (Scenario Table & Sequence Toolbar)
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

        # Toolbar with responsive FlowLayout + dedicated bottom row for reorder & undo/redo
        tb_container = QWidget()
        tb_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        tb_v_layout = QVBoxLayout(tb_container)
        tb_v_layout.setContentsMargins(0, 0, 0, 0)
        tb_v_layout.setSpacing(4)

        # Row 1 (Upper tools wrapped with FlowLayout): CRUD, Folder, Loops, Presets, Save/Load
        row1_flow_widget = QWidget()
        row1_flow_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        row1_flow = FlowLayout(row1_flow_widget, margin=0, spacing=4)

        btn_new_scen = QPushButton("📄 새 시나리오")
        btn_new_scen.setToolTip("노드가 하나도 없는 완전히 빈 새 시나리오 프로젝트를 생성합니다. (Ctrl+N)")
        btn_new_scen.clicked.connect(self._on_new_scenario_project)
        row1_flow.addWidget(btn_new_scen)

        btn_add = QPushButton("➕ 추가")
        btn_add.clicked.connect(self._on_add_scenario)
        row1_flow.addWidget(btn_add)

        btn_add_folder = QPushButton("📁 폴더 추가")
        btn_add_folder.setToolTip("시인성 향상 및 시나리오 목록 정리를 위한 그룹 폴더를 추가합니다. (진행에 영향 없음)")
        btn_add_folder.clicked.connect(self._on_add_folder)
        row1_flow.addWidget(btn_add_folder)

        btn_add_loop = QPushButton("🔁 루프 추가")
        btn_add_loop.setToolTip("루프 시작과 종료 노드로 구성된 루프 블록을 추가합니다.")
        btn_add_loop.clicked.connect(self._on_add_loop_block)
        row1_flow.addWidget(btn_add_loop)

        btn_dup = QPushButton("📋 복제")
        btn_dup.clicked.connect(self._on_duplicate_scenario)
        row1_flow.addWidget(btn_dup)

        btn_del = QPushButton("🗑️ 삭제")
        btn_del.clicked.connect(self._on_delete_scenario)
        row1_flow.addWidget(btn_del)

        # PRESET BUTTON
        self.btn_preset = QPushButton("📦 프리셋 ▼")
        self.btn_preset.setObjectName("btn_preset")
        self.btn_preset.setToolTip("시나리오 프리셋 선택 저장 및 불러오기 (단축키: Ctrl+L / Ctrl+Shift+S)")
        menu_preset = QMenu(self)

        act_load_preset = menu_preset.addAction("📥 프리셋 불러오기... (Ctrl+L)")
        act_load_preset.triggered.connect(self._on_open_preset_manager)

        act_save_preset = menu_preset.addAction("💾 선택한 시나리오 프리셋 저장... (Ctrl+Shift+S)")
        act_save_preset.triggered.connect(self._on_save_preset)

        menu_preset.addSeparator()

        sub_quick = menu_preset.addMenu("⚡ 빠른 기본 프리셋 추가")
        act_q1 = sub_quick.addAction("[기본] 전투 사이클 템플릿")
        act_q1.triggered.connect(lambda: self._on_quick_load_preset("preset_battle_cycle"))
        act_q2 = sub_quick.addAction("[기본] 단순 반복 클릭 및 딜레이")
        act_q2.triggered.connect(lambda: self._on_quick_load_preset("preset_click_delay"))
        act_q3 = sub_quick.addAction("[기본] 5회 카운트 루프 블록")
        act_q3.triggered.connect(lambda: self._on_quick_load_preset("preset_loop_block"))

        self.btn_preset.setMenu(menu_preset)
        row1_flow.addWidget(self.btn_preset)

        btn_save_proj = QPushButton("💾 저장")
        btn_save_proj.setToolTip("불러들인 파일에 바로 저장 (Ctrl+S)")
        btn_save_proj.clicked.connect(self._on_save_project)
        row1_flow.addWidget(btn_save_proj)

        btn_save_as_proj = QPushButton("💾 다른이름 저장")
        btn_save_as_proj.setToolTip("새로운 파일로 다른 이름 저장")
        btn_save_as_proj.clicked.connect(self._on_save_project_as)
        row1_flow.addWidget(btn_save_as_proj)

        btn_open_proj = QPushButton("📂 열기")
        btn_open_proj.clicked.connect(self._on_open_project)
        row1_flow.addWidget(btn_open_proj)

        tb_v_layout.addWidget(row1_flow_widget)

        # Row 2 (마지막 줄): 순서 위, 아래 이동, 취소, 다시(redo) 를 한 그룹으로 마지막 줄에 배치
        row2_reorder_bar = QWidget()
        row2_reorder_bar.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        row2_reorder_layout = FlowLayout(row2_reorder_bar, margin=0, spacing=4)

        btn_up = QPushButton("⬆️ 위로")
        btn_up.setToolTip("선택한 시나리오를 한 줄 위로 이동")
        btn_up.clicked.connect(self._on_move_up)
        row2_reorder_layout.addWidget(btn_up)

        btn_down = QPushButton("⬇️ 아래로")
        btn_down.setToolTip("선택한 시나리오를 한 줄 아래로 이동")
        btn_down.clicked.connect(self._on_move_down)
        row2_reorder_layout.addWidget(btn_down)

        # Undo / Redo for Scenario List
        self.btn_undo_scenario = QPushButton("↩️ 취소")
        self.btn_undo_scenario.setToolTip("시나리오 목록 변경 작업 실행 취소 (Ctrl+Z)")
        self.btn_undo_scenario.clicked.connect(self._undo_scenario)
        self.btn_undo_scenario.setEnabled(False)
        row2_reorder_layout.addWidget(self.btn_undo_scenario)

        self.btn_redo_scenario = QPushButton("▶️ 다시")
        self.btn_redo_scenario.setToolTip("취소한 시나리오 목록 변경 작업 다시 실행 (Ctrl+Y / Ctrl+Shift+Z)")
        self.btn_redo_scenario.clicked.connect(self._redo_scenario)
        self.btn_redo_scenario.setEnabled(False)
        row2_reorder_layout.addWidget(self.btn_redo_scenario)

        # Column visibility button with dropdown menu
        self.btn_col_visibility = QPushButton("👁️ 열 보기 ▼")
        self.btn_col_visibility.setToolTip("시나리오 목록의 표시할 열(인식조건, 액션 시퀀스, 분기)을 선택합니다.")
        row2_reorder_layout.addWidget(self.btn_col_visibility)

        tb_v_layout.addWidget(row2_reorder_bar)

        l_layout.addWidget(tb_container)

        # Scenario Table (Full height)
        self.tbl_scenarios = DraggableScenarioTableWidget()
        self.tbl_scenarios.setColumnCount(7)
        self.tbl_scenarios.sig_row_reordered.connect(self._on_scenario_row_reordered)
        self.tbl_scenarios.sig_delete_requested.connect(self._on_delete_scenario)
        self.tbl_scenarios.setHorizontalHeaderLabels([
            "스냅샷", "고유 ID", "활성", "시나리오 이름", "인식조건 모듈", "액션시퀀스 모듈", "분기"
        ])
        
        # Responsive header resizing (Interactive mode allowing user adjustment and dynamic proportionality)
        header = self.tbl_scenarios.horizontalHeader()
        for col_idx in range(7):
            header.setSectionResizeMode(col_idx, QHeaderView.Interactive)
        self.tbl_scenarios.adjust_column_widths()
        self.tbl_scenarios.verticalHeader().setDefaultSectionSize(26)

        # Connect column visibility menu and auto-save
        self.btn_col_visibility.setMenu(self.tbl_scenarios.create_column_visibility_menu(self.btn_col_visibility))
        self.tbl_scenarios.sig_column_visibility_changed.connect(lambda col, vis: self._save_app_config())

        # Restore cached column visibility if present
        if hasattr(self, "_cached_config") and self._cached_config:
            cols_vis = self._cached_config.get("scenario_columns_visible")
            if isinstance(cols_vis, dict):
                self.tbl_scenarios.set_column_visibility_state(cols_vis)

        self.tbl_scenarios.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_scenarios.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tbl_scenarios.setAlternatingRowColors(True)
        self.tbl_scenarios.itemSelectionChanged.connect(self._on_table_selection_changed)
        self.tbl_scenarios.cellDoubleClicked.connect(self._on_scenario_cell_double_clicked)
        self.tbl_scenarios.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tbl_scenarios.customContextMenuRequested.connect(self._on_scenario_context_menu)
        l_layout.addWidget(self.tbl_scenarios, 1)

        # Dock 1: Left Pane (Scenarios & Modules Responsive Tab Widget)
        self.tab_scenario_manager = ResponsiveTabWidget()
        self.tab_scenario_manager.setObjectName("TabScenarioManager")
        self.tab_scenario_manager.addTab(left_pane, "📜 시나리오 흐름")

        self.modules_widget = ModulesManagerWidget(self.project, self.target_hwnd, parent=self)
        self.modules_widget.sig_module_changed.connect(self._on_modules_changed)
        self.modules_widget.sig_log.connect(self._append_log)
        self.tab_scenario_manager.addTab(self.modules_widget, "🧩 모듈 / 노드 목록")
        self.tab_scenario_manager.currentChanged.connect(lambda _: self.dock_scenarios.updateGeometry())

        self.dock_scenarios = QDockWidget("📜 시나리오 및 모듈 (Hierarchy)", self)
        self.dock_scenarios.setObjectName("DockScenarios")
        self.dock_scenarios.setFeatures(
            QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable | QDockWidget.DockWidgetClosable
        )
        self.dock_scenarios.setWidget(self.tab_scenario_manager)
        self.dock_scenarios.setMinimumWidth(280)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_scenarios)

        # ==========================================
        # Pane 2: Center (Unity-Style Always-Open Inspector)
        # ==========================================
        self.inspector = InspectorWidget(self)
        self.inspector.hide()
        self.inspector.sig_scenario_saved.connect(self._on_inspector_scenario_saved)
        self.inspector.sig_scenario_changed.connect(self._on_inspector_scenario_changed)
        self.inspector.sig_modules_manager_requested.connect(lambda: self.tab_scenario_manager.setCurrentIndex(1))
        self.inspector.sig_log.connect(self._append_log)

        # Dock 2: Condition & Branching Pane (Inspector: Conditions)
        self.dock_inspector = QDockWidget("👁️ 인식 조건 및 분기 (Conditions)", self)
        self.dock_inspector.setObjectName("DockInspector")
        self.dock_inspector.setFeatures(
            QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable | QDockWidget.DockWidgetClosable
        )
        self.dock_inspector.setWidget(self.inspector.condition_panel)
        self.dock_inspector.setMinimumWidth(200)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_inspector)

        # Dock 2-B: Action Sequence Pane (Inspector: Actions)
        self.dock_actions = QDockWidget("✋ 액션 시퀀스 (Actions)", self)
        self.dock_actions.setObjectName("DockActions")
        self.dock_actions.setFeatures(
            QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable | QDockWidget.DockWidgetClosable
        )
        self.dock_actions.setWidget(self.inspector.action_panel)
        self.dock_actions.setMinimumWidth(200)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_actions)

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

        self.chk_robust_trace = QCheckBox("강력 로그추적")
        self.chk_robust_trace.setToolTip("각 로그 출력 시 화면 스크린샷을 자동 촬영하여 링크합니다 (최소 1초 간격, 초고속 저화질).")
        self.chk_robust_trace.toggled.connect(self._on_robust_trace_toggled)
        log_header.addWidget(self.chk_robust_trace)

        self.btn_delete_trace = QPushButton("🗑️ 추적 폴더 일괄 삭제")
        self.btn_delete_trace.setFixedHeight(22)
        self.btn_delete_trace.setToolTip("강력 로그추적으로 생성된 모든 스크린샷 및 루프 폴더를 일괄 삭제합니다.")
        self.btn_delete_trace.clicked.connect(self._on_delete_trace_logs)
        log_header.addWidget(self.btn_delete_trace)

        self.chk_autoscroll = QCheckBox("자동 스크롤")
        self.chk_autoscroll.setChecked(True)
        self.chk_autoscroll.toggled.connect(lambda _: self._save_app_config())
        log_header.addWidget(self.chk_autoscroll)

        btn_clear_log = QPushButton("비우기")
        btn_clear_log.setFixedHeight(22)
        btn_clear_log.clicked.connect(self._clear_logs)
        log_header.addWidget(btn_clear_log)
        r_layout.addLayout(log_header)

        # Text Browser Log (Takes full height, supports interactive collapsible anchors)
        self.txt_log = QTextBrowser()
        self.txt_log.setReadOnly(True)
        self.txt_log.setOpenLinks(False)
        self.txt_log.anchorClicked.connect(self._on_log_anchor_clicked)
        log_font = QFont("Consolas", 9)
        log_font.setStyleHint(QFont.Monospace)
        self.txt_log.setFont(log_font)
        self.txt_log.document().setMaximumBlockCount(1000)
        r_layout.addWidget(self.txt_log, 1)

        # Dock 3: Right Pane (Log)
        self.dock_log = QDockWidget("📋 실시간 실행 로그 (Console)", self)
        self.dock_log.setObjectName("DockLog")
        self.dock_log.setFeatures(
            QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable | QDockWidget.DockWidgetClosable
        )
        self.dock_log.setWidget(right_log_pane)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock_log)

        # Panels toggle menu
        menu_panels = QMenu(self)
        act_dock_scen = self.dock_scenarios.toggleViewAction()
        act_dock_scen.setText("📜 시나리오 목록 (Hierarchy)")
        menu_panels.addAction(act_dock_scen)

        act_dock_insp = self.dock_inspector.toggleViewAction()
        act_dock_insp.setText("👁️ 인식 조건 및 분기 (Conditions)")
        menu_panels.addAction(act_dock_insp)

        act_dock_act = self.dock_actions.toggleViewAction()
        act_dock_act.setText("✋ 액션 시퀀스 (Actions)")
        menu_panels.addAction(act_dock_act)

        act_dock_log = self.dock_log.toggleViewAction()
        act_dock_log.setText("📋 실시간 실행 로그 (Console)")
        menu_panels.addAction(act_dock_log)

        self.btn_panels_menu.setMenu(menu_panels)

        # Compatibility placeholder for legacy splitter
        self.main_h_splitter = None

        # 3. Execution Controller Bottom Bar (시나리오 재생 컨트롤 - 2줄 기능별 분류 레이아웃)
        ctrl_frame = QFrame()
        ctrl_frame.setObjectName("card_frame")
        ctrl_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        c_layout = QVBoxLayout(ctrl_frame)
        c_layout.setContentsMargins(10, 6, 10, 6)
        c_layout.setSpacing(6)

        # ----------------------------------------------------
        # Row 1: 시나리오 재생 실행 제어 & 시각화/플로팅 & 상태
        # ----------------------------------------------------
        row1_ctrl = QHBoxLayout()
        row1_ctrl.setContentsMargins(0, 0, 0, 0)
        row1_ctrl.setSpacing(6)

        lbl_playback_title = QLabel("▶ 시나리오 재생:")
        lbl_playback_title.setStyleSheet("font-weight: bold; font-size: 9.5pt;")
        row1_ctrl.addWidget(lbl_playback_title)

        self.btn_run = QPushButton("▶ 전체 시작 (F5)")
        self.btn_run.setObjectName("btn_run")
        self.btn_run.setToolTip("첫 번째 시나리오 노드부터 전체를 순차적으로 실행합니다. (단축키: F5)")
        self.btn_run.clicked.connect(self._on_start_all_execution)
        row1_ctrl.addWidget(self.btn_run)

        self.btn_run_selected = QPushButton("▶ 선택부터 시작 (Shift+F5)")
        self.btn_run_selected.setObjectName("btn_run_selected")
        self.btn_run_selected.setToolTip("현재 목록에서 선택된 시나리오 노드부터 이어서 실행합니다. (단축키: Shift+F5)")
        self.btn_run_selected.clicked.connect(self._on_start_selected_execution)
        row1_ctrl.addWidget(self.btn_run_selected)

        self.btn_pause = QPushButton("⏸ 일시정지 (Shift+F6)")
        self.btn_pause.setObjectName("btn_pause")
        self.btn_pause.setToolTip("실행 중인 시나리오를 일시정지하거나 재개합니다. (단축키: Shift+F6)")
        self.btn_pause.setEnabled(False)
        self.btn_pause.clicked.connect(self._on_pause_execution)
        row1_ctrl.addWidget(self.btn_pause)

        self.btn_stop = QPushButton("⏹ 정지 (F6)")
        self.btn_stop.setObjectName("btn_stop")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._on_stop_execution)
        row1_ctrl.addWidget(self.btn_stop)

        self.btn_step = QPushButton("⏭ 단일 스텝 (F7)")
        self.btn_step.setToolTip("선택한 시나리오 노드부터 1단계를 실행하고 다음 노드로 포인터를 이동한 뒤 일시정지합니다. (단축키: F7)")
        self.btn_step.clicked.connect(self._on_step_execution)
        row1_ctrl.addWidget(self.btn_step)

        sep_c1 = QFrame()
        sep_c1.setFrameShape(QFrame.VLine)
        sep_c1.setFrameShadow(QFrame.Sunken)
        sep_c1.setStyleSheet("color: #94a3b8; margin: 2px 4px;")
        row1_ctrl.addWidget(sep_c1)

        self.chk_action_overlay = QCheckBox("🎯 조작 시각화")
        self.chk_action_overlay.setChecked(True)
        self.chk_action_overlay.setToolTip("오토 실행 중 조작할 좌표나 범위를 앱 화면 위에 점선 박스/화살표로 시각화 표시합니다.")
        self.chk_action_overlay.toggled.connect(self._on_toggle_action_overlay)
        row1_ctrl.addWidget(self.chk_action_overlay)

        self.chk_floating_stop = QCheckBox("🛑 전역 플로팅 정지")
        self.chk_floating_stop.setChecked(False)
        self.chk_floating_stop.setToolTip("오토 실행 시 화면 최상위에 어디서나 마우스로 원클릭 정지 가능한 빨간색 플로팅 버튼을 자동 표시합니다.")
        self.chk_floating_stop.toggled.connect(self._on_toggle_floating_stop)
        row1_ctrl.addWidget(self.chk_floating_stop)

        self.chk_background_mode = QCheckBox("👻 백그라운드 제어")
        self.chk_background_mode.setObjectName("chk_background_mode")
        self.chk_background_mode.setChecked(False)
        self.chk_background_mode.setToolTip(
            "물리 마우스 커서를 움직이지 않고(PostMessage) 타겟 창에 직접 비활성 입력을 전송하며,\n"
            "창이 다른 프로그램에 가려져 있어도 백그라운드에서 화면을 인식합니다.\n"
            "(실행 중에도 웹 서핑, 문서 작업 등 다른 마우스 조작 가능)"
        )
        self.chk_background_mode.toggled.connect(self._on_toggle_background_mode)
        row1_ctrl.addWidget(self.chk_background_mode)

        row1_ctrl.addStretch()

        self.lbl_run_status = QLabel("대기 중")
        self.lbl_run_status.setStyleSheet("font-weight: bold; font-size: 10pt;")
        row1_ctrl.addWidget(self.lbl_run_status)

        c_layout.addLayout(row1_ctrl)

        # ----------------------------------------------------
        # Row 2: 반복 제어, 루프 간격, 안전/보안(안티밴), 디스플레이(번인 방지)
        # ----------------------------------------------------
        row2_ctrl = QHBoxLayout()
        row2_ctrl.setContentsMargins(0, 0, 0, 0)
        row2_ctrl.setSpacing(6)

        lbl_loop_icon = QLabel("🔁 반복 실행:")
        lbl_loop_icon.setStyleSheet("font-weight: bold; font-size: 9pt;")
        row2_ctrl.addWidget(lbl_loop_icon)

        self.spin_loops = CustomSpinBox()
        self.spin_loops.setObjectName("spin_loops")
        self.spin_loops.setRange(0, 99999)
        self.spin_loops.setValue(self.project.loop_count)
        self.spin_loops.setSpecialValueText("무한 반복 (∞)")
        self.spin_loops.setMinimumWidth(120)
        self.spin_loops.setToolTip("시나리오 전체 반복 실행 횟수 (0: 무한 반복, 1 이상: 지정 횟수 반복)")
        self.spin_loops.valueChanged.connect(self._on_loop_count_changed)
        row2_ctrl.addWidget(self.spin_loops)

        self.lbl_loop_progress = QLabel("(대기)")
        self.lbl_loop_progress.setStyleSheet("font-weight: bold; color: #64748b; font-size: 8.5pt;")
        self.lbl_loop_progress.setToolTip("현재 진행 중인 시나리오 루프 횟수")
        row2_ctrl.addWidget(self.lbl_loop_progress)

        sep_c2 = QFrame()
        sep_c2.setFrameShape(QFrame.VLine)
        sep_c2.setFrameShadow(QFrame.Sunken)
        sep_c2.setStyleSheet("color: #94a3b8; margin: 2px 4px;")
        row2_ctrl.addWidget(sep_c2)

        row2_ctrl.addWidget(QLabel("루프 간격:"))
        self.spin_loop_delay = QDoubleSpinBox()
        self.spin_loop_delay.setRange(0.0, 3600.0)
        self.spin_loop_delay.setValue(self.project.loop_delay_seconds)
        self.spin_loop_delay.setSuffix(" 초")
        self.spin_loop_delay.valueChanged.connect(self._on_loop_delay_changed)
        row2_ctrl.addWidget(self.spin_loop_delay)

        sep_c3 = QFrame()
        sep_c3.setFrameShape(QFrame.VLine)
        sep_c3.setFrameShadow(QFrame.Sunken)
        sep_c3.setStyleSheet("color: #94a3b8; margin: 2px 4px;")
        row2_ctrl.addWidget(sep_c3)

        self.btn_anti_ban = QPushButton("🛡️ 안티밴 설정...")
        self.btn_anti_ban.setObjectName("btn_anti_ban")
        self.btn_anti_ban.setToolTip("타임 지연 및 좌표 오프셋 안티밴 설정을 엽니다.")
        self.btn_anti_ban.clicked.connect(self._on_open_anti_ban_dialog)
        row2_ctrl.addWidget(self.btn_anti_ban)

        sep_c4 = QFrame()
        sep_c4.setFrameShape(QFrame.VLine)
        sep_c4.setFrameShadow(QFrame.Sunken)
        sep_c4.setStyleSheet("color: #94a3b8; margin: 2px 4px;")
        row2_ctrl.addWidget(sep_c4)

        # Monitor Burn-in Prevention
        self.chk_anti_burn = QCheckBox("🖥️ 번인 방지")
        self.chk_anti_burn.setChecked(False)
        self.chk_anti_burn.setToolTip("지정한 n분 주기마다 화면을 서서히 블랙으로 전환하여 모니터 번인을 방지합니다. (조작 간섭 없음, 긴급탈출: F12)")
        self.chk_anti_burn.toggled.connect(self._on_toggle_anti_burn)
        row2_ctrl.addWidget(self.chk_anti_burn)

        self.combo_anti_burn_mode = NoWheelComboBox()
        self.combo_anti_burn_mode.addItem("모드 1: 앱 창", 1)
        self.combo_anti_burn_mode.addItem("모드 2: 전체 화면 (데스크탑)", 2)
        self.combo_anti_burn_mode.setToolTip("번인 방지 모드 선택:\n- 모드 1: FGOA 창 내부 화면 전환\n- 모드 2: 모니터 데스크탑 전체 화면 전환 (해상도 무관)")
        self.combo_anti_burn_mode.currentIndexChanged.connect(self._on_anti_burn_mode_changed)
        row2_ctrl.addWidget(self.combo_anti_burn_mode)

        self.spin_anti_burn_min = NoWheelSpinBox()
        self.spin_anti_burn_min.setRange(1, 120)
        self.spin_anti_burn_min.setValue(5)
        self.spin_anti_burn_min.setSuffix("분 주기")
        self.spin_anti_burn_min.setToolTip("번인 방지 화면 전환 주기 (1~120분)")
        self.spin_anti_burn_min.valueChanged.connect(self._on_anti_burn_interval_changed)
        row2_ctrl.addWidget(self.spin_anti_burn_min)

        self.spin_anti_burn_hold_min = NoWheelSpinBox()
        self.spin_anti_burn_hold_min.setRange(1, 120)
        self.spin_anti_burn_hold_min.setValue(1)
        self.spin_anti_burn_hold_min.setSuffix("분 유지")
        self.spin_anti_burn_hold_min.setToolTip("블랙 상태로 머무는 시간 (1~120분 단위)")
        self.spin_anti_burn_hold_min.valueChanged.connect(self._on_anti_burn_hold_changed)
        row2_ctrl.addWidget(self.spin_anti_burn_hold_min)

        self.btn_test_anti_burn = QPushButton("🧪 테스트")
        self.btn_test_anti_burn.setObjectName("btn_test_anti_burn")
        self.btn_test_anti_burn.setToolTip("선택한 번인 방지 모드의 화면 전환 효과를 즉시 1회 테스트합니다. (실행 중 클릭 시 중지, 긴급탈출: F12)")
        self.btn_test_anti_burn.clicked.connect(self._on_test_anti_burn)
        row2_ctrl.addWidget(self.btn_test_anti_burn)

        if hasattr(self, "anti_burn_overlay") and self.anti_burn_overlay:
            self.anti_burn_overlay.sig_transition_started.connect(self._on_anti_burn_started)
            self.anti_burn_overlay.sig_transition_finished.connect(self._on_anti_burn_finished)

        row2_ctrl.addStretch()
        c_layout.addLayout(row2_ctrl)

        # Bottom ToolBar
        self.bottom_toolbar = QToolBar("시나리오 재생 컨트롤", self)
        self.bottom_toolbar.setObjectName("BottomToolBar")
        self.bottom_toolbar.setMovable(False)
        self.bottom_toolbar.setFloatable(False)
        self.bottom_toolbar.setStyleSheet("border: none; padding: 0px; margin: 2px 4px;")
        self.bottom_toolbar.addWidget(ctrl_frame)
        self.addToolBar(Qt.BottomToolBarArea, self.bottom_toolbar)

        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage(f"준비 완료 - FGOA v{__version__} 화면 인식 스마트 오토 툴")

        # Shortcuts
        self.sc_reload = QShortcut(QKeySequence("Ctrl+R"), self)
        self.sc_reload.activated.connect(self._reload_application)

        self.sc_f8 = QShortcut(QKeySequence("F8"), self)
        self.sc_f8.activated.connect(self._reload_application)

        # Single Step Shortcuts (F7 / F10)
        self.sc_f7 = QShortcut(QKeySequence("F7"), self)
        self.sc_f7.activated.connect(self._on_step_execution)

        self.sc_f10 = QShortcut(QKeySequence("F10"), self)
        self.sc_f10.activated.connect(self._on_step_execution)

        # Action sequence visualizer overlay window
        self.action_overlay = ActionOverlayWindow(target_hwnd=self.target_hwnd, parent=self)

        # Popup Play Bar (Floating Mini Control Bar)
        from ui.popup_play_bar import PopupPlayBar
        self.popup_play_bar = PopupPlayBar(self)
        self.popup_play_bar.set_target_hwnd(self.target_hwnd)
        self.popup_play_bar.sig_start_requested.connect(self._on_playbar_start)
        self.popup_play_bar.sig_start_selected_requested.connect(self._on_start_selected_execution)
        self.popup_play_bar.sig_pause_requested.connect(self._on_pause_execution)
        self.popup_play_bar.sig_stop_requested.connect(self._on_stop_execution)
        self.popup_play_bar.sig_step_requested.connect(self._on_playbar_step)
        self.popup_play_bar.sig_select_scenario_requested.connect(self._on_playbar_select_scenario)
        self.popup_play_bar.sig_closed.connect(self._on_playbar_closed)

        # F4 Shortcut to toggle popup play bar
        self.sc_f4 = QShortcut(QKeySequence("F4"), self)
        self.sc_f4.activated.connect(self._toggle_popup_playbar)

        self.sc_preset_load = QShortcut(QKeySequence("Ctrl+L"), self)
        self.sc_preset_load.activated.connect(self._on_open_preset_manager)

        self.sc_preset_save = QShortcut(QKeySequence("Ctrl+Shift+S"), self)
        self.sc_preset_save.activated.connect(self._on_save_preset)

        self.sc_proj_save = QShortcut(QKeySequence("Ctrl+S"), self)
        self.sc_proj_save.activated.connect(self._on_save_project)

        self.sc_proj_new = QShortcut(QKeySequence("Ctrl+N"), self)
        self.sc_proj_new.activated.connect(self._on_new_scenario_project)

        # Global Undo / Redo Shortcuts
        self.sc_undo = QShortcut(QKeySequence("Ctrl+Z"), self)
        self.sc_undo.activated.connect(self._on_global_undo)

        self.sc_redo_y = QShortcut(QKeySequence("Ctrl+Y"), self)
        self.sc_redo_y.activated.connect(self._on_global_redo)

        self.sc_redo_shift_z = QShortcut(QKeySequence("Ctrl+Shift+Z"), self)
        self.sc_redo_shift_z.activated.connect(self._on_global_redo)

    # Code Watcher & Theme methods have been extracted to MainWindowLayoutThemeMixin (ui/main_window_parts/layout_theme_manager.py)

    # Scenario Table, Selection & Hierarchy methods have been extracted to MainWindowTableMixin (ui/main_window_parts/table_controller.py)

    # Target Window & Canvas Management methods have been extracted to MainWindowTargetMixin (ui/main_window_parts/target_manager.py)

    # Scenario Playback & Runner Control methods have been extracted to MainWindowPlaybackMixin (ui/main_window_parts/playback_controller.py)

    # Logging & Trace Manager methods have been extracted to MainWindowLogMixin (ui/main_window_parts/log_manager.py)

    def _on_loop_count_changed(self, val: int):
        self.project.loop_count = val

    def _on_loop_delay_changed(self, val: float):
        self.project.loop_delay_seconds = val

    def _on_anti_ban_toggled(self, checked: bool):
        self.project.anti_ban_enabled = checked
        if hasattr(self, "spin_anti_ban_offset"):
            self.spin_anti_ban_offset.setEnabled(checked)
        cur_offset = float(getattr(self.project, "anti_ban_offset_seconds", getattr(self.project, "anti_ban_max_delay", 1.0)))
        state_str = f"활성화 (시나리오 전체 일괄 적용, 오프셋: +{cur_offset:.2f}초, 좌표 무작위 분산)" if checked else "비활성화"
        self._append_log("INFO", f"🛡️ 안티밴 모드가 시나리오 재생에 {state_str}되었습니다.")

    def _on_anti_ban_offset_changed(self, val: float):
        self.project.anti_ban_offset_seconds = val
        self.project.anti_ban_max_delay = val

    def _on_coord_weak_changed(self, val: int):
        self.project.anti_ban_coord_weak = val

    def _on_coord_strong_changed(self, val: int):
        self.project.anti_ban_coord_strong = val

    # ==========================================
    # Project Management (New / Save / Open)
    # ==========================================
    def _on_new_scenario_project(self):
        """시나리오가 하나도 없는 완전히 빈 새 시나리오 프로젝트 생성 (Ctrl+N)"""
        if self.project and self.project.scenarios:
            reply = QMessageBox.question(
                self,
                "새 시나리오 프로젝트",
                "현재 프로젝트를 닫고 완전히 비어 있는 새 시나리오 프로젝트를 생성하시겠습니까?\n(저장하지 않은 변경사항은 사라집니다)",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        self.project = Project(name="새 시나리오", scenarios=[])
        self.current_project_path = None
        if hasattr(self, "_scenario_undo_stack"):
            self._scenario_undo_stack.clear()
        if hasattr(self, "_scenario_redo_stack"):
            self._scenario_redo_stack.clear()

        self._update_window_title()
        if hasattr(self, "spin_loops"):
            self.spin_loops.setValue(self.project.loop_count)
        if hasattr(self, "spin_loop_delay"):
            self.spin_loop_delay.setValue(self.project.loop_delay_seconds)
        if hasattr(self, "chk_anti_ban"):
            self.chk_anti_ban.setChecked(self.project.anti_ban_enabled)

        self._refresh_scenario_table()
        if hasattr(self, "modules_widget") and self.modules_widget:
            self.modules_widget.set_project(self.project, self.target_hwnd)
        if hasattr(self, "inspector") and self.inspector:
            self.inspector.set_project(self.project)
            self.inspector.set_scenario(None)

        self.status_bar.showMessage("📄 빈 새 시나리오 프로젝트가 생성되었습니다. (시나리오 0개)", 3000)
        self._append_log("INFO", "📄 완전히 비어 있는 새 시나리오 프로젝트를 생성했습니다.")

    def _on_save_project(self):
        """불러들인 파일에 바로 저장하고, 경로가 없으면 다른 이름으로 저장 수행"""
        if self.current_project_path:
            try:
                with open(self.current_project_path, "w", encoding="utf-8") as f:
                    json.dump(self.project.to_dict(), f, indent=2, ensure_ascii=False)
                self._update_window_title()
                self._save_app_config()
                self.status_bar.showMessage(f"💾 프로젝트 저장 완료: {self.current_project_path}", 4000)
            except Exception as e:
                QMessageBox.critical(self, "저장 오류", f"프로젝트를 저장할 수 없습니다:\n{e}")
        else:
            self._on_save_project_as()

    def _on_save_project_as(self):
        """새로운 파일 경로를 선택하여 프로젝트 다른 이름으로 저장"""
        path, _ = QFileDialog.getSaveFileName(
            self, "프로젝트 다른 이름으로 저장", self.current_project_path or "fgoa_project.json", "FGOA Project (*.json)"
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(self.project.to_dict(), f, indent=2, ensure_ascii=False)
                self.current_project_path = path
                self._update_window_title()
                self._save_app_config()
                self.status_bar.showMessage(f"💾 프로젝트 다른 이름으로 저장 완료: {path}", 4000)
            except Exception as e:
                QMessageBox.critical(self, "저장 오류", f"프로젝트를 저장할 수 없습니다:\n{e}")

    def _on_open_anti_ban_dialog(self):
        dlg = AntiBanDialog(self.project, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self._mark_dirty()
            state_str = "활성화" if self.project.anti_ban_enabled else "비활성화"
            cur_off = float(getattr(self.project, "anti_ban_offset_seconds", getattr(self.project, "anti_ban_max_delay", 1.0)))
            w_px = getattr(self.project, "anti_ban_coord_weak", 5)
            s_px = getattr(self.project, "anti_ban_coord_strong", 15)
            self._append_log("INFO", f"🛡️ 안티밴 설정 변경: 타임 {state_str}(+{cur_off}초), 좌표 약 ±{w_px}px / 강 ±{s_px}px")
            self.status_bar.showMessage("안티밴 설정이 적용되었습니다.", 3000)

    def _load_project_file(self, path: str, silent: bool = False) -> bool:
        """Loads a project from JSON file path, updates UI components and saves config."""
        if not path or not os.path.isfile(path):
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.project = Project.from_dict(data)
            self.current_project_path = path
            self._update_window_title()
            if hasattr(self, "spin_loops"):
                self.spin_loops.setValue(self.project.loop_count)
            if hasattr(self, "spin_loop_delay"):
                self.spin_loop_delay.setValue(self.project.loop_delay_seconds)
            if hasattr(self, "chk_anti_ban"):
                self.chk_anti_ban.setChecked(self.project.anti_ban_enabled)
            cur_off = float(getattr(self.project, "anti_ban_offset_seconds", getattr(self.project, "anti_ban_max_delay", 1.0)))
            if hasattr(self, "spin_anti_ban_offset"):
                self.spin_anti_ban_offset.setValue(cur_off)
                self.spin_anti_ban_offset.setEnabled(self.project.anti_ban_enabled)
            if hasattr(self, "spin_coord_weak"):
                self.spin_coord_weak.setValue(getattr(self.project, "anti_ban_coord_weak", 5))
            if hasattr(self, "spin_coord_strong"):
                self.spin_coord_strong.setValue(getattr(self.project, "anti_ban_coord_strong", 15))
            self._refresh_scenario_table()
            if hasattr(self, "modules_widget") and self.modules_widget:
                self.modules_widget.set_project(self.project, self.target_hwnd)
            if hasattr(self, "inspector") and self.inspector:
                self.inspector.set_project(self.project)
            if self.project.scenarios and hasattr(self, "tbl_scenarios"):
                self.tbl_scenarios.selectRow(0)
            self._update_authoring_resolution_display()
            if hasattr(self, "status_bar"):
                self.status_bar.showMessage(f"프로젝트 불러오기 완료: {path}", 4000)
            self._save_app_config()
            self._auto_track_target_window()
            return True
        except Exception as e:
            if not silent:
                QMessageBox.critical(self, "열기 오류", f"프로젝트를 불러올 수 없습니다:\n{e}")
            return False

    def _on_open_project(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "프로젝트 열기", "", "FGOA Project (*.json)"
        )
        if path:
            self._load_project_file(path, silent=False)

    # ==========================================
    # Hotkeys
    # ==========================================
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F5:
            if event.modifiers() & Qt.ShiftModifier:
                if not self.runner or not self.runner.isRunning():
                    self._on_start_selected_execution()
                else:
                    self._on_pause_execution()
            else:
                if not self.runner or not self.runner.isRunning():
                    self._on_start_all_execution()
                else:
                    self._on_pause_execution()
            event.accept()
        elif event.key() == Qt.Key_F6:
            if event.modifiers() & Qt.ShiftModifier:
                if self.runner and self.runner.isRunning():
                    self._on_pause_execution()
            else:
                self._on_stop_execution()
            event.accept()
        elif event.key() == Qt.Key_F7:
            self._on_step_execution()
            event.accept()
        else:
            super().keyPressEvent(event)
