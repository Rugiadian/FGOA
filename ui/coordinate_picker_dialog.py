"""
Coordinate Picker Dialog for FGOA.
Allows visually picking action execution coordinates (X, Y) directly from a
reference image or live target window capture, complete with magnifier loupe.
"""
import os
from typing import Optional, Tuple
from PIL import Image, ImageQt
from PyQt5.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QFileDialog, QMessageBox, QFrame
)
from PyQt5.QtCore import Qt, QPoint, QRect
from PyQt5.QtGui import QPixmap, QPainter, QPen, QColor, QBrush, QCursor, QFont

from core.screen_capture import ScreenCapture


class CoordinateCanvas(QWidget):
    """Interactive canvas that displays an image, handles click coordinates, and draws crosshairs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pixmap: Optional[QPixmap] = None
        self.pil_image: Optional[Image.Image] = None

        self.drag_mode = False
        self.point1: Optional[Tuple[int, int]] = None
        self.point2: Optional[Tuple[int, int]] = None
        self.current_hover: Optional[Tuple[int, int]] = None
        self.hover_color: Optional[Tuple[int, int, int]] = None

        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)

    def set_image(self, pil_img: Image.Image):
        self.pil_image = pil_img
        qim = ImageQt.ImageQt(pil_img)
        self.pixmap = QPixmap.fromImage(qim)
        self.setFixedSize(self.pixmap.size())
        self.update()

    def set_initial_points(self, p1: Optional[Tuple[int, int]], p2: Optional[Tuple[int, int]] = None):
        self.point1 = p1
        self.point2 = p2
        self.update()

    def mouseMoveEvent(self, event):
        if not self.pixmap:
            return
        x = max(0, min(event.x(), self.pixmap.width() - 1))
        y = max(0, min(event.y(), self.pixmap.height() - 1))
        self.current_hover = (x, y)

        if self.pil_image:
            try:
                rgb = self.pil_image.getpixel((x, y))
                if isinstance(rgb, int):
                    rgb = (rgb, rgb, rgb)
                self.hover_color = (rgb[0], rgb[1], rgb[2])
            except Exception:
                self.hover_color = (0, 0, 0)

        # Notify parent dialog
        parent_dlg = self.window()
        if hasattr(parent_dlg, "update_hover_info"):
            parent_dlg.update_hover_info(x, y, self.hover_color)

        self.update()

    def mousePressEvent(self, event):
        if not self.pixmap or event.button() != Qt.LeftButton:
            return
        x = max(0, min(event.x(), self.pixmap.width() - 1))
        y = max(0, min(event.y(), self.pixmap.height() - 1))

        if not self.drag_mode:
            self.point1 = (x, y)
        else:
            if self.point1 is None or self.point2 is not None:
                self.point1 = (x, y)
                self.point2 = None
            else:
                self.point2 = (x, y)

        parent_dlg = self.window()
        if hasattr(parent_dlg, "on_point_selected"):
            parent_dlg.on_point_selected(self.point1, self.point2)

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        if not self.pixmap:
            painter.fillRect(self.rect(), QColor(240, 240, 240))
            painter.drawText(self.rect(), Qt.AlignCenter, "이미지가 없습니다.")
            return

        painter.drawPixmap(0, 0, self.pixmap)

        # Draw Point 1 (Start or single click)
        if self.point1:
            p1_x, p1_y = self.point1
            pen = QPen(QColor(239, 68, 68), 2)  # Red
            painter.setPen(pen)
            painter.setBrush(QBrush(QColor(239, 68, 68, 120)))
            painter.drawEllipse(p1_x - 8, p1_y - 8, 16, 16)
            painter.drawLine(p1_x - 14, p1_y, p1_x + 14, p1_y)
            painter.drawLine(p1_x, p1_y - 14, p1_x, p1_y + 14)

            # Label
            tag = "시작점" if self.drag_mode else "클릭 위치"
            painter.fillRect(p1_x + 12, p1_y - 18, 120, 20, QColor(0, 0, 0, 180))
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(QFont("Arial", 8, QFont.Bold))
            painter.drawText(p1_x + 16, p1_y - 4, f"{tag} ({p1_x}, {p1_y})")

        # Draw Point 2 (End for drag)
        if self.drag_mode and self.point2:
            p2_x, p2_y = self.point2
            pen = QPen(QColor(37, 99, 235), 2)  # Blue
            painter.setPen(pen)
            painter.setBrush(QBrush(QColor(37, 99, 235, 120)))
            painter.drawEllipse(p2_x - 8, p2_y - 8, 16, 16)
            painter.drawLine(p2_x - 14, p2_y, p2_x + 14, p2_y)
            painter.drawLine(p2_x, p2_y - 14, p2_x, p2_y + 14)

            painter.fillRect(p2_x + 12, p2_y - 18, 120, 20, QColor(0, 0, 0, 180))
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(QFont("Arial", 8, QFont.Bold))
            painter.drawText(p2_x + 16, p2_y - 4, f"종료점 ({p2_x}, {p2_y})")

            # Draw arrow line connecting point 1 and 2
            if self.point1:
                pen_line = QPen(QColor(16, 185, 129), 2, Qt.DashLine)
                painter.setPen(pen_line)
                painter.drawLine(self.point1[0], self.point1[1], p2_x, p2_y)


class CoordinatePickerDialog(QDialog):
    """
    Visual Dialog for picking coordinates from an image or live target window.
    """

    def __init__(
        self,
        image_path: Optional[str] = None,
        target_hwnd: int = 0,
        initial_x: int = 0,
        initial_y: int = 0,
        drag_mode: bool = False,
        initial_end_x: int = 0,
        initial_end_y: int = 0,
        parent=None
    ):
        super().__init__(parent)
        self.setWindowTitle("🎯 레퍼런스 이미지에서 좌표 지정")
        self.resize(1000, 680)

        self.target_hwnd = target_hwnd
        self.drag_mode = drag_mode
        self.selected_x = initial_x
        self.selected_y = initial_y
        self.selected_end_x = initial_end_x
        self.selected_end_y = initial_end_y

        self._init_ui()

        # Load image
        loaded = False
        if image_path and os.path.exists(image_path):
            try:
                img = Image.open(image_path).convert("RGB")
                self.canvas.set_image(img)
                loaded = True
            except Exception:
                pass

        if not loaded and self.target_hwnd:
            self._capture_target_window()

        # Set initial points
        p1 = (initial_x, initial_y) if (initial_x > 0 or initial_y > 0) else None
        p2 = (initial_end_x, initial_end_y) if drag_mode and (initial_end_x > 0 or initial_end_y > 0) else None
        self.canvas.set_initial_points(p1, p2)
        self._update_coord_badge()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # Top Bar (Toolbar + Status)
        top_bar = QFrame()
        top_bar.setObjectName("card_frame")
        t_layout = QHBoxLayout(top_bar)
        t_layout.setContentsMargins(8, 6, 8, 6)

        btn_capture = QPushButton("📸 게임 화면 새로 캡처")
        btn_capture.setObjectName("btn_primary")
        btn_capture.clicked.connect(self._capture_target_window)
        t_layout.addWidget(btn_capture)

        btn_browse = QPushButton("📂 다른 이미지 열기...")
        btn_browse.clicked.connect(self._browse_image)
        t_layout.addWidget(btn_browse)

        t_layout.addSpacing(12)

        # Status labels
        self.lbl_hover_info = QLabel("마우스 커서를 이미지 위로 이동하세요")
        self.lbl_hover_info.setStyleSheet("color: #64748b; font-size: 9pt;")
        t_layout.addWidget(self.lbl_hover_info)

        t_layout.addStretch()

        self.lbl_selected_badge = QLabel("선택된 좌표: (0, 0)")
        self.lbl_selected_badge.setStyleSheet(
            "background-color: #2563eb; color: white; font-weight: bold; "
            "padding: 4px 10px; border-radius: 4px; font-size: 9.5pt;"
        )
        t_layout.addWidget(self.lbl_selected_badge)

        main_layout.addWidget(top_bar)

        # Center: ScrollArea with Canvas
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.canvas = CoordinateCanvas(self)
        self.canvas.drag_mode = self.drag_mode
        self.scroll_area.setWidget(self.canvas)
        main_layout.addWidget(self.scroll_area, 1)

        # Bottom Bar: Instructions + Apply / Cancel buttons
        btm_bar = QHBoxLayout()
        guide_text = "원하는 클릭 지점을 마우스 좌클릭하세요." if not self.drag_mode else "1번째 클릭: 드래그 시작점 | 2번째 클릭: 드래그 종료점"
        lbl_guide = QLabel(f"💡 {guide_text}")
        lbl_guide.setStyleSheet("color: #475569; font-weight: bold; font-size: 9pt;")
        btm_bar.addWidget(lbl_guide)

        btm_bar.addStretch()

        btn_apply = QPushButton("✅ 이 좌표 적용")
        btn_apply.setObjectName("btn_primary")
        btn_apply.setStyleSheet("padding: 6px 18px; font-weight: bold;")
        btn_apply.clicked.connect(self.accept)
        btm_bar.addWidget(btn_apply)

        btn_cancel = QPushButton("취소")
        btn_cancel.clicked.connect(self.reject)
        btm_bar.addWidget(btn_cancel)

        main_layout.addLayout(btm_bar)

    def _capture_target_window(self):
        if not self.target_hwnd:
            QMessageBox.warning(self, "타겟 창 없음", "타겟 게임 창이 선택되어 있지 않습니다.")
            return
        img = ScreenCapture.capture_client_area(self.target_hwnd)
        if img:
            self.canvas.set_image(img)
        else:
            QMessageBox.warning(self, "캡처 실패", "타겟 창의 클라이언트 영역을 캡처할 수 없습니다.")

    def _browse_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "레퍼런스 이미지 열기", "", "이미지 파일 (*.png *.jpg *.jpeg *.bmp)"
        )
        if path and os.path.exists(path):
            try:
                img = Image.open(path).convert("RGB")
                self.canvas.set_image(img)
            except Exception as ex:
                QMessageBox.critical(self, "열기 실패", f"이미지를 열 수 없습니다: {ex}")

    def update_hover_info(self, x: int, y: int, rgb: Optional[Tuple[int, int, int]]):
        if rgb:
            hex_color = f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"
            self.lbl_hover_info.setText(f"커서 좌표: ({x}, {y}) | RGB: ({rgb[0]}, {rgb[1]}, {rgb[2]}) {hex_color}")
        else:
            self.lbl_hover_info.setText(f"커서 좌표: ({x}, {y})")

    def on_point_selected(self, p1: Optional[Tuple[int, int]], p2: Optional[Tuple[int, int]]):
        if p1:
            self.selected_x, self.selected_y = p1
        if p2:
            self.selected_end_x, self.selected_end_y = p2
        self._update_coord_badge()

    def _update_coord_badge(self):
        if self.drag_mode:
            self.lbl_selected_badge.setText(
                f"드래그: ({self.selected_x}, {self.selected_y}) → ({self.selected_end_x}, {self.selected_end_y})"
            )
        else:
            self.lbl_selected_badge.setText(f"선택 좌표: ({self.selected_x}, {self.selected_y})")

    def get_coordinates(self) -> Tuple[int, int, int, int]:
        """Returns (x, y, end_x, end_y)."""
        return self.selected_x, self.selected_y, self.selected_end_x, self.selected_end_y
