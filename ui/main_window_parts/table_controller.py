"""Scenario Table, Selection and Hierarchy Controller Mixin for MainWindow.

Handles:
- Scenario table cell rendering, custom widgets, badges, thumbnails, and indentation
- Folder and Loop block hierarchy, collapse/expand, depth visualization, and color themes
- Undo/Redo historical action stack (full snapshot restore)
- Scenario and block CRUD (Add, Duplicate, Delete, Move Up/Down, Drag-and-drop reorder)
- Module linking (Condition / Action Sequence picker, assignment, unlink, clear)
- Context menu operations (Color palette, Enable/Disable subtree, etc.)
"""

import os
import copy
import uuid
from typing import Optional, List, Dict, Tuple, Any

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QIcon, QCursor, QPixmap
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QTableWidgetItem,
    QCheckBox, QMessageBox, QMenu, QInputDialog, QStyle, QColorDialog
)

from core.models import Scenario, Condition, ActionSequence, make_block_palette
from core.path_utils import to_absolute_path
from ui.theme import CHECK_ICON_PATH
from ui.image_preview_dialog import show_image_preview
from ui.clickable_thumbnail import ClickableLabel


class MainWindowTableMixin:
    """Mixin providing scenario table rendering, hierarchy management, and editing operations."""
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
        ancestor_colors = []
        for row, scen in enumerate(self.project.scenarios):
            is_start = getattr(scen, "is_folder_start", scen.node_type in ("folder", "folder_start"))
            is_end = getattr(scen, "is_folder_end", scen.node_type == "folder_end")
            is_loop_start = (scen.node_type == "loop_start")
            is_loop_end = (scen.node_type == "loop_end")

            is_in_disabled_folder = any(folder_disabled_stack)

            if is_start:
                folder_disabled_stack.append((not scen.enabled) or is_in_disabled_folder)

            is_hidden = any(collapsed_stack)
            self.tbl_scenarios.setRowHidden(row, is_hidden)

            depth = depths[row] if row < len(depths) else 0
            loop_info = loop_analysis.get(row)
            folder_info = folder_analysis.get(row)

            # Pre-close end node from threadline stack so end node doesn't have an extra inner line
            if is_end or is_loop_end:
                if ancestor_colors:
                    ancestor_colors.pop()

            thread_colors = list(ancestor_colors)

            self._update_table_row(row, scen, depth, loop_info, folder_info, is_in_disabled_folder=is_in_disabled_folder, thread_colors=thread_colors)

            # Push start node color onto thread color stack for child guidelines
            if is_start:
                f_col = folder_info.get("base_color") if folder_info else "#d97706"
                ancestor_colors.append(f_col)
            elif is_loop_start:
                l_col = loop_info.get("base_color") if loop_info else "#2563eb"
                ancestor_colors.append(l_col)

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
        elif getattr(self, "_paused_scenario_id", None):
            paused_idx = next((i for i, s in enumerate(self.project.scenarios) if s.id == self._paused_scenario_id), None)
            if paused_idx is not None and 0 <= paused_idx < len(self.project.scenarios):
                self.tbl_scenarios.selectRow(paused_idx)
        elif hasattr(self, "runner") and self.runner and self.runner.isRunning():
            # 러너 실행 중(not paused)에는 테이블 행 선택을 강제하지 않고 비워둠
            self.tbl_scenarios.clearSelection()
        elif self.project.scenarios:
            # 대기(완전 정지) 상태에서만 기본으로 첫 번째 행 선택
            self.tbl_scenarios.selectRow(0)

    def _update_table_row(self, row: int, scen: Scenario, depth: int = 0, loop_info: Optional[Dict[str, Any]] = None, folder_info: Optional[Dict[str, Any]] = None, is_in_disabled_folder: bool = False, thread_colors: Optional[List[str]] = None):
        is_folder_start = getattr(scen, "is_folder_start", scen.node_type in ("folder", "folder_start"))
        is_folder_end = getattr(scen, "is_folder_end", scen.node_type == "folder_end")
        is_folder = is_folder_start or is_folder_end
        is_loop_start = (scen.node_type == "loop_start")
        is_loop_end = (scen.node_type == "loop_end")
        is_loop = is_loop_start or is_loop_end

        is_node_disabled = bool(is_in_disabled_folder or (not scen.enabled))
        folder_is_disabled = is_folder and is_node_disabled
        loop_is_disabled = is_loop and is_node_disabled

        child_disabled_color = QColor("#94a3b8" if self.current_theme == "light" else "#64748b")
        child_disabled_bg = QColor("#f8fafc" if self.current_theme == "light" else "#0b0f19")

        # Distinct child member background for nodes inside folders / loops
        is_folder_child = bool(folder_info and folder_info.get("is_child", False))
        is_loop_child = bool(loop_info and loop_info.get("is_child", False))
        child_tint_bg = None
        if not is_folder and not is_loop:
            if is_loop_child:
                child_bg_str = loop_info.get("bg_light" if self.current_theme == "light" else "bg_dark")
                if child_bg_str:
                    child_tint_bg = QColor(child_bg_str)
            elif is_folder_child:
                child_bg_str = folder_info.get("bg_light" if self.current_theme == "light" else "bg_dark")
                if child_bg_str:
                    child_tint_bg = QColor(child_bg_str)

        folder_bg = None
        folder_txt = None
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
                folder_bg = QColor("#fee2e2" if self.current_theme == "light" else "#450a0a")
                folder_txt = QColor("#ef4444" if self.current_theme == "light" else "#f87171")

        loop_bg = None
        loop_txt = None
        if is_loop:
            if loop_is_disabled:
                loop_bg = QColor("#f1f5f9" if self.current_theme == "light" else "#1e293b")
                loop_txt = QColor("#64748b" if self.current_theme == "light" else "#94a3b8")
            elif loop_info and loop_info.get("has_pair", True):
                loop_bg_str = loop_info.get("bg_light" if self.current_theme == "light" else "bg_dark", "#dbeafe")
                loop_txt_str = loop_info.get("color_light" if self.current_theme == "light" else "color_dark", "#1d4ed8")
                loop_bg = QColor(loop_bg_str)
                loop_txt = QColor(loop_txt_str)
            else:
                loop_bg = QColor("#fee2e2" if self.current_theme == "light" else "#450a0a")
                loop_txt = QColor("#ef4444" if self.current_theme == "light" else "#f87171")

        # Row background color resolution:
        # Custom color on scenario itself > folder_bg / loop_bg > child_tint_bg
        row_bg = None
        if getattr(scen, "custom_color", None):
            custom_pal = make_block_palette(scen.custom_color)
            row_bg_str = custom_pal.get("bg_light" if self.current_theme == "light" else "bg_dark")
            if row_bg_str:
                row_bg = QColor(row_bg_str)
        elif is_folder and folder_bg:
            row_bg = folder_bg
        elif is_loop and loop_bg:
            row_bg = loop_bg
        elif child_tint_bg:
            row_bg = child_tint_bg

        # 0. Snapshot (레퍼런스 이미지 스냅샷)
        if is_folder:
            self.tbl_scenarios.setCellWidget(row, 0, None)
            it_empty = QTableWidgetItem("")
            if row_bg:
                it_empty.setBackground(row_bg)
            it_empty.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.tbl_scenarios.setItem(row, 0, it_empty)
        elif is_loop_end:
            self.tbl_scenarios.setCellWidget(row, 0, None)
            it_empty = QTableWidgetItem("")
            if row_bg:
                it_empty.setBackground(row_bg)
            it_empty.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.tbl_scenarios.setItem(row, 0, it_empty)
        else:
            eff_ref = scen.get_effective_reference_image(self.project)
            abs_ref = to_absolute_path(eff_ref) if eff_ref else None
            if abs_ref and os.path.isfile(abs_ref):
                pix = QPixmap(abs_ref)
                if not pix.isNull():
                    thumb = pix.scaled(44, 22, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    lbl_thumb = ClickableLabel()
                    lbl_thumb.setPixmap(thumb)
                    lbl_thumb.setAlignment(Qt.AlignCenter)
                    lbl_thumb.setToolTip(f"📸 레퍼런스 스냅샷: {os.path.basename(abs_ref)}\n클릭 시 이미지 크게 보기")
                    lbl_thumb.setStyleSheet("background-color: transparent;")
                    lbl_thumb.setCursor(Qt.PointingHandCursor)
                    lbl_thumb.clicked.connect(lambda p=abs_ref, s=scen: show_image_preview(p, title=f"📸 [s{s.scenario_number}] {s.name} 레퍼런스 스냅샷", parent=self))

                    box = QWidget()
                    bl = QHBoxLayout(box)
                    bl.setContentsMargins(1, 1, 1, 1)
                    bl.setAlignment(Qt.AlignCenter)
                    bl.addWidget(lbl_thumb)
                    if row_bg:
                        box.setStyleSheet(f"background-color: {row_bg.name()};")
                    self.tbl_scenarios.setCellWidget(row, 0, box)
                else:
                    self.tbl_scenarios.setCellWidget(row, 0, None)
                    it_empty = QTableWidgetItem("")
                    if row_bg:
                        it_empty.setBackground(row_bg)
                    it_empty.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    self.tbl_scenarios.setItem(row, 0, it_empty)
            else:
                self.tbl_scenarios.setCellWidget(row, 0, None)
                it_empty = QTableWidgetItem("")
                if row_bg:
                    it_empty.setBackground(row_bg)
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
            if row_bg:
                it_uid.setBackground(row_bg)
            if folder_is_disabled:
                it_uid.setData(Qt.UserRole + 99, True)
            f = it_uid.font()
            f.setBold(True)
            it_uid.setFont(f)
            self.tbl_scenarios.setItem(row, 1, it_uid)
        elif is_loop:
            uid_str = f"🔁s{scen.scenario_number}"
            it_uid = QTableWidgetItem(uid_str)
            it_uid.setTextAlignment(Qt.AlignCenter)
            it_uid.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            it_uid.setToolTip(f"루프 블록: s{scen.scenario_number}")
            it_uid.setForeground(child_disabled_color if loop_is_disabled else loop_txt)
            if row_bg:
                it_uid.setBackground(row_bg)
            if loop_is_disabled:
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
            if row_bg:
                it_uid.setBackground(row_bg)
            if is_node_disabled:
                it_uid.setForeground(child_disabled_color)
                it_uid.setData(Qt.UserRole + 99, True)
                it_uid.setToolTip(f"시나리오 고유 ID: s{scen.scenario_number} ({'상위 폴더/루프 비활성화' if is_in_disabled_folder else '개별 비활성화됨'})")
            else:
                it_uid.setToolTip(f"시나리오 고유 ID: s{scen.scenario_number}")
            self.tbl_scenarios.setItem(row, 1, it_uid)

        # 2. Enabled Checkbox
        chk_widget = QWidget()
        if row_bg:
            chk_widget.setStyleSheet(f"background-color: {row_bg.name()};")
        chk_layout = QHBoxLayout(chk_widget)
        chk_layout.setContentsMargins(0, 0, 0, 0)
        chk_layout.setAlignment(Qt.AlignCenter)
        chk = QCheckBox()
        chk.setChecked(scen.enabled)
        if is_folder:
            chk.setToolTip("폴더 및 하위 항목 전체 활성화/비활성화 토글")
        elif is_loop:
            chk.setToolTip("루프 노드 활성화/비활성화 토글")
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

        # 3. Name with Loop & Folder Hierarchy UI (Clean names & Reddit-style indentation)
        if is_folder_start:
            c_cnt = folder_info.get("child_count", 0) if folder_info else 0
            if folder_info and not folder_info.get("has_pair", True):
                it_name = QTableWidgetItem(f"⚠️ [폴더 짝 없음] 📁 {scen.name}")
                it_name.setForeground(QColor("#ef4444"))
                it_name.setToolTip("대응되는 폴더 종료 노드가 없습니다. 폴더 블록을 확인해주세요.")
            else:
                collapse_icon = "▶ " if getattr(scen, "is_collapsed", False) else "▼ "
                if getattr(scen, "is_collapsed", False):
                    it_name = QTableWidgetItem(f"{collapse_icon}📁 {scen.name}  ({c_cnt}개 항목 접힘)")
                else:
                    it_name = QTableWidgetItem(f"{collapse_icon}📂 {scen.name}")
                it_name.setToolTip(f"📁 그룹 폴더: {scen.name} (더블 클릭하여 펼치기/접기)")
                it_name.setForeground(child_disabled_color if folder_is_disabled else folder_txt)
                it_name.setBackground(folder_bg)
            f = it_name.font()
            f.setBold(True)
            it_name.setFont(f)
        elif is_folder_end:
            if folder_info and not folder_info.get("has_pair", True):
                it_name = QTableWidgetItem(f"⚠️ [폴더 짝 없음] 📁 {scen.name}")
                it_name.setForeground(QColor("#ef4444"))
                it_name.setToolTip("대응되는 폴더 시작 노드가 없습니다.")
            else:
                it_name = QTableWidgetItem(f"📁 {scen.name}")
                it_name.setToolTip(f"📁 그룹 폴더 종료 지점: {scen.name}")
                it_name.setForeground(child_disabled_color if folder_is_disabled else folder_txt)
                it_name.setBackground(folder_bg)
            f = it_name.font()
            f.setBold(True)
            it_name.setFont(f)
        elif scen.node_type == "loop_start":
            if loop_info and not loop_info.get("has_pair", True):
                it_name = QTableWidgetItem(f"⚠️ [루프 짝 없음] 🔁 {scen.name}")
                it_name.setForeground(QColor("#ef4444"))
                it_name.setToolTip("⚠️ 대응되는 루프 종료 노드가 없습니다! 루프 블록을 확인해주세요.")
            else:
                it_name = QTableWidgetItem(f"🔁 {scen.name}")
                it_name.setForeground(child_disabled_color if loop_is_disabled else loop_txt)
                if loop_bg:
                    it_name.setBackground(loop_bg)
                it_name.setToolTip(f"🔁 루프 시작 노드: {scen.name} ({scen.loop_count}회 반복)")
            f = it_name.font()
            f.setBold(True)
            it_name.setFont(f)
        elif scen.node_type == "loop_end":
            if loop_info and not loop_info.get("has_pair", True):
                it_name = QTableWidgetItem(f"⚠️ [루프 짝 없음] 🔁 {scen.name}")
                it_name.setForeground(QColor("#ef4444"))
                it_name.setToolTip("⚠️ 대응되는 루프 시작 노드가 없습니다! 루프 블록을 확인해주세요.")
            else:
                it_name = QTableWidgetItem(f"🔁 {scen.name}")
                it_name.setForeground(child_disabled_color if loop_is_disabled else loop_txt)
                if loop_bg:
                    it_name.setBackground(loop_bg)
                it_name.setToolTip(f"🔁 루프 종료 노드: {scen.name}")
            f = it_name.font()
            f.setBold(True)
            it_name.setFont(f)
        else:
            it_name = QTableWidgetItem(scen.name)
            if is_node_disabled:
                it_name.setForeground(child_disabled_color)
                if is_in_disabled_folder:
                    it_name.setToolTip(f"상위 그룹 폴더가 비활성화되어 실행 시 건너뜁니다.\n{scen.name}")
                else:
                    it_name.setToolTip(f"🚫 [비활성] 이 노드는 비활성화되어 실행되지 않습니다.\n{scen.name}")
            else:
                it_name.setToolTip(scen.name)

        it_name.setData(Qt.UserRole + 100, depth)
        it_name.setData(Qt.UserRole + 101, thread_colors or [])
        if (folder_is_disabled if is_folder else (loop_is_disabled if is_loop else is_node_disabled)):
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
        elif is_loop_end:
            it_cond = QTableWidgetItem("-")
            it_cond.setForeground(child_disabled_color if loop_is_disabled else loop_txt)
            if loop_bg:
                it_cond.setBackground(loop_bg)
            if loop_is_disabled:
                it_cond.setData(Qt.UserRole + 99, True)
            it_cond.setTextAlignment(Qt.AlignCenter)
            it_cond.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.tbl_scenarios.setItem(row, 4, it_cond)
        elif is_loop_start:
            eff_cond = scen.get_effective_condition(self.project)
            if scen.loop_mode in ("until_match", "while_match") and eff_cond and eff_cond.points:
                mode_str = "일치시 탈출" if scen.loop_mode == "until_match" else "일치시 반복"
                cond_text = f"탈출: {eff_cond.name} ({mode_str})"
            else:
                cond_text = f"횟수 제어: {scen.loop_count}회 반복"
            it_cond = QTableWidgetItem(cond_text)
            it_cond.setForeground(child_disabled_color if loop_is_disabled else loop_txt)
            if loop_bg:
                it_cond.setBackground(loop_bg)
            if loop_is_disabled:
                it_cond.setData(Qt.UserRole + 99, True)
            it_cond.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            it_cond.setToolTip("더블 클릭하여 루프 조건 모듈 교체")
            self.tbl_scenarios.setItem(row, 4, it_cond)
        else:
            eff_cond = scen.get_effective_condition(self.project)
            is_cond_en = getattr(scen, "condition_enabled", True)
            if eff_cond:
                c_num = getattr(eff_cond, "condition_number", "")
                prefix = f"[C{c_num}] " if (c_num and getattr(scen, "condition_id", None)) else "[인스턴트] "
                cond_text = f"{prefix}{eff_cond.name} ({len(eff_cond.points)}pt)"
                if not is_cond_en:
                    cond_text = f"⏸ [조건 비활성] {cond_text}"
            else:
                cond_text = "(조건 없음)"
            it_cond = QTableWidgetItem(cond_text)
            if is_node_disabled:
                it_cond.setForeground(child_disabled_color)
                it_cond.setData(Qt.UserRole + 99, True)
            elif not is_cond_en:
                it_cond.setForeground(QColor("#94a3b8" if self.current_theme == "light" else "#64748b"))
            elif eff_cond and getattr(scen, "condition_id", None):
                it_cond.setForeground(QColor("#2563eb" if self.current_theme == "light" else "#60a5fa"))
            elif scen.node_type != "normal":
                it_cond.setForeground(QColor("#64748b"))
            it_cond.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            it_cond.setToolTip("조건 감지가 비활성화되어 실행 시 조건을 평가하지 않고 즉시 통과합니다." if not is_cond_en else "더블 클릭하여 인식조건 모듈 교체")
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
        elif is_loop_end:
            it_act = QTableWidgetItem("(루프 시작 복귀)")
            it_act.setForeground(child_disabled_color if loop_is_disabled else loop_txt)
            if loop_bg:
                it_act.setBackground(loop_bg)
            if loop_is_disabled:
                it_act.setData(Qt.UserRole + 99, True)
            it_act.setTextAlignment(Qt.AlignCenter)
            it_act.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.tbl_scenarios.setItem(row, 5, it_act)
        elif is_loop_start:
            eff_acts = scen.get_effective_actions(self.project)
            act_text = f"{len(eff_acts)}개 액션" if eff_acts else "(액션 없음)"
            it_act = QTableWidgetItem(act_text)
            it_act.setForeground(child_disabled_color if loop_is_disabled else loop_txt)
            if loop_bg:
                it_act.setBackground(loop_bg)
            if loop_is_disabled:
                it_act.setData(Qt.UserRole + 99, True)
            it_act.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.tbl_scenarios.setItem(row, 5, it_act)
        else:
            eff_acts = scen.get_effective_actions(self.project)
            if getattr(scen, "sequence_id", None):
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
        elif is_loop_start:
            it_branch = QTableWidgetItem(f"🔁 회차 반복 ({scen.loop_count}회)")
            it_branch.setForeground(child_disabled_color if loop_is_disabled else loop_txt)
            if loop_bg:
                it_branch.setBackground(loop_bg)
            if loop_is_disabled:
                it_branch.setData(Qt.UserRole + 99, True)
            it_branch.setTextAlignment(Qt.AlignCenter)
            it_branch.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.tbl_scenarios.setItem(row, 6, it_branch)
        elif is_loop_end:
            it_branch = QTableWidgetItem("🔁 시작점 복귀")
            it_branch.setForeground(child_disabled_color if loop_is_disabled else loop_txt)
            if loop_bg:
                it_branch.setBackground(loop_bg)
            if loop_is_disabled:
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

        # Distinct cell background tint for scenarios (custom color, folder, loop, or child tint)
        if row_bg:
            for col_idx in (1, 3, 4, 5, 6):
                it = self.tbl_scenarios.item(row, col_idx)
                if it:
                    it.setBackground(row_bg)
            it_0 = self.tbl_scenarios.item(row, 0)
            if it_0:
                it_0.setBackground(row_bg)
            if chk_widget:
                chk_widget.setStyleSheet(f"background-color: {row_bg.name()};")

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

    # Dock Layout & Preset methods have been extracted to MainWindowLayoutThemeMixin (ui/main_window_parts/layout_theme_manager.py)

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
                sub_color = menu.addMenu("🎨 폴더 색상 변경")
                self._populate_color_menu(sub_color, scen, is_folder=True)
                menu.addSeparator()
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
                sub_color = menu.addMenu("🎨 폴더 색상 변경")
                self._populate_color_menu(sub_color, scen, is_folder=True)
                menu.addSeparator()
                act_move_up = menu.addAction("⬆️ 폴더 단위 위로 이동")
                act_move_up.triggered.connect(self._on_move_up)
                act_move_dn = menu.addAction("⬇️ 폴더 단위 아래로 이동")
                act_move_dn.triggered.connect(self._on_move_down)
                menu.addSeparator()
            elif scen.node_type in ("loop_start", "loop_end"):
                sub_color = menu.addMenu("🎨 루프 색상 변경")
                self._populate_color_menu(sub_color, scen, is_folder=False)
                menu.addSeparator()
                act_move_up = menu.addAction("⬆️ 루프 단위 위로 이동")
                act_move_up.triggered.connect(self._on_move_up)
                act_move_dn = menu.addAction("⬇️ 루프 단위 아래로 이동")
                act_move_dn.triggered.connect(self._on_move_down)
                menu.addSeparator()
            else:
                act_pick_cond = menu.addAction(f"👁️ [s{scen.scenario_number}] 인식조건 모듈 교체...")
                act_pick_cond.triggered.connect(lambda checked, s=scen: self._show_condition_module_picker(s))
                act_pick_seq = menu.addAction(f"✋ [s{scen.scenario_number}] 액션시퀀스 모듈 교체...")
                act_pick_seq.triggered.connect(lambda checked, s=scen: self._show_sequence_module_picker(s))
                sub_color = menu.addMenu("🎨 시나리오 색상 변경")
                self._populate_color_menu(sub_color, scen, node_kind="scenario")
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
        menu.addSeparator()
        menu_view_cols = self.tbl_scenarios.create_column_visibility_menu(menu, title="👁️ 열 표시 / 숨기기")
        menu.addMenu(menu_view_cols)
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

    def _populate_color_menu(self, menu: QMenu, scen: Scenario, is_folder: bool = True, node_kind: str = ""):
        """Populates color preset actions and custom color dialog option for folder, loop, or scenario."""
        presets = [
            ("기본 (자동 테마 색상)", None),
            ("블루 (Blue)", "#3b82f6"),
            ("에메랄드 (Green)", "#10b981"),
            ("퍼플 (Purple)", "#8b5cf6"),
            ("호박/앰버 (Amber)", "#f59e0b"),
            ("로즈 (Rose)", "#f43f5e"),
            ("인디고 (Indigo)", "#6366f1"),
            ("틸 (Teal)", "#14b8a6"),
            ("오렌지 (Orange)", "#f97316"),
            ("시안 (Cyan)", "#06b6d4"),
        ]

        current_color = getattr(scen, "custom_color", None)

        effective_kind = node_kind if node_kind else ("folder" if is_folder else "loop")

        for label, hex_col in presets:
            pixmap = QPixmap(14, 14)
            if hex_col:
                pixmap.fill(QColor(hex_col))
            else:
                pixmap.fill(QColor("#94a3b8"))
            act = menu.addAction(QIcon(pixmap), label)
            if current_color == hex_col:
                act.setIcon(self.style().standardIcon(QStyle.SP_DialogApplyButton))
            if effective_kind == "folder":
                act.triggered.connect(lambda checked, c=hex_col, s=scen: self._change_folder_color(s, c))
            elif effective_kind == "loop":
                act.triggered.connect(lambda checked, c=hex_col, s=scen: self._change_loop_color(s, c))
            else:
                act.triggered.connect(lambda checked, c=hex_col, s=scen: self._change_scenario_color(s, c))

        menu.addSeparator()
        act_custom = menu.addAction("🎨 직접 색상 선택 (Color Picker)...")
        act_custom.triggered.connect(lambda checked, s=scen, k=effective_kind: self._pick_block_color_dialog(s, node_kind=k))

    def _change_scenario_color(self, scen: Scenario, color: Optional[str]):
        """Sets custom color for an individual scenario."""
        self._push_scenario_undo_state(f"시나리오 '{scen.name}' 색상 변경")
        scen.custom_color = color
        self._refresh_scenario_table()
        if self.inspector.current_scenario and self.inspector.current_scenario.id == scen.id:
            self.inspector.set_scenario(scen, self.target_hwnd, self.project)

    def _change_folder_color(self, scen: Scenario, color: Optional[str]):
        """Sets custom color for a folder start and its corresponding folder end."""
        self._push_scenario_undo_state(f"폴더 '{scen.name}' 색상 변경")
        scen.custom_color = color
        idx = self.project.find_scenario_index(scen.id)
        if idx is not None and idx >= 0:
            if getattr(scen, "is_folder_start", scen.node_type in ("folder", "folder_start")):
                end_idx = self.project.find_matching_folder_end(idx)
                if end_idx is not None and end_idx < len(self.project.scenarios):
                    self.project.scenarios[end_idx].custom_color = color
            elif getattr(scen, "is_folder_end", scen.node_type == "folder_end"):
                start_idx = self.project.find_matching_folder_start(idx)
                if start_idx is not None and start_idx < len(self.project.scenarios):
                    self.project.scenarios[start_idx].custom_color = color
        self._refresh_scenario_table()
        if self.inspector.current_scenario and self.inspector.current_scenario.id == scen.id:
            self.inspector.set_scenario(scen, self.target_hwnd, self.project)

    def _change_loop_color(self, scen: Scenario, color: Optional[str]):
        """Sets custom color for a loop start and its corresponding loop end."""
        self._push_scenario_undo_state(f"루프 '{scen.name}' 색상 변경")
        scen.custom_color = color
        idx = self.project.find_scenario_index(scen.id)
        if idx is not None and idx >= 0:
            if scen.node_type == "loop_start":
                end_idx = self.project.find_matching_loop_end(idx)
                if end_idx is not None and end_idx < len(self.project.scenarios):
                    self.project.scenarios[end_idx].custom_color = color
            elif scen.node_type == "loop_end":
                start_idx = self.project.find_matching_loop_start(idx)
                if start_idx is not None and start_idx < len(self.project.scenarios):
                    self.project.scenarios[start_idx].custom_color = color
        self._refresh_scenario_table()
        if self.inspector.current_scenario and self.inspector.current_scenario.id == scen.id:
            self.inspector.set_scenario(scen, self.target_hwnd, self.project)

    def _pick_block_color_dialog(self, scen: Scenario, is_folder: bool = True, node_kind: str = ""):
        initial = QColor(scen.custom_color) if scen.custom_color else QColor("#3b82f6")
        effective_kind = node_kind if node_kind else ("folder" if is_folder else "loop")
        if effective_kind == "folder":
            title = "폴더 색상 선택"
        elif effective_kind == "loop":
            title = "루프 색상 선택"
        else:
            title = "시나리오 색상 선택"
        picked = QColorDialog.getColor(initial, self, title)
        if picked.isValid():
            hex_code = picked.name()
            if effective_kind == "folder":
                self._change_folder_color(scen, hex_code)
            elif effective_kind == "loop":
                self._change_loop_color(scen, hex_code)
            else:
                self._change_scenario_color(scen, hex_code)

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
    def _on_add_scenario(self, *args, custom_insert_idx: Optional[int] = None):
        new_scen_num = self.project.get_next_scenario_number()
        target_idx = None
        if custom_insert_idx is not None and not isinstance(custom_insert_idx, bool):
            target_idx = custom_insert_idx
        elif args and isinstance(args[0], int) and not isinstance(args[0], bool):
            target_idx = args[0]

        if target_idx is not None:
            insert_idx = target_idx
        else:
            selected_rows = sorted([r.row() for r in self.tbl_scenarios.selectionModel().selectedRows()])
            if not selected_rows and self.tbl_scenarios.selectionModel().hasSelection():
                selected_rows = sorted(list(set(idx.row() for idx in self.tbl_scenarios.selectedIndexes())))

            if selected_rows:
                target_row = selected_rows[-1]
                target_scen = self.project.scenarios[target_row] if target_row < len(self.project.scenarios) else None
                insert_idx = target_row + 1
                if target_scen and getattr(target_scen, "is_folder_start", target_scen.node_type in ("folder", "folder_start")):
                    target_scen.is_collapsed = False
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
        it_focus = self.tbl_scenarios.item(insert_idx, 3) or self.tbl_scenarios.item(insert_idx, 1)
        if it_focus:
            self.tbl_scenarios.scrollToItem(it_focus)

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
                target_row = selected_rows[-1]
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
        selected_rows = sorted([r.row() for r in self.tbl_scenarios.selectionModel().selectedRows()])
        if not selected_rows and self.tbl_scenarios.selectionModel().hasSelection():
            selected_rows = sorted(list(set(idx.row() for idx in self.tbl_scenarios.selectedIndexes())))
        insert_idx = selected_rows[-1] + 1 if selected_rows else len(self.project.scenarios)

        self._push_scenario_undo_state(f"루프 블록 #{start_num} 추가")
        self.project.scenarios[insert_idx:insert_idx] = [scen_start, scen_child, scen_end]
        self.project.renumber_steps()
        self._refresh_scenario_table()
        # Select loop start
        self.tbl_scenarios.selectRow(insert_idx)

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

