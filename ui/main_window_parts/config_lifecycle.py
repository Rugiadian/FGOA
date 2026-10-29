"""
Config & Lifecycle Management Mixin for MainWindow.
Handles window geometry persistence, app settings load/save (fgoa_config.json),
global hotkeys (F6/Shift+F6/F12), anti-burn lifecycle handlers, and window events.
"""
import os
import json
from typing import Optional, Dict, Any

from PyQt5.QtCore import QByteArray, QPoint
from PyQt5.QtWidgets import QApplication

from core.version import __version__
from core.config import get_config_filepath
from core.models import Project
from core.global_hotkey import GlobalHotkeyListener
from core.power_manager import PowerManager
from ui.floating_stop_widget import GlobalFloatingStopWidget
from ui.anti_burn_in_overlay import AntiBurnInOverlay

TEMP_RELOAD_FILE = "_temp_reload_project.json"


class MainWindowConfigLifecycleMixin:
    """Mixin providing configuration persistence, hotkeys, anti-burn and lifecycle events."""

    def _init_global_hotkey_and_floating_stop(self):
        """Initializes global F6 keyboard listener and always-on-top floating emergency stop widget."""
        self.global_hotkey = GlobalHotkeyListener(None)
        self.global_hotkey.sig_stop_hotkey.connect(self._on_global_hotkey_stop)
        self.global_hotkey.sig_pause_hotkey.connect(self._on_global_hotkey_pause)
        self.global_hotkey.sig_anti_burn_escape.connect(self._on_anti_burn_emergency_escape)
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
        if hasattr(self, "runner") and self.runner and self.runner.isRunning():
            self._append_log("WARN", "🛑 [전역 단축키] F6 긴급 정지가 수신되었습니다.")
            self._on_stop_execution()

    def _on_global_hotkey_pause(self):
        """Global Shift+F6 hotkey handler (toggles pause/resume system-wide)."""
        if hasattr(self, "runner") and self.runner and self.runner.isRunning():
            is_paused = getattr(self.runner, "_is_paused", False)
            state_desc = "재개" if is_paused else "일시정지"
            self._append_log("INFO", f"⏸ [전역 단축키] Shift+F6 {state_desc}가 수신되었습니다.")
            self._on_pause_execution()

    def _on_anti_burn_emergency_escape(self):
        """Global F12 emergency escape handler: immediately aborts anti-burn overlay."""
        aborted = AntiBurnInOverlay.escape_all()
        if aborted:
            self._append_log("WARN", "🚨 [번인 긴급탈출] F12 단축키가 감지되어 번인 방지 화면이 즉시 강제 해제되었습니다.")

    def _update_window_title(self):
        """Update window title with application version and current project filename."""
        title = f"FGOA v{__version__} - 화면 인식 스마트 윈도우 오토 툴"
        if getattr(self, "current_project_path", None):
            proj_name = os.path.basename(self.current_project_path)
            title = f"{title} [{proj_name}]"
        self.setWindowTitle(title)

    def _mark_dirty(self):
        """Marks the current project or inspector as modified and updates state."""
        if hasattr(self, "inspector") and self.inspector:
            self.inspector._mark_dirty()
        self._update_window_title()

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
                    if hasattr(self, "project") and hasattr(self.project, "target_client_width"):
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
        burn_hold = cfg.get("anti_burn_hold_min", 1)
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

        if hasattr(self, "spin_anti_burn_hold_min") and self.spin_anti_burn_hold_min:
            self.spin_anti_burn_hold_min.blockSignals(True)
            self.spin_anti_burn_hold_min.setValue(burn_hold)
            self.spin_anti_burn_hold_min.blockSignals(False)

        if hasattr(self, "chk_anti_burn") and self.chk_anti_burn:
            self.chk_anti_burn.blockSignals(True)
            self.chk_anti_burn.setChecked(burn_enabled)
            self.chk_anti_burn.blockSignals(False)

        if hasattr(self, "anti_burn_overlay") and self.anti_burn_overlay:
            self.anti_burn_overlay.set_mode(burn_mode)
            self.anti_burn_overlay.set_interval_minutes(burn_interval)
            self.anti_burn_overlay.set_hold_minutes(burn_hold)
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

        # Background mode (백그라운드 제어)
        background_mode_enabled = cfg.get("background_mode_enabled", False)
        if hasattr(self, "chk_background_mode") and self.chk_background_mode:
            self.chk_background_mode.blockSignals(True)
            self.chk_background_mode.setChecked(background_mode_enabled)
            self.chk_background_mode.blockSignals(False)

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

        # 5-1. Robust Trace Mode (강력 로그추적)
        robust_trace_en = cfg.get("robust_trace_enabled", False)
        if hasattr(self, "chk_robust_trace") and self.chk_robust_trace:
            self.chk_robust_trace.blockSignals(True)
            self.chk_robust_trace.setChecked(robust_trace_en)
            self.chk_robust_trace.blockSignals(False)

        # 5-2. Prevent Screensaver Mode (화면보호기 차단)
        prevent_ss_en = cfg.get("prevent_screensaver_enabled", True)
        if hasattr(self, "btn_prevent_screensaver") and self.btn_prevent_screensaver:
            self.btn_prevent_screensaver.blockSignals(True)
            self.btn_prevent_screensaver.setChecked(prevent_ss_en)
            if hasattr(self, "_update_prevent_screensaver_btn_ui"):
                self._update_prevent_screensaver_btn_ui(prevent_ss_en)
            self.btn_prevent_screensaver.blockSignals(False)

        # 6. Scenario Table Column Visibility (시나리오 테이블 열 표시 여부)
        cols_vis = cfg.get("scenario_columns_visible")
        if isinstance(cols_vis, dict) and hasattr(self, "tbl_scenarios") and self.tbl_scenarios:
            self.tbl_scenarios.set_column_visibility_state(cols_vis)

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
                "theme": getattr(self, "current_theme", "light"),
                "window_x": win_x,
                "window_y": win_y,
                "window_width": win_w,
                "window_height": win_h,
                "window_is_maximized": is_maximized,
                "window_geometry": self.saveGeometry().toHex().data().decode(),
                "last_target_title": (getattr(self.project, "target_window_title", "") if hasattr(self, "project") else "") or getattr(self, "_last_config_target_title", ""),
                "last_target_width": getattr(self.project, "target_client_width", 1600) if hasattr(self, "project") else 1600,
                "last_target_height": getattr(self.project, "target_client_height", 900) if hasattr(self, "project") else 900,
                "layout_name": getattr(self, "current_layout_name", "기본 3열 (Default)"),
                "custom_layouts": getattr(self, "custom_layouts", {}),
                "last_project_path": getattr(self, "current_project_path", None),
            })

            # Save UI controls state safely (only overwrite if widget exists to avoid erasing loaded configs)
            if hasattr(self, "chk_anti_burn") and self.chk_anti_burn:
                cfg["anti_burn_enabled"] = self.chk_anti_burn.isChecked()
            if hasattr(self, "combo_anti_burn_mode") and self.combo_anti_burn_mode and self.combo_anti_burn_mode.currentData() is not None:
                cfg["anti_burn_mode"] = self.combo_anti_burn_mode.currentData()
            if hasattr(self, "spin_anti_burn_min") and self.spin_anti_burn_min:
                cfg["anti_burn_interval_min"] = self.spin_anti_burn_min.value()
            if hasattr(self, "spin_anti_burn_hold_min") and self.spin_anti_burn_hold_min:
                cfg["anti_burn_hold_min"] = self.spin_anti_burn_hold_min.value()
            if hasattr(self, "chk_action_overlay") and self.chk_action_overlay:
                cfg["action_overlay_enabled"] = self.chk_action_overlay.isChecked()
            if hasattr(self, "chk_floating_stop") and self.chk_floating_stop:
                cfg["floating_stop_enabled"] = self.chk_floating_stop.isChecked()
            if hasattr(self, "chk_background_mode") and self.chk_background_mode:
                cfg["background_mode_enabled"] = self.chk_background_mode.isChecked()
            if hasattr(self, "chk_hot_reload") and self.chk_hot_reload:
                cfg["hot_reload_enabled"] = self.chk_hot_reload.isChecked()
            if hasattr(self, "chk_autoscroll") and self.chk_autoscroll:
                cfg["autoscroll_enabled"] = self.chk_autoscroll.isChecked()
            if hasattr(self, "chk_robust_trace") and self.chk_robust_trace:
                cfg["robust_trace_enabled"] = self.chk_robust_trace.isChecked()
            if hasattr(self, "btn_prevent_screensaver") and self.btn_prevent_screensaver:
                cfg["prevent_screensaver_enabled"] = self.btn_prevent_screensaver.isChecked()
            if hasattr(self, "tbl_scenarios") and self.tbl_scenarios:
                cfg["scenario_columns_visible"] = self.tbl_scenarios.get_column_visibility_state()

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
        PowerManager.allow_screensaver()
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
            hold_mins = self.spin_anti_burn_hold_min.value() if hasattr(self, "spin_anti_burn_hold_min") else 1
            mode = self.anti_burn_overlay.get_mode()
            mode_name = "앱 창" if mode == 1 else "데스크탑 전체 화면"
            if checked:
                self._append_log("INFO", f"🖥️ [모니터 번인 방지] 모드 {mode}({mode_name}) {mins}분 주기 / {hold_mins}분 블랙 유지 화면 전환 활성화 (조작 간섭 없음)")
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
            hold_mins = self.spin_anti_burn_hold_min.value() if hasattr(self, "spin_anti_burn_hold_min") else 1
            self._append_log("INFO", f"🖥️ [모니터 번인 방지] {mode_name} 블랙 화면 전환 효과 테스트 시작 ({hold_mins}분 유지, 조작 간섭 없음)")
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

    def _on_anti_burn_hold_changed(self, val: int):
        if hasattr(self, "anti_burn_overlay") and self.anti_burn_overlay:
            self.anti_burn_overlay.set_hold_minutes(val)
            self._save_app_config()

    def __del__(self):
        if hasattr(self, "global_hotkey") and self.global_hotkey:
            try:
                self.global_hotkey.stop_listening()
            except Exception:
                pass
