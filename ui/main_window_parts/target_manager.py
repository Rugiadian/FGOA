"""Target Window & Virtual Canvas Management Mixin for MainWindow.

Handles:
- Window auto-tracking, selection via WindowPickerDialog, and focus
- Virtual Canvas window lifecycle and coordination
- Authoring resolution and reference screenshot registration/gallery
- Target alive monitoring timer
"""

import os
from typing import Optional, Any
from PyQt5.QtCore import QTimer, QPoint
from PyQt5.QtGui import QPixmap, QCursor
from PyQt5.QtWidgets import QMessageBox, QFileDialog, QDialog, QMenu, QInputDialog

from core.window_manager import WindowManager, WindowInfo
from core.path_utils import to_relative_path, to_absolute_path
from ui.theme import get_theme_colors
from ui.window_picker_dialog import WindowPickerDialog
from ui.virtual_canvas_window import VirtualCanvasWindow


class MainWindowTargetMixin:
    """Mixin providing target window discovery, tracking, canvas, and authoring resolution management."""

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
            hwnd_val = getattr(win, "hwnd", 0)
            if isinstance(hwnd_val, int):
                hwnd_str = f"0x{hwnd_val:X}"
            else:
                hwnd_str = str(hwnd_val)
            if hwnd_val:
                new_text = f"'{win.title}' (HWND: {hwnd_str}, 해상도: {win.client_width}×{win.client_height})"
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
