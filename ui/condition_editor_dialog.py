"""
Condition and Color Picker Preset Editor Dialog for FGOA.
Integrates CanvasView, Magnifier, Reference Image handling,
Continuous Line sampling, and Duplicate/Uniqueness validation.
"""
import os
import copy
from typing import Optional, List
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
    QComboBox, QSpinBox, QGroupBox, QSplitter, QMessageBox,
    QApplication, QInputDialog
)
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import Qt
from PIL import Image

from core.models import Condition, ColorPoint, Project, Scenario
from core.screen_capture import ScreenCapture
from core.evaluator import ConditionEvaluator
from ui.canvas_view import CanvasView
from ui.magnifier_widget import MagnifierWidget
from ui.widgets.color_badge import ColorChipWidget, WarningBadge


class ConditionEditorDialog(QDialog):
    """Visual Condition and Color Picker Preset Editor."""

    def __init__(self, condition: Optional[Condition], project: Project,
                 current_scenario_id: str, target_hwnd: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("실행 조건 & 컬러 피커 프리셋 편집기")
        self.resize(1180, 780)

        self.project = project
        self.current_scenario_id = current_scenario_id
        self.target_hwnd = target_hwnd

        # Deep copy to allow cancel
        self.condition = copy.deepcopy(condition) if condition else Condition(name="새 조건")

        self._init_ui()
        self._load_condition_data()
        self._check_uniqueness()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # 1. Top Header Toolbar: Reference Image & Tools
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        # Image Load Buttons
        btn_open_img = QPushButton("📁 레퍼런스 이미지 열기")
        btn_open_img.clicked.connect(self._on_open_image_file)
        top_bar.addWidget(btn_open_img)

        btn_capture_win = QPushButton("📸 타겟 창에서 캡처")
        btn_capture_win.clicked.connect(self._on_capture_target_window)
        top_bar.addWidget(btn_capture_win)

        btn_paste_clip = QPushButton("📋 클립보드 붙여넣기")
        btn_paste_clip.clicked.connect(self._on_paste_clipboard)
        top_bar.addWidget(btn_paste_clip)

        top_bar.addSpacing(15)

        # Mode Selection Buttons
        top_bar.addWidget(QLabel("도구 모드:"))
        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["🔴 단일 점 피커 (Point)", "📏 선 모양 연속 피커 (Line)", "👆 선택 / 이동 (Select)"])
        self.combo_mode.currentIndexChanged.connect(self._on_tool_mode_changed)
        top_bar.addWidget(self.combo_mode)

        top_bar.addSpacing(15)

        # Logic Operator
        top_bar.addWidget(QLabel("판정 논리:"))
        self.combo_logic = QComboBox()
        self.combo_logic.addItems(["AND (모든 포인트 일치)", "OR (하나 이상 일치)"])
        self.combo_logic.currentIndexChanged.connect(self._on_logic_changed)
        top_bar.addWidget(self.combo_logic)

        top_bar.addStretch()

        # Reset zoom button
        btn_reset_zoom = QPushButton("🔍 뷰 리셋")
        btn_reset_zoom.clicked.connect(lambda: self.canvas.reset_view())
        top_bar.addWidget(btn_reset_zoom)

        main_layout.addLayout(top_bar)

        # Warning Banner for Duplicates / Non-uniqueness
        self.lbl_warning_banner = QLabel()
        self.lbl_warning_banner.setStyleSheet(
            "background-color: #5c3800; color: #ffe082; padding: 6px 12px; "
            "border: 1px solid #ffa000; border-radius: 4px; font-weight: bold; font-size: 9.5pt;"
        )
        self.lbl_warning_banner.setVisible(False)
        main_layout.addWidget(self.lbl_warning_banner)

        # 2. Main Content Splitter: Canvas (Left) + Sidebar (Right)
        splitter = QSplitter(Qt.Horizontal)

        # Left: Interactive Canvas
        self.canvas = CanvasView(self)
        self.canvas.sig_pixel_hovered.connect(self._on_canvas_pixel_hovered)
        self.canvas.sig_point_added.connect(self._on_canvas_point_added)
        self.canvas.sig_line_points_added.connect(self._on_canvas_line_added)
        self.canvas.sig_point_selected.connect(self._on_canvas_point_selected)
        splitter.addWidget(self.canvas)

        # Right Sidebar: Magnifier + Points Table + Controls
        sidebar = QWidget()
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(6, 0, 0, 0)
        side_layout.setSpacing(8)

        # Magnifier Widget
        self.magnifier = MagnifierWidget(self)
        side_layout.addWidget(self.magnifier)

        # Points Table Group
        grp_points = QGroupBox("추출된 컬러 피커 포인트 목록")
        grp_layout = QVBoxLayout(grp_points)
        grp_layout.setContentsMargins(6, 12, 6, 6)

        self.tbl_points = QTableWidget()
        self.tbl_points.setColumnCount(6)
        self.tbl_points.setHorizontalHeaderLabels(["#", "상대좌표", "색상 (RGB)", "오차", "모드", "삭제"])
        self.tbl_points.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tbl_points.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tbl_points.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl_points.itemSelectionChanged.connect(self._on_table_row_selected)
        grp_layout.addWidget(self.tbl_points)

        # Table buttons
        btn_row_layout = QHBoxLayout()
        btn_del_point = QPushButton("선택 포인트 삭제")
        btn_del_point.clicked.connect(self._on_delete_selected_point)
        btn_clear_all = QPushButton("전체 포인트 비우기")
        btn_clear_all.clicked.connect(self._on_clear_all_points)
        btn_row_layout.addWidget(btn_del_point)
        btn_row_layout.addWidget(btn_clear_all)
        grp_layout.addLayout(btn_row_layout)

        side_layout.addWidget(grp_points)
        splitter.addWidget(sidebar)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        main_layout.addWidget(splitter)

        # 3. Bottom Action Buttons: Save / Cancel
        bottom_bar = QHBoxLayout()
        bottom_bar.addStretch()

        btn_cancel = QPushButton("취소")
        btn_cancel.clicked.connect(self.reject)
        bottom_bar.addWidget(btn_cancel)

        btn_save = QPushButton("💾 조건 저장")
        btn_save.setStyleSheet("background-color: #1b5e20; color: white; font-weight: bold; padding: 6px 18px;")
        btn_save.clicked.connect(self._on_save)
        bottom_bar.addWidget(btn_save)

        main_layout.addLayout(bottom_bar)

    def _load_condition_data(self):
        # Set target resolution on canvas
        from core.window_manager import WindowManager
        target_info = WindowManager.get_window_info(self.target_hwnd)
        if target_info:
            self.canvas.set_target_resolution(target_info.client_width, target_info.client_height)

        # Load reference image if exists
        if self.condition.reference_image_path and os.path.exists(self.condition.reference_image_path):
            self.canvas.load_image_from_path(self.condition.reference_image_path)

        # Set logic combo
        self.combo_logic.setCurrentIndex(0 if self.condition.logic_operator == "AND" else 1)

        # Set canvas points
        self.canvas.set_points(self.condition.points)
        self._refresh_points_table()

    def _refresh_points_table(self):
        self.tbl_points.setRowCount(len(self.condition.points))
        for row, pt in enumerate(self.condition.points):
            # 1. Index
            it_idx = QTableWidgetItem(f"#{row + 1}")
            it_idx.setTextAlignment(Qt.AlignCenter)
            self.tbl_points.setItem(row, 0, it_idx)

            # 2. Coordinates
            it_coord = QTableWidgetItem(f"({pt.x}, {pt.y})")
            it_coord.setTextAlignment(Qt.AlignCenter)
            self.tbl_points.setItem(row, 1, it_coord)

            # 3. Color Badge
            badge = ColorChipWidget(pt.r, pt.g, pt.b, size=16)
            self.tbl_points.setCellWidget(row, 2, badge)

            # 4. Tolerance SpinBox
            spin_tol = QSpinBox()
            spin_tol.setRange(0, 255)
            spin_tol.setValue(pt.tolerance)
            spin_tol.valueChanged.connect(lambda val, p=pt: self._on_point_tolerance_changed(p, val))
            self.tbl_points.setCellWidget(row, 3, spin_tol)

            # 5. Match Mode ComboBox
            combo_match = QComboBox()
            combo_match.addItems(["일치", "불일치"])
            combo_match.setCurrentIndex(0 if pt.match_mode == "match" else 1)
            combo_match.currentIndexChanged.connect(lambda idx, p=pt: self._on_point_match_mode_changed(p, idx))
            self.tbl_points.setCellWidget(row, 4, combo_match)

            # 6. Delete Button
            btn_del = QPushButton("X")
            btn_del.setFixedSize(24, 24)
            btn_del.setStyleSheet("color: #ff5252; font-weight: bold; padding: 0;")
            btn_del.clicked.connect(lambda _, p=pt: self._remove_point(p))
            self.tbl_points.setCellWidget(row, 5, btn_del)

        self.canvas.update()
        self._check_uniqueness()

    def _on_canvas_pixel_hovered(self, rx: int, ry: int):
        self.magnifier.set_position(self.canvas.qimage, rx, ry)

    def _on_canvas_point_added(self, x: int, y: int, r: int, g: int, b: int):
        new_pt = ColorPoint(
            x=x, y=y, r=r, g=g, b=b,
            tolerance=15,
            match_mode="match",
            point_type="single"
        )
        self.condition.points.append(new_pt)
        self.canvas.set_points(self.condition.points)
        self._refresh_points_table()

    def _on_canvas_line_added(self, x1: int, y1: int, x2: int, y2: int):
        # Prompt user for number of points along the line
        count, ok = QInputDialog.getInt(self, "연속 선 포인트 생성", "생성할 샘플 포인트 개수를 입력하세요 (2~30개):", 5, 2, 30)
        if not ok:
            return

        sampled_pts = ConditionEvaluator.sample_line_points(
            start_x=x1, start_y=y1, end_x=x2, end_y=y2,
            count=count,
            image=None if not self.canvas.qimage else Image.fromqimage(self.canvas.qimage),
            hwnd=self.target_hwnd
        )
        self.condition.points.extend(sampled_pts)
        self.canvas.set_points(self.condition.points)
        self._refresh_points_table()

    def _on_canvas_point_selected(self, point_id: str):
        for row, pt in enumerate(self.condition.points):
            if pt.id == point_id:
                self.tbl_points.selectRow(row)
                break

    def _on_table_row_selected(self):
        selected_rows = self.tbl_points.selectionModel().selectedRows()
        if selected_rows:
            row = selected_rows[0].row()
            if row < len(self.condition.points):
                pt = self.condition.points[row]
                self.canvas.selected_point_id = pt.id
                self.canvas.update()

    def _on_tool_mode_changed(self, index: int):
        self.canvas.current_mode = index

    def _on_logic_changed(self, index: int):
        self.condition.logic_operator = "AND" if index == 0 else "OR"

    def _on_point_tolerance_changed(self, pt: ColorPoint, val: int):
        pt.tolerance = val

    def _on_point_match_mode_changed(self, pt: ColorPoint, index: int):
        pt.match_mode = "match" if index == 0 else "not_match"

    def _remove_point(self, pt: ColorPoint):
        if pt in self.condition.points:
            self.condition.points.remove(pt)
            self.canvas.set_points(self.condition.points)
            self._refresh_points_table()

    def _on_delete_selected_point(self):
        selected_rows = self.tbl_points.selectionModel().selectedRows()
        if not selected_rows:
            return
        row = selected_rows[0].row()
        if row < len(self.condition.points):
            del self.condition.points[row]
            self.canvas.set_points(self.condition.points)
            self._refresh_points_table()

    def _on_clear_all_points(self):
        if not self.condition.points:
            return
        res = QMessageBox.question(self, "확인", "모든 포인트를 삭제하시겠습니까?", QMessageBox.Yes | QMessageBox.No)
        if res == QMessageBox.Yes:
            self.condition.points.clear()
            self.canvas.set_points(self.condition.points)
            self._refresh_points_table()

    def _on_open_image_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "레퍼런스 이미지 열기", "", "Images (*.png *.jpg *.jpeg *.bmp)"
        )
        if path:
            self.condition.reference_image_path = path
            self.canvas.load_image_from_path(path)

    def _on_capture_target_window(self):
        if not self.target_hwnd:
            QMessageBox.warning(self, "경고", "타겟 창이 선택되지 않았습니다.")
            return

        pil_img = ScreenCapture.capture_client_area(self.target_hwnd)
        if not pil_img:
            QMessageBox.warning(self, "캡처 실패", "타겟 창의 클라이언트 영역을 캡처할 수 없습니다.")
            return

        # Save to temporary reference image in user's temp or project dir
        save_dir = os.path.join(os.path.expanduser("~"), ".fgoa_refs")
        os.makedirs(save_dir, exist_ok=True)
        ref_path = os.path.join(save_dir, f"capture_{self.current_scenario_id}.png")
        pil_img.save(ref_path)

        self.condition.reference_image_path = ref_path
        self.canvas.load_image_from_path(ref_path)
        QMessageBox.information(self, "캡처 완료", f"타겟 창 화면을 레퍼런스로 등록했습니다.\n({ref_path})")

    def _on_paste_clipboard(self):
        clipboard = QApplication.clipboard()
        pix = clipboard.pixmap()
        if pix.isNull():
            QMessageBox.warning(self, "클립보드", "클립보드에 복사된 이미지가 없습니다.")
            return

        save_dir = os.path.join(os.path.expanduser("~"), ".fgoa_refs")
        os.makedirs(save_dir, exist_ok=True)
        ref_path = os.path.join(save_dir, f"clip_{self.current_scenario_id}.png")
        pix.save(ref_path, "PNG")

        self.condition.reference_image_path = ref_path
        self.canvas.load_image_from_path(ref_path)
        QMessageBox.information(self, "붙여넣기 완료", "클립보드 이미지를 레퍼런스로 등록했습니다.")

    def _check_uniqueness(self):
        """Check if current condition's points are duplicate of other scenarios."""
        if not self.condition.points:
            self.lbl_warning_banner.setVisible(False)
            return

        # Compare with all scenarios in project except current
        duplicate_scenarios = []
        for scen in self.project.scenarios:
            if scen.id == self.current_scenario_id:
                continue
            if not scen.condition or not scen.condition.points:
                continue
            if ConditionEvaluator.are_conditions_duplicate(self.condition, scen.condition):
                duplicate_scenarios.append(f"#{scen.step_number} [{scen.name}]")

        if duplicate_scenarios:
            names_str = ", ".join(duplicate_scenarios)
            self.lbl_warning_banner.setText(
                f"⚠️ [고유화 경고] 동일한 좌표/색상 조건이 {names_str}에 이미 존재합니다!"
            )
            self.lbl_warning_banner.setVisible(True)
        else:
            self.lbl_warning_banner.setVisible(False)

    def _on_save(self):
        self.accept()

    def get_condition(self) -> Condition:
        return self.condition
