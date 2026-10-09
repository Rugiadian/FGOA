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
    QDialog
)
from PyQt5.QtGui import QColor, QFont, QIcon, QKeySequence, QDrag, QCursor, QPixmap
from PyQt5.QtCore import Qt, QTimer, QFileSystemWatcher, QProcess, QByteArray, pyqtSignal, QMimeData, QSize, QPoint

from core.models import Project, Scenario, Condition, Action, ColorPoint, ActionSequence
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
from core.global_hotkey import GlobalHotkeyListener
from ui.floating_stop_widget import GlobalFloatingStopWidget
from ui.custom_spinbox import CustomSpinBox
from core.path_utils import to_absolute_path, to_relative_path
from core.config import get_config_filepath


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

    def _init_global_hotkey_and_floating_stop(self):
        """Initializes global F6 keyboard listener and always-on-top floating emergency stop widget."""
        self.global_hotkey = GlobalHotkeyListener(None)
        self.global_hotkey.sig_stop_hotkey.connect(self._on_global_hotkey_stop)
        self.global_hotkey.sig_pause_hotkey.connect(self._on_global_hotkey_pause)
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

    def _on_global_hotkey_pause(self):
        """Global Shift+F6 hotkey handler (toggles pause/resume system-wide)."""
        if self.runner and self.runner.isRunning():
            is_paused = getattr(self.runner, "_is_paused", False)
            state_desc = "재개" if is_paused else "일시정지"
            self._append_log("INFO", f"⏸ [전역 단축키] Shift+F6 {state_desc}가 수신되었습니다.")
            self._on_pause_execution()

    def _update_window_title(self):
        """Update window title with application version and current project filename."""
        title = f"FGOA v{__version__} - 화면 인식 스마트 윈도우 오토 툴"
        if self.current_project_path:
            proj_name = os.path.basename(self.current_project_path)
            title = f"{title} [{proj_name}]"
        self.setWindowTitle(title)

    def _check_reload_state(self) -> bool:
        """Restore project state if reloading after code modification."""
        if os.path.exists(TEMP_RELOAD_FILE):
            try:
                with open(TEMP_RELOAD_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.project = Project.from_dict(data)
                os.remove(TEMP_RELOAD_FILE)
                return True
            except Exception:
                pass
        return False

    def _load_app_config(self):
        cfg_file = get_config_filepath()
        if os.path.exists(cfg_file):
            try:
                with open(cfg_file, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    self._cached_config = cfg
                    self.current_theme = cfg.get("theme", "light")
                    self.current_layout_name = cfg.get("layout_name", "기본 3열 (Default)")
                    self.custom_layouts = cfg.get("custom_layouts", {})
                    self._saved_dock_state = cfg.get("dock_layout_state", None)
                    self.last_project_path = cfg.get("last_project_path", None)
                    self._last_config_target_title = cfg.get("last_target_title", "")
                    if hasattr(self.project, "target_client_width"):
                        self.project.target_client_width = cfg.get("last_target_width", 1600)
                        self.project.target_client_height = cfg.get("last_target_height", 900)
                        self.project.target_window_title = self._last_config_target_title

                    # If UI controls are already initialized, apply them immediately
                    self._apply_ui_config(cfg)

                    # Restore window geometry (exact position, size, maximized state, screen)
                    geom_hex = cfg.get("window_geometry")
                    restored = False
                    if geom_hex:
                        try:
                            restored = self.restoreGeometry(QByteArray.fromHex(geom_hex.encode()))
                        except Exception:
                            restored = False
                    if not restored:
                        w = cfg.get("window_width")
                        h = cfg.get("window_height")
                        x = cfg.get("window_x")
                        y = cfg.get("window_y")
                        if w and h:
                            self.resize(max(1020, int(w)), max(650, int(h)))
                        if x is not None and y is not None:
                            try:
                                screens = QApplication.screens()
                                on_screen = any(s.geometry().contains(QPoint(int(x), int(y))) for s in screens)
                                if on_screen:
                                    self.move(int(x), int(y))
                            except Exception:
                                self.move(int(x), int(y))
                        if cfg.get("window_is_maximized", False):
                            self.showMaximized()
            except Exception:
                pass

    def _apply_ui_config(self, cfg: Optional[Dict[str, Any]] = None):
        """Applies loaded user configuration to UI widgets and overlays safely without trigger cascades."""
        if cfg is None:
            cfg = getattr(self, "_cached_config", None)
        if not cfg:
            return

        # 1. Anti-burn in settings (번인 방지)
        burn_mode = cfg.get("anti_burn_mode", 1)
        burn_interval = cfg.get("anti_burn_interval_min", 5)
        burn_enabled = cfg.get("anti_burn_enabled", False)

        if hasattr(self, "combo_anti_burn_mode") and self.combo_anti_burn_mode:
            idx = self.combo_anti_burn_mode.findData(burn_mode)
            if idx >= 0:
                self.combo_anti_burn_mode.blockSignals(True)
                self.combo_anti_burn_mode.setCurrentIndex(idx)
                self.combo_anti_burn_mode.blockSignals(False)

        if hasattr(self, "spin_anti_burn_min") and self.spin_anti_burn_min:
            self.spin_anti_burn_min.blockSignals(True)
            self.spin_anti_burn_min.setValue(burn_interval)
            self.spin_anti_burn_min.blockSignals(False)

        if hasattr(self, "chk_anti_burn") and self.chk_anti_burn:
            self.chk_anti_burn.blockSignals(True)
            self.chk_anti_burn.setChecked(burn_enabled)
            self.chk_anti_burn.blockSignals(False)

        if hasattr(self, "anti_burn_overlay") and self.anti_burn_overlay:
            self.anti_burn_overlay.set_mode(burn_mode)
            self.anti_burn_overlay.set_interval_minutes(burn_interval)
            self.anti_burn_overlay.set_enabled(burn_enabled)

        # 2. Action Overlay (조작 시각화)
        action_overlay_enabled = cfg.get("action_overlay_enabled", True)
        if hasattr(self, "chk_action_overlay") and self.chk_action_overlay:
            self.chk_action_overlay.blockSignals(True)
            self.chk_action_overlay.setChecked(action_overlay_enabled)
            self.chk_action_overlay.blockSignals(False)
        if hasattr(self, "action_overlay") and self.action_overlay:
            self.action_overlay.is_overlay_enabled = action_overlay_enabled

        # 3. Global Floating Stop (전역 플로팅 정지)
        floating_stop_enabled = cfg.get("floating_stop_enabled", False)
        if hasattr(self, "chk_floating_stop") and self.chk_floating_stop:
            self.chk_floating_stop.blockSignals(True)
            self.chk_floating_stop.setChecked(floating_stop_enabled)
            self.chk_floating_stop.blockSignals(False)

        # 4. Hot Reload (코드 자동 리로드)
        hot_reload_enabled = cfg.get("hot_reload_enabled", False)
        if hasattr(self, "chk_hot_reload") and self.chk_hot_reload:
            self.chk_hot_reload.blockSignals(True)
            self.chk_hot_reload.setChecked(hot_reload_enabled)
            self.chk_hot_reload.blockSignals(False)

        # 5. Log Autoscroll (자동 스크롤)
        autoscroll_enabled = cfg.get("autoscroll_enabled", True)
        if hasattr(self, "chk_autoscroll") and self.chk_autoscroll:
            self.chk_autoscroll.blockSignals(True)
            self.chk_autoscroll.setChecked(autoscroll_enabled)
            self.chk_autoscroll.blockSignals(False)

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

            is_maximized = self.isMaximized()
            if is_maximized:
                norm_geo = self.normalGeometry()
                win_x = norm_geo.x()
                win_y = norm_geo.y()
                win_w = norm_geo.width()
                win_h = norm_geo.height()
            else:
                win_x = self.x()
                win_y = self.y()
                win_w = self.width()
                win_h = self.height()

            cfg.update({
                "theme": self.current_theme,
                "window_x": win_x,
                "window_y": win_y,
                "window_width": win_w,
                "window_height": win_h,
                "window_is_maximized": is_maximized,
                "window_geometry": self.saveGeometry().toHex().data().decode(),
                "last_target_title": getattr(self.project, "target_window_title", "") or getattr(self, "_last_config_target_title", ""),
                "last_target_width": getattr(self.project, "target_client_width", 1600),
                "last_target_height": getattr(self.project, "target_client_height", 900),
                "layout_name": getattr(self, "current_layout_name", "기본 3열 (Default)"),
                "custom_layouts": getattr(self, "custom_layouts", {}),
                "last_project_path": self.current_project_path,
            })

            # Save UI controls state safely (only overwrite if widget exists to avoid erasing loaded configs)
            if hasattr(self, "chk_anti_burn") and self.chk_anti_burn:
                cfg["anti_burn_enabled"] = self.chk_anti_burn.isChecked()
            if hasattr(self, "combo_anti_burn_mode") and self.combo_anti_burn_mode and self.combo_anti_burn_mode.currentData() is not None:
                cfg["anti_burn_mode"] = self.combo_anti_burn_mode.currentData()
            if hasattr(self, "spin_anti_burn_min") and self.spin_anti_burn_min:
                cfg["anti_burn_interval_min"] = self.spin_anti_burn_min.value()
            if hasattr(self, "chk_action_overlay") and self.chk_action_overlay:
                cfg["action_overlay_enabled"] = self.chk_action_overlay.isChecked()
            if hasattr(self, "chk_floating_stop") and self.chk_floating_stop:
                cfg["floating_stop_enabled"] = self.chk_floating_stop.isChecked()
            if hasattr(self, "chk_hot_reload") and self.chk_hot_reload:
                cfg["hot_reload_enabled"] = self.chk_hot_reload.isChecked()
            if hasattr(self, "chk_autoscroll") and self.chk_autoscroll:
                cfg["autoscroll_enabled"] = self.chk_autoscroll.isChecked()

            self._cached_config = cfg

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
        if hasattr(self, "runner") and self.runner and self.runner.isRunning():
            try:
                self.runner.stop()
                self.runner.wait(1000)
            except Exception:
                pass
        if hasattr(self, "_config_save_timer") and self._config_save_timer:
            self._config_save_timer.stop()
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
        if hasattr(self, "virtual_canvas_window") and self.virtual_canvas_window:
            try:
                self.virtual_canvas_window.close()
            except Exception:
                pass
        if hasattr(self, "anti_burn_overlay") and self.anti_burn_overlay:
            try:
                self.anti_burn_overlay.cleanup()
            except Exception:
                pass
        self._save_app_config()
        super().closeEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "anti_burn_overlay") and self.anti_burn_overlay:
            self.anti_burn_overlay.update_geometry()
        if hasattr(self, "_config_save_timer") and self._config_save_timer:
            self._config_save_timer.start()

    def moveEvent(self, event):
        super().moveEvent(event)
        if hasattr(self, "_config_save_timer") and self._config_save_timer:
            self._config_save_timer.start()

    def _on_toggle_anti_burn(self, checked: bool):
        if hasattr(self, "anti_burn_overlay") and self.anti_burn_overlay:
            self.anti_burn_overlay.set_enabled(checked)
            self._save_app_config()
            mins = self.spin_anti_burn_min.value() if hasattr(self, "spin_anti_burn_min") else 5
            mode = self.anti_burn_overlay.get_mode()
            mode_name = "앱 창" if mode == 1 else "데스크탑 전체 화면"
            if checked:
                self._append_log("INFO", f"🖥️ [모니터 번인 방지] 모드 {mode}({mode_name}) {mins}분 주기로 화면 전환 활성화 (조작 간섭 없음)")
            else:
                self._append_log("INFO", "🖥️ [모니터 번인 방지] 비활성화됨")

    def _on_anti_burn_mode_changed(self, index: int):
        if not hasattr(self, "combo_anti_burn_mode") or not self.combo_anti_burn_mode:
            return
        mode = self.combo_anti_burn_mode.itemData(index)
        if hasattr(self, "anti_burn_overlay") and self.anti_burn_overlay:
            self.anti_burn_overlay.set_mode(mode)
        self._save_app_config()
        mode_name = "앱 창" if mode == 1 else "데스크탑 전체 화면 (해상도 무관)"
        self._append_log("INFO", f"🖥️ [모니터 번인 방지] 모드 {mode} ({mode_name}) 설정됨")

    def _on_test_anti_burn(self):
        if not hasattr(self, "anti_burn_overlay") or not self.anti_burn_overlay:
            return
        if self.anti_burn_overlay.is_transitioning():
            self.anti_burn_overlay.stop_transition()
            self._append_log("INFO", "🖥️ [모니터 번인 방지] 번인 방지 테스트 중지됨")
        else:
            mode = self.anti_burn_overlay.get_mode()
            mode_name = "모드 1 (앱 창)" if mode == 1 else "모드 2 (데스크탑 전체 화면)"
            self._append_log("INFO", f"🖥️ [모니터 번인 방지] {mode_name} 화면 전환 효과 테스트 시작 (조작 간섭 없음)")
            self.anti_burn_overlay.start_transition()

    def _on_anti_burn_started(self):
        if hasattr(self, "btn_test_anti_burn") and self.btn_test_anti_burn:
            self.btn_test_anti_burn.setText("⏹ 중지")

    def _on_anti_burn_finished(self):
        if hasattr(self, "btn_test_anti_burn") and self.btn_test_anti_burn:
            self.btn_test_anti_burn.setText("🧪 테스트")

    def _on_anti_burn_interval_changed(self, val: int):
        if hasattr(self, "anti_burn_overlay") and self.anti_burn_overlay:
            self.anti_burn_overlay.set_interval_minutes(val)
            self._save_app_config()

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
        self.combo_layout = QComboBox()
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
        row2_reorder_layout = QHBoxLayout(row2_reorder_bar)
        row2_reorder_layout.setContentsMargins(0, 0, 0, 0)
        row2_reorder_layout.setSpacing(4)

        btn_up = QPushButton("⬆️ 위로")
        btn_up.setToolTip("선택한 시나리오를 한 줄 위로 이동")
        btn_up.clicked.connect(self._on_move_up)
        row2_reorder_layout.addWidget(btn_up)

        btn_down = QPushButton("⬇️ 아래로")
        btn_down.setToolTip("선택한 시나리오를 한 줄 아래로 이동")
        btn_down.clicked.connect(self._on_move_down)
        row2_reorder_layout.addWidget(btn_down)

        sep_tb = QFrame()
        sep_tb.setFrameShape(QFrame.VLine)
        sep_tb.setFrameShadow(QFrame.Sunken)
        sep_tb.setStyleSheet("color: #94a3b8; margin: 2px 2px;")
        row2_reorder_layout.addWidget(sep_tb)

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

        row2_reorder_layout.addStretch()
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
        self.chk_anti_burn.setToolTip("지정한 n분 주기마다 화면을 서서히 전환하여 모니터 번인을 방지합니다. (조작 간섭 전혀 없음)")
        self.chk_anti_burn.toggled.connect(self._on_toggle_anti_burn)
        row2_ctrl.addWidget(self.chk_anti_burn)

        self.combo_anti_burn_mode = QComboBox()
        self.combo_anti_burn_mode.addItem("모드 1: 앱 창", 1)
        self.combo_anti_burn_mode.addItem("모드 2: 전체 화면 (데스크탑)", 2)
        self.combo_anti_burn_mode.setToolTip("번인 방지 모드 선택:\n- 모드 1: FGOA 창 내부 화면 전환\n- 모드 2: 모니터 데스크탑 전체 화면 전환 (해상도 무관)")
        self.combo_anti_burn_mode.currentIndexChanged.connect(self._on_anti_burn_mode_changed)
        row2_ctrl.addWidget(self.combo_anti_burn_mode)

        self.spin_anti_burn_min = QSpinBox()
        self.spin_anti_burn_min.setRange(1, 120)
        self.spin_anti_burn_min.setValue(5)
        self.spin_anti_burn_min.setSuffix("분")
        self.spin_anti_burn_min.setToolTip("번인 방지 화면 전환 주기 (1~120분)")
        self.spin_anti_burn_min.valueChanged.connect(self._on_anti_burn_interval_changed)
        row2_ctrl.addWidget(self.spin_anti_burn_min)

        self.btn_test_anti_burn = QPushButton("🧪 테스트")
        self.btn_test_anti_burn.setObjectName("btn_test_anti_burn")
        self.btn_test_anti_burn.setToolTip("선택한 번인 방지 모드의 화면 전환 효과를 즉시 1회 테스트합니다. (실행 중 클릭 시 중지)")
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
        stylesheet = get_stylesheet(self.current_theme)
        self.setStyleSheet(stylesheet)
        app = QApplication.instance()
        if app:
            app.setStyleSheet(stylesheet)
        if hasattr(self, "tbl_scenarios"):
            self.tbl_scenarios.current_theme = self.current_theme
        self._update_theme_toggle_btn()
        if hasattr(self, "lbl_authoring_res"):
            self._update_authoring_resolution_display()
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
            # 러너 실행 중에는 녹색 헤더 하이라이트만 유지하고 표 항목 선택을 강제 복원하지 않음
            if self.runner and self.runner.isRunning():
                return
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
        if saved_scen and self.project:
            for idx, s in enumerate(self.project.scenarios):
                if s.id == saved_scen.id:
                    if getattr(s, "is_folder_start", s.node_type in ("folder", "folder_start")):
                        end_idx = self.project.find_matching_folder_end(idx)
                        if end_idx is not None and end_idx < len(self.project.scenarios):
                            self.project.scenarios[end_idx].enabled = s.enabled
                    elif getattr(s, "is_folder_end", s.node_type == "folder_end"):
                        start_idx = self.project.find_matching_folder_start(idx)
                        if start_idx is not None and start_idx < len(self.project.scenarios):
                            self.project.scenarios[start_idx].enabled = s.enabled
                    break
        self._push_scenario_undo_state(f"시나리오 s{saved_scen.scenario_number} 속성 저장")
        self._refresh_scenario_table()
        self.status_bar.showMessage(f"💾 시나리오 s{saved_scen.scenario_number} [{saved_scen.name}] 저장 완료", 3000)

    def _on_inspector_scenario_changed(self, modified_scen: Scenario):
        """Called when scenario is saved or updated."""
        pass

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
        folder_analysis = self.project.analyze_folders() if hasattr(self.project, "analyze_folders") else {}

        if hasattr(self, "lbl_scen_count"):
            self.lbl_scen_count.setText(f"총 {len(self.project.scenarios)}개")

        selected_row = -1
        rows = self.tbl_scenarios.selectionModel().selectedRows()
        if rows:
            selected_row = rows[0].row()

        self.tbl_scenarios.blockSignals(True)
        self.tbl_scenarios.setRowCount(len(self.project.scenarios))

        collapsed_stack = []
        folder_disabled_stack = []
        for row, scen in enumerate(self.project.scenarios):
            is_start = getattr(scen, "is_folder_start", scen.node_type in ("folder", "folder_start"))
            is_end = getattr(scen, "is_folder_end", scen.node_type == "folder_end")

            is_in_disabled_folder = any(folder_disabled_stack)

            if is_start:
                folder_disabled_stack.append((not scen.enabled) or is_in_disabled_folder)

            is_hidden = any(collapsed_stack)
            self.tbl_scenarios.setRowHidden(row, is_hidden)

            depth = depths[row] if row < len(depths) else 0
            loop_info = loop_analysis.get(row)
            folder_info = folder_analysis.get(row)
            self._update_table_row(row, scen, depth, loop_info, folder_info, is_in_disabled_folder=is_in_disabled_folder)

            # Ensure vertical header item exists
            v_item = self.tbl_scenarios.verticalHeaderItem(row)
            if not v_item:
                v_item = QTableWidgetItem(str(row + 1))
                self.tbl_scenarios.setVerticalHeaderItem(row, v_item)

            if is_start:
                collapsed_stack.append(getattr(scen, "is_collapsed", False))
            elif is_end:
                if folder_disabled_stack:
                    folder_disabled_stack.pop()
                if collapsed_stack:
                    collapsed_stack.pop()

        self.tbl_scenarios.blockSignals(False)

        # Restore running header highlight if actively executing
        if hasattr(self, "_current_running_row") and self._current_running_row is not None:
            self._highlight_running_row_header(self._current_running_row)

        # Restore paused row highlight if execution is paused
        if getattr(self, "_paused_scenario_id", None):
            paused_idx = next((i for i, s in enumerate(self.project.scenarios) if s.id == self._paused_scenario_id), None)
            if paused_idx is not None and hasattr(self.tbl_scenarios, "set_paused_row"):
                self.tbl_scenarios.set_paused_row(paused_idx)
        else:
            if hasattr(self.tbl_scenarios, "set_paused_row"):
                self.tbl_scenarios.set_paused_row(-1)

        # Restore selection
        if 0 <= selected_row < len(self.project.scenarios):
            self.tbl_scenarios.selectRow(selected_row)
        elif self.project.scenarios:
            self.tbl_scenarios.selectRow(0)

        # Notify popup play bar of scenario changes
        if hasattr(self, "popup_play_bar") and self.popup_play_bar:
            self.popup_play_bar.refresh_scenarios(self.project.scenarios)

    def _update_table_row(self, row: int, scen: Scenario, depth: int = 0, loop_info: Optional[Dict[str, Any]] = None, folder_info: Optional[Dict[str, Any]] = None, is_in_disabled_folder: bool = False):
        is_folder_start = getattr(scen, "is_folder_start", scen.node_type in ("folder", "folder_start"))
        is_folder_end = getattr(scen, "is_folder_end", scen.node_type == "folder_end")
        is_folder = is_folder_start or is_folder_end
        is_node_disabled = bool(is_in_disabled_folder or (not scen.enabled))
        folder_is_disabled = is_folder and is_node_disabled

        child_disabled_color = QColor("#94a3b8" if self.current_theme == "light" else "#64748b")
        child_disabled_bg = QColor("#f8fafc" if self.current_theme == "light" else "#0b0f19")

        # Distinct child member background for nodes inside folders
        is_folder_child = bool(folder_info and folder_info.get("is_child", False))
        child_tint_bg = None
        if is_folder_child and not is_folder:
            child_bg_str = folder_info.get("bg_light" if self.current_theme == "light" else "bg_dark")
            if child_bg_str:
                child_tint_bg = QColor(child_bg_str)

        if is_folder:
            if folder_is_disabled:
                folder_bg = QColor("#f1f5f9" if self.current_theme == "light" else "#1e293b")
                folder_txt = QColor("#64748b" if self.current_theme == "light" else "#94a3b8")
            elif folder_info and folder_info.get("has_pair", True):
                folder_bg_str = folder_info.get("bg_light" if self.current_theme == "light" else "bg_dark", "#fef3c7")
                folder_txt_str = folder_info.get("color_light" if self.current_theme == "light" else "color_dark", "#b45309")
                folder_bg = QColor(folder_bg_str)
                folder_txt = QColor(folder_txt_str)
            else:
                folder_bg = QColor("#fef3c7" if self.current_theme == "light" else "#451a03")
                folder_txt = QColor("#b45309" if self.current_theme == "light" else "#fde68a")

        # 0. Snapshot (레퍼런스 이미지 스냅샷 - 인식조건 이미지 기본값, 없으면 빈칸)
        if is_folder:
            self.tbl_scenarios.setCellWidget(row, 0, None)
            it_empty = QTableWidgetItem("")
            it_empty.setBackground(folder_bg)
            it_empty.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.tbl_scenarios.setItem(row, 0, it_empty)
        else:
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
        if is_folder:
            uid_str = f"📁s{scen.scenario_number}"
            it_uid = QTableWidgetItem(uid_str)
            it_uid.setTextAlignment(Qt.AlignCenter)
            it_uid.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            it_uid.setToolTip(f"그룹 폴더: s{scen.scenario_number}")
            it_uid.setForeground(child_disabled_color if folder_is_disabled else folder_txt)
            it_uid.setBackground(folder_bg)
            if folder_is_disabled:
                it_uid.setData(Qt.UserRole + 99, True)
            f = it_uid.font()
            f.setBold(True)
            it_uid.setFont(f)
            self.tbl_scenarios.setItem(row, 1, it_uid)
        else:
            uid_str = f"s{scen.scenario_number}"
            it_uid = QTableWidgetItem(uid_str)
            it_uid.setTextAlignment(Qt.AlignCenter)
            it_uid.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            if is_node_disabled:
                it_uid.setForeground(child_disabled_color)
                it_uid.setData(Qt.UserRole + 99, True)
                it_uid.setToolTip(f"시나리오 고유 ID: s{scen.scenario_number} ({'상위 폴더 비활성화' if is_in_disabled_folder else '개별 비활성화됨'})")
            else:
                it_uid.setToolTip(f"시나리오 고유 ID: s{scen.scenario_number}")
            self.tbl_scenarios.setItem(row, 1, it_uid)

        # 2. Enabled Checkbox
        chk_widget = QWidget()
        if is_folder:
            chk_widget.setStyleSheet(f"background-color: {folder_bg.name()};")
        chk_layout = QHBoxLayout(chk_widget)
        chk_layout.setContentsMargins(0, 0, 0, 0)
        chk_layout.setAlignment(Qt.AlignCenter)
        chk = QCheckBox()
        chk.setChecked(scen.enabled)
        if is_folder:
            chk.setToolTip("폴더 및 하위 항목 전체 활성화/비활성화 토글")
        elif is_in_disabled_folder:
            chk.setToolTip("상위 그룹 폴더가 비활성화되어 있어 이 노드는 실행 시 건너뜁니다.")
        chk.stateChanged.connect(lambda state, s=scen: self._on_scenario_toggle(s, state))

        # 폴더 비활성화 시 내부 노드의 체크 버튼을 회색으로 표시
        if is_in_disabled_folder:
            chk_color = "#94a3b8" if self.current_theme == "light" else "#64748b"
            chk_border = "#cbd5e1" if self.current_theme == "light" else "#475569"
            chk_bg = "#f8fafc" if self.current_theme == "light" else "#1e293b"
            chk.setStyleSheet(f"""
                QCheckBox::indicator {{
                    width: 16px;
                    height: 16px;
                    border: 1px solid {chk_border};
                    border-radius: 3px;
                    background-color: {chk_bg};
                }}
                QCheckBox::indicator:checked {{
                    background-color: {chk_color};
                    border-color: {chk_color};
                    image: url("{CHECK_ICON_PATH}");
                }}
            """)

        chk_layout.addWidget(chk)
        self.tbl_scenarios.setCellWidget(row, 2, chk_widget)

        # 3. Name with Loop & Folder Hierarchy UI, distinct pair colors, and orphaned warnings
        indent = ("    " * (depth - 1)) + "  ↳ " if depth > 0 else ""
        if is_folder_start:
            p_num = folder_info.get("pair_number", 1) if folder_info else 1
            c_cnt = folder_info.get("child_count", 0) if folder_info else 0
            if folder_info and not folder_info.get("has_pair", True):
                it_name = QTableWidgetItem(f"{indent}⚠️ [폴더 짝 없음: 종료 노드 소실!] 📁 {scen.name}")
                it_name.setForeground(QColor("#ef4444"))
                it_name.setToolTip("대응되는 폴더 종료 노드가 없습니다. 폴더 블록을 확인해주세요.")
            else:
                collapse_icon = "▶ " if getattr(scen, "is_collapsed", False) else "▼ "
                if getattr(scen, "is_collapsed", False):
                    it_name = QTableWidgetItem(f"{indent}{collapse_icon}📁 [폴더 #{p_num}] {scen.name}  ({c_cnt}개 항목 접힘)")
                else:
                    it_name = QTableWidgetItem(f"{indent}{collapse_icon}📂 [폴더 #{p_num} 시작] {scen.name}")
                it_name.setToolTip(f"📁 그룹 폴더 #{p_num}: {scen.name} (더블 클릭하여 펼치기/접기)")
                it_name.setForeground(child_disabled_color if folder_is_disabled else folder_txt)
                it_name.setBackground(folder_bg)
            f = it_name.font()
            f.setBold(True)
            it_name.setFont(f)
        elif is_folder_end:
            p_num = folder_info.get("pair_number", 1) if folder_info else 1
            if folder_info and not folder_info.get("has_pair", True):
                it_name = QTableWidgetItem(f"{indent}⚠️ [폴더 짝 없음: 시작 노드 소실!] 📁 {scen.name}")
                it_name.setForeground(QColor("#ef4444"))
                it_name.setToolTip("대응되는 폴더 시작 노드가 없습니다.")
            else:
                partner_idx = folder_info.get("partner_index") if folder_info else None
                start_str = f"s{self.project.scenarios[partner_idx].scenario_number} " if partner_idx is not None and partner_idx < len(self.project.scenarios) else ""
                it_name = QTableWidgetItem(f"{indent}📁 [폴더 #{p_num} 끝] → {start_str}{scen.name} 종료")
                it_name.setToolTip(f"📁 그룹 폴더 #{p_num} 종료 지점")
                it_name.setForeground(child_disabled_color if folder_is_disabled else folder_txt)
                it_name.setBackground(folder_bg)
            f = it_name.font()
            f.setBold(True)
            it_name.setFont(f)
        elif scen.node_type == "loop_start":
            if loop_info and not loop_info.get("has_pair", True):
                loop_desc = scen.get_loop_summary()
                it_name = QTableWidgetItem(f"{indent}⚠️ [루프 짝 없음: 종료 노드 소실!] {loop_desc} [{scen.name}]")
                it_name.setForeground(QColor("#ef4444"))
                it_name.setToolTip("⚠️ 대응되는 루프 종료 노드가 없습니다! 루프 블록을 확인해주세요.")
            else:
                p_num = loop_info.get("pair_number", 1) if loop_info else 1
                color_hex = (loop_info.get("color_light") if self.current_theme == "light" else loop_info.get("color_dark")) if loop_info else ("#2563eb" if self.current_theme == "light" else "#60a5fa")
                it_name = QTableWidgetItem(f"{indent}🔁 [루프 #{p_num} 시작: {scen.loop_count}회] [{scen.name}]")
                it_name.setForeground(child_disabled_color if is_node_disabled else QColor(color_hex))
                it_name.setToolTip(f"루프 #{p_num} 시작 노드")
            f = it_name.font()
            f.setBold(True)
            it_name.setFont(f)
        elif scen.node_type == "loop_end":
            if loop_info and not loop_info.get("has_pair", True):
                it_name = QTableWidgetItem(f"{indent}⚠️ [루프 짝 없음: 시작 노드 소실!] 🔁 루프 종료 (시작 노드 없음)")
                it_name.setForeground(QColor("#ef4444"))
                it_name.setToolTip("⚠️ 대응되는 루프 시작 노드가 없습니다! 루프 블록을 확인해주세요.")
            else:
                p_num = loop_info.get("pair_number", 1) if loop_info else 1
                color_hex = (loop_info.get("color_light") if self.current_theme == "light" else loop_info.get("color_dark")) if loop_info else ("#7c3aed" if self.current_theme == "light" else "#c084fc")
                partner_idx = loop_info.get("partner_index") if loop_info else None
                start_num_str = f"s{self.project.scenarios[partner_idx].scenario_number}" if partner_idx is not None and partner_idx < len(self.project.scenarios) else ""
                it_name = QTableWidgetItem(f"{indent}🔁 [루프 #{p_num} 종료] → 루프 {start_num_str} 복귀")
                it_name.setForeground(child_disabled_color if is_node_disabled else QColor(color_hex))
                it_name.setToolTip(f"루프 #{p_num} 종료 노드 (루프 #{p_num} 시작점으로 복귀)")
            f = it_name.font()
            f.setBold(True)
            it_name.setFont(f)
        else:
            it_name = QTableWidgetItem(f"{indent}{scen.name}")
            if is_node_disabled:
                it_name.setForeground(child_disabled_color)
                if is_in_disabled_folder:
                    it_name.setToolTip(f"상위 그룹 폴더가 비활성화되어 실행 시 건너뜁니다.\n{scen.name}")
                else:
                    it_name.setToolTip(f"🚫 [비활성] 이 노드는 비활성화되어 실행되지 않습니다.\n{scen.name}")
            else:
                it_name.setToolTip(scen.name)
        if folder_is_disabled if is_folder else is_node_disabled:
            it_name.setData(Qt.UserRole + 99, True)
        it_name.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        is_paused = (scen.id == getattr(self, "_paused_scenario_id", None))
        if is_paused:
            it_name.setText(f"⏸ [일시정지] {it_name.text()}")
            it_name.setForeground(QColor("#ea580c"))
            f = it_name.font()
            f.setBold(True)
            it_name.setFont(f)
            it_name.setToolTip(f"⏸ [일시정지 중] 실행이 일시정지된 노드입니다. 재개 시 이 노드(s{scen.scenario_number})부터 실행됩니다.\n{it_name.toolTip() or ''}")
        self.tbl_scenarios.setItem(row, 3, it_name)

        # 4. Condition Module (Eye)
        self.tbl_scenarios.setCellWidget(row, 4, None)
        if is_folder_start:
            it_cond = QTableWidgetItem("(그룹 폴더 시작)")
            it_cond.setForeground(child_disabled_color if folder_is_disabled else folder_txt)
            it_cond.setBackground(folder_bg)
            if folder_is_disabled:
                it_cond.setData(Qt.UserRole + 99, True)
            it_cond.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            it_cond.setToolTip("하위 시나리오들을 시각적으로 묶어주는 그룹 폴더입니다. (실행 시 즉시 통과)")
            self.tbl_scenarios.setItem(row, 4, it_cond)
        elif is_folder_end:
            it_cond = QTableWidgetItem("(그룹 폴더 종료)")
            it_cond.setForeground(child_disabled_color if folder_is_disabled else folder_txt)
            it_cond.setBackground(folder_bg)
            if folder_is_disabled:
                it_cond.setData(Qt.UserRole + 99, True)
            it_cond.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            it_cond.setToolTip("그룹 폴더가 끝나는 지점입니다. (실행 시 즉시 통과)")
            self.tbl_scenarios.setItem(row, 4, it_cond)
        else:
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
            if is_node_disabled:
                it_cond.setForeground(child_disabled_color)
                it_cond.setData(Qt.UserRole + 99, True)
            elif eff_cond and getattr(scen, "condition_id", None):
                it_cond.setForeground(QColor("#2563eb" if self.current_theme == "light" else "#60a5fa"))
            elif scen.node_type != "normal":
                it_cond.setForeground(QColor("#64748b"))
            it_cond.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            it_cond.setToolTip("더블 클릭하여 인식조건 모듈 교체")
            self.tbl_scenarios.setItem(row, 4, it_cond)

        # 5. ActionSequence Module (Hand)
        self.tbl_scenarios.setCellWidget(row, 5, None)
        if is_folder_start:
            c_cnt = folder_info.get("child_count", 0) if folder_info else 0
            act_str = f"하위 {c_cnt}개 항목 포함" if c_cnt > 0 else "(비어 있음)"
            it_act = QTableWidgetItem(act_str)
            it_act.setForeground(child_disabled_color if folder_is_disabled else folder_txt)
            it_act.setBackground(folder_bg)
            if folder_is_disabled:
                it_act.setData(Qt.UserRole + 99, True)
            it_act.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            it_act.setToolTip("폴더 내 하위 항목 수")
            self.tbl_scenarios.setItem(row, 5, it_act)
        elif is_folder_end:
            it_act = QTableWidgetItem("(통과)")
            it_act.setForeground(child_disabled_color if folder_is_disabled else folder_txt)
            it_act.setBackground(folder_bg)
            if folder_is_disabled:
                it_act.setData(Qt.UserRole + 99, True)
            it_act.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.tbl_scenarios.setItem(row, 5, it_act)
        else:
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
            if is_node_disabled:
                it_act.setForeground(child_disabled_color)
                it_act.setData(Qt.UserRole + 99, True)
            elif getattr(scen, "sequence_id", None):
                it_act.setForeground(QColor("#16a34a" if self.current_theme == "light" else "#4ade80"))
            elif scen.node_type != "normal":
                it_act.setForeground(QColor("#64748b"))
            it_act.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            it_act.setToolTip("더블 클릭하여 액션시퀀스 모듈 교체")
            self.tbl_scenarios.setItem(row, 5, it_act)

        # 6. Branch Summary (On Match / On Mismatch / Loop)
        if is_folder:
            it_branch = QTableWidgetItem("-")
            it_branch.setForeground(child_disabled_color if folder_is_disabled else folder_txt)
            it_branch.setBackground(folder_bg)
            if folder_is_disabled:
                it_branch.setData(Qt.UserRole + 99, True)
            it_branch.setTextAlignment(Qt.AlignCenter)
            it_branch.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.tbl_scenarios.setItem(row, 6, it_branch)
        elif scen.node_type == "loop_start":
            it_branch = QTableWidgetItem("🔁 회차 반복 제어")
            it_branch.setForeground(child_disabled_color if is_node_disabled else QColor("#2563eb" if self.current_theme == "light" else "#60a5fa"))
            if is_node_disabled:
                it_branch.setData(Qt.UserRole + 99, True)
            it_branch.setTextAlignment(Qt.AlignCenter)
            it_branch.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.tbl_scenarios.setItem(row, 6, it_branch)
        elif scen.node_type == "loop_end":
            it_branch = QTableWidgetItem("🔁 시작점 복귀")
            it_branch.setForeground(child_disabled_color if is_node_disabled else QColor("#7c3aed" if self.current_theme == "light" else "#c084fc"))
            if is_node_disabled:
                it_branch.setData(Qt.UserRole + 99, True)
            it_branch.setTextAlignment(Qt.AlignCenter)
            it_branch.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.tbl_scenarios.setItem(row, 6, it_branch)
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
            if is_node_disabled:
                it_branch.setForeground(child_disabled_color)
                it_branch.setData(Qt.UserRole + 99, True)
            it_branch.setTextAlignment(Qt.AlignCenter)
            it_branch.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.tbl_scenarios.setItem(row, 6, it_branch)

        # Distinct cell background tint for nodes inside groups/folders
        if not is_folder and child_tint_bg:
            for col_idx in (1, 3, 4, 5, 6):
                it = self.tbl_scenarios.item(row, col_idx)
                if it:
                    it.setBackground(child_tint_bg)
            it_0 = self.tbl_scenarios.item(row, 0)
            if it_0:
                it_0.setBackground(child_tint_bg)
            if chk_widget:
                chk_widget.setStyleSheet(f"background-color: {child_tint_bg.name()};")

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
        is_checked = (state == Qt.Checked)
        self._push_scenario_undo_state(f"시나리오 s{scenario.scenario_number} 활성화 토글")
        scenario.enabled = is_checked

        is_fld_start = getattr(scenario, "is_folder_start", scenario.node_type in ("folder", "folder_start"))
        is_fld_end = getattr(scenario, "is_folder_end", scenario.node_type == "folder_end")

        if is_fld_start:
            idx = self.project.find_scenario_index(scenario.id)
            if idx is not None and idx >= 0:
                end_idx = self.project.find_matching_folder_end(idx)
                if end_idx is not None and end_idx < len(self.project.scenarios):
                    self.project.scenarios[end_idx].enabled = is_checked
            action_desc = "활성화" if is_checked else "비활성화"
            self._append_log("INFO", f"📁 [폴더 {action_desc}] '{scenario.name}' 그룹 폴더가 {action_desc}되었습니다.")
        elif is_fld_end:
            idx = self.project.find_scenario_index(scenario.id)
            if idx is not None and idx >= 0:
                start_idx = self.project.find_matching_folder_start(idx)
                if start_idx is not None and start_idx < len(self.project.scenarios):
                    self.project.scenarios[start_idx].enabled = is_checked
            action_desc = "활성화" if is_checked else "비활성화"
            self._append_log("INFO", f"📁 [폴더 {action_desc}] '{scenario.name}' 그룹 폴더가 {action_desc}되었습니다.")

        if self.inspector.current_scenario and self.inspector.current_scenario.id == scenario.id:
            self.inspector.chk_enabled.blockSignals(True)
            self.inspector.chk_enabled.setChecked(scenario.enabled)
            self.inspector.chk_enabled.blockSignals(False)

        self._refresh_scenario_table()

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
            self.splitDockWidget(self.dock_inspector, self.dock_log, Qt.Horizontal)
            if hasattr(self, "dock_actions"):
                self.splitDockWidget(self.dock_inspector, self.dock_actions, Qt.Vertical)
                self.resizeDocks([self.dock_scenarios, self.dock_inspector, self.dock_log], [420, 580, 280], Qt.Horizontal)
                self.resizeDocks([self.dock_inspector, self.dock_actions], [330, 290], Qt.Vertical)
            else:
                self.resizeDocks([self.dock_scenarios, self.dock_inspector, self.dock_log], [440, 580, 280], Qt.Horizontal)

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

        selected_rows = self.tbl_scenarios.selectionModel().selectedRows()
        if len(selected_rows) >= 2:
            act_group = menu.addAction(f"📁 선택한 {len(selected_rows)}개 시나리오를 새 폴더로 묶기")
            act_group.triggered.connect(self._on_add_folder)
            menu.addSeparator()

        curr_row = self.tbl_scenarios.rowAt(pos.y())
        if 0 <= curr_row < len(self.project.scenarios):
            scen = self.project.scenarios[curr_row]
            is_fld_start = getattr(scen, "is_folder_start", scen.node_type in ("folder", "folder_start"))
            is_fld_end = getattr(scen, "is_folder_end", scen.node_type == "folder_end")
            if is_fld_start:
                act_add_inside = menu.addAction("➕ 이 폴더 안에 새 시나리오 추가")
                act_add_inside.triggered.connect(lambda checked, r=curr_row: self._on_add_scenario(custom_insert_idx=r + 1))
                toggle_txt = "📂 폴더 펼치기" if getattr(scen, "is_collapsed", False) else "📁 폴더 접기"
                act_toggle = menu.addAction(toggle_txt)
                act_toggle.triggered.connect(lambda checked, s=scen: self._toggle_folder_collapse(s))
                en_txt = "👁️ 폴더 활성화" if not scen.enabled else "🚫 폴더 비활성화"
                act_en = menu.addAction(en_txt)
                act_en.triggered.connect(lambda checked, s=scen: self._toggle_folder_enabled(s))
                act_en_all = menu.addAction("☑️ 하위 모든 시나리오 일괄 활성화")
                act_en_all.triggered.connect(lambda checked, s=scen: self._set_folder_children_enabled(s, True))
                act_dis_all = menu.addAction("⬜ 하위 모든 시나리오 일괄 비활성화")
                act_dis_all.triggered.connect(lambda checked, s=scen: self._set_folder_children_enabled(s, False))
                menu.addSeparator()
                act_rename = menu.addAction("✏️ 폴더 이름 변경...")
                act_rename.triggered.connect(lambda checked, s=scen: self._rename_folder(s))
                act_move_up = menu.addAction("⬆️ 폴더 단위 위로 이동")
                act_move_up.triggered.connect(self._on_move_up)
                act_move_dn = menu.addAction("⬇️ 폴더 단위 아래로 이동")
                act_move_dn.triggered.connect(self._on_move_down)
                menu.addSeparator()
            elif is_fld_end:
                act_add_inside_end = menu.addAction("➕ 이 폴더 끝에 새 시나리오 추가")
                act_add_inside_end.triggered.connect(lambda checked, r=curr_row: self._on_add_scenario(custom_insert_idx=r))
                en_txt = "👁️ 폴더 활성화" if not scen.enabled else "🚫 폴더 비활성화"
                act_en = menu.addAction(en_txt)
                act_en.triggered.connect(lambda checked, s=scen: self._toggle_folder_enabled(s))
                act_en_all = menu.addAction("☑️ 하위 모든 시나리오 일괄 활성화")
                act_en_all.triggered.connect(lambda checked, s=scen: self._set_folder_children_enabled(s, True))
                act_dis_all = menu.addAction("⬜ 하위 모든 시나리오 일괄 비활성화")
                act_dis_all.triggered.connect(lambda checked, s=scen: self._set_folder_children_enabled(s, False))
                menu.addSeparator()
                act_rename = menu.addAction("✏️ 폴더 이름 변경...")
                act_rename.triggered.connect(lambda checked, s=scen: self._rename_folder(s))
                act_move_up = menu.addAction("⬆️ 폴더 단위 위로 이동")
                act_move_up.triggered.connect(self._on_move_up)
                act_move_dn = menu.addAction("⬇️ 폴더 단위 아래로 이동")
                act_move_dn.triggered.connect(self._on_move_down)
                menu.addSeparator()
            else:
                act_pick_cond = menu.addAction(f"👁️ [s{scen.scenario_number}] 인식조건 모듈 교체...")
                act_pick_cond.triggered.connect(lambda checked, s=scen: self._show_condition_module_picker(s))
                act_pick_seq = menu.addAction(f"✋ [s{scen.scenario_number}] 액션시퀀스 모듈 교체...")
                act_pick_seq.triggered.connect(lambda checked, s=scen: self._show_sequence_module_picker(s))
                menu.addSeparator()

        act_add = menu.addAction("➕ 새 시나리오 추가 (조합형)")
        act_add.triggered.connect(self._on_add_scenario)
        act_add_folder = menu.addAction("📁 새 그룹 폴더 추가")
        act_add_folder.triggered.connect(self._on_add_folder)
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

    def _toggle_folder_enabled(self, scen: Scenario):
        """Toggles enabled state for the folder start and its corresponding folder end."""
        new_state = not scen.enabled
        self._push_scenario_undo_state(f"폴더 '{scen.name}' 활성화 토글")
        scen.enabled = new_state
        idx = self.project.find_scenario_index(scen.id)
        if idx is not None and idx >= 0:
            if getattr(scen, "is_folder_start", scen.node_type in ("folder", "folder_start")):
                end_idx = self.project.find_matching_folder_end(idx)
                if end_idx is not None and end_idx < len(self.project.scenarios):
                    self.project.scenarios[end_idx].enabled = new_state
            elif getattr(scen, "is_folder_end", scen.node_type == "folder_end"):
                start_idx = self.project.find_matching_folder_start(idx)
                if start_idx is not None and start_idx < len(self.project.scenarios):
                    self.project.scenarios[start_idx].enabled = new_state
        desc = "활성화" if new_state else "비활성화"
        self._append_log("INFO", f"📁 [폴더 {desc}] '{scen.name}' 그룹 폴더가 {desc}되었습니다.")
        self._refresh_scenario_table()

    def _set_folder_children_enabled(self, scen: Scenario, enabled: bool):
        """Batch enables or disables all child scenarios inside a folder."""
        idx = self.project.find_scenario_index(scen.id)
        if idx is None or idx < 0:
            return
        if getattr(scen, "is_folder_start", scen.node_type in ("folder", "folder_start")):
            start_idx = idx
            end_idx = self.project.find_matching_folder_end(idx)
        else:
            end_idx = idx
            start_idx = self.project.find_matching_folder_start(idx)

        if start_idx is None or end_idx is None:
            return

        desc = "활성화" if enabled else "비활성화"
        self._push_scenario_undo_state(f"폴더 '{scen.name}' 하위 항목 {desc}")
        count = 0
        for i in range(start_idx + 1, end_idx):
            self.project.scenarios[i].enabled = enabled
            count += 1
        self._append_log("INFO", f"📁 [폴더 하위 {desc}] '{scen.name}' 하위 {count}개 항목이 {desc}되었습니다.")
        self._refresh_scenario_table()

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
        if getattr(scen, "is_folder_start", scen.node_type in ("folder", "folder_start")):
            self._toggle_folder_collapse(scen)
            return
        if getattr(scen, "is_folder_end", scen.node_type == "folder_end"):
            s_idx = self.project.find_matching_folder_start(row)
            if s_idx is not None:
                self.tbl_scenarios.selectRow(s_idx)
            return
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
    def _on_add_scenario(self, custom_insert_idx: Optional[int] = None):
        new_scen_num = self.project.get_next_scenario_number()
        selected_rows = sorted([r.row() for r in self.tbl_scenarios.selectionModel().selectedRows()])
        if not selected_rows and self.tbl_scenarios.selectionModel().hasSelection():
            selected_rows = sorted(list(set(idx.row() for idx in self.tbl_scenarios.selectedIndexes())))

        if custom_insert_idx is not None:
            insert_idx = custom_insert_idx
        elif selected_rows:
            target_row = selected_rows[-1]
            target_scen = self.project.scenarios[target_row] if target_row < len(self.project.scenarios) else None
            
            # If target is folder_start: insert immediately inside folder after start, and expand!
            if target_scen and getattr(target_scen, "is_folder_start", target_scen.node_type in ("folder", "folder_start")):
                insert_idx = target_row + 1
                target_scen.is_collapsed = False
            # If target is folder_end: insert immediately inside folder before end, and expand parent folder!
            elif target_scen and getattr(target_scen, "is_folder_end", target_scen.node_type == "folder_end"):
                insert_idx = target_row
                start_idx = self.project.find_matching_folder_start(target_row)
                if start_idx is not None and start_idx < len(self.project.scenarios):
                    self.project.scenarios[start_idx].is_collapsed = False
            else:
                insert_idx = target_row + 1
        else:
            insert_idx = len(self.project.scenarios)

        self._push_scenario_undo_state(f"시나리오 #{new_scen_num} 추가")
        new_scen = self.project.create_composite_scenario(
            name=f"시나리오 {new_scen_num}",
            node_type="normal",
            insert_index=insert_idx
        )
        self._refresh_scenario_table()
        if hasattr(self, "modules_widget"):
            self.modules_widget.refresh_modules()
        self.tbl_scenarios.selectRow(insert_idx)

    def _get_block_range(self, row: int) -> Tuple[int, int]:
        """
        If row is a folder or loop boundary (start or end), returns (start_idx, end_idx) of the block.
        Otherwise returns (row, row).
        """
        if not (0 <= row < len(self.project.scenarios)):
            return (row, row)
        scen = self.project.scenarios[row]
        if getattr(scen, "is_folder_start", scen.node_type in ("folder", "folder_start")):
            end_idx = self.project.find_matching_folder_end(row)
            if end_idx is not None and end_idx >= row:
                return (row, end_idx)
        elif getattr(scen, "is_folder_end", scen.node_type == "folder_end"):
            start_idx = self.project.find_matching_folder_start(row)
            if start_idx is not None and start_idx <= row:
                return (start_idx, row)
        elif scen.node_type == "loop_start":
            end_idx = self.project.find_matching_loop_end(row)
            if end_idx is not None and end_idx >= row:
                return (row, end_idx)
        elif scen.node_type == "loop_end":
            start_idx = self.project.find_matching_loop_start(row)
            if start_idx is not None and start_idx <= row:
                return (start_idx, row)
        return (row, row)

    def _on_add_folder(self):
        """Add an organizational folder block to group scenarios (Photoshop-like layer group)."""
        selected_rows = sorted([r.row() for r in self.tbl_scenarios.selectionModel().selectedRows()])
        fld_num = self.project.get_next_scenario_number()

        if len(selected_rows) >= 2:
            min_r = selected_rows[0]
            max_r = selected_rows[-1]
            self._push_scenario_undo_state(f"선택 항목을 폴더 #{fld_num}로 그룹화")

            start_scen = Scenario(
                scenario_number=fld_num,
                name=f"그룹 폴더 {fld_num}",
                node_type="folder_start",
                is_collapsed=False,
                enabled=True
            )
            end_num = self.project.get_next_scenario_number()
            end_scen = Scenario(
                scenario_number=end_num,
                name=f"그룹 폴더 {fld_num} 끝",
                node_type="folder_end",
                folder_target_id=start_scen.id,
                enabled=True
            )
            start_scen.folder_target_id = end_scen.id

            self.project.scenarios.insert(min_r, start_scen)
            self.project.scenarios.insert(max_r + 2, end_scen)
            self.project.renumber_steps()
            self._refresh_scenario_table()
            self.tbl_scenarios.selectRow(min_r)
            self.status_bar.showMessage(f"📁 선택한 {len(selected_rows)}개 시나리오를 '그룹 폴더 {fld_num}'로 묶었습니다.", 3000)
        else:
            insert_idx = len(self.project.scenarios)
            if selected_rows:
                target_row = selected_rows[0]
                target_scen = self.project.scenarios[target_row] if target_row < len(self.project.scenarios) else None
                if target_scen and getattr(target_scen, "is_folder_end", target_scen.node_type == "folder_end"):
                    insert_idx = target_row
                else:
                    insert_idx = target_row + 1

            self._push_scenario_undo_state(f"폴더 블록 #{fld_num} 짝 추가")
            start_scen = Scenario(
                scenario_number=fld_num,
                name=f"그룹 폴더 {fld_num}",
                node_type="folder_start",
                is_collapsed=False,
                enabled=True
            )
            end_num = self.project.get_next_scenario_number()
            end_scen = Scenario(
                scenario_number=end_num,
                name=f"그룹 폴더 {fld_num} 끝",
                node_type="folder_end",
                folder_target_id=start_scen.id,
                enabled=True
            )
            start_scen.folder_target_id = end_scen.id

            # 사용자 요구사항: 폴더 생성 시 짝(Start, End)만 깔끔하게 쌍으로 생성
            self.project.scenarios[insert_idx:insert_idx] = [start_scen, end_scen]
            self.project.renumber_steps()
            self._refresh_scenario_table()
            self.tbl_scenarios.selectRow(insert_idx)
            self.status_bar.showMessage(f"📁 새 그룹 폴더 's{start_scen.scenario_number}' 짝이 추가되었습니다.", 3000)

    def _toggle_folder_collapse(self, scen: Scenario):
        """Toggle collapse/expand state of a folder node."""
        if getattr(scen, "is_folder_end", scen.node_type == "folder_end"):
            idx = self.project.scenarios.index(scen) if scen in self.project.scenarios else -1
            if idx >= 0:
                s_idx = self.project.find_matching_folder_start(idx)
                if s_idx is not None:
                    scen = self.project.scenarios[s_idx]
        scen.is_collapsed = not getattr(scen, "is_collapsed", False)
        self._refresh_scenario_table()
        state_str = "접힘" if scen.is_collapsed else "펼침"
        self.status_bar.showMessage(f"📁 폴더 '{scen.name}' {state_str}", 2000)

    def _rename_folder(self, scen: Scenario):
        """Prompt to rename a folder node and synchronize start & end names."""
        base_name = scen.name
        if base_name.endswith(" 끝") or base_name.endswith(" 종료"):
            base_name = base_name.replace(" 끝", "").replace(" 종료", "")
        name, ok = QInputDialog.getText(self, "폴더 이름 변경", "폴더 이름을 입력하세요:", text=base_name)
        if ok and name.strip():
            new_name = name.strip()
            self._push_scenario_undo_state(f"폴더 '{scen.name}' 이름 변경")
            idx = self.project.scenarios.index(scen) if scen in self.project.scenarios else -1
            if idx >= 0:
                if getattr(scen, "is_folder_start", scen.node_type in ("folder", "folder_start")):
                    scen.name = new_name
                    e_idx = self.project.find_matching_folder_end(idx)
                    if e_idx is not None:
                        self.project.scenarios[e_idx].name = f"{new_name} 끝"
                elif getattr(scen, "is_folder_end", scen.node_type == "folder_end"):
                    scen.name = f"{new_name} 끝"
                    s_idx = self.project.find_matching_folder_start(idx)
                    if s_idx is not None:
                        self.project.scenarios[s_idx].name = new_name
                else:
                    scen.name = new_name
            else:
                scen.name = new_name

            self._refresh_scenario_table()
            if hasattr(self, "inspector") and self.inspector.current_scenario and self.inspector.current_scenario.id == scen.id:
                self.inspector.edit_name.setText(scen.name)

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

        selected_indices = sorted(list(set(r.row() for r in rows if 0 <= r.row() < len(self.project.scenarios))))
        if not selected_indices:
            return

        if len(selected_indices) == 1:
            row = selected_indices[0]
            scen = self.project.scenarios[row]
            is_fld_start = getattr(scen, "is_folder_start", scen.node_type in ("folder", "folder_start"))
            is_fld_end = getattr(scen, "is_folder_end", scen.node_type == "folder_end")

            if is_fld_start or is_fld_end:
                b_start, b_end = self._get_block_range(row)
                if b_end > b_start:
                    msg_box = QMessageBox(self)
                    msg_box.setWindowTitle("폴더 삭제 확인")
                    msg_box.setText(f"📁 그룹 폴더 [{self.project.scenarios[b_start].name}] 삭제 방식 선택")
                    msg_box.setInformativeText("폴더와 내부 시나리오를 모두 삭제하시겠습니까, 아니면 폴더만 해제(내용물 유지)하시겠습니까?")
                    btn_all = msg_box.addButton("전체 삭제 (하위 포함)", QMessageBox.YesRole)
                    btn_group_only = msg_box.addButton("폴더만 해제 (내용물 유지)", QMessageBox.NoRole)
                    btn_cancel = msg_box.addButton("취소", QMessageBox.RejectRole)
                    msg_box.exec_()

                    clicked = msg_box.clickedButton()
                    if clicked == btn_all:
                        self._push_scenario_undo_state(f"폴더 '{self.project.scenarios[b_start].name}' 전체 삭제")
                        del self.project.scenarios[b_start : b_end + 1]
                        self.project.renumber_steps()
                        self._refresh_scenario_table()
                        new_sel = min(b_start, len(self.project.scenarios) - 1)
                        if new_sel >= 0:
                            self.tbl_scenarios.selectRow(new_sel)
                        return
                    elif clicked == btn_group_only:
                        self._push_scenario_undo_state(f"폴더 '{self.project.scenarios[b_start].name}' 그룹 해제")
                        del self.project.scenarios[b_end]
                        del self.project.scenarios[b_start]
                        self.project.renumber_steps()
                        self._refresh_scenario_table()
                        new_sel = min(b_start, len(self.project.scenarios) - 1)
                        if new_sel >= 0:
                            self.tbl_scenarios.selectRow(new_sel)
                        return
                    else:
                        return

            res = QMessageBox.question(self, "삭제 확인", f"시나리오 고유 s{scen.scenario_number} (실행 #{scen.step_number}) [{scen.name}]를 삭제하시겠습니까?")
            if res == QMessageBox.Yes:
                self._push_scenario_undo_state(f"시나리오 s{scen.scenario_number} 삭제")
                del self.project.scenarios[row]
                self.project.renumber_steps()
                self._refresh_scenario_table()
                new_sel = min(row, len(self.project.scenarios) - 1)
                if new_sel >= 0:
                    self.tbl_scenarios.selectRow(new_sel)
        else:
            # Multi-selection deletion
            count = len(selected_indices)
            res = QMessageBox.question(
                self,
                "다중 노드 삭제 확인",
                f"선택한 {count}개의 시나리오 노드를 모두 삭제하시겠습니까?\n(폴더 또는 루프 경계 노드가 포함되어 있을 수 있습니다.)",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if res == QMessageBox.Yes:
                self._push_scenario_undo_state(f"시나리오 {count}개 일괄 삭제")
                for r in reversed(selected_indices):
                    if 0 <= r < len(self.project.scenarios):
                        del self.project.scenarios[r]
                self.project.renumber_steps()
                self._refresh_scenario_table()
                first_r = selected_indices[0]
                new_sel = min(first_r, len(self.project.scenarios) - 1)
                if new_sel >= 0:
                    self.tbl_scenarios.selectRow(new_sel)

    def _on_move_up(self):
        rows = self.tbl_scenarios.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        b_start, b_end = self._get_block_range(row)
        if b_start <= 0:
            self.status_bar.showMessage("이미 최상단에 위치해 있어 위로 이동할 수 없습니다.", 2000)
            return

        prev_row = b_start - 1
        prev_b_start, prev_b_end = self._get_block_range(prev_row)
        target = prev_b_start

        self._push_scenario_undo_state(f"시나리오 s{self.project.scenarios[b_start].scenario_number} 위로 이동")
        block = self.project.scenarios[b_start : b_end + 1]
        del self.project.scenarios[b_start : b_end + 1]
        self.project.scenarios[target:target] = block
        self.project.renumber_steps()
        self._refresh_scenario_table()
        self.tbl_scenarios.selectRow(target)
        unit_str = "📁 폴더" if getattr(block[0], "is_folder", False) else "시나리오"
        self.status_bar.showMessage(f"{unit_str} '{block[0].name}' 위로 이동 완료", 2000)

    def _on_move_down(self):
        rows = self.tbl_scenarios.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        b_start, b_end = self._get_block_range(row)
        if b_end >= len(self.project.scenarios) - 1:
            self.status_bar.showMessage("이미 최하단에 위치해 있어 아래로 이동할 수 없습니다.", 2000)
            return

        next_row = b_end + 1
        next_b_start, next_b_end = self._get_block_range(next_row)
        target = next_b_end + 1

        self._push_scenario_undo_state(f"시나리오 s{self.project.scenarios[b_start].scenario_number} 아래로 이동")
        block = self.project.scenarios[b_start : b_end + 1]
        block_len = len(block)
        del self.project.scenarios[b_start : b_end + 1]
        target_after_del = target - block_len
        self.project.scenarios[target_after_del:target_after_del] = block
        self.project.renumber_steps()
        self._refresh_scenario_table()
        self.tbl_scenarios.selectRow(target_after_del)
        unit_str = "📁 폴더" if getattr(block[0], "is_folder", False) else "시나리오"
        self.status_bar.showMessage(f"{unit_str} '{block[0].name}' 아래로 이동 완료", 2000)

    def _on_scenario_row_reordered(self, from_row: int, to_row: int):
        """Reorders scenarios in the project via drag-and-drop, including inserting into empty folders."""
        if not self.project or not self.project.scenarios or from_row == to_row:
            return
        scens = self.project.scenarios
        if not (0 <= from_row < len(scens) and 0 <= to_row < len(scens)):
            return
        b_start, b_end = self._get_block_range(from_row)
        if b_start <= to_row <= b_end:
            return

        target_scen = scens[to_row]
        is_target_fld_start = getattr(target_scen, "is_folder_start", target_scen.node_type in ("folder", "folder_start"))
        is_target_fld_end = getattr(target_scen, "is_folder_end", target_scen.node_type == "folder_end")

        self._push_scenario_undo_state(f"시나리오 s{scens[b_start].scenario_number} 드래그 이동")
        block = scens[b_start : b_end + 1]
        block_len = len(block)
        del scens[b_start : b_end + 1]

        try:
            curr_target_idx = scens.index(target_scen)
        except ValueError:
            curr_target_idx = to_row if to_row <= len(scens) else len(scens)

        if is_target_fld_start:
            # Folder Start에 드롭 시: 폴더 내부(Folder Start 바로 뒤)로 삽입 & 폴더 자동 펼침
            target_idx = curr_target_idx + 1
            target_scen.is_collapsed = False
        elif is_target_fld_end:
            # Folder End에 드롭 시: 폴더 내부(Folder End 바로 앞)로 삽입 & 상위 폴더 자동 펼침
            target_idx = curr_target_idx
            parent_start_idx = self.project.find_matching_folder_start(curr_target_idx)
            if parent_start_idx is not None and parent_start_idx < len(scens):
                scens[parent_start_idx].is_collapsed = False
        else:
            if to_row > b_start:
                target_idx = max(0, to_row - block_len + 1)
            else:
                target_idx = to_row

        scens[target_idx:target_idx] = block
        self.project.renumber_steps()
        self._refresh_scenario_table()
        self.tbl_scenarios.selectRow(target_idx)

    # ==========================================
    # Target Window Management
    # ==========================================
    def _auto_track_target_window(self) -> bool:
        """
        마지막 기록(프로젝트 설정 또는 앱 config)의 타겟 창 제목을 참고하여,
        현재 실행 중인 윈도우 중 일치하는 창을 자동으로 검색하고 타겟으로 등록합니다.
        """
        last_title = getattr(self.project, "target_window_title", "") or getattr(self, "_last_config_target_title", "")
        if not last_title or last_title == "가상 캔버스 타겟":
            return False

        win = WindowManager.find_window_by_title(last_title)
        if win and win.hwnd:
            if self.target_hwnd == win.hwnd:
                return True
            self.target_hwnd = win.hwnd
            self.project.target_window_title = win.title
            self.project.target_client_width = win.client_width
            self.project.target_client_height = win.client_height
            self._save_app_config()
            if hasattr(self, "inspector") and self.inspector:
                self.inspector.set_target_hwnd(self.target_hwnd)
            if hasattr(self, "modules_widget") and self.modules_widget:
                self.modules_widget.target_hwnd = self.target_hwnd
            if hasattr(self, "action_overlay") and self.action_overlay:
                self.action_overlay.set_target_hwnd(self.target_hwnd)
            if hasattr(self, "popup_play_bar") and self.popup_play_bar:
                self.popup_play_bar.set_target_hwnd(self.target_hwnd)
            self._update_target_label(win)
            self._append_log("INFO", f"🎯 [타겟창 자동 추적] 마지막 기록('{last_title}')의 타겟 창 '{win.title}'(HWND: 0x{win.hwnd:X})을 자동으로 감지하여 등록했습니다.")
            return True
        return False

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
            if hasattr(self, "popup_play_bar") and self.popup_play_bar:
                self.popup_play_bar.set_target_hwnd(self.target_hwnd)
            self._update_target_label(dlg.selected_window)
            self._append_log("INFO", f"타겟 지정 완료: '{dlg.selected_window.title}' ({dlg.selected_window.client_width}×{dlg.selected_window.client_height})")

    def _on_focus_target_window(self):
        if self.target_hwnd:
            WindowManager.bring_to_foreground(self.target_hwnd)
        elif self.virtual_canvas_window and self.virtual_canvas_window.isVisible():
            self.virtual_canvas_window.raise_()
            self.virtual_canvas_window.activateWindow()
        else:
            QMessageBox.information(
                self, "창 활성화 안내",
                "현재 실행 중인 특정 윈도우 창이 선택되지 않았습니다.\n(직접 지정 해상도 모드에서는 활성화할 윈도우가 없습니다.)"
            )

    def _on_open_virtual_canvas(self):
        """Opens or focuses the virtual canvas window and sets it as the active target."""
        w = getattr(self.project, "target_client_width", 1600)
        h = getattr(self.project, "target_client_height", 900)
        if not self.virtual_canvas_window:
            self.virtual_canvas_window = VirtualCanvasWindow(w, h)
            self.virtual_canvas_window.sig_closed.connect(self._on_virtual_canvas_closed)
        else:
            self.virtual_canvas_window.set_target_resolution(w, h)

        self.virtual_canvas_window.show()
        self.virtual_canvas_window.raise_()
        self.virtual_canvas_window.activateWindow()

        self.target_hwnd = int(self.virtual_canvas_window.winId())
        self.inspector.set_target_hwnd(self.target_hwnd)
        if hasattr(self, "modules_widget") and self.modules_widget:
            self.modules_widget.target_hwnd = self.target_hwnd
        if hasattr(self, "action_overlay") and self.action_overlay:
            self.action_overlay.set_target_hwnd(self.target_hwnd)
        if hasattr(self, "popup_play_bar") and self.popup_play_bar:
            self.popup_play_bar.set_target_hwnd(self.target_hwnd)

        win_info = WindowManager.get_window_info(self.target_hwnd)
        self._update_target_label(win_info)
        self._append_log("INFO", f"🎨 [가상 타겟] 가상 캔버스 창을 열고 타깃으로 연결했습니다. ({w}×{h})")
        self.status_bar.showMessage(f"가상 캔버스 타깃 연결: {w}×{h}", 3000)

    def _on_virtual_canvas_closed(self):
        """Handler invoked when the virtual canvas target window is closed."""
        if self.virtual_canvas_window and self.target_hwnd == int(self.virtual_canvas_window.winId()):
            self.target_hwnd = 0
            if hasattr(self, "popup_play_bar") and self.popup_play_bar:
                self.popup_play_bar.set_target_hwnd(0)
            self._update_target_label(None)
            self._append_log("INFO", "🎨 [가상 타겟] 가상 캔버스 창이 닫혀 타깃 연결이 해제되었습니다.")

    def _update_target_label(self, win: Optional[WindowInfo]):
        pal = get_theme_colors(self.current_theme)
        if win:
            if win.hwnd:
                new_text = f"'{win.title}' (HWND: 0x{win.hwnd:X}, 해상도: {win.client_width}×{win.client_height})"
            else:
                new_text = f"📐 직접 지정 해상도: {win.client_width}×{win.client_height} ('{win.title}')"
            new_style = f"font-weight: bold; color: {pal['info']};"
        else:
            w = getattr(self.project, "target_client_width", 0)
            h = getattr(self.project, "target_client_height", 0)
            title = getattr(self.project, "target_window_title", "")
            if w > 0 and h > 0:
                new_text = f"📐 기억된 해상도: {w}×{h} ('{title or '가상 타겟'}')"
                new_style = f"font-weight: bold; color: {pal['info']};"
            else:
                new_text = "선택된 창 없음 (창 선택 버튼을 클릭하세요)"
                new_style = f"font-weight: bold; color: {pal['warning']};"

        if getattr(self, "_last_target_label_text", None) != new_text:
            self._last_target_label_text = new_text
            self.lbl_target_info.setText(new_text)
        if getattr(self, "_last_target_label_style", None) != new_style:
            self._last_target_label_style = new_style
            self.lbl_target_info.setStyleSheet(new_style)

    def _update_authoring_resolution_display(self):
        """Update the authoring resolution badge text, tooltip, and theme styling."""
        if not hasattr(self, "lbl_authoring_res") or not self.lbl_authoring_res:
            return

        auth_w = getattr(self.project, "authoring_width", getattr(self.project, "target_client_width", 1600))
        auth_h = getattr(self.project, "authoring_height", getattr(self.project, "target_client_height", 900))
        ref_path = getattr(self.project, "reference_image_path", None)

        is_dark = getattr(self, "current_theme", "light") == "dark"
        bg_col = "rgba(59, 130, 246, 0.22)" if is_dark else "rgba(37, 99, 235, 0.10)"
        txt_col = "#60a5fa" if is_dark else "#1d4ed8"
        border_col = "rgba(96, 165, 250, 0.4)" if is_dark else "rgba(37, 99, 235, 0.3)"

        style = (
            f"font-weight: bold; font-size: 9pt; padding: 2px 8px; border-radius: 4px; "
            f"background-color: {bg_col}; color: {txt_col}; border: 1px solid {border_col};"
        )
        self.lbl_authoring_res.setStyleSheet(style)

        base_txt = f"📐 제작 해상도: {auth_w} × {auth_h}"
        if ref_path:
            fname = os.path.basename(ref_path)
            self.lbl_authoring_res.setText(f"{base_txt} ({fname})")
            self.lbl_authoring_res.setToolTip(
                f"시나리오 제작 기준 해상도: {auth_w} × {auth_h}\n"
                f"기준 레퍼런스 이미지: {ref_path}\n"
                f"(우클릭: 기준 이미지 변경/해제 또는 해상도 직접 입력)"
            )
        else:
            self.lbl_authoring_res.setText(base_txt)
            self.lbl_authoring_res.setToolTip(
                f"시나리오 제작 기준 해상도: {auth_w} × {auth_h}\n"
                f"(등록된 기준 이미지가 없습니다. [🖼️ 기준 이미지 등록...] 버튼으로 등록할 수 있습니다.)\n"
                f"(우클릭: 해상도 직접 수동 입력)"
            )

    def _apply_authoring_image(self, file_path: str):
        if not file_path or not os.path.exists(file_path):
            return

        pix = QPixmap(file_path)
        img_w, img_h = 0, 0
        if not pix.isNull():
            img_w, img_h = pix.width(), pix.height()
        else:
            try:
                from PIL import Image
                with Image.open(file_path) as img:
                    img_w, img_h = img.size
            except Exception as e:
                QMessageBox.warning(self, "이미지 오류", f"이미지 파일을 읽을 수 없습니다:\n{e}")
                return

        if img_w <= 0 or img_h <= 0:
            QMessageBox.warning(self, "해상도 오류", "유효한 해상도를 가진 이미지가 아닙니다.")
            return

        self.project.authoring_width = img_w
        self.project.authoring_height = img_h
        self.project.reference_image_path = to_relative_path(file_path)

        # If no active window is attached, also sync target client size
        if not self.target_hwnd:
            self.project.target_client_width = img_w
            self.project.target_client_height = img_h

        self._update_authoring_resolution_display()
        self._append_log("INFO", f"📐 제작 기준 해상도가 {img_w}×{img_h}로 설정되었습니다. (기준 이미지: {os.path.basename(file_path)})")
        if hasattr(self, "status_bar"):
            self.status_bar.showMessage(f"제작 기준 해상도 설정됨: {img_w}×{img_h} ({os.path.basename(file_path)})", 4000)

    def _on_register_authoring_image(self):
        """Register a reference screenshot via file dialog."""
        start_dir = ""
        cur_ref = getattr(self.project, "reference_image_path", None)
        if cur_ref:
            abs_p = to_absolute_path(cur_ref)
            if abs_p and os.path.exists(abs_p):
                start_dir = os.path.dirname(abs_p)

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "제작 해상도 추적용 레퍼런스 이미지 선택",
            start_dir,
            "이미지 파일 (*.png *.jpg *.jpeg *.bmp *.webp);;모든 파일 (*.*)"
        )
        if file_path:
            self._apply_authoring_image(file_path)

    def _on_select_authoring_image_from_gallery(self):
        """Select authoring reference image from Reference Gallery dialog."""
        from ui.reference_gallery_dialog import ReferenceGalleryDialog
        dlg = ReferenceGalleryDialog(project=self.project, target_hwnd=self.target_hwnd, picker_mode=True, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            sel_path = dlg.get_selected_image_path()
            if sel_path:
                self._apply_authoring_image(sel_path)

    def _create_authoring_menu(self) -> QMenu:
        """Create popup menu for authoring reference image options."""
        menu = QMenu(self)
        act_gallery = menu.addAction("🖼️ 레퍼런스 갤러리에서 선택...")
        act_gallery.triggered.connect(self._on_select_authoring_image_from_gallery)
        act_file = menu.addAction("📂 파일 탐색기에서 선택...")
        act_file.triggered.connect(self._on_register_authoring_image)
        menu.addSeparator()
        act_manual = menu.addAction("📐 해상도 수동 직접 입력...")
        act_manual.triggered.connect(self._on_manual_authoring_resolution)
        if getattr(self.project, "reference_image_path", None):
            menu.addSeparator()
            act_clear = menu.addAction("❌ 기준 이미지 등록 해제")
            act_clear.triggered.connect(self._on_clear_authoring_image)
        return menu

    def _on_show_authoring_menu(self):
        """Show dropdown menu on clicking the register reference image button."""
        menu = self._create_authoring_menu()
        if hasattr(self, "btn_register_ref_img"):
            menu.exec_(self.btn_register_ref_img.mapToGlobal(QPoint(0, self.btn_register_ref_img.height())))
        else:
            menu.exec_(QCursor.pos())

    def _on_authoring_res_context_menu(self, pos):
        """Context menu for authoring resolution display and button."""
        menu = self._create_authoring_menu()
        menu.exec_(QCursor.pos())

    def _on_manual_authoring_resolution(self):
        """Prompt user for manual entry of authoring resolution."""
        cur_w = getattr(self.project, "authoring_width", getattr(self.project, "target_client_width", 1600))
        cur_h = getattr(self.project, "authoring_height", getattr(self.project, "target_client_height", 900))
        text, ok = QInputDialog.getText(
            self,
            "제작 기준 해상도 수동 입력",
            "시나리오 제작 기준 해상도를 '가로x세로' 형식으로 입력하세요 (예: 1600x900):",
            text=f"{cur_w}x{cur_h}"
        )
        if ok and text:
            clean = text.lower().replace(" ", "").replace("*", "x")
            if "x" in clean:
                parts = clean.split("x")
                try:
                    w = int(parts[0])
                    h = int(parts[1])
                    if w > 0 and h > 0:
                        self.project.authoring_width = w
                        self.project.authoring_height = h
                        if not self.target_hwnd:
                            self.project.target_client_width = w
                            self.project.target_client_height = h
                        self._update_authoring_resolution_display()
                        self._append_log("INFO", f"📐 제작 기준 해상도가 수동으로 {w}×{h}로 변경되었습니다.")
                        return
                except ValueError:
                    pass
            QMessageBox.warning(self, "입력 오류", "유효한 해상도 형식이 아닙니다. (예: 1600x900 또는 1920x1080)")

    def _on_clear_authoring_image(self):
        """Clear registered reference image from project."""
        self.project.reference_image_path = None
        self._update_authoring_resolution_display()
        self._append_log("INFO", "제작 기준 레퍼런스 이미지 등록이 해제되었습니다.")

    def _start_target_monitor_timer(self):
        self.timer_monitor = QTimer(self)
        self.timer_monitor.setInterval(1500)
        self.timer_monitor.timeout.connect(self._check_target_alive)
        self.timer_monitor.start()

    def _check_target_alive(self):
        if self.target_hwnd:
            win_info = WindowManager.get_window_info(self.target_hwnd)
            if not win_info:
                if not self._auto_track_target_window():
                    self.target_hwnd = 0
                    pal = get_theme_colors(self.current_theme)
                    warn_text = "⚠️ 타겟 창이 닫혔거나 감지되지 않습니다!"
                    warn_style = f"font-weight: bold; color: {pal['danger']};"
                    if getattr(self, "_last_target_label_text", None) != warn_text:
                        self._last_target_label_text = warn_text
                        self.lbl_target_info.setText(warn_text)
                    if getattr(self, "_last_target_label_style", None) != warn_style:
                        self._last_target_label_style = warn_style
                        self.lbl_target_info.setStyleSheet(warn_style)
            else:
                self._update_target_label(win_info)
        else:
            self._auto_track_target_window()

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

    def _set_paused_state(self, scenario_id: Optional[str]):
        """Records paused scenario ID and visually marks it in header and scenario list."""
        self._paused_scenario_id = scenario_id
        self._refresh_scenario_table()

    def _clear_paused_state(self):
        """Clears paused scenario ID and removes paused visual markers."""
        self._paused_scenario_id = None
        self._refresh_scenario_table()

    def _on_start_execution(self, start_scenario_id: Optional[str] = None):
        if not self.target_hwnd or not WindowManager.get_window_info(self.target_hwnd):
            # Target window not selected or closed: Auto-launch virtual canvas window
            self._on_open_virtual_canvas()
            self._append_log("INFO", "🚀 타깃 앱이 설정되어 있지 않아 가상 캔버스를 띄우고 실행을 시작합니다.")

        if self.runner and self.runner.isRunning():
            if self.runner._is_paused:
                target_id = start_scenario_id or getattr(self, "_paused_scenario_id", None)
                if target_id:
                    self.runner.set_next_scenario_id(target_id)
                self.runner.resume()
                self._clear_paused_state()
                self.lbl_run_status.setText("실행 중...")
                self.btn_pause.setText("⏸ 일시정지 (Shift+F6)")
                if hasattr(self, "popup_play_bar") and self.popup_play_bar:
                    self.popup_play_bar.set_runner_state("running", "재개되어 실행 중...")
                return
            else:
                self.runner.stop()
                self.runner.wait(100)

        # If starting execution with a paused scenario remembered and no specific start_scenario_id
        if start_scenario_id is None and getattr(self, "_paused_scenario_id", None):
            start_scenario_id = self._paused_scenario_id
        self._clear_paused_state()

        self.runner = WorkflowRunner(
            self.project,
            self.target_hwnd,
            start_scenario_id=start_scenario_id,
            anti_burn_overlay=self.anti_burn_overlay,
            parent=self
        )
        self.runner.sig_log.connect(self._append_log)
        self.runner.sig_scenario_started.connect(self._on_scenario_started)
        self.runner.sig_scenario_completed.connect(self._on_scenario_completed)
        self.runner.sig_action_executing.connect(self._on_action_executing_visual)
        self.runner.sig_action_finished.connect(self._on_action_finished_visual)
        self.runner.sig_action_sequence_started.connect(self._on_action_sequence_started_visual)
        self.runner.sig_action_sequence_finished.connect(self._on_action_sequence_finished_visual)
        self.runner.sig_loop_progress.connect(self._on_loop_progress)
        self.runner.sig_loop_completed.connect(self._on_loop_completed)
        self.runner.sig_step_completed.connect(self._on_step_completed)
        self.runner.sig_finished.connect(self._on_runner_finished)

        self._current_run_loop = 0
        self._last_loop_duration = 0.0
        if hasattr(self, "lbl_loop_progress"):
            self.lbl_loop_progress.setText("(준비 중...)")
            self.lbl_loop_progress.setStyleSheet("font-weight: bold; color: #16a34a; font-size: 8.5pt;")

        self.btn_run.setEnabled(False)
        if hasattr(self, "btn_run_selected"):
            self.btn_run_selected.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_stop.setEnabled(True)
        self.lbl_run_status.setText("실행 중 (F5/F6)")
        self.lbl_run_status.setStyleSheet("color: #16a34a; font-weight: bold;")
        if hasattr(self, "popup_play_bar") and self.popup_play_bar:
            self.popup_play_bar.set_runner_state("running", "시나리오 실행 중...")

        if hasattr(self, "chk_floating_stop") and self.chk_floating_stop.isChecked():
            if hasattr(self, "floating_stop") and self.floating_stop:
                self.floating_stop.show()
                self.floating_stop.raise_()

        self.runner.start()

    def _on_pause_execution(self):
        if self.runner and self.runner.isRunning():
            if self.runner._is_paused:
                # Resuming execution from paused node
                if getattr(self, "_paused_scenario_id", None):
                    self.runner.set_next_scenario_id(self._paused_scenario_id)
                self.runner.resume()
                self._clear_paused_state()
                self.btn_pause.setText("⏸ 일시정지 (Shift+F6)")
                self.lbl_run_status.setText("실행 중...")
                self.lbl_run_status.setStyleSheet("color: #16a34a; font-weight: bold;")
                if hasattr(self, "popup_play_bar") and self.popup_play_bar:
                    self.popup_play_bar.set_runner_state("running", "재개되어 실행 중...")
                if hasattr(self, "floating_stop") and self.floating_stop:
                    self.floating_stop.set_paused_state(False)
            else:
                # Pausing execution and recording paused node
                self.runner.pause()
                paused_id = getattr(self.runner, "current_scenario_id", None) or getattr(self, "_last_running_scenario_id", None)
                self._set_paused_state(paused_id)
                self.btn_pause.setText("▶ 재개 (Shift+F6)")
                self.lbl_run_status.setText("일시정지됨")
                self.lbl_run_status.setStyleSheet("color: #ea580c; font-weight: bold;")
                if hasattr(self, "popup_play_bar") and self.popup_play_bar:
                    self.popup_play_bar.set_runner_state("paused", "일시정지됨")
                if hasattr(self, "floating_stop") and self.floating_stop:
                    self.floating_stop.set_paused_state(True)

    def _on_stop_execution(self):
        if self.runner:
            self.runner.stop()
            self.runner.wait(50)
        self._clear_paused_state()
        self._last_running_scenario_id = None
        self.btn_run.setEnabled(True)
        if hasattr(self, "btn_run_selected"):
            self.btn_run_selected.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.btn_pause.setText("⏸ 일시정지 (Shift+F6)")
        self.lbl_run_status.setText("정지됨")
        self.lbl_run_status.setStyleSheet("color: #dc2626; font-weight: bold;")
        self._highlight_running_row_header(None)
        if hasattr(self, "floating_stop") and self.floating_stop:
            self.floating_stop.hide()
        if hasattr(self, "popup_play_bar") and self.popup_play_bar:
            self.popup_play_bar.set_runner_state("stopped", "정지됨")
        if hasattr(self, "action_overlay") and self.action_overlay:
            self.action_overlay.clear_action()
        if hasattr(self, "lbl_loop_progress"):
            dur_str = f" | 최근 루프: {WorkflowRunner._format_duration(self._last_loop_duration)}" if self._last_loop_duration > 0 else ""
            if self._current_run_loop > 0:
                self.lbl_loop_progress.setText(f"({self._current_run_loop}회차 정지{dur_str})")
                self.lbl_loop_progress.setStyleSheet("font-weight: bold; color: #dc2626; font-size: 8.5pt;")
            else:
                self.lbl_loop_progress.setText("(대기)")
                self.lbl_loop_progress.setStyleSheet("font-weight: bold; color: #64748b; font-size: 8.5pt;")
        self.status_bar.showMessage("시나리오 실행이 즉시 정지되었습니다.", 3000)

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
        """단일 스텝 실행 완료 시 다음 노드로 포인터(헤더 번호) 이동 및 하이라이트 갱신"""
        if 0 <= next_index < len(self.project.scenarios):
            self.tbl_scenarios.blockSignals(True)
            self.tbl_scenarios.setCurrentCell(next_index, 0)
            self.tbl_scenarios.clearSelection()
            self.tbl_scenarios.blockSignals(False)
            it = self.tbl_scenarios.item(next_index, 0)
            if it:
                self.tbl_scenarios.scrollToItem(it)
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

    def _on_action_sequence_started_visual(self, actions: list, scenario_name: str):
        """전체 액션 시퀀스의 모든 포인트들을 오버레이 화면상에 동시 시각화"""
        if hasattr(self, "action_overlay") and self.action_overlay and hasattr(self, "chk_action_overlay") and self.chk_action_overlay.isChecked():
            self.action_overlay.set_target_hwnd(self.target_hwnd)
            self.action_overlay.show_sequence(actions, 1, scenario_name)

    def _on_action_sequence_finished_visual(self):
        """액션 시퀀스 완료 시 오버레이 화면 서서히 정리"""
        if hasattr(self, "action_overlay") and self.action_overlay:
            self.action_overlay.hide_action_delayed(500)

    def _on_action_executing_visual(self, action, index, total):
        # 1. Action overlay for click/drag coordinates on target screen (completely click-through)
        if hasattr(self, "action_overlay") and self.action_overlay and hasattr(self, "chk_action_overlay") and self.chk_action_overlay.isChecked():
            self.action_overlay.set_target_hwnd(self.target_hwnd)
            self.action_overlay.set_current_action_index(index, action)

        # 2. Real-time sequence action progress output on play bar
        if hasattr(self, "popup_play_bar") and self.popup_play_bar:
            self.popup_play_bar.set_action_status(action, index, total)

        # 3. Virtual canvas target visual click effect
        if hasattr(self, "virtual_canvas_window") and self.virtual_canvas_window and self.virtual_canvas_window.isVisible():
            if hasattr(action, "action_type") and action.action_type in ("mouse_click", "mouse_drag"):
                cx = getattr(action, "x", getattr(action, "start_x", 0))
                cy = getattr(action, "y", getattr(action, "start_y", 0))
                self.virtual_canvas_window.trigger_click_effect(cx, cy)

    def _on_action_finished_visual(self, action):
        pass

    def _on_toggle_action_overlay(self, checked: bool):
        if hasattr(self, "action_overlay") and self.action_overlay:
            self.action_overlay.is_overlay_enabled = checked
            if not checked:
                self.action_overlay.clear_action()
        self._save_app_config()

    def _on_toggle_floating_stop(self, checked: bool):
        if hasattr(self, "floating_stop") and self.floating_stop:
            if self.runner and self.runner.isRunning() and checked:
                self.floating_stop.show()
                self.floating_stop.raise_()
            elif not checked:
                self.floating_stop.hide()
        self._save_app_config()

    def _on_scenario_started(self, scenario_id: str):
        self._last_running_scenario_id = scenario_id
        for row, s in enumerate(self.project.scenarios):
            if s.id == scenario_id:
                # 행 선택(드래그 모양)을 유발하지 않고 스크롤 이동 및 헤더 녹색 하이라이트만 적용
                self.tbl_scenarios.blockSignals(True)
                self.tbl_scenarios.setCurrentCell(row, 0)
                self.tbl_scenarios.clearSelection()
                self.tbl_scenarios.blockSignals(False)
                it = self.tbl_scenarios.item(row, 0)
                if it:
                    self.tbl_scenarios.scrollToItem(it)
                self._highlight_running_row_header(row)
                if hasattr(self, "popup_play_bar") and self.popup_play_bar:
                    self.popup_play_bar.set_runner_state("running", f"s{s.scenario_number} [{s.name}] 실행 중...")
                if hasattr(self, "floating_stop") and self.floating_stop:
                    self.floating_stop.set_status(f"s{s.scenario_number} [{s.name}]")
                break

    def _on_scenario_completed(self, scenario_id: str, result: str):
        pass

    def _on_runner_finished(self, reason: str):
        self._clear_paused_state()
        self._last_running_scenario_id = None
        self.btn_run.setEnabled(True)
        if hasattr(self, "btn_run_selected"):
            self.btn_run_selected.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.btn_pause.setText("⏸ 일시정지 (Shift+F6)")
        self.lbl_run_status.setText(f"완료 ({reason})")
        self.lbl_run_status.setStyleSheet("font-weight: bold;")
        self._highlight_running_row_header(None)
        if hasattr(self, "floating_stop") and self.floating_stop:
            self.floating_stop.hide()
        if hasattr(self, "popup_play_bar") and self.popup_play_bar:
            self.popup_play_bar.set_runner_state("stopped", f"완료 ({reason})")
        if hasattr(self, "action_overlay") and self.action_overlay:
            self.action_overlay.clear_action()
        if hasattr(self, "lbl_loop_progress"):
            dur_str = f" | 최근 루프: {WorkflowRunner._format_duration(self._last_loop_duration)}" if self._last_loop_duration > 0 else ""
            if self._current_run_loop > 0:
                self.lbl_loop_progress.setText(f"(총 {self._current_run_loop}회 완료{dur_str})")
                self.lbl_loop_progress.setStyleSheet("font-weight: bold; color: #2563eb; font-size: 8.5pt;")
            else:
                self.lbl_loop_progress.setText("(대기)")
                self.lbl_loop_progress.setStyleSheet("font-weight: bold; color: #64748b; font-size: 8.5pt;")

    def _on_loop_completed(self, completed_loop: int, total_loops: int, duration: float):
        self._last_loop_duration = duration
        dur_str = WorkflowRunner._format_duration(duration)
        if hasattr(self, "lbl_loop_progress"):
            if total_loops > 0:
                self.lbl_loop_progress.setText(f"({completed_loop} / {total_loops}회 완료 | 소요: {dur_str})")
            else:
                self.lbl_loop_progress.setText(f"({completed_loop}회 완료 | 소요: {dur_str})")
            self.lbl_loop_progress.setStyleSheet("font-weight: bold; color: #16a34a; font-size: 8.5pt;")

    def _on_loop_progress(self, current_loop: int, total_loops: int):
        self._current_run_loop = current_loop
        dur_str = f" | 이전 루프: {WorkflowRunner._format_duration(self._last_loop_duration)}" if self._last_loop_duration > 0 else ""
        if hasattr(self, "lbl_loop_progress"):
            if total_loops > 0:
                self.lbl_loop_progress.setText(f"({current_loop} / {total_loops}회 진행 중{dur_str})")
            else:
                self.lbl_loop_progress.setText(f"({current_loop}회 진행 중{dur_str})")
            self.lbl_loop_progress.setStyleSheet("font-weight: bold; color: #16a34a; font-size: 8.5pt;")

    # ==========================================
    # Popup Play Bar Controls & Signal Handlers
    # ==========================================
    def _on_playbar_closed(self):
        if hasattr(self, "btn_popup_playbar") and self.btn_popup_playbar:
            self.btn_popup_playbar.setChecked(False)

    def _toggle_popup_playbar(self):
        if not hasattr(self, "popup_play_bar") or not self.popup_play_bar:
            return
        if self.popup_play_bar.isVisible():
            self.popup_play_bar.hide()
            if hasattr(self, "btn_popup_playbar"):
                self.btn_popup_playbar.setChecked(False)
        else:
            self.popup_play_bar.refresh_scenarios(self.project.scenarios)
            self.popup_play_bar.position_relative_to_target(self.target_hwnd, self.geometry())
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
        self._next_log_id = 0

    def _append_log(self, level: str, msg: str):
        if not hasattr(self, "_log_records"):
            self._log_records = []
        if not hasattr(self, "_next_log_id"):
            self._next_log_id = 0

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

        log_id = self._next_log_id
        self._next_log_id += 1

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

        # Cap in-memory log records to prevent memory leak on long-running macro sessions
        MAX_LOG_RECORDS = 1000
        if len(self._log_records) > MAX_LOG_RECORDS:
            del self._log_records[:len(self._log_records) - MAX_LOG_RECORDS]

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

        elif "루프 시작" in record['raw_msg']:
            badge = "<span style='background: #2563eb; color: #ffffff; padding: 2px 7px; border-radius: 4px; font-weight: bold; font-size: 8.5pt;'>🔄 루프 시작</span>"
            border_c = "#3b82f6"
            bg_c = "rgba(59, 130, 246, 0.12)" if not pal["is_light"] else "#eff6ff"
            return f"<div style='margin: 3px 0; padding: 3px 6px; background-color: {bg_c}; border-left: 3px solid {border_c}; border-radius: 4px;'>{tag_prefix} {badge} <span style='color: {color}; font-weight: bold;'>{html.escape(record['raw_msg'])}</span></div>"

        elif "루프 탈출" in record['raw_msg'] or "루프 종료" in record['raw_msg']:
            badge = "<span style='background: #d97706; color: #ffffff; padding: 2px 7px; border-radius: 4px; font-weight: bold; font-size: 8.5pt;'>⚡ 루프 탈출</span>"
            border_c = "#f59e0b"
            bg_c = "rgba(245, 158, 11, 0.12)" if not pal["is_light"] else "#fffbeb"
            return f"<div style='margin: 3px 0; padding: 3px 6px; background-color: {bg_c}; border-left: 3px solid {border_c}; border-radius: 4px;'>{tag_prefix} {badge} <span style='color: {color}; font-weight: bold;'>{html.escape(record['raw_msg'])}</span></div>"

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
                if hasattr(self, "_log_records"):
                    target_rec = next((r for r in self._log_records if r.get("id") == log_id), None)
                    if target_rec:
                        target_rec["expanded"] = not target_rec.get("expanded", False)
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
