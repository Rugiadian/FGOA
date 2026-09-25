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
    QAction, QInputDialog, QSizePolicy, QApplication, QTabWidget, QStyle
)
from PyQt5.QtGui import QColor, QFont, QIcon, QKeySequence, QDrag, QCursor, QPixmap
from PyQt5.QtCore import Qt, QTimer, QFileSystemWatcher, QProcess, QByteArray, pyqtSignal, QMimeData

from core.models import Project, Scenario, Condition, Action, ColorPoint, ActionSequence
from core.window_manager import WindowManager, WindowInfo
from core.evaluator import ConditionEvaluator
from core.runner import WorkflowRunner
from core.preset_manager import PresetManager
from core.version import __version__
from ui.theme import get_stylesheet, get_theme_colors
from ui.window_picker_dialog import WindowPickerDialog
from ui.inspector_widget import InspectorWidget
from ui.modules_manager_widget import ModulesManagerWidget
from ui.widgets.color_badge import WarningBadge
from ui.widgets.flow_layout import FlowLayout
from ui.preset_dialog import SavePresetDialog, PresetManagerDialog
from ui.action_overlay import ActionOverlayWindow
from core.global_hotkey import GlobalHotkeyListener
from ui.floating_stop_widget import GlobalFloatingStopWidget
from core.path_utils import to_absolute_path, to_relative_path
from core.config import get_config_filepath


CONFIG_FILE = get_config_filepath()
TEMP_RELOAD_FILE = "_temp_reload_project.json"


class ScenarioVerticalHeader(QHeaderView):
    """Custom vertical header that highlights the currently executing scenario row with distinct cell color."""

    def __init__(self, parent=None):
        super().__init__(Qt.Vertical, parent)
        self.highlight_row: int = -1

    def set_highlight_row(self, row: int):
        if self.highlight_row != row:
            self.highlight_row = row
            self.viewport().update()

    def paintSection(self, painter, rect, logicalIndex):
        if logicalIndex == self.highlight_row:
            painter.save()
            # Vivid emerald green background for currently running scenario node
            painter.fillRect(rect, QColor("#16a34a"))
            painter.setPen(QColor("#15803d"))
            painter.drawRect(rect.adjusted(0, 0, -1, -1))
            # Bold white text
            painter.setPen(QColor("#ffffff"))
            font = painter.font()
            font.setBold(True)
            painter.setFont(font)
            text = self.model().headerData(logicalIndex, Qt.Vertical, Qt.DisplayRole) if self.model() else ""
            if not text:
                text = str(logicalIndex + 1)
            painter.drawText(rect, Qt.AlignCenter, str(text))
            painter.restore()
        else:
            super().paintSection(painter, rect, logicalIndex)


class DraggableScenarioTableWidget(QTableWidget):
    """QTableWidget supporting safe mouse drag-and-drop scenario row reordering without item loss."""
    sig_row_reordered = pyqtSignal(int, int)  # (from_row, to_row)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._custom_v_header = ScenarioVerticalHeader(self)
        self.setVerticalHeader(self._custom_v_header)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.horizontalHeader().setMinimumSectionSize(20)
        self._drag_start_pos = None
        self._drag_start_row = -1

    def set_highlight_row(self, row: int):
        """Highlights the specified row in the vertical header."""
        self._custom_v_header.set_highlight_row(row)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.adjust_column_widths()

    def adjust_column_widths(self):
        """Dynamically adjusts column widths in proportion to the table viewport width."""
        w = self.viewport().width()
        if w <= 0:
            return

        # Fixed-width compact columns:
        # 0: 스냅샷 (48px), 1: 고유 ID (s1, s2...) (48px), 2: 활성 (38px)
        fixed_sum = 48 + 48 + 38
        rem = max(320, w - fixed_sum)

        # Distribute remaining width proportionally:
        # 3: 시나리오 이름 (28%), 4: 인식조건 모듈 (26%), 5: 액션시퀀스 모듈 (26%), 6: 분기 (20%)
        w_name = max(80, int(rem * 0.28))
        w_cond = max(85, int(rem * 0.26))
        w_act = max(85, int(rem * 0.26))
        w_branch = max(65, rem - w_name - w_cond - w_act)

        header = self.horizontalHeader()
        header.resizeSection(0, 48)
        header.resizeSection(1, 48)
        header.resizeSection(2, 38)
        header.resizeSection(3, w_name)
        header.resizeSection(4, w_cond)
        header.resizeSection(5, w_act)
        header.resizeSection(6, w_branch)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.pos()
            self._drag_start_row = self.rowAt(event.pos().y())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            (event.buttons() & Qt.LeftButton)
            and self._drag_start_pos is not None
            and self._drag_start_row >= 0
        ):
            dist = (event.pos() - self._drag_start_pos).manhattanLength()
            if dist >= QApplication.startDragDistance():
                drag = QDrag(self)
                mime = QMimeData()
                mime.setData("application/x-fgoa-scen-row", str(self._drag_start_row).encode("utf-8"))
                drag.setMimeData(mime)
                self._drag_start_pos = None
                drag.exec_(Qt.MoveAction)
                self._drag_start_row = -1
                return
        super().mouseMoveEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-fgoa-scen-row"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-fgoa-scen-row"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasFormat("application/x-fgoa-scen-row"):
            data_bytes = event.mimeData().data("application/x-fgoa-scen-row").data()
            try:
                from_row = int(data_bytes.decode("utf-8"))
            except Exception:
                from_row = -1
            to_row = self.rowAt(event.pos().y())
            if to_row < 0:
                to_row = self.rowCount() - 1
            if to_row < 0:
                to_row = 0
            event.acceptProposedAction()
            if from_row != to_row and from_row >= 0 and to_row >= 0:
                self.sig_row_reordered.emit(from_row, to_row)
        else:
            event.ignore()


class MainWindow(QMainWindow):
    """
    Main application window with 3-Pane (Scenario Table | Inspector | Realtime Log) layout
    and full Light/Dark mode support.
    """

    def __init__(self):
        super().__init__()
        self.project = Project()
        self.target_hwnd: int = 0
        self.runner: Optional[WorkflowRunner] = None
        self.current_project_path: Optional[str] = None
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

        # Load user settings
        self._load_app_config()

        # Check for reload state
        self._check_reload_state()

        # Sample initial scenario if empty
        self._init_sample_project()

        self._init_ui()
        self._init_layout_and_docks()
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

        # Global hotkey and floating emergency stop widget
        self._init_global_hotkey_and_floating_stop()

    def _init_global_hotkey_and_floating_stop(self):
        """Initializes global F6 keyboard listener and always-on-top floating emergency stop widget."""
        self.global_hotkey = GlobalHotkeyListener(None)
        self.global_hotkey.sig_stop_hotkey.connect(self._on_global_hotkey_stop)
        self.global_hotkey.start()
        self.destroyed.connect(self._cleanup_global_hotkey)

        self.floating_stop = GlobalFloatingStopWidget(None)
        self.floating_stop.sig_stop_requested.connect(self._on_stop_execution)
        self.floating_stop.sig_pause_requested.connect(self._on_pause_execution)

    def _cleanup_global_hotkey(self):
        if hasattr(self, "global_hotkey") and self.global_hotkey:
            try:
                self.global_hotkey.stop_listening()
            except Exception:
                pass

    def _on_global_hotkey_stop(self):
        """Global F6 / Pause hotkey handler (operates system-wide even when FGOA is not focused)."""
        if self.runner and self.runner.isRunning():
            self._append_log("WARN", "🛑 [전역 단축키] F6 긴급 정지가 수신되었습니다.")
            self._on_stop_execution()

    def _update_window_title(self):
        """Update window title with application version and current project filename."""
        title = f"FGOA v{__version__} - 화면 인식 스마트 윈도우 오토 툴"
        if self.current_project_path:
            proj_name = os.path.basename(self.current_project_path)
            title = f"{title} [{proj_name}]"
        self.setWindowTitle(title)

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
        cfg_file = get_config_filepath()
        if os.path.exists(cfg_file):
            try:
                with open(cfg_file, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    self.current_theme = cfg.get("theme", "light")
                    self.current_layout_name = cfg.get("layout_name", "기본 3열 (Default)")
                    self.custom_layouts = cfg.get("custom_layouts", {})
                    self._saved_dock_state = cfg.get("dock_layout_state", None)
                    if hasattr(self.project, "target_client_width"):
                        self.project.target_client_width = cfg.get("last_target_width", 1600)
                        self.project.target_client_height = cfg.get("last_target_height", 900)
                        self.project.target_window_title = cfg.get("last_target_title", "")
            except Exception:
                pass

    def _save_app_config(self):
        try:
            cfg_file = get_config_filepath()
            cfg = {}
            if os.path.exists(cfg_file):
                try:
                    with open(cfg_file, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                except Exception:
                    pass
            cfg.update({
                "theme": self.current_theme,
                "window_width": self.width(),
                "window_height": self.height(),
                "last_target_title": getattr(self.project, "target_window_title", ""),
                "last_target_width": getattr(self.project, "target_client_width", 1600),
                "last_target_height": getattr(self.project, "target_client_height", 900),
                "layout_name": getattr(self, "current_layout_name", "기본 3열 (Default)"),
                "custom_layouts": getattr(self, "custom_layouts", {}),
            })
            if hasattr(self, "saveState"):
                try:
                    cfg["dock_layout_state"] = self.saveState().toHex().data().decode()
                except Exception:
                    pass
            from ui.coordinate_picker_dialog import CoordinatePickerDialog
            last_img = CoordinatePickerDialog.get_last_used_image_path()
            if last_img:
                cfg["last_picker_image_path"] = last_img
            with open(cfg_file, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def closeEvent(self, event):
        if hasattr(self, "global_hotkey") and self.global_hotkey:
            try:
                self.global_hotkey.stop_listening()
            except Exception:
                pass
        if hasattr(self, "floating_stop") and self.floating_stop:
            try:
                self.floating_stop.close()
            except Exception:
                pass
        if hasattr(self, "popup_play_bar") and self.popup_play_bar:
            try:
                self.popup_play_bar.close()
            except Exception:
                pass
        if hasattr(self, "action_overlay") and self.action_overlay:
            try:
                self.action_overlay.close()
            except Exception:
                pass
        self._save_app_config()
        super().closeEvent(event)

    def __del__(self):
        if hasattr(self, "global_hotkey") and self.global_hotkey:
            try:
                self.global_hotkey.stop_listening()
            except Exception:
                pass

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
        self.setCorner(Qt.TopLeftCorner, Qt.LeftDockWidgetArea)
        self.setCorner(Qt.BottomLeftCorner, Qt.LeftDockWidgetArea)
        self.setCorner(Qt.TopRightCorner, Qt.RightDockWidgetArea)
        self.setCorner(Qt.BottomRightCorner, Qt.RightDockWidgetArea)

        dummy_central = QWidget()
        dummy_central.setMaximumSize(0, 0)
        self.setCentralWidget(dummy_central)

        # 1. Top Target Window & Layout Selector Bar
        target_frame = QFrame()
        target_frame.setObjectName("card_frame")
        target_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
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

        # Unity-style Dynamic Layout Selector
        t_layout.addWidget(QLabel("📐 레이아웃:"))
        self.combo_layout = QComboBox()
        self.combo_layout.setObjectName("combo_layout")
        self.combo_layout.setMinimumWidth(135)
        self.combo_layout.setToolTip("유니티 스타일 유동적 레이아웃 전환 (기본/와이드/세로/탭/인스펙터 전면 등)")
        self.combo_layout.currentTextChanged.connect(self._on_layout_combo_changed)
        t_layout.addWidget(self.combo_layout)

        # Unity-style Window/Panels Menu
        self.btn_panels_menu = QPushButton("🪟 패널 표시 ▼")
        self.btn_panels_menu.setToolTip("패널(시나리오 목록, 인스펙터, 실행 로그) 표시/숨김 상태 제어")
        t_layout.addWidget(self.btn_panels_menu)

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

        self.btn_popup_playbar = QPushButton("🎮 플레이바 (F4)")
        self.btn_popup_playbar.setCheckable(True)
        self.btn_popup_playbar.setToolTip("항상 위에 떠 있는 미니 플레이바 창을 열거나 닫습니다. (단축키: F4)")
        self.btn_popup_playbar.clicked.connect(self._toggle_popup_playbar)
        t_layout.addWidget(self.btn_popup_playbar)

        t_layout.addSpacing(10)

        # Theme Toggle Button
        self.btn_theme_toggle = QPushButton()
        self.btn_theme_toggle.setObjectName("btn_theme")
        self.btn_theme_toggle.clicked.connect(self._toggle_theme)
        self._update_theme_toggle_btn()
        t_layout.addWidget(self.btn_theme_toggle)

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

        # Toolbar with responsive FlowLayout (automatically wraps buttons when width is constrained)
        tb_widget = QWidget()
        tb_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        tb_layout = FlowLayout(tb_widget, margin=0, spacing=4)

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

        btn_up = QPushButton("⬆️")
        btn_up.setToolTip("위로 이동")
        btn_up.clicked.connect(self._on_move_up)
        tb_layout.addWidget(btn_up)

        btn_down = QPushButton("⬇️")
        btn_down.setToolTip("아래로 이동")
        btn_down.clicked.connect(self._on_move_down)
        tb_layout.addWidget(btn_down)

        # Undo / Redo for Scenario List
        self.btn_undo_scenario = QPushButton("↩️ 취소")
        self.btn_undo_scenario.setToolTip("시나리오 목록 변경 작업 실행 취소 (Ctrl+Z)")
        self.btn_undo_scenario.clicked.connect(self._undo_scenario)
        self.btn_undo_scenario.setEnabled(False)
        tb_layout.addWidget(self.btn_undo_scenario)

        self.btn_redo_scenario = QPushButton("▶️ 다시")
        self.btn_redo_scenario.setToolTip("취소한 시나리오 목록 변경 작업 다시 실행 (Ctrl+Y / Ctrl+Shift+Z)")
        self.btn_redo_scenario.clicked.connect(self._redo_scenario)
        self.btn_redo_scenario.setEnabled(False)
        tb_layout.addWidget(self.btn_redo_scenario)

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
        tb_layout.addWidget(self.btn_preset)

        btn_save_proj = QPushButton("💾 저장")
        btn_save_proj.clicked.connect(self._on_save_project)
        tb_layout.addWidget(btn_save_proj)

        btn_open_proj = QPushButton("📂 열기")
        btn_open_proj.clicked.connect(self._on_open_project)
        tb_layout.addWidget(btn_open_proj)

        l_layout.addWidget(tb_widget)

        # Scenario Table (Full height)
        self.tbl_scenarios = DraggableScenarioTableWidget()
        self.tbl_scenarios.setColumnCount(7)
        self.tbl_scenarios.sig_row_reordered.connect(self._on_scenario_row_reordered)
        self.tbl_scenarios.setHorizontalHeaderLabels([
            "스냅샷", "고유 ID", "활성", "시나리오 이름", "인식조건 모듈", "액션시퀀스 모듈", "분기"
        ])
        
        # Responsive header resizing (Interactive mode allowing user adjustment and dynamic proportionality)
        header = self.tbl_scenarios.horizontalHeader()
        for col_idx in range(7):
            header.setSectionResizeMode(col_idx, QHeaderView.Interactive)
        self.tbl_scenarios.adjust_column_widths()
        self.tbl_scenarios.verticalHeader().setDefaultSectionSize(26)

        self.tbl_scenarios.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_scenarios.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tbl_scenarios.setAlternatingRowColors(True)
        self.tbl_scenarios.itemSelectionChanged.connect(self._on_table_selection_changed)
        self.tbl_scenarios.cellDoubleClicked.connect(self._on_scenario_cell_double_clicked)
        self.tbl_scenarios.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tbl_scenarios.customContextMenuRequested.connect(self._on_scenario_context_menu)
        l_layout.addWidget(self.tbl_scenarios, 1)

        # Dock 1: Left Pane (Scenarios & Modules Tab Widget)
        self.tab_scenario_manager = QTabWidget()
        self.tab_scenario_manager.setObjectName("TabScenarioManager")
        self.tab_scenario_manager.addTab(left_pane, "📜 시나리오 흐름")

        self.modules_widget = ModulesManagerWidget(self.project, self.target_hwnd, parent=self)
        self.modules_widget.sig_module_changed.connect(self._on_modules_changed)
        self.modules_widget.sig_log.connect(self._append_log)
        self.tab_scenario_manager.addTab(self.modules_widget, "🧩 모듈 / 노드 목록")

        self.dock_scenarios = QDockWidget("📜 시나리오 및 모듈 (Hierarchy)", self)
        self.dock_scenarios.setObjectName("DockScenarios")
        self.dock_scenarios.setFeatures(
            QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable | QDockWidget.DockWidgetClosable
        )
        self.dock_scenarios.setWidget(self.tab_scenario_manager)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_scenarios)

        # ==========================================
        # Pane 2: Center (Unity-Style Always-Open Inspector)
        # ==========================================
        self.inspector = InspectorWidget(self)
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
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_inspector)

        # Dock 2-B: Action Sequence Pane (Inspector: Actions)
        self.dock_actions = QDockWidget("✋ 액션 시퀀스 (Actions)", self)
        self.dock_actions.setObjectName("DockActions")
        self.dock_actions.setFeatures(
            QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable | QDockWidget.DockWidgetClosable
        )
        self.dock_actions.setWidget(self.inspector.action_panel)
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

        self.chk_autoscroll = QCheckBox("자동 스크롤")
        self.chk_autoscroll.setChecked(True)
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

        # 3. Execution Controller Bottom Bar (시나리오 재생 창)
        ctrl_frame = QFrame()
        ctrl_frame.setObjectName("card_frame")
        ctrl_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        c_layout = QHBoxLayout(ctrl_frame)
        c_layout.setContentsMargins(10, 6, 10, 6)

        lbl_playback_title = QLabel("▶ 시나리오 재생:")
        lbl_playback_title.setStyleSheet("font-weight: bold; font-size: 9.5pt;")
        c_layout.addWidget(lbl_playback_title)

        self.btn_run = QPushButton("▶ 전체 시작 (F5)")
        self.btn_run.setObjectName("btn_run")
        self.btn_run.setToolTip("첫 번째 시나리오 노드부터 전체를 순차적으로 실행합니다. (단축키: F5)")
        self.btn_run.clicked.connect(self._on_start_all_execution)
        c_layout.addWidget(self.btn_run)

        self.btn_run_selected = QPushButton("▶ 선택부터 시작 (Shift+F5)")
        self.btn_run_selected.setObjectName("btn_run_selected")
        self.btn_run_selected.setToolTip("현재 목록에서 선택된 시나리오 노드부터 이어서 실행합니다. (단축키: Shift+F5)")
        self.btn_run_selected.clicked.connect(self._on_start_selected_execution)
        c_layout.addWidget(self.btn_run_selected)

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

        self.btn_step = QPushButton("⏭ 단일 스텝 (F7)")
        self.btn_step.setToolTip("선택한 시나리오 노드부터 1단계를 실행하고 다음 노드로 포인터를 이동한 뒤 일시정지합니다. (단축키: F7)")
        self.btn_step.clicked.connect(self._on_step_execution)
        c_layout.addWidget(self.btn_step)

        self.chk_action_overlay = QCheckBox("🎯 조작 시각화")
        self.chk_action_overlay.setChecked(True)
        self.chk_action_overlay.setToolTip("오토 실행 중 조작할 좌표나 범위를 앱 화면 위에 점선 박스/화살표로 시각화 표시합니다.")
        self.chk_action_overlay.toggled.connect(self._on_toggle_action_overlay)
        c_layout.addWidget(self.chk_action_overlay)

        self.chk_floating_stop = QCheckBox("🛑 전역 플로팅 정지")
        self.chk_floating_stop.setChecked(False)
        self.chk_floating_stop.setToolTip("오토 실행 시 화면 최상위에 어디서나 마우스로 원클릭 정지 가능한 빨간색 플로팅 버튼을 자동 표시합니다.")
        c_layout.addWidget(self.chk_floating_stop)

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

        c_layout.addSpacing(15)

        self.chk_anti_ban = QCheckBox("🛡️ 타임 안티밴")
        self.chk_anti_ban.setChecked(self.project.anti_ban_enabled)
        self.chk_anti_ban.setToolTip(
            "시나리오 재생 타임 안티밴 모드 (시나리오 전역 일괄 적용):\n"
            "- 시나리오 재생 시 액션 지연 시간에 +n초 가변 지연시간 무작위 추가 (단축 없이 +0~+n초)\n"
            "- 좌표 오프셋은 각 액션별(해제/약/강)로 지정됩니다."
        )
        self.chk_anti_ban.toggled.connect(self._on_anti_ban_toggled)
        c_layout.addWidget(self.chk_anti_ban)

        self.lbl_anti_ban_offset = QLabel("오프셋:")
        self.lbl_anti_ban_offset.setStyleSheet("font-size: 8.5pt;")
        c_layout.addWidget(self.lbl_anti_ban_offset)
        self.spin_anti_ban_offset = QDoubleSpinBox()
        self.spin_anti_ban_offset.setRange(0.0, 30.0)
        self.spin_anti_ban_offset.setSingleStep(0.1)
        self.spin_anti_ban_offset.setPrefix("+")
        self.spin_anti_ban_offset.setSuffix(" 초")
        init_offset = float(getattr(self.project, "anti_ban_offset_seconds", getattr(self.project, "anti_ban_max_delay", 1.0)))
        self.spin_anti_ban_offset.setValue(init_offset)
        self.spin_anti_ban_offset.setToolTip("타임 안티밴 적용 시 무작위로 추가될 최대 지연시간 (+0.0 ~ +n초)")
        self.spin_anti_ban_offset.setEnabled(self.project.anti_ban_enabled)
        self.spin_anti_ban_offset.valueChanged.connect(self._on_anti_ban_offset_changed)
        c_layout.addWidget(self.spin_anti_ban_offset)

        c_layout.addSpacing(15)

        # Coordinate Anti-ban Global Strength (강약 조절)
        c_layout.addWidget(QLabel("🎯 좌표 오프셋:"))
        lbl_w = QLabel("약: ±")
        lbl_w.setStyleSheet("font-size: 8.5pt;")
        c_layout.addWidget(lbl_w)
        self.spin_coord_weak = QSpinBox()
        self.spin_coord_weak.setRange(1, 100)
        self.spin_coord_weak.setValue(getattr(self.project, "anti_ban_coord_weak", 5))
        self.spin_coord_weak.setSuffix(" px")
        self.spin_coord_weak.setToolTip("액션의 좌표 안티밴이 '약'일 때 적용할 무작위 픽셀 오차 (±N px)")
        self.spin_coord_weak.valueChanged.connect(self._on_coord_weak_changed)
        c_layout.addWidget(self.spin_coord_weak)

        lbl_s = QLabel("강: ±")
        lbl_s.setStyleSheet("font-size: 8.5pt;")
        c_layout.addWidget(lbl_s)
        self.spin_coord_strong = QSpinBox()
        self.spin_coord_strong.setRange(1, 200)
        self.spin_coord_strong.setValue(getattr(self.project, "anti_ban_coord_strong", 15))
        self.spin_coord_strong.setSuffix(" px")
        self.spin_coord_strong.setToolTip("액션의 좌표 안티밴이 '강'일 때 적용할 무작위 픽셀 오차 (±N px)")
        self.spin_coord_strong.valueChanged.connect(self._on_coord_strong_changed)
        c_layout.addWidget(self.spin_coord_strong)

        c_layout.addStretch()

        self.lbl_run_status = QLabel("대기 중")
        self.lbl_run_status.setStyleSheet("font-weight: bold; font-size: 10pt;")
        c_layout.addWidget(self.lbl_run_status)

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
        self.popup_play_bar.sig_start_requested.connect(self._on_playbar_start)
        self.popup_play_bar.sig_pause_requested.connect(self._on_pause_execution)
        self.popup_play_bar.sig_stop_requested.connect(self._on_stop_execution)
        self.popup_play_bar.sig_step_requested.connect(self._on_playbar_step)
        self.popup_play_bar.sig_select_scenario_requested.connect(self._on_playbar_select_scenario)

        # F4 Shortcut to toggle popup play bar
        self.sc_f4 = QShortcut(QKeySequence("F4"), self)
        self.sc_f4.activated.connect(self._toggle_popup_playbar)

        self.sc_preset_load = QShortcut(QKeySequence("Ctrl+L"), self)
        self.sc_preset_load.activated.connect(self._on_open_preset_manager)

        self.sc_preset_save = QShortcut(QKeySequence("Ctrl+Shift+S"), self)
        self.sc_preset_save.activated.connect(self._on_save_preset)

        # Global Undo / Redo Shortcuts
        self.sc_undo = QShortcut(QKeySequence("Ctrl+Z"), self)
        self.sc_undo.activated.connect(self._on_global_undo)

        self.sc_redo_y = QShortcut(QKeySequence("Ctrl+Y"), self)
        self.sc_redo_y.activated.connect(self._on_global_redo)

        self.sc_redo_shift_z = QShortcut(QKeySequence("Ctrl+Shift+Z"), self)
        self.sc_redo_shift_z.activated.connect(self._on_global_redo)

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
        self._rerender_all_logs()
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
            target_scen = self.project.scenarios[row]
            # If current inspector has unsaved changes for a different scenario, ask user
            if (self.inspector.is_dirty and self.inspector.original_scenario and
                    self.inspector.original_scenario.id != target_scen.id):
                msg_box = QMessageBox(self)
                msg_box.setWindowTitle("저장되지 않은 변경사항")
                msg_box.setText(
                    f"시나리오 s{self.inspector.original_scenario.scenario_number} [{self.inspector.original_scenario.name}]의 "
                    f"인스펙터 변경사항이 저장되지 않았습니다.\n변경사항을 저장하시겠습니까?"
                )
                msg_box.setIcon(QMessageBox.Question)

                btn_save = msg_box.addButton("저장 (&S)", QMessageBox.AcceptRole)
                btn_discard = msg_box.addButton("저장 안함 (&D)", QMessageBox.DestructiveRole)
                btn_cancel = msg_box.addButton("취소 (&C)", QMessageBox.RejectRole)

                # 선택되어 있는 저장 버튼에 뚜렷한 시각적 강조(Primary 버튼 스타일) 적용 및 포커스 유지
                btn_save.setStyleSheet("""
                    QPushButton {
                        background-color: #2563eb;
                        color: #ffffff;
                        font-weight: bold;
                        border: 2px solid #60a5fa;
                        border-radius: 5px;
                        padding: 6px 18px;
                        font-size: 9.5pt;
                    }
                    QPushButton:hover {
                        background-color: #1d4ed8;
                        border-color: #93c5fd;
                    }
                    QPushButton:focus {
                        border: 2px solid #ffffff;
                        outline: none;
                    }
                """)
                btn_discard.setStyleSheet("""
                    QPushButton {
                        background-color: #374151;
                        color: #f3f4f6;
                        border: 1px solid #4b5563;
                        border-radius: 5px;
                        padding: 6px 14px;
                        font-size: 9pt;
                    }
                    QPushButton:hover {
                        background-color: #4b5563;
                    }
                    QPushButton:focus {
                        border: 2px solid #9ca3af;
                        outline: none;
                    }
                """)
                btn_cancel.setStyleSheet("""
                    QPushButton {
                        background-color: #1f2937;
                        color: #d1d5db;
                        border: 1px solid #374151;
                        border-radius: 5px;
                        padding: 6px 14px;
                        font-size: 9pt;
                    }
                    QPushButton:hover {
                        background-color: #374151;
                    }
                    QPushButton:focus {
                        border: 2px solid #9ca3af;
                        outline: none;
                    }
                """)

                msg_box.setDefaultButton(btn_save)
                btn_save.setFocus()

                msg_box.exec_()
                clicked_btn = msg_box.clickedButton()

                if clicked_btn == btn_save:
                    self.inspector._on_save_inspector()
                elif clicked_btn == btn_cancel:
                    # Restore previous selection
                    for r, s in enumerate(self.project.scenarios):
                        if s.id == self.inspector.original_scenario.id:
                            self.tbl_scenarios.blockSignals(True)
                            self.tbl_scenarios.selectRow(r)
                            self.tbl_scenarios.blockSignals(False)
                            break
                    return
                else:
                    self.inspector._on_cancel_inspector()

            self.inspector.set_scenario(target_scen, self.target_hwnd, self.project)

    def _on_inspector_scenario_saved(self, saved_scen: Scenario):
        """Called when user explicitly clicks Save in Inspector."""
        self._push_scenario_undo_state(f"시나리오 s{saved_scen.scenario_number} 속성 저장")
        self._refresh_scenario_table()
        self.status_bar.showMessage(f"💾 시나리오 s{saved_scen.scenario_number} [{saved_scen.name}] 저장 완료", 3000)

    def _on_inspector_scenario_changed(self, modified_scen: Scenario):
        """Called when properties are edited inside the Inspector."""
        self._refresh_scenario_table()

    # ==========================================
    # Global & Scenario List Undo / Redo
    # ==========================================
    def _on_global_undo(self):
        """Dispatches undo to Inspector if focused and has edits, else to scenario list."""
        if hasattr(self, "inspector") and self.inspector.hasFocus() and self.inspector.inspector_undo_stack:
            self.inspector._on_undo_inspector()
        else:
            self._undo_scenario()

    def _on_global_redo(self):
        """Dispatches redo to Inspector if focused and has redo stack, else to scenario list."""
        if hasattr(self, "inspector") and self.inspector.hasFocus() and self.inspector.inspector_redo_stack:
            self.inspector._on_redo_inspector()
        else:
            self._redo_scenario()

    def _push_scenario_undo_state(self, action_name: str):
        """Saves current scenarios snapshot into scenario_undo_stack before an action."""
        if getattr(self, "_is_undoing_redoing_scenario", False):
            return
        snapshot = [s.to_dict() for s in self.project.scenarios]
        self.scenario_undo_stack.append((action_name, snapshot))
        if len(self.scenario_undo_stack) > 50:
            self.scenario_undo_stack.pop(0)
        self.scenario_redo_stack.clear()
        self._update_scenario_undo_redo_buttons()

    def _update_scenario_undo_redo_buttons(self):
        """Updates enablement and tooltip of undo/redo buttons in toolbar."""
        can_undo = bool(self.scenario_undo_stack)
        can_redo = bool(self.scenario_redo_stack)

        if hasattr(self, "btn_undo_scenario"):
            self.btn_undo_scenario.setEnabled(can_undo)
            if can_undo:
                self.btn_undo_scenario.setToolTip(f"실행 취소: '{self.scenario_undo_stack[-1][0]}' (Ctrl+Z)")
            else:
                self.btn_undo_scenario.setToolTip("시나리오 목록 변경 실행 취소 (Ctrl+Z)")

        if hasattr(self, "btn_redo_scenario"):
            self.btn_redo_scenario.setEnabled(can_redo)
            if can_redo:
                self.btn_redo_scenario.setToolTip(f"다시 실행: '{self.scenario_redo_stack[-1][0]}' (Ctrl+Y / Ctrl+Shift+Z)")
            else:
                self.btn_redo_scenario.setToolTip("취소한 변경 다시 실행 (Ctrl+Y / Ctrl+Shift+Z)")

    def _undo_scenario(self):
        """Undoes last scenario list modification."""
        if not self.scenario_undo_stack:
            return
        cur_snapshot = [s.to_dict() for s in self.project.scenarios]
        action_name, prev_snapshot = self.scenario_undo_stack.pop()
        self.scenario_redo_stack.append((action_name, cur_snapshot))

        self._is_undoing_redoing_scenario = True
        try:
            self.project.scenarios = [Scenario.from_dict(d) for d in prev_snapshot]
            self._refresh_scenario_table()
        finally:
            self._is_undoing_redoing_scenario = False

        self._update_scenario_undo_redo_buttons()
        self.status_bar.showMessage(f"↩️ '{action_name}' 작업 실행 취소 완료", 3000)
        self._append_log("INFO", f"↩️ [실행 취소] '{action_name}' 작업이 취소되었습니다.")

    def _redo_scenario(self):
        """Redoes previously undone scenario list modification."""
        if not self.scenario_redo_stack:
            return
        cur_snapshot = [s.to_dict() for s in self.project.scenarios]
        action_name, next_snapshot = self.scenario_redo_stack.pop()
        self.scenario_undo_stack.append((action_name, cur_snapshot))

        self._is_undoing_redoing_scenario = True
        try:
            self.project.scenarios = [Scenario.from_dict(d) for d in next_snapshot]
            self._refresh_scenario_table()
        finally:
            self._is_undoing_redoing_scenario = False

        self._update_scenario_undo_redo_buttons()
        self.status_bar.showMessage(f"▶️ '{action_name}' 작업 다시 실행 완료", 3000)
        self._append_log("INFO", f"▶️ [다시 실행] '{action_name}' 작업이 다시 실행되었습니다.")

    # ==========================================
    # Table Rendering & Hierarchy UI
    # ==========================================
    def _refresh_scenario_table(self):
        self.project.renumber_steps()
        depths = self.project.compute_hierarchy_depths()
        loop_analysis = self.project.analyze_loops() if hasattr(self.project, "analyze_loops") else {}

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
            loop_info = loop_analysis.get(row)
            self._update_table_row(row, scen, depth, loop_info)

            # Ensure vertical header item exists
            v_item = self.tbl_scenarios.verticalHeaderItem(row)
            if not v_item:
                v_item = QTableWidgetItem(str(row + 1))
                self.tbl_scenarios.setVerticalHeaderItem(row, v_item)

        self.tbl_scenarios.blockSignals(False)

        # Restore running header highlight if actively executing
        if hasattr(self, "_current_running_row") and self._current_running_row is not None:
            self._highlight_running_row_header(self._current_running_row)

        # Restore selection
        if 0 <= selected_row < len(self.project.scenarios):
            self.tbl_scenarios.selectRow(selected_row)
        elif self.project.scenarios:
            self.tbl_scenarios.selectRow(0)

        # Notify popup play bar of scenario changes
        if hasattr(self, "popup_play_bar") and self.popup_play_bar:
            self.popup_play_bar.refresh_scenarios(self.project.scenarios)

    def _update_table_row(self, row: int, scen: Scenario, depth: int = 0, loop_info: Optional[Dict[str, Any]] = None):

        # 0. Snapshot (레퍼런스 이미지 스냅샷 - 인식조건 이미지 기본값, 없으면 빈칸)
        eff_ref = scen.get_effective_reference_image(self.project)
        abs_ref = to_absolute_path(eff_ref) if eff_ref else None
        if abs_ref and os.path.isfile(abs_ref):
            pix = QPixmap(abs_ref)
            if not pix.isNull():
                thumb = pix.scaled(44, 22, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                lbl_thumb = QLabel()
                lbl_thumb.setPixmap(thumb)
                lbl_thumb.setAlignment(Qt.AlignCenter)
                lbl_thumb.setToolTip(f"📸 레퍼런스 스냅샷: {os.path.basename(abs_ref)}")
                lbl_thumb.setStyleSheet("background-color: transparent;")

                box = QWidget()
                bl = QHBoxLayout(box)
                bl.setContentsMargins(1, 1, 1, 1)
                bl.setAlignment(Qt.AlignCenter)
                bl.addWidget(lbl_thumb)
                self.tbl_scenarios.setCellWidget(row, 0, box)
            else:
                self.tbl_scenarios.setCellWidget(row, 0, None)
                it_empty = QTableWidgetItem("")
                it_empty.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.tbl_scenarios.setItem(row, 0, it_empty)
        else:
            self.tbl_scenarios.setCellWidget(row, 0, None)
            it_empty = QTableWidgetItem("")
            it_empty.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.tbl_scenarios.setItem(row, 0, it_empty)

        # 1. Scenario # (시나리오 고유 번호)
        it_uid = QTableWidgetItem(f"s{scen.scenario_number}")
        it_uid.setTextAlignment(Qt.AlignCenter)
        it_uid.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        it_uid.setToolTip(f"시나리오 고유 ID: s{scen.scenario_number}")
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

        # 3. Name with Loop Hierarchy UI, distinct pair colors, and orphaned warnings
        if scen.node_type == "loop_start":
            if loop_info and not loop_info.get("has_pair", True):
                # 짝 소실 경고!
                loop_desc = scen.get_loop_summary()
                it_name = QTableWidgetItem(f"⚠️ [루프 짝 없음: 종료 노드 소실!] {loop_desc} [{scen.name}]")
                it_name.setForeground(QColor("#ef4444"))
                it_name.setToolTip("⚠️ 대응되는 루프 종료 노드가 없습니다! 루프 블록을 확인해주세요.")
            else:
                p_num = loop_info.get("pair_number", 1) if loop_info else 1
                color_hex = (loop_info.get("color_light") if self.current_theme == "light" else loop_info.get("color_dark")) if loop_info else ("#2563eb" if self.current_theme == "light" else "#60a5fa")
                it_name = QTableWidgetItem(f"🔁 [루프 #{p_num} 시작: {scen.loop_count}회] [{scen.name}]")
                it_name.setForeground(QColor(color_hex))
                it_name.setToolTip(f"루프 #{p_num} 시작 노드")
            f = it_name.font()
            f.setBold(True)
            it_name.setFont(f)
        elif scen.node_type == "loop_end":
            if loop_info and not loop_info.get("has_pair", True):
                # 짝 소실 경고!
                it_name = QTableWidgetItem(f"⚠️ [루프 짝 없음: 시작 노드 소실!] 🔁 루프 종료 (시작 노드 없음)")
                it_name.setForeground(QColor("#ef4444"))
                it_name.setToolTip("⚠️ 대응되는 루프 시작 노드가 없습니다! 루프 블록을 확인해주세요.")
            else:
                p_num = loop_info.get("pair_number", 1) if loop_info else 1
                color_hex = (loop_info.get("color_light") if self.current_theme == "light" else loop_info.get("color_dark")) if loop_info else ("#7c3aed" if self.current_theme == "light" else "#c084fc")
                partner_idx = loop_info.get("partner_index") if loop_info else None
                start_num_str = f"s{self.project.scenarios[partner_idx].scenario_number}" if partner_idx is not None and partner_idx < len(self.project.scenarios) else ""
                it_name = QTableWidgetItem(f"🔁 [루프 #{p_num} 종료] → 루프 {start_num_str} 복귀")
                it_name.setForeground(QColor(color_hex))
                it_name.setToolTip(f"루프 #{p_num} 종료 노드 (루프 #{p_num} 시작점으로 복귀)")
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

        # 4. Condition Module (Eye)
        self.tbl_scenarios.setCellWidget(row, 4, None)
        eff_cond = scen.get_effective_condition(self.project)
        if scen.node_type == "loop_end":
            cond_text = "-"
        elif eff_cond:
            c_num = getattr(eff_cond, "condition_number", "")
            prefix = f"[C{c_num}] " if (c_num and getattr(scen, "condition_id", None)) else "[인스턴트] "
            cond_text = f"{prefix}{eff_cond.name} ({len(eff_cond.points)}pt)"
        else:
            cond_text = "(조건 없음)"
        it_cond = QTableWidgetItem(cond_text)
        if eff_cond and getattr(scen, "condition_id", None):
            it_cond.setForeground(QColor("#2563eb" if self.current_theme == "light" else "#60a5fa"))
        elif scen.node_type != "normal":
            it_cond.setForeground(QColor("#64748b"))
        it_cond.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        it_cond.setToolTip("더블 클릭하여 인식조건 모듈 교체")
        self.tbl_scenarios.setItem(row, 4, it_cond)

        # 5. ActionSequence Module (Hand)
        self.tbl_scenarios.setCellWidget(row, 5, None)
        eff_acts = scen.get_effective_actions(self.project)
        if scen.node_type == "loop_end":
            act_text = "-"
        elif getattr(scen, "sequence_id", None):
            seq = self.project.find_action_sequence(scen.sequence_id)
            if seq:
                s_num = getattr(seq, "sequence_number", "")
                prefix = f"[A{s_num}] " if s_num else ""
                act_text = f"{prefix}{seq.name} ({len(eff_acts)}개)"
            else:
                act_text = f"{len(eff_acts)}개 액션"
        elif eff_acts:
            act_text = f"[인스턴트] ({len(eff_acts)}개)"
        else:
            act_text = "(액션 없음)"
        it_act = QTableWidgetItem(act_text)
        if getattr(scen, "sequence_id", None):
            it_act.setForeground(QColor("#16a34a" if self.current_theme == "light" else "#4ade80"))
        elif scen.node_type != "normal":
            it_act.setForeground(QColor("#64748b"))
        it_act.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        it_act.setToolTip("더블 클릭하여 액션시퀀스 모듈 교체")
        self.tbl_scenarios.setItem(row, 5, it_act)

        # 6. Branch Summary (On Match / On Mismatch / Loop)
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
        self.tbl_scenarios.setItem(row, 6, it_branch)

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
            return f"고유 s{target_scen.scenario_number} (실행 #{target_scen.step_number}) [{target_scen.name}]"
        return target_id

    def _on_scenario_toggle(self, scenario: Scenario, state: int):
        self._push_scenario_undo_state(f"시나리오 s{scenario.scenario_number} 활성화 토글")
        scenario.enabled = (state == Qt.Checked)
        if self.inspector.current_scenario and self.inspector.current_scenario.id == scenario.id:
            self.inspector.chk_enabled.blockSignals(True)
            self.inspector.chk_enabled.setChecked(scenario.enabled)
            self.inspector.chk_enabled.blockSignals(False)

    # ==========================================
    # Unity-Style Dynamic Layout Management
    # ==========================================
    def _init_layout_and_docks(self):
        """Initializes dock arrangement from saved state or default preset."""
        self._refresh_layout_combo()
        if getattr(self, "_saved_dock_state", None):
            try:
                success = self.restoreState(QByteArray.fromHex(self._saved_dock_state.encode()))
                if success:
                    return
            except Exception:
                pass
        self.apply_layout(getattr(self, "current_layout_name", "기본 3열 (Default)"), save_current=False)

    def _refresh_layout_combo(self, select_name: Optional[str] = None):
        """Populates the layout switcher dropdown with built-ins and custom layouts."""
        if not hasattr(self, "combo_layout"):
            return
        self.combo_layout.blockSignals(True)
        self.combo_layout.clear()

        builtins = [
            "기본 3열 (Default)",
            "인식 조건 / 액션 나란히 (Side-by-Side)",
            "와이드 (하단 콘솔)",
            "세로 분할 (Tall)",
            "2 by 3 (Unity 스타일)",
            "탭 묶음 (Tabbed)",
            "인스펙터 전면 (Inspector Focus)"
        ]
        for b in builtins:
            self.combo_layout.addItem(b)

        # Custom layouts if any
        if hasattr(self, "custom_layouts") and self.custom_layouts:
            self.combo_layout.insertSeparator(self.combo_layout.count())
            for c_name in sorted(self.custom_layouts.keys()):
                self.combo_layout.addItem(f"⭐ {c_name}")

        self.combo_layout.insertSeparator(self.combo_layout.count())
        self.combo_layout.addItem("💾 현재 레이아웃 저장...")
        self.combo_layout.addItem("🔄 기본 레이아웃으로 초기화")

        target = select_name or getattr(self, "current_layout_name", "기본 3열 (Default)")
        idx = self.combo_layout.findText(target)
        if idx >= 0:
            self.combo_layout.setCurrentIndex(idx)
        else:
            self.combo_layout.setCurrentIndex(0)
        self.combo_layout.blockSignals(False)

    def _on_layout_combo_changed(self, text: str):
        if not text:
            return
        if text == "💾 현재 레이아웃 저장...":
            self._on_save_custom_layout()
        elif text == "🔄 기본 레이아웃으로 초기화":
            self._on_reset_layout()
        elif text.startswith("───"):
            idx = self.combo_layout.findText(self.current_layout_name)
            if idx >= 0:
                self.combo_layout.blockSignals(True)
                self.combo_layout.setCurrentIndex(idx)
                self.combo_layout.blockSignals(False)
        else:
            self.apply_layout(text)

    def apply_layout(self, layout_name: str, save_current: bool = True):
        """Applies requested dock layout preset with Unity-like docking behavior."""
        self.current_layout_name = layout_name
        if hasattr(self, "combo_layout"):
            self.combo_layout.blockSignals(True)
            idx = self.combo_layout.findText(layout_name)
            if idx >= 0:
                self.combo_layout.setCurrentIndex(idx)
            self.combo_layout.blockSignals(False)

        # Custom layout check
        pure_name = layout_name.replace("⭐ ", "")
        if hasattr(self, "custom_layouts") and pure_name in self.custom_layouts:
            try:
                hex_data = self.custom_layouts[pure_name]
                self.restoreState(QByteArray.fromHex(hex_data.encode()))
                self.status_bar.showMessage(f"📐 사용자 레이아웃 '{pure_name}'이(가) 적용되었습니다.", 3000)
                return
            except Exception:
                pass

        # Ensure all docks are unfloated and shown
        all_docks = [self.dock_scenarios, self.dock_inspector, self.dock_log]
        if hasattr(self, "dock_actions"):
            all_docks.append(self.dock_actions)
        for dock in all_docks:
            dock.setFloating(False)
            dock.show()

        if layout_name == "기본 3열 (Default)":
            self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_scenarios)
            self.splitDockWidget(self.dock_scenarios, self.dock_inspector, Qt.Horizontal)
            if hasattr(self, "dock_actions"):
                self.splitDockWidget(self.dock_inspector, self.dock_actions, Qt.Vertical)
                self.splitDockWidget(self.dock_inspector, self.dock_log, Qt.Horizontal)
                self.resizeDocks([self.dock_scenarios, self.dock_inspector, self.dock_log], [460, 580, 280], Qt.Horizontal)
                self.resizeDocks([self.dock_inspector, self.dock_actions], [330, 290], Qt.Vertical)
            else:
                self.splitDockWidget(self.dock_inspector, self.dock_log, Qt.Horizontal)
                self.resizeDocks([self.dock_scenarios, self.dock_inspector, self.dock_log], [480, 560, 280], Qt.Horizontal)

        elif layout_name == "인식 조건 / 액션 나란히 (Side-by-Side)":
            self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_scenarios)
            self.splitDockWidget(self.dock_scenarios, self.dock_inspector, Qt.Horizontal)
            if hasattr(self, "dock_actions"):
                self.splitDockWidget(self.dock_inspector, self.dock_actions, Qt.Horizontal)
                self.splitDockWidget(self.dock_actions, self.dock_log, Qt.Horizontal)
                self.resizeDocks([self.dock_scenarios, self.dock_inspector, self.dock_actions, self.dock_log], [380, 420, 420, 260], Qt.Horizontal)
            else:
                self.splitDockWidget(self.dock_inspector, self.dock_log, Qt.Horizontal)

        elif layout_name == "와이드 (하단 콘솔)":
            self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_scenarios)
            self.splitDockWidget(self.dock_scenarios, self.dock_inspector, Qt.Horizontal)
            if hasattr(self, "dock_actions"):
                self.splitDockWidget(self.dock_inspector, self.dock_actions, Qt.Horizontal)
                self.addDockWidget(Qt.BottomDockWidgetArea, self.dock_log)
                self.resizeDocks([self.dock_scenarios, self.dock_inspector, self.dock_actions], [450, 480, 480], Qt.Horizontal)
                self.resizeDocks([self.dock_inspector, self.dock_log], [550, 200], Qt.Vertical)
            else:
                self.addDockWidget(Qt.BottomDockWidgetArea, self.dock_log)
                self.resizeDocks([self.dock_scenarios, self.dock_inspector], [500, 700], Qt.Horizontal)
                self.resizeDocks([self.dock_scenarios, self.dock_log], [550, 200], Qt.Vertical)

        elif layout_name in ("세로 분할 (Tall)", "2 by 3 (Unity 스타일)"):
            self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_scenarios)
            self.splitDockWidget(self.dock_scenarios, self.dock_log, Qt.Vertical)
            self.addDockWidget(Qt.RightDockWidgetArea, self.dock_inspector)
            if hasattr(self, "dock_actions"):
                self.splitDockWidget(self.dock_inspector, self.dock_actions, Qt.Vertical)
                self.resizeDocks([self.dock_scenarios, self.dock_inspector], [450, 750], Qt.Horizontal)
                self.resizeDocks([self.dock_scenarios, self.dock_log], [500, 280], Qt.Vertical)
                self.resizeDocks([self.dock_inspector, self.dock_actions], [360, 360], Qt.Vertical)
            else:
                self.resizeDocks([self.dock_scenarios, self.dock_inspector], [450, 750], Qt.Horizontal)
                self.resizeDocks([self.dock_scenarios, self.dock_log], [500, 280], Qt.Vertical)

        elif layout_name == "탭 묶음 (Tabbed)":
            self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_scenarios)
            self.addDockWidget(Qt.RightDockWidgetArea, self.dock_inspector)
            if hasattr(self, "dock_actions"):
                self.tabifyDockWidget(self.dock_inspector, self.dock_actions)
            self.tabifyDockWidget(self.dock_inspector, self.dock_log)
            self.dock_inspector.raise_()
            self.resizeDocks([self.dock_scenarios, self.dock_inspector], [450, 750], Qt.Horizontal)

        elif layout_name == "인스펙터 전면 (Inspector Focus)":
            self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_scenarios)
            self.addDockWidget(Qt.RightDockWidgetArea, self.dock_inspector)
            if hasattr(self, "dock_actions"):
                self.splitDockWidget(self.dock_inspector, self.dock_actions, Qt.Horizontal)
                self.tabifyDockWidget(self.dock_actions, self.dock_log)
                self.resizeDocks([self.dock_scenarios, self.dock_inspector], [280, 1050], Qt.Horizontal)
            else:
                self.tabifyDockWidget(self.dock_inspector, self.dock_log)
                self.dock_inspector.raise_()
                self.resizeDocks([self.dock_scenarios, self.dock_inspector], [320, 950], Qt.Horizontal)

        self.status_bar.showMessage(f"📐 레이아웃이 '{layout_name}'(으)로 변경되었습니다.", 3000)

    def _on_save_custom_layout(self):
        """Saves current dock arrangement as a custom layout."""
        name, ok = QInputDialog.getText(
            self, "레이아웃 저장", "현재 패널 배치를 저장할 레이아웃 이름을 입력하세요:"
        )
        if ok and name.strip():
            clean_name = name.strip()
            state_hex = self.saveState().toHex().data().decode()
            if not hasattr(self, "custom_layouts"):
                self.custom_layouts = {}
            self.custom_layouts[clean_name] = state_hex
            self._refresh_layout_combo(f"⭐ {clean_name}")
            self.status_bar.showMessage(f"💾 사용자 레이아웃 '{clean_name}'이(가) 저장되었습니다.", 4000)

    def _on_reset_layout(self):
        """Resets layout to Default 3-column configuration."""
        self.apply_layout("기본 3열 (Default)")
        self.status_bar.showMessage("🔄 레이아웃이 기본 3열 배치로 초기화되었습니다.", 3000)

    # ==========================================
    # Scenario Preset Handlers
    # ==========================================
    def _on_save_preset(self):
        """Saves selected scenario(s) in table as a reusable preset."""
        selected_rows = [r.row() for r in self.tbl_scenarios.selectionModel().selectedRows()]
        if not selected_rows:
            curr = self.tbl_scenarios.currentRow()
            if 0 <= curr < len(self.project.scenarios):
                selected_rows = [curr]

        if not selected_rows:
            QMessageBox.warning(self, "선택 필요", "프리셋으로 저장할 시나리오를 1개 이상 선택해주세요.")
            return

        selected_scens = [
            self.project.scenarios[r]
            for r in sorted(selected_rows)
            if 0 <= r < len(self.project.scenarios)
        ]

        dlg = SavePresetDialog(selected_scens, parent=self)
        if dlg.exec_() == QDialog.Accepted and dlg.saved_filepath:
            self.status_bar.showMessage(f"💾 프리셋이 저장되었습니다: {os.path.basename(dlg.saved_filepath)}", 5000)

    def _on_open_preset_manager(self):
        """Opens preset manager dialog to browse, export, import, and load presets."""
        curr_row = self.tbl_scenarios.currentRow()
        dlg = PresetManagerDialog(current_selection_index=curr_row, parent=self)
        dlg.sig_scenarios_imported.connect(self._apply_imported_scenarios)
        dlg.exec_()

    def _on_quick_load_preset(self, preset_id: str):
        """Quick loads a starter preset by ID into the scenario sequence."""
        presets = PresetManager.list_presets()
        target_preset = None
        for p in presets:
            if p.get("id") == preset_id:
                target_preset = p
                break

        if not target_preset:
            QMessageBox.warning(self, "프리셋 없음", f"프리셋 '{preset_id}'을(를) 찾을 수 없습니다.")
            return

        scenarios = PresetManager.instantiate_preset_scenarios(target_preset)
        if not scenarios:
            return

        curr_row = self.tbl_scenarios.currentRow()
        mode = "after_selected" if curr_row >= 0 else "append"
        self._apply_imported_scenarios(scenarios, mode)

    def _apply_imported_scenarios(self, scenarios: List[Scenario], mode: str):
        """Applies imported scenarios into project with automatic step renumbering."""
        if not scenarios:
            return

        self._push_scenario_undo_state(f"프리셋 시나리오 {len(scenarios)}건 불러오기")

        if mode == "replace":
            self.project.scenarios = scenarios
            insert_idx = 0
        elif mode == "after_selected":
            curr_row = self.tbl_scenarios.currentRow()
            if 0 <= curr_row < len(self.project.scenarios):
                insert_idx = curr_row + 1
                self.project.scenarios[insert_idx:insert_idx] = scenarios
            else:
                insert_idx = len(self.project.scenarios)
                self.project.scenarios.extend(scenarios)
        else:  # "append"
            insert_idx = len(self.project.scenarios)
            self.project.scenarios.extend(scenarios)

        self.project.renumber_steps()
        self._refresh_scenario_table()

        # Select first inserted scenario
        if 0 <= insert_idx < len(self.project.scenarios):
            self.tbl_scenarios.selectRow(insert_idx)

        self.status_bar.showMessage(f"✅ 프리셋에서 시나리오 {len(scenarios)}건을 성공적으로 불러왔습니다.", 4000)
        self._append_log("SUCCESS", f"📦 프리셋 시나리오 {len(scenarios)}건 불러오기 완료 (적용 모드: {mode})")

    def _on_scenario_context_menu(self, pos):
        """Right-click context menu for scenario table rows."""
        menu = QMenu(self)
        act_save_preset = menu.addAction("💾 선택한 시나리오 프리셋 저장...")
        act_save_preset.triggered.connect(self._on_save_preset)
        act_load_preset = menu.addAction("📥 프리셋 보관함에서 불러오기...")
        act_load_preset.triggered.connect(self._on_open_preset_manager)
        menu.addSeparator()

        curr_row = self.tbl_scenarios.rowAt(pos.y())
        if 0 <= curr_row < len(self.project.scenarios):
            scen = self.project.scenarios[curr_row]
            act_pick_cond = menu.addAction(f"👁️ [s{scen.scenario_number}] 인식조건 모듈 교체...")
            act_pick_cond.triggered.connect(lambda: self._show_condition_module_picker(scen))
            act_pick_seq = menu.addAction(f"✋ [s{scen.scenario_number}] 액션시퀀스 모듈 교체...")
            act_pick_seq.triggered.connect(lambda: self._show_sequence_module_picker(scen))
            menu.addSeparator()

        act_add = menu.addAction("➕ 새 시나리오 추가 (조합형)")
        act_add.triggered.connect(self._on_add_scenario)
        act_dup = menu.addAction("📋 시나리오 복제")
        act_dup.triggered.connect(self._on_duplicate_scenario)
        act_del = menu.addAction("🗑️ 시나리오 삭제")
        act_del.triggered.connect(self._on_delete_scenario)
        menu.addSeparator()
        act_up = menu.addAction("⬆️ 위로 이동")
        act_up.triggered.connect(self._on_move_up)
        act_dn = menu.addAction("⬇️ 아래로 이동")
        act_dn.triggered.connect(self._on_move_down)
        menu.addSeparator()
        act_undo = menu.addAction("↩️ 실행 취소 (Ctrl+Z)")
        act_undo.triggered.connect(self._undo_scenario)
        act_undo.setEnabled(bool(self.scenario_undo_stack))
        act_redo = menu.addAction("▶️ 다시 실행 (Ctrl+Y)")
        act_redo.triggered.connect(self._redo_scenario)
        act_redo.setEnabled(bool(self.scenario_redo_stack))
        menu.exec_(self.tbl_scenarios.viewport().mapToGlobal(pos))

    # ==========================================
    # Modular Composite Scenario Handlers
    # ==========================================
    def _on_modules_changed(self):
        """Called when modules are added/edited/deleted from ModulesManagerWidget."""
        self._refresh_scenario_table()
        if hasattr(self, "inspector") and self.inspector:
            self.inspector._populate_condition_combo()
            self.inspector._populate_sequence_combo()
            self.inspector._refresh_actions_table()
            self.inspector._refresh_points_table()

    def _on_scenario_cell_double_clicked(self, row: int, col: int):
        """Handles fast module swapping or snapshot inspection on double click."""
        if not (0 <= row < len(self.project.scenarios)):
            return
        scen = self.project.scenarios[row]
        if col == 0:
            self.tbl_scenarios.selectRow(row)
            if hasattr(self, "inspector") and self.inspector:
                self.inspector._on_node_snapshot_clicked()
        elif col == 4:
            self._show_condition_module_picker(scen)
        elif col == 5:
            self._show_sequence_module_picker(scen)

    def _show_condition_module_picker(self, scen: Scenario):
        """Presents quick menu to swap condition module or create a new one."""
        menu = QMenu(self)
        eff_cond = scen.get_effective_condition(self.project)
        cur_title = f"[C{eff_cond.condition_number}] {eff_cond.name}" if eff_cond else "(조건 없음)"
        header_act = menu.addAction(f"👁️ 인식조건 모듈 선택 (현재: {cur_title})")
        header_act.setEnabled(False)
        menu.addSeparator()

        for cond in getattr(self.project, "conditions", []):
            c_num = getattr(cond, "condition_number", "")
            act = menu.addAction(f"🔗 [C{c_num}] {cond.name} ({len(cond.points)}개 포인트)")
            if getattr(scen, "condition_id", None) == cond.id:
                act.setIcon(self.style().standardIcon(QStyle.SP_DialogApplyButton))
            act.triggered.connect(lambda checked, c=cond: self._assign_condition_to_scenario(scen, c.id))

        menu.addSeparator()
        act_new = menu.addAction("➕ 새 인식조건 모듈 생성 및 조립...")
        act_new.triggered.connect(lambda: self._create_and_assign_condition(scen))

        if getattr(scen, "condition_id", None):
            act_unlink = menu.addAction("🔓 인스턴트 인식 조건으로 분리 (연결 해제)")
            act_unlink.triggered.connect(lambda: self._unlink_condition_from_scenario(scen))

        act_none = menu.addAction("❌ 조건 없음 (무조건 실행)")
        act_none.triggered.connect(lambda: self._clear_condition_from_scenario(scen))

        menu.exec_(QCursor.pos())

    def _assign_condition_to_scenario(self, scen: Scenario, cond_id: str):
        self._push_scenario_undo_state(f"시나리오 s{scen.scenario_number} 인식조건 모듈 변경")
        scen.condition_id = cond_id
        cond = self.project.find_condition(cond_id)
        if cond and cond.action_sequence_id and getattr(scen, "sequence_id", None) != cond.action_sequence_id:
            scen.sequence_id = cond.action_sequence_id
        elif cond and getattr(scen, "sequence_id", None) and not cond.action_sequence_id:
            cond.action_sequence_id = scen.sequence_id

        self._refresh_scenario_table()
        if self.inspector.current_scenario and self.inspector.current_scenario.id == scen.id:
            self.inspector.set_scenario(scen, self.target_hwnd, self.project)
        if hasattr(self, "modules_widget"):
            self.modules_widget.refresh_modules()
        c_num = cond.condition_number if cond else ""
        c_name = cond.name if cond else ""
        self._append_log("INFO", f"시나리오 s{scen.scenario_number} [{scen.name}]에 인식조건 모듈 [C{c_num}] '{c_name}'이 조립되었습니다.")

    def _create_and_assign_condition(self, scen: Scenario):
        name, ok = QInputDialog.getText(
            self, "새 인식조건 모듈 생성", "인식조건 모듈 이름:",
            text=f"{scen.name} 인식조건"
        )
        if not ok or not name.strip():
            return
        self._push_scenario_undo_state(f"새 인식조건 모듈 생성 및 s{scen.scenario_number} 조립")
        new_cond = Condition(
            name=name.strip(),
            logic_operator="AND",
            points=[],
            action_sequence_id=getattr(scen, "sequence_id", None)
        )
        self.project.add_condition(new_cond)
        scen.condition_id = new_cond.id
        self._refresh_scenario_table()
        if self.inspector.current_scenario and self.inspector.current_scenario.id == scen.id:
            self.inspector.set_scenario(scen, self.target_hwnd, self.project)
        if hasattr(self, "modules_widget"):
            self.modules_widget.refresh_modules()
        self._append_log("INFO", f"새 인식조건 모듈 [C{new_cond.condition_number}] '{new_cond.name}' 생성 및 조립 완료")

    def _unlink_condition_from_scenario(self, scen: Scenario):
        if not getattr(scen, "condition_id", None):
            return
        self._push_scenario_undo_state(f"시나리오 s{scen.scenario_number} 인스턴트 조건 분리")
        eff_cond = scen.get_effective_condition(self.project)
        if eff_cond:
            scen.condition = copy.deepcopy(eff_cond)
        scen.condition_id = None
        self._refresh_scenario_table()
        if self.inspector.current_scenario and self.inspector.current_scenario.id == scen.id:
            self.inspector.set_scenario(scen, self.target_hwnd, self.project)
        if hasattr(self, "modules_widget"):
            self.modules_widget.refresh_modules()
        self._append_log("INFO", f"시나리오 s{scen.scenario_number}의 인식조건이 공용 모듈에서 인스턴트 인식 조건으로 분리되었습니다.")

    def _clear_condition_from_scenario(self, scen: Scenario):
        self._push_scenario_undo_state(f"시나리오 s{scen.scenario_number} 조건 제거")
        scen.condition_id = None
        scen.condition = None
        self._refresh_scenario_table()
        if self.inspector.current_scenario and self.inspector.current_scenario.id == scen.id:
            self.inspector.set_scenario(scen, self.target_hwnd, self.project)
        if hasattr(self, "modules_widget"):
            self.modules_widget.refresh_modules()
        self._append_log("INFO", f"시나리오 s{scen.scenario_number}의 조건이 제거되어 무조건 실행으로 변경되었습니다.")

    def _show_sequence_module_picker(self, scen: Scenario):
        """Presents quick menu to swap action sequence module or create a new one."""
        menu = QMenu(self)
        eff_acts = scen.get_effective_actions(self.project)
        seq_mod = self.project.find_action_sequence(scen.sequence_id) if getattr(scen, "sequence_id", None) else None
        cur_title = f"[A{seq_mod.sequence_number}] {seq_mod.name}" if seq_mod else f"{len(eff_acts)}개 액션"
        header_act = menu.addAction(f"✋ 액션시퀀스 모듈 선택 (현재: {cur_title})")
        header_act.setEnabled(False)
        menu.addSeparator()

        for seq in getattr(self.project, "action_sequences", []):
            s_num = getattr(seq, "sequence_number", "")
            act = menu.addAction(f"🔗 [A{s_num}] {seq.name} ({len(seq.actions)}개 액션)")
            if getattr(scen, "sequence_id", None) == seq.id:
                act.setIcon(self.style().standardIcon(QStyle.SP_DialogApplyButton))
            act.triggered.connect(lambda checked, s=seq: self._assign_sequence_to_scenario(scen, s.id))

        menu.addSeparator()
        act_new = menu.addAction("➕ 새 액션시퀀스 모듈 생성 및 조립...")
        act_new.triggered.connect(lambda: self._create_and_assign_sequence(scen))

        if getattr(scen, "sequence_id", None):
            act_unlink = menu.addAction("🔓 인스턴트 액션 시퀀스로 분리 (연결 해제)")
            act_unlink.triggered.connect(lambda: self._unlink_sequence_from_scenario(scen))

        act_none = menu.addAction("❌ 액션 없음")
        act_none.triggered.connect(lambda: self._clear_sequence_from_scenario(scen))

        menu.exec_(QCursor.pos())

    def _assign_sequence_to_scenario(self, scen: Scenario, seq_id: str):
        self._push_scenario_undo_state(f"시나리오 s{scen.scenario_number} 액션시퀀스 모듈 변경")
        scen.sequence_id = seq_id
        eff_cond = scen.get_effective_condition(self.project)
        if eff_cond:
            eff_cond.action_sequence_id = seq_id

        self._refresh_scenario_table()
        if self.inspector.current_scenario and self.inspector.current_scenario.id == scen.id:
            self.inspector.set_scenario(scen, self.target_hwnd, self.project)
        if hasattr(self, "modules_widget"):
            self.modules_widget.refresh_modules()
        seq = self.project.find_action_sequence(seq_id)
        s_num = seq.sequence_number if seq else ""
        s_name = seq.name if seq else ""
        self._append_log("INFO", f"시나리오 s{scen.scenario_number} [{scen.name}]에 액션시퀀스 모듈 [A{s_num}] '{s_name}'이 조립되었습니다.")

    def _create_and_assign_sequence(self, scen: Scenario):
        name, ok = QInputDialog.getText(
            self, "새 액션시퀀스 모듈 생성", "액션시퀀스 모듈 이름:",
            text=f"{scen.name} 액션시퀀스"
        )
        if not ok or not name.strip():
            return
        self._push_scenario_undo_state(f"새 액션시퀀스 모듈 생성 및 s{scen.scenario_number} 조립")
        new_seq = ActionSequence(
            name=name.strip(),
            actions=[]
        )
        self.project.add_action_sequence(new_seq)
        scen.sequence_id = new_seq.id
        eff_cond = scen.get_effective_condition(self.project)
        if eff_cond:
            eff_cond.action_sequence_id = new_seq.id

        self._refresh_scenario_table()
        if self.inspector.current_scenario and self.inspector.current_scenario.id == scen.id:
            self.inspector.set_scenario(scen, self.target_hwnd, self.project)
        if hasattr(self, "modules_widget"):
            self.modules_widget.refresh_modules()
        self._append_log("INFO", f"새 액션시퀀스 모듈 [A{new_seq.sequence_number}] '{new_seq.name}' 생성 및 조립 완료")

    def _unlink_sequence_from_scenario(self, scen: Scenario):
        if not getattr(scen, "sequence_id", None):
            return
        self._push_scenario_undo_state(f"시나리오 s{scen.scenario_number} 인스턴트 액션 시퀀스 분리")
        eff_acts = scen.get_effective_actions(self.project)
        scen.actions = copy.deepcopy(eff_acts)
        scen.sequence_id = None
        self._refresh_scenario_table()
        if self.inspector.current_scenario and self.inspector.current_scenario.id == scen.id:
            self.inspector.set_scenario(scen, self.target_hwnd, self.project)
        if hasattr(self, "modules_widget"):
            self.modules_widget.refresh_modules()
        self._append_log("INFO", f"시나리오 s{scen.scenario_number}의 액션시퀀스가 공용 모듈에서 인스턴트 액션 시퀀스로 분리되었습니다.")

    def _clear_sequence_from_scenario(self, scen: Scenario):
        self._push_scenario_undo_state(f"시나리오 s{scen.scenario_number} 액션 제거")
        scen.sequence_id = None
        scen.actions = []
        self._refresh_scenario_table()
        if self.inspector.current_scenario and self.inspector.current_scenario.id == scen.id:
            self.inspector.set_scenario(scen, self.target_hwnd, self.project)
        if hasattr(self, "modules_widget"):
            self.modules_widget.refresh_modules()
        self._append_log("INFO", f"시나리오 s{scen.scenario_number}의 액션이 제거되었습니다.")

    # ==========================================
    # Toolbar Actions
    # ==========================================
    def _on_add_scenario(self):
        new_scen_num = self.project.get_next_scenario_number()
        self._push_scenario_undo_state(f"시나리오 #{new_scen_num} 추가")
        new_scen = self.project.create_composite_scenario(
            name=f"시나리오 {new_scen_num}",
            node_type="normal"
        )
        self._refresh_scenario_table()
        if hasattr(self, "modules_widget"):
            self.modules_widget.refresh_modules()
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
        self._push_scenario_undo_state(f"루프 블록 #{start_num} 추가")
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
        orig = self.project.scenarios[row]
        cloned = copy.deepcopy(orig)
        import uuid
        cloned.id = f"scen_{uuid.uuid4().hex[:6]}"
        cloned.scenario_number = self.project.get_next_scenario_number()
        cloned.name = f"{cloned.name} (복제)"
        self._push_scenario_undo_state(f"시나리오 s{orig.scenario_number} 복제")
        self.project.scenarios.insert(row + 1, cloned)
        self._refresh_scenario_table()
        self.tbl_scenarios.selectRow(row + 1)

    def _on_delete_scenario(self):
        rows = self.tbl_scenarios.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        scen = self.project.scenarios[row]
        res = QMessageBox.question(self, "삭제 확인", f"시나리오 고유 s{scen.scenario_number} (실행 #{scen.step_number}) [{scen.name}]를 삭제하시겠습니까?")
        if res == QMessageBox.Yes:
            self._push_scenario_undo_state(f"시나리오 s{scen.scenario_number} 삭제")
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
        self._push_scenario_undo_state(f"시나리오 s{self.project.scenarios[row].scenario_number} 위로 이동")
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
        self._push_scenario_undo_state(f"시나리오 s{self.project.scenarios[row].scenario_number} 아래로 이동")
        self.project.scenarios[row + 1], self.project.scenarios[row] = (
            self.project.scenarios[row], self.project.scenarios[row + 1]
        )
        self._refresh_scenario_table()
        self.tbl_scenarios.selectRow(row + 1)

    def _on_scenario_row_reordered(self, from_row: int, to_row: int):
        """Reorders scenarios in the project via drag-and-drop."""
        if not self.project or not self.project.scenarios or from_row == to_row:
            return
        scens = self.project.scenarios
        if 0 <= from_row < len(scens) and 0 <= to_row < len(scens):
            self._push_scenario_undo_state(f"시나리오 s{scens[from_row].scenario_number} 드래그 이동")
            scen = scens.pop(from_row)
            scens.insert(to_row, scen)
            self._refresh_scenario_table()
            self.tbl_scenarios.selectRow(to_row)

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
            if hasattr(self, "modules_widget") and self.modules_widget:
                self.modules_widget.target_hwnd = self.target_hwnd
            if hasattr(self, "action_overlay") and self.action_overlay:
                self.action_overlay.set_target_hwnd(self.target_hwnd)
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
    def _on_start_all_execution(self):
        """첫 번째 시나리오 노드부터 전체를 순차적으로 실행"""
        self._on_start_execution(start_scenario_id=None)

    def _on_start_selected_execution(self):
        """현재 목록에서 선택된 시나리오 노드부터 실행"""
        selected_indexes = self.tbl_scenarios.selectedIndexes()
        selected_scen_id = None
        if selected_indexes:
            row = selected_indexes[0].row()
            if 0 <= row < len(self.project.scenarios):
                selected_scen_id = self.project.scenarios[row].id
        self._on_start_execution(start_scenario_id=selected_scen_id)

    def _on_start_execution(self, start_scenario_id: Optional[str] = None):
        if not self.target_hwnd:
            QMessageBox.warning(self, "타겟 창 필요", "먼저 상단에서 오토 입력을 수행할 타겟 게임 창을 선택해주세요.")
            return

        if self.runner and self.runner.isRunning():
            if self.runner._is_paused:
                if start_scenario_id:
                    self.runner.set_next_scenario_id(start_scenario_id)
                self.runner.resume()
                self.lbl_run_status.setText("실행 중...")
                self.btn_pause.setText("⏸ 일시정지")
                if hasattr(self, "popup_play_bar") and self.popup_play_bar:
                    self.popup_play_bar.set_runner_state("running", "재개되어 실행 중...")
                return

        self.runner = WorkflowRunner(self.project, self.target_hwnd, start_scenario_id=start_scenario_id, parent=self)
        self.runner.sig_log.connect(self._append_log)
        self.runner.sig_scenario_started.connect(self._on_scenario_started)
        self.runner.sig_scenario_completed.connect(self._on_scenario_completed)
        self.runner.sig_action_executing.connect(self._on_action_executing_visual)
        self.runner.sig_action_finished.connect(self._on_action_finished_visual)
        self.runner.sig_step_completed.connect(self._on_step_completed)
        self.runner.sig_finished.connect(self._on_runner_finished)

        self.btn_run.setEnabled(False)
        if hasattr(self, "btn_run_selected"):
            self.btn_run_selected.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_stop.setEnabled(True)
        self.lbl_run_status.setText("실행 중 (F5/F6)")
        self.lbl_run_status.setStyleSheet("color: #16a34a; font-weight: bold;")
        if hasattr(self, "popup_play_bar") and self.popup_play_bar:
            self.popup_play_bar.set_runner_state("running", "시나리오 실행 중...")
            if not self.popup_play_bar.isVisible():
                geo = self.geometry()
                self.popup_play_bar.move(max(0, geo.x() + geo.width() - 480), max(0, geo.y() + 60))
                self.popup_play_bar.show()
                self.popup_play_bar.raise_()
                if hasattr(self, "btn_popup_playbar"):
                    self.btn_popup_playbar.setChecked(True)

        self.runner.start()

    def _on_pause_execution(self):
        if self.runner and self.runner.isRunning():
            if self.runner._is_paused:
                self.runner.resume()
                self.btn_pause.setText("⏸ 일시정지")
                self.lbl_run_status.setText("실행 중...")
                self.lbl_run_status.setStyleSheet("color: #16a34a; font-weight: bold;")
                if hasattr(self, "popup_play_bar") and self.popup_play_bar:
                    self.popup_play_bar.set_runner_state("running", "재개되어 실행 중...")
                if hasattr(self, "floating_stop") and self.floating_stop:
                    self.floating_stop.set_paused_state(False)
            else:
                self.runner.pause()
                self.btn_pause.setText("▶ 재개")
                self.lbl_run_status.setText("일시정지됨")
                self.lbl_run_status.setStyleSheet("color: #ea580c; font-weight: bold;")
                if hasattr(self, "popup_play_bar") and self.popup_play_bar:
                    self.popup_play_bar.set_runner_state("paused", "일시정지됨")
                if hasattr(self, "floating_stop") and self.floating_stop:
                    self.floating_stop.set_paused_state(True)

    def _on_stop_execution(self):
        if self.runner:
            self.runner.stop()
            self.lbl_run_status.setText("정지 요청 중...")
            self.lbl_run_status.setStyleSheet("color: #dc2626; font-weight: bold;")
        self._highlight_running_row_header(None)
        if hasattr(self, "floating_stop") and self.floating_stop:
            self.floating_stop.hide()
        if hasattr(self, "popup_play_bar") and self.popup_play_bar:
            self.popup_play_bar.set_runner_state("stopped", "정지됨")
        if hasattr(self, "action_overlay") and self.action_overlay:
            self.action_overlay.clear_action()

    def _on_step_execution(self):
        if not self.target_hwnd:
            QMessageBox.warning(self, "타겟 창 필요", "타겟 창을 먼저 선택해주세요.")
            return

        # Find selected scenario node (start from selected node, not from beginning)
        selected_indexes = self.tbl_scenarios.selectedIndexes()
        selected_scen_id = None
        if selected_indexes:
            row = selected_indexes[0].row()
            if 0 <= row < len(self.project.scenarios):
                selected_scen_id = self.project.scenarios[row].id

        if not self.runner or not self.runner.isRunning():
            self._on_start_execution(start_scenario_id=selected_scen_id)
            if self.runner:
                self.runner.step_forward()
                self.lbl_run_status.setText("단일 스텝 (F7)")
                self.lbl_run_status.setStyleSheet("color: #0284c7; font-weight: bold;")
        else:
            if selected_scen_id:
                self.runner.set_next_scenario_id(selected_scen_id)
            self.runner.step_forward()
            self.lbl_run_status.setText("단일 스텝 (F7)")
            self.lbl_run_status.setStyleSheet("color: #0284c7; font-weight: bold;")
        if hasattr(self, "popup_play_bar") and self.popup_play_bar:
            self.popup_play_bar.set_runner_state("stepping", "단일 스텝 실행 중...")

    def _on_step_completed(self, next_index: int):
        """단일 스텝 실행 완료 시 다음 노드로 포인터(선택 행) 이동 및 하이라이트 갱신"""
        if 0 <= next_index < len(self.project.scenarios):
            self.tbl_scenarios.selectRow(next_index)
            self._highlight_running_row_header(next_index)
            next_scen = self.project.scenarios[next_index]
            if hasattr(self, "popup_play_bar") and self.popup_play_bar:
                self.popup_play_bar.set_runner_state("paused", f"대기: s{next_scen.scenario_number} [{next_scen.name}]")
        else:
            self._highlight_running_row_header(None)

    def _highlight_running_row_header(self, row: Optional[int]):
        """시나리오 목록 표의 행 넘버링(세로 헤더) 셀 컬러로 현재 진행 중인 노드 강조 표기"""
        self._current_running_row = row
        idx = row if row is not None else -1
        if hasattr(self.tbl_scenarios, "set_highlight_row"):
            self.tbl_scenarios.set_highlight_row(idx)

    def _on_action_executing_visual(self, action, index, total):
        # 1. Action overlay for click/drag coordinates on target screen (completely click-through)
        if hasattr(self, "action_overlay") and self.action_overlay and hasattr(self, "chk_action_overlay") and self.chk_action_overlay.isChecked():
            self.action_overlay.set_target_hwnd(self.target_hwnd)
            self.action_overlay.show_action(action, index, total)

        # 2. Real-time sequence action progress output on play bar
        if hasattr(self, "popup_play_bar") and self.popup_play_bar:
            self.popup_play_bar.set_action_status(action, index, total)

    def _on_action_finished_visual(self, action):
        if hasattr(self, "action_overlay") and self.action_overlay:
            self.action_overlay.hide_action_delayed(500)

    def _on_toggle_action_overlay(self, checked: bool):
        if hasattr(self, "action_overlay") and self.action_overlay:
            self.action_overlay.is_overlay_enabled = checked
            if not checked:
                self.action_overlay.clear_action()

    def _on_scenario_started(self, scenario_id: str):
        for row, s in enumerate(self.project.scenarios):
            if s.id == scenario_id:
                self.tbl_scenarios.selectRow(row)
                self._highlight_running_row_header(row)
                if hasattr(self, "popup_play_bar") and self.popup_play_bar:
                    self.popup_play_bar.set_runner_state("running", f"s{s.scenario_number} [{s.name}] 실행 중...")
                if hasattr(self, "floating_stop") and self.floating_stop:
                    self.floating_stop.set_status(f"s{s.scenario_number} [{s.name}]")
                break

    def _on_scenario_completed(self, scenario_id: str, result: str):
        pass

    def _on_runner_finished(self, reason: str):
        self.btn_run.setEnabled(True)
        if hasattr(self, "btn_run_selected"):
            self.btn_run_selected.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.btn_pause.setText("⏸ 일시정지")
        self.lbl_run_status.setText(f"완료 ({reason})")
        self.lbl_run_status.setStyleSheet("font-weight: bold;")
        self._highlight_running_row_header(None)
        if hasattr(self, "floating_stop") and self.floating_stop:
            self.floating_stop.hide()
        if hasattr(self, "popup_play_bar") and self.popup_play_bar:
            self.popup_play_bar.set_runner_state("stopped", f"완료 ({reason})")
        if hasattr(self, "action_overlay") and self.action_overlay:
            self.action_overlay.clear_action()

    # ==========================================
    # Popup Play Bar Controls & Signal Handlers
    # ==========================================
    def _toggle_popup_playbar(self):
        if not hasattr(self, "popup_play_bar") or not self.popup_play_bar:
            return
        if self.popup_play_bar.isVisible():
            self.popup_play_bar.hide()
            if hasattr(self, "btn_popup_playbar"):
                self.btn_popup_playbar.setChecked(False)
        else:
            self.popup_play_bar.refresh_scenarios(self.project.scenarios)
            geo = self.geometry()
            self.popup_play_bar.move(max(0, geo.x() + geo.width() - 480), max(0, geo.y() + 60))
            self.popup_play_bar.show()
            self.popup_play_bar.raise_()
            if hasattr(self, "btn_popup_playbar"):
                self.btn_popup_playbar.setChecked(True)

    def _on_playbar_start(self, scenario_id: Optional[str] = None):
        if scenario_id:
            for row, s in enumerate(self.project.scenarios):
                if s.id == scenario_id:
                    self.tbl_scenarios.selectRow(row)
                    break
            self._on_start_execution(start_scenario_id=scenario_id)
        else:
            self._on_start_execution()

    def _on_playbar_step(self, scenario_id: Optional[str] = None):
        if scenario_id:
            for row, s in enumerate(self.project.scenarios):
                if s.id == scenario_id:
                    self.tbl_scenarios.selectRow(row)
                    break
        self._on_step_execution()

    def _on_playbar_select_scenario(self, scenario_id: str):
        for row, s in enumerate(self.project.scenarios):
            if s.id == scenario_id:
                self.tbl_scenarios.selectRow(row)
                break

    def _clear_logs(self):
        self.txt_log.clear()
        if hasattr(self, "_log_records"):
            self._log_records.clear()

    def _append_log(self, level: str, msg: str):
        if not hasattr(self, "_log_records"):
            self._log_records = []

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

        log_id = len(self._log_records)
        record = {
            "id": log_id,
            "level": level,
            "raw_msg": msg,
            "expanded": False,
            "has_mismatch": False
        }

        # Check for explicit [MISMATCH:count]detail[/MISMATCH] tags
        m_tag = re.search(r'\[MISMATCH(?::(\d+))?\](.*?)\[/MISMATCH\]', msg, re.DOTALL)
        if m_tag:
            count = m_tag.group(1) or ""
            detail = m_tag.group(2).strip()
            record["has_mismatch"] = True
            record["prefix_text"] = msg[:m_tag.start()].strip()
            record["suffix_text"] = msg[m_tag.end():].strip()
            record["mismatch_detail"] = detail
            record["fail_count"] = count
        elif "\n     └ 불일치: " in msg or "\n  └ 불일치: " in msg:
            sep = "\n     └ 불일치: " if "\n     └ 불일치: " in msg else "\n  └ 불일치: "
            parts = msg.split(sep, 1)
            record["has_mismatch"] = True
            record["prefix_text"] = parts[0].strip()
            record["suffix_text"] = ""
            record["mismatch_detail"] = parts[1].strip()
            record["fail_count"] = ""

        self._log_records.append(record)

        # Append newly formatted HTML
        html = self._format_log_record_html(record, pal, color, prefix_color)
        self.txt_log.append(html)

        if self.chk_autoscroll.isChecked():
            sb = self.txt_log.verticalScrollBar()
            sb.setValue(sb.maximum())

    def _format_log_record_html(self, record: dict, pal: dict, color: str, prefix_color: str) -> str:
        log_id = record["id"]
        level = record["level"]

        # Equalize word width for log levels (INFO, SUCCESS, ACTION, WARN, ERROR)
        # Pad to 7 characters (length of 'SUCCESS') with non-breaking spaces for alignment
        padded_level = level.ljust(7)
        level_html = padded_level.replace(" ", "&nbsp;")
        tag_prefix = f"<span style='color: {prefix_color}; font-family: Consolas, monospace;'>[{level_html}]</span>"

        if record.get("has_mismatch"):
            prefix_t = record.get("prefix_text", "")
            suffix_t = record.get("suffix_text", "")
            suffix_part = f" {suffix_t}" if suffix_t else ""
            detail_t = record.get("mismatch_detail", "")
            cnt_str = f"불일치 {record['fail_count']}건" if record.get("fail_count") else "불일치"

            if not record.get("expanded", False):
                # Collapsed: Show clickable badge link to expand
                btn_link = f"<a href='toggle-mismatch:{log_id}' style='color: #38bdf8; text-decoration: none; font-weight: bold;'>[▶ {cnt_str} 세부내역 열기]</a>"
                return f"<div id='mismatch_{log_id}' style='margin: 1px 0;'>{tag_prefix} <span style='color: {color};'>{prefix_t} {btn_link}{suffix_part}</span></div>"
            else:
                # Expanded: Show clickable badge link to collapse, and formatted details indented per-point
                btn_link = f"<a href='toggle-mismatch:{log_id}' style='color: #f87171; text-decoration: none; font-weight: bold;'>[▼ {cnt_str} 세부내역 닫기]</a>"
                header_line = f"{tag_prefix} <span style='color: {color};'>{prefix_t} {btn_link}{suffix_part}</span>"

                # Format per-point detail lines
                detail_lines = [l.strip() for l in detail_t.split("\n") if l.strip()]
                formatted_items = []
                for line in detail_lines:
                    clean_l = line.lstrip("•").strip()
                    escaped_l = html.escape(clean_l)
                    escaped_l = escaped_l.replace("[일치]", "<span style='color: #22c55e; font-weight: bold;'>[일치]</span>")
                    escaped_l = escaped_l.replace("[불일치]", "<span style='color: #ef4444; font-weight: bold;'>[불일치]</span>")
                    formatted_items.append(f"<div style='margin: 2px 0;'>&bull; {escaped_l}</div>")
                inner_details = "".join(formatted_items)

                box_bg = "rgba(239, 68, 68, 0.12)" if not pal["is_light"] else "#fee2e2"
                box_border = "#ef4444"
                text_detail_color = "#fca5a5" if not pal["is_light"] else "#991b1b"

                detail_box = (
                    f"<div style='margin-left: 18px; margin-top: 3px; margin-bottom: 4px; padding: 6px 10px; "
                    f"background-color: {box_bg}; border-left: 3px solid {box_border}; border-radius: 4px; "
                    f"font-family: Consolas, monospace; font-size: 8.5pt; color: {text_detail_color}; line-height: 1.45;'>"
                    f"<div style='font-weight: bold; margin-bottom: 3px; color: {box_border};'>🔍 불일치 세부 포인트 목록:</div>"
                    f"{inner_details}"
                    f"</div>"
                )
                return f"<div id='mismatch_{log_id}' style='margin: 1px 0;'>{header_line}{detail_box}</div>"

        elif level == "USER":
            prefix_html = f"<span style='color: {color}; font-weight: bold;'>[사용자 로그]</span>"
            msg_html = f"<span style='color: {color}; font-weight: bold;'>{html.escape(record['raw_msg'])}</span>"
            return f"{prefix_html} {msg_html}"
        else:
            return f"{tag_prefix} <span style='color: {color};'>{record['raw_msg']}</span>"

    def _on_log_anchor_clicked(self, url):
        if hasattr(url, "toString"):
            url_str = url.toString() or url.path() or ""
        else:
            url_str = str(url)

        if "toggle-mismatch:" in url_str or "toggle_mismatch:" in url_str:
            try:
                for prefix in ("toggle-mismatch:", "toggle_mismatch:"):
                    if prefix in url_str:
                        log_id = int(url_str.split(prefix)[1].strip("/"))
                        break
                if hasattr(self, "_log_records") and 0 <= log_id < len(self._log_records):
                    self._log_records[log_id]["expanded"] = not self._log_records[log_id].get("expanded", False)
                    self._rerender_all_logs()
            except Exception:
                pass

    def _rerender_all_logs(self):
        if not hasattr(self, "_log_records") or not self._log_records:
            return

        sb = self.txt_log.verticalScrollBar()
        val = sb.value()
        was_at_bottom = (val >= sb.maximum() - 20)

        pal = get_theme_colors(self.current_theme)
        color_map = {
            "INFO": pal["log_info"],
            "ACTION": pal["log_action"],
            "SUCCESS": pal["log_success"],
            "WARN": pal["log_warn"],
            "ERROR": pal["log_error"],
            "USER": pal["log_user"]
        }
        prefix_color = "#64748b" if pal["is_light"] else "#8da4c4"

        html_blocks = []
        for rec in self._log_records:
            color = color_map.get(rec["level"], pal["text_primary"])
            html_blocks.append(self._format_log_record_html(rec, pal, color, prefix_color))

        self.txt_log.setHtml("<br>".join(html_blocks))

        if was_at_bottom and self.chk_autoscroll.isChecked():
            sb.setValue(sb.maximum())
        else:
            sb.setValue(val)

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
                self._update_window_title()
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
                self._update_window_title()
                self.spin_loops.setValue(self.project.loop_count)
                self.spin_loop_delay.setValue(self.project.loop_delay_seconds)
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
                if hasattr(self, "modules_widget"):
                    self.modules_widget.set_project(self.project, self.target_hwnd)
                if hasattr(self, "inspector"):
                    self.inspector.set_project(self.project)
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
            self._on_stop_execution()
            event.accept()
        elif event.key() == Qt.Key_F7:
            self._on_step_execution()
            event.accept()
        else:
            super().keyPressEvent(event)
