"""Layout, Theme & Code Watcher Management Mixin for MainWindow.

Handles:
- Python code watcher and live auto-reload debounce
- Light/Dark theme toggling and global stylesheet updates
- Unity-style dock panel layout presets (Default 3-column, Tall, Tabbed, etc.) and custom layout saving
- Scenario preset persistence and manager dialog coordination
"""

import os
import sys
import json
from typing import Optional, List, Dict, Any

from PyQt5.QtCore import Qt, QTimer, QFileSystemWatcher, QProcess, QByteArray
from PyQt5.QtWidgets import QApplication, QMessageBox, QInputDialog, QDialog

from core.window_manager import WindowManager
from core.preset_manager import PresetManager
from ui.theme import get_stylesheet
from ui.preset_dialog import SavePresetDialog, PresetManagerDialog

TEMP_RELOAD_FILE = "_temp_reload_project.json"


class MainWindowLayoutThemeMixin:
    """Mixin managing dock layouts, theme modes, preset loading, and live code reloading."""

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
