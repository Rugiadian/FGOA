"""
Condition and Color Picker Preset Editor Dialog for FGOA.
Integrates CanvasView, Magnifier, Reference Image handling,
Continuous Line sampling, and Duplicate/Uniqueness validation.
"""
import os
import copy
from typing import Optional, List
from PyQt5.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
    QComboBox, QSpinBox, QGroupBox, QSplitter, QMessageBox,
    QApplication, QInputDialog, QButtonGroup, QSizePolicy
)
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import Qt, QTimer
from PIL import Image

from core.models import Condition, ColorPoint, Project, Scenario
from core.screen_capture import ScreenCapture
from core.evaluator import ConditionEvaluator
from ui.canvas_view import CanvasView
from ui.magnifier_widget import MagnifierWidget
from ui.widgets.color_badge import ColorChipWidget, WarningBadge
from core.path_utils import get_references_dir, to_relative_path, to_absolute_path
from ui.reference_gallery_dialog import ReferenceGalleryDialog
from ui.qt_image_utils import qimage_to_pil


class ConditionEditorDialog(QDialog):
    """Visual Condition and Color Picker Preset Editor."""

    def __init__(self, condition: Optional[Condition], project: Project,
                 current_scenario_id: str, target_hwnd: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("이미지에서 좌표 지정 작업창")
        self.resize(1260, 820)

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

        # Initialize Interactive Canvas early so toolbar buttons can bind to it
        self.canvas = CanvasView(self)
        self.canvas.sig_pixel_hovered.connect(self._on_canvas_pixel_hovered)
        self.canvas.sig_point_added.connect(self._on_canvas_point_added)
        self.canvas.sig_line_points_added.connect(self._on_canvas_line_added)
        self.canvas.sig_point_selected.connect(self._on_canvas_point_selected)
        self.canvas.sig_nudge_requested.connect(self._on_nudge_point)

        # 1. Top Header Toolbar: Reference Image & Tools
        top_bar_widget = QWidget()
        top_bar_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        top_bar = QHBoxLayout(top_bar_widget)
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(6)

        # Image Load Buttons
        btn_open_img = QPushButton("📁 레퍼런스 열기")
        btn_open_img.clicked.connect(self._on_open_image_file)
        top_bar.addWidget(btn_open_img)

        btn_gallery = QPushButton("🖼️ 갤러리에서 선택...")
        btn_gallery.clicked.connect(self._on_open_gallery)
        top_bar.addWidget(btn_gallery)

        btn_capture_win = QPushButton("📸 타겟 창 캡처")
        btn_capture_win.clicked.connect(self._on_capture_target_window)
        top_bar.addWidget(btn_capture_win)

        btn_paste_clip = QPushButton("📋 붙여넣기")
        btn_paste_clip.clicked.connect(self._on_paste_clipboard)
        top_bar.addWidget(btn_paste_clip)

        top_bar.addSpacing(12)

        # Mode Selection Buttons (Direct Icon Buttons)
        mode_box = QHBoxLayout()
        mode_box.setSpacing(3)
        mode_style = """
            QPushButton {
                padding: 4px 10px;
                border: 1px solid #94a3b8;
                border-radius: 4px;
            }
            QPushButton:checked {
                background-color: #2563eb;
                color: #ffffff;
                font-weight: bold;
                border: 1px solid #1d4ed8;
            }
        """

        self.btn_group_mode = QButtonGroup(self)
        self.btn_group_mode.setExclusive(True)

        self.btn_mode_point = QPushButton("🔴 점 피커")
        self.btn_mode_point.setCheckable(True)
        self.btn_mode_point.setChecked(True)
        self.btn_mode_point.setStyleSheet(mode_style)
        self.btn_mode_point.setToolTip("단일 점을 클릭하여 좌표와 색상을 추출합니다.")
        self.btn_group_mode.addButton(self.btn_mode_point)
        self.btn_mode_point.clicked.connect(lambda: self._set_tool_mode(0))
        mode_box.addWidget(self.btn_mode_point)

        self.btn_mode_line = QPushButton("📏 선 피커")
        self.btn_mode_line.setCheckable(True)
        self.btn_mode_line.setStyleSheet(mode_style)
        self.btn_mode_line.setToolTip("드래그하여 선을 긋고 연속 샘플 포인트를 균등 생성합니다.")
        self.btn_group_mode.addButton(self.btn_mode_line)
        self.btn_mode_line.clicked.connect(lambda: self._set_tool_mode(1))
        mode_box.addWidget(self.btn_mode_line)

        self.btn_mode_select = QPushButton("👆 선택/이동")
        self.btn_mode_select.setCheckable(True)
        self.btn_mode_select.setStyleSheet(mode_style)
        self.btn_mode_select.setToolTip("기존 등록된 포인트를 마우스로 선택하거나 드래그하여 이동합니다.")
        self.btn_group_mode.addButton(self.btn_mode_select)
        self.btn_mode_select.clicked.connect(lambda: self._set_tool_mode(2))
        mode_box.addWidget(self.btn_mode_select)

        top_bar.addLayout(mode_box)

        top_bar.addStretch()

        # Canvas View Controls: Fit, 1:1, Fullscreen
        btn_fit = QPushButton("📐 화면 맞춤")
        btn_fit.setToolTip("타겟 해상도 또는 이미지가 화면에 딱 맞도록 자동 축소/확대")
        btn_fit.clicked.connect(lambda: self.canvas.fit_to_view())
        top_bar.addWidget(btn_fit)

        btn_100 = QPushButton("1:1 원본")
        btn_100.setToolTip("100% 원본 배율로 보기")
        btn_100.clicked.connect(lambda: self.canvas.zoom_100())
        top_bar.addWidget(btn_100)

        self.btn_fullscreen = QPushButton("⛶ 전체 화면")
        self.btn_fullscreen.setToolTip("창을 최대화하거나 원래 크기로 복원합니다.")
        self.btn_fullscreen.clicked.connect(self._toggle_fullscreen)
        top_bar.addWidget(self.btn_fullscreen)

        main_layout.addWidget(top_bar_widget)

        # Warning Banner for Duplicates / Non-uniqueness
        self.lbl_warning_banner = QLabel()
        self.lbl_warning_banner.setStyleSheet(
            "background-color: #5c3800; color: #ffe082; padding: 6px 12px; "
            "border: 1px solid #ffa000; border-radius: 4px; font-weight: bold; font-size: 9.5pt;"
        )
        self.lbl_warning_banner.setVisible(False)
        main_layout.addWidget(self.lbl_warning_banner)

        # 2. Main Content Splitter: Canvas (Left) + Sidebar (Right)
        self.splitter = QSplitter(Qt.Horizontal)

        # Left: Interactive Canvas
        self.splitter.addWidget(self.canvas)

        # Right Sidebar: Magnifier + Points Table + Controls
        sidebar = QWidget()
        sidebar.setMinimumWidth(260)
        # No setMaximumWidth so user can expand it freely
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(4, 0, 0, 0)
        side_layout.setSpacing(6)

        # Magnifier Widget
        self.magnifier = MagnifierWidget(self)
        self.magnifier.sig_nudge_requested.connect(self._on_nudge_point)
        side_layout.addWidget(self.magnifier)

        # Points Table Group
        grp_points = QGroupBox("추출된 컬러 피커 포인트 목록")
        grp_layout = QVBoxLayout(grp_points)
        grp_layout.setContentsMargins(4, 8, 4, 4)

        # Logic Operator Selector (AND / OR)
        logic_row = QHBoxLayout()
        logic_row.setContentsMargins(2, 0, 2, 4)
        lbl_logic = QLabel("일치 규칙:")
        lbl_logic.setStyleSheet("font-weight: bold; font-size: 8.5pt;")
        self.combo_logic = QComboBox()
        self.combo_logic.addItem("모든 포인트 일치 (AND)", "AND")
        self.combo_logic.addItem("하나라도 일치 (OR)", "OR")
        curr_logic = getattr(self.condition, "logic_operator", "AND") or "AND"
        idx_logic = self.combo_logic.findData(curr_logic)
        if idx_logic >= 0:
            self.combo_logic.setCurrentIndex(idx_logic)
        self.combo_logic.currentIndexChanged.connect(self._on_logic_changed)
        logic_row.addWidget(lbl_logic)
        logic_row.addWidget(self.combo_logic, 1)
        grp_layout.addLayout(logic_row)

        self.tbl_points = QTableWidget()
        self.tbl_points.setColumnCount(6)
        self.tbl_points.setHorizontalHeaderLabels(["ID", "좌표", "색상", "오차", "모드", "삭제"])
        self.tbl_points.verticalHeader().setVisible(False)  # Remove duplicate vertical row numbering!
        self.tbl_points.verticalHeader().setDefaultSectionSize(26)
        self.tbl_points.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl_points.itemSelectionChanged.connect(self._on_table_row_selected)

        # Precision column sizing so coordinates are fully visible with no horizontal scrolling
        hdr = self.tbl_points.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Fixed)
        self.tbl_points.setColumnWidth(0, 32)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)  # Coordinates take all flexible room
        hdr.setSectionResizeMode(2, QHeaderView.Fixed)
        self.tbl_points.setColumnWidth(2, 38)
        hdr.setSectionResizeMode(3, QHeaderView.Fixed)
        self.tbl_points.setColumnWidth(3, 50)
        hdr.setSectionResizeMode(4, QHeaderView.Fixed)
        self.tbl_points.setColumnWidth(4, 58)
        hdr.setSectionResizeMode(5, QHeaderView.Fixed)
        self.tbl_points.setColumnWidth(5, 28)

        grp_layout.addWidget(self.tbl_points)

        # Table buttons
        btn_row_layout = QHBoxLayout()
        btn_row_layout.setSpacing(4)
        btn_del_point = QPushButton("선택 삭제")
        btn_del_point.clicked.connect(self._on_delete_selected_point)
        btn_clear_all = QPushButton("전체 비우기")
        btn_clear_all.clicked.connect(self._on_clear_all_points)
        btn_row_layout.addWidget(btn_del_point)
        btn_row_layout.addWidget(btn_clear_all)
        grp_layout.addLayout(btn_row_layout)

        side_layout.addWidget(grp_points)
        self.splitter.addWidget(sidebar)

        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([940, 320])
        main_layout.addWidget(self.splitter, 1)

        # 3. Bottom Action Buttons: Save / Cancel
        bottom_bar_widget = QWidget()
        bottom_bar_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        bottom_bar = QHBoxLayout(bottom_bar_widget)
        bottom_bar.setContentsMargins(0, 0, 0, 0)
        bottom_bar.addStretch()

        btn_cancel = QPushButton("취소")
        btn_cancel.clicked.connect(self.reject)
        bottom_bar.addWidget(btn_cancel)

        btn_save = QPushButton("💾 조건 저장")
        btn_save.setStyleSheet("background-color: #1b5e20; color: white; font-weight: bold; padding: 6px 18px;")
        btn_save.clicked.connect(self._on_save)
        bottom_bar.addWidget(btn_save)

        main_layout.addWidget(bottom_bar_widget)

    def _load_condition_data(self):
        # Set target resolution on canvas
        from core.window_manager import WindowManager
        target_info = WindowManager.get_window_info(self.target_hwnd) if self.target_hwnd else None
        target_w = target_info.client_width if target_info and target_info.client_width > 0 else (getattr(self.project, "target_client_width", 0) or 1600)
        target_h = target_info.client_height if target_info and target_info.client_height > 0 else (getattr(self.project, "target_client_height", 0) or 900)
        self.canvas.set_target_resolution(target_w, target_h)

        loaded = False
        # Load reference image if exists
        if self.condition.reference_image_path and os.path.exists(self.condition.reference_image_path):
            try:
                self.canvas.load_image_from_path(self.condition.reference_image_path)
                loaded = True
            except Exception:
                pass

        if not loaded and self.target_hwnd:
            try:
                from core.screen_capture import ScreenCapture
                img = ScreenCapture.capture_client_area(self.target_hwnd)
                if img:
                    from ui.qt_image_utils import pil_to_qpixmap
                    self.canvas.pixmap = pil_to_qpixmap(img)
                    self.canvas.qimage = self.canvas.pixmap.toImage()
                    self.canvas.fit_to_view()
                    self.canvas.update()
                    loaded = True
            except Exception:
                pass

        if not loaded:
            # Create Dummy Canvas when target app is not specified!
            from core.dummy_canvas import create_dummy_canvas_qimage
            dummy_qimg = create_dummy_canvas_qimage(target_w, target_h)
            self.canvas.set_qimage(dummy_qimg)

        # Set canvas points
        self.canvas.set_points(self.condition.points)
        if hasattr(self, "combo_logic") and self.condition:
            curr_logic = getattr(self.condition, "logic_operator", "AND") or "AND"
            idx_logic = self.combo_logic.findData(curr_logic)
            if idx_logic >= 0:
                self.combo_logic.blockSignals(True)
                self.combo_logic.setCurrentIndex(idx_logic)
                self.combo_logic.blockSignals(False)
        self._refresh_points_table()

    def _refresh_points_table(self):
        self.tbl_points.setRowCount(len(self.condition.points))
        for row, pt in enumerate(self.condition.points):
            # 1. Index
            it_idx = QTableWidgetItem(f"p{row + 1}")
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
        self.canvas.selected_point_id = new_pt.id
        self.canvas.set_points(self.condition.points)
        self._refresh_points_table()
        new_row = len(self.condition.points) - 1
        self.tbl_points.selectRow(new_row)
        self.magnifier.set_position(self.canvas.qimage, x, y)

    def _on_canvas_line_added(self, x1: int, y1: int, x2: int, y2: int):
        # Prompt user for number of points along the line
        count, ok = QInputDialog.getInt(self, "연속 선 포인트 생성", "생성할 샘플 포인트 개수를 입력하세요 (2~30개):", 5, 2, 30)
        if not ok:
            return

        pil_ref = None
        if self.canvas.qimage and not self.canvas.qimage.isNull():
            try:
                pil_ref = qimage_to_pil(self.canvas.qimage)
            except Exception:
                pil_ref = None

        sampled_pts = ConditionEvaluator.sample_line_points(
            start_x=x1, start_y=y1, end_x=x2, end_y=y2,
            count=count,
            image=pil_ref,
            hwnd=self.target_hwnd
        )
        self.condition.points.extend(sampled_pts)
        self.canvas.set_points(self.condition.points)
        self._refresh_points_table()

    def _on_canvas_point_selected(self, point_id: str):
        for row, pt in enumerate(self.condition.points):
            if pt.id == point_id:
                self.tbl_points.selectRow(row)
                self.magnifier.set_position(self.canvas.qimage, pt.x, pt.y)
                break

    def _on_table_row_selected(self):
        selected_rows = self.tbl_points.selectionModel().selectedRows()
        if selected_rows:
            row = selected_rows[0].row()
            if row < len(self.condition.points):
                pt = self.condition.points[row]
                self.canvas.selected_point_id = pt.id
                self.magnifier.set_position(self.canvas.qimage, pt.x, pt.y)
                self.canvas.update()

    def _on_nudge_point(self, dx: int, dy: int):
        if not self.condition.points:
            return

        selected_point = None
        selected_row = -1

        # 1. Match by selected_point_id
        if self.canvas.selected_point_id:
            for row, pt in enumerate(self.condition.points):
                if pt.id == self.canvas.selected_point_id:
                    selected_point = pt
                    selected_row = row
                    break

        # 2. Match by table selection
        if not selected_point:
            selected_rows = self.tbl_points.selectionModel().selectedRows()
            if selected_rows:
                selected_row = selected_rows[0].row()
                if 0 <= selected_row < len(self.condition.points):
                    selected_point = self.condition.points[selected_row]
                    self.canvas.selected_point_id = selected_point.id

        # 3. Fallback to last point
        if not selected_point:
            selected_row = len(self.condition.points) - 1
            selected_point = self.condition.points[selected_row]
            self.canvas.selected_point_id = selected_point.id

        max_w = max(1, self.canvas.target_width)
        max_h = max(1, self.canvas.target_height)
        new_x = max(0, min(max_w - 1, selected_point.x + dx))
        new_y = max(0, min(max_h - 1, selected_point.y + dy))

        selected_point.x = new_x
        selected_point.y = new_y

        color = self.canvas.get_pixel_color_at(new_x, new_y)
        if color:
            if hasattr(color, "red"):
                selected_point.r = color.red()
                selected_point.g = color.green()
                selected_point.b = color.blue()
            else:
                selected_point.r = color[0]
                selected_point.g = color[1]
                selected_point.b = color[2]

        if 0 <= selected_row < self.tbl_points.rowCount():
            it_coord = self.tbl_points.item(selected_row, 1)
            if it_coord:
                it_coord.setText(f"({new_x}, {new_y})")
            badge = ColorChipWidget(selected_point.r, selected_point.g, selected_point.b, size=16)
            self.tbl_points.setCellWidget(selected_row, 2, badge)

        self.magnifier.set_position(self.canvas.qimage, new_x, new_y)
        self.canvas.update()
        self._check_uniqueness()

    def _set_tool_mode(self, mode: int):
        self.canvas.current_mode = mode

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

    def _on_capture_target_window(self, silent: bool = False):
        if not self.target_hwnd:
            if not silent:
                QMessageBox.warning(self, "경고", "타겟 창이 선택되지 않았습니다.")
            return

        pil_img = ScreenCapture.capture_client_area(self.target_hwnd)
        if not pil_img:
            if not silent:
                QMessageBox.warning(self, "캡처 실패", "타겟 창의 클라이언트 영역을 캡처할 수 없습니다.")
            return

        # Save to reference gallery directory (references/) so it appears in Reference Gallery
        save_dir = get_references_dir()
        os.makedirs(save_dir, exist_ok=True)
        import datetime
        now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"capture_{now_str}.png"
        ref_path = os.path.join(save_dir, fname)
        if os.path.exists(ref_path):
            idx = 1
            while os.path.exists(os.path.join(save_dir, f"capture_{now_str}_{idx}.png")):
                idx += 1
            ref_path = os.path.join(save_dir, f"capture_{now_str}_{idx}.png")
        pil_img.save(ref_path)

        rel_path = to_relative_path(ref_path)
        self.condition.reference_image_path = rel_path
        self.canvas.load_image_from_path(ref_path)
        if not silent:
            QMessageBox.information(
                self, "캡처 완료",
                f"타겟 창 화면을 캡처하여 레퍼런스 갤러리에 저장했습니다.\n({os.path.basename(ref_path)})"
            )

    def _on_paste_clipboard(self):
        clipboard = QApplication.clipboard()
        pix = clipboard.pixmap()
        if pix.isNull():
            QMessageBox.warning(self, "클립보드", "클립보드에 복사된 이미지가 없습니다.")
            return

        save_dir = get_references_dir()
        os.makedirs(save_dir, exist_ok=True)
        import datetime
        now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        ref_path = os.path.join(save_dir, f"clip_{now_str}.png")
        pix.save(ref_path, "PNG")

        rel_path = to_relative_path(ref_path)
        self.condition.reference_image_path = rel_path
        self.canvas.load_image_from_path(ref_path)
        QMessageBox.information(
            self, "붙여넣기 완료",
            f"클립보드 이미지를 레퍼런스 갤러리에 저장했습니다.\n({os.path.basename(ref_path)})"
        )

    def _on_open_gallery(self):
        dlg = ReferenceGalleryDialog(self.project, target_hwnd=self.target_hwnd, picker_mode=True, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            sel_path = dlg.get_selected_image_path()
            if sel_path and os.path.exists(sel_path):
                self.condition.reference_image_path = sel_path
                self.canvas.load_image_from_path(sel_path)
                QTimer.singleShot(60, self.canvas.fit_to_view)

    def _toggle_fullscreen(self):
        if self.isMaximized():
            self.showNormal()
            self.btn_fullscreen.setText("⛶ 전체 화면")
            self.splitter.setSizes([940, 320])
        else:
            self.showMaximized()
            self.btn_fullscreen.setText("🗗 창 크기 복원")
            avail_w = self.width()
            self.splitter.setSizes([max(600, avail_w - 320), 320])
        QTimer.singleShot(100, self.canvas.fit_to_view)

    def showEvent(self, event):
        super().showEvent(event)
        self.splitter.setSizes([940, 320])
        QTimer.singleShot(60, self.canvas.fit_to_view)

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

    def _on_logic_changed(self):
        if hasattr(self, "combo_logic") and self.condition:
            self.condition.logic_operator = self.combo_logic.currentData() or "AND"

    def _on_save(self):
        if hasattr(self, "combo_logic") and self.condition:
            self.condition.logic_operator = self.combo_logic.currentData() or "AND"
        self.accept()

    def get_condition(self) -> Condition:
        return self.condition
