"""
Action Sequence Image Coordinate Picker Dialog for FGOA.
(액션 시퀀스 이미지로 좌표 지정 작업창)

Allows visually setting, recording, and testing action sequence coordinates directly
on a reference image or live game capture. Features include:
- Compact 1px directional nudge controls (without bulky magnifier/color info)
  to maximize vertical screen space for the action sequence list.
- Image-based operation recording: record clicks and wait times directly on the
  reference image without requiring a target app.
- Visual full sequence simulation with an animated virtual cursor on the canvas.
- No intrusive completion popups.
"""
import os
import copy
import math
import time
import random
from typing import Optional, Tuple, List, Dict, Any
from PIL import Image

from PyQt5.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QMessageBox, QFrame, QSplitter, QGroupBox,
    QApplication, QSizePolicy
)
from PyQt5.QtCore import Qt, QPoint, QPointF, QRectF, pyqtSignal, QTimer
from PyQt5.QtGui import (
    QPixmap, QPainter, QPen, QColor, QBrush, QCursor, QFont,
    QImage, QPolygonF
)

from core.models import Action, Project
from core.screen_capture import ScreenCapture
from core.input_controller import InputController
from core.dummy_canvas import create_dummy_canvas_qimage
from ui.qt_image_utils import pil_to_qpixmap, qimage_to_pil


class ActionCanvasView(QWidget):
    """
    Interactive 2D Canvas for displaying reference images,
    navigating with zoom/pan, placing action waypoints,
    drawing a virtual cursor for simulation, and recording clicks/drags.
    """
    sig_pixel_hovered = pyqtSignal(int, int)  # (rel_x, rel_y)
    sig_action_selected = pyqtSignal(int)     # action_index
    sig_action_modified = pyqtSignal(int)     # action_index
    sig_canvas_clicked = pyqtSignal(int, int) # (rel_x, rel_y)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.CrossCursor)

        # Image & Dimensions
        self.pixmap: Optional[QPixmap] = None
        self.qimage: Optional[QImage] = None
        self.target_width: int = 1600
        self.target_height: int = 900

        # Actions & Selection
        self.actions: List[Action] = []
        self.selected_action_index: int = -1
        self._drag_setting_end = False

        # View transform (Zoom & Pan)
        self.zoom: float = 1.0
        self.pan_x: float = 20.0
        self.pan_y: float = 20.0

        # Interaction state
        self._is_panning = False
        self._pan_start_pos = QPointF()

        # Drag & Click Recording State
        self._is_recording_drag: bool = False
        self._record_press_pos: Optional[Tuple[int, int]] = None
        self._record_press_time: float = 0.0
        self._record_current_pos: Optional[Tuple[int, int]] = None

        # Virtual Cursor Simulation State
        self.virtual_cursor_pos: Optional[QPointF] = None
        self.virtual_cursor_visible: bool = False
        self.virtual_cursor_clicking: bool = False
        self.virtual_cursor_label: str = ""

    def set_target_resolution(self, width: int, height: int):
        self.target_width = max(50, width)
        self.target_height = max(50, height)
        self.update()

    def load_image_from_path(self, file_path: str):
        if not file_path or not os.path.exists(file_path):
            return
        pix = QPixmap(file_path)
        if not pix.isNull():
            self.pixmap = pix
            self.qimage = pix.toImage()
            self.fit_to_view()
            self.update()

    def set_pil_image(self, pil_img: Image.Image):
        if pil_img:
            self.pixmap = pil_to_qpixmap(pil_img)
            self.qimage = self.pixmap.toImage()
            self.fit_to_view()
            self.update()

    def set_image(self, pil_img: Image.Image):
        """Alias for backwards compatibility with tests and callers."""
        self.set_pil_image(pil_img)

    def set_qimage(self, qimg: QImage):
        if not qimg.isNull():
            self.qimage = qimg
            self.pixmap = QPixmap.fromImage(qimg)
            self.fit_to_view()
            self.update()

    def set_actions(self, actions: List[Action], selected_index: int = 0):
        self.actions = actions
        if self.actions:
            self.selected_action_index = max(0, min(selected_index, len(self.actions) - 1))
        else:
            self.selected_action_index = -1
        self._drag_setting_end = False
        self.update()

    def set_selected_action_index(self, index: int):
        self.selected_action_index = index
        self._drag_setting_end = False
        self.update()

    # Virtual Cursor Controls
    def set_virtual_cursor(self, pos: Optional[Tuple[float, float]], visible: bool = True, clicking: bool = False, label: str = ""):
        self.virtual_cursor_visible = visible
        self.virtual_cursor_clicking = clicking
        self.virtual_cursor_label = label
        if pos is not None:
            self.virtual_cursor_pos = QPointF(float(pos[0]), float(pos[1]))
        else:
            self.virtual_cursor_pos = None
        self.update()

    # Coordinate mapping
    def client_to_screen_pos(self, cx: float, cy: float) -> QPointF:
        """Canvas logical (X, Y) to widget pixel position."""
        return QPointF(self.pan_x + cx * self.zoom, self.pan_y + cy * self.zoom)

    def screen_to_client_pos(self, sx: float, sy: float) -> QPointF:
        """Widget pixel position to canvas logical (X, Y)."""
        return QPointF((sx - self.pan_x) / self.zoom, (sy - self.pan_y) / self.zoom)

    # View Controls: Fit, 1:1
    def fit_to_view(self):
        """Fit target resolution or reference image completely into visible area."""
        img_w = self.pixmap.width() if self.pixmap else self.target_width
        img_h = self.pixmap.height() if self.pixmap else self.target_height

        avail_w = max(50, self.width() - 30)
        avail_h = max(50, self.height() - 30)

        if img_w <= 0 or img_h <= 0 or avail_w <= 50:
            return

        scale_x = avail_w / img_w
        scale_y = avail_h / img_h
        best_zoom = min(scale_x, scale_y)
        self.zoom = max(0.05, best_zoom)

        self.pan_x = max(10.0, (self.width() - img_w * self.zoom) / 2.0)
        self.pan_y = max(10.0, (self.height() - img_h * self.zoom) / 2.0)
        self.update()

    def zoom_100(self):
        """Reset view to 100% 1:1 pixel scale."""
        self.zoom = 1.0
        self.pan_x = 20.0
        self.pan_y = 20.0
        self.update()

    def nudge_selected_action(self, dx: int, dy: int):
        """Adjust selected action's coordinates by 1 pixel."""
        if 0 <= self.selected_action_index < len(self.actions):
            act = self.actions[self.selected_action_index]
            if act.action_type == "mouse_click":
                act.x = max(0, act.x + dx)
                act.y = max(0, act.y + dy)
                self.sig_action_modified.emit(self.selected_action_index)
                self.update()
            elif act.action_type == "mouse_drag":
                act.x = max(0, act.x + dx)
                act.y = max(0, act.y + dy)
                act.end_x = max(0, act.end_x + dx)
                act.end_y = max(0, act.end_y + dy)
                self.sig_action_modified.emit(self.selected_action_index)
                self.update()

    # Mouse Events
    def wheelEvent(self, event):
        angle = event.angleDelta().y()
        factor = 1.15 if angle > 0 else (1.0 / 1.15)

        mouse_pos = event.pos()
        old_logical = self.screen_to_client_pos(mouse_pos.x(), mouse_pos.y())

        new_zoom = self.zoom * factor
        if 0.05 <= new_zoom <= 25.0:
            self.zoom = new_zoom
            self.pan_x = mouse_pos.x() - old_logical.x() * self.zoom
            self.pan_y = mouse_pos.y() - old_logical.y() * self.zoom
            self.update()

    def mousePressEvent(self, event):
        # Middle or Right button initiates panning
        if event.button() in (Qt.MiddleButton, Qt.RightButton):
            self._is_panning = True
            self._pan_start_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            return

        if event.button() == Qt.LeftButton:
            logical_pos = self.screen_to_client_pos(event.x(), event.y())
            lx = int(round(logical_pos.x()))
            ly = int(round(logical_pos.y()))

            parent_dlg = self.window()
            if getattr(parent_dlg, "is_recording_mode", False):
                # Start recording mouse press / potential drag
                self._is_recording_drag = True
                self._record_press_pos = (lx, ly)
                self._record_press_time = time.time()
                self._record_current_pos = (lx, ly)
                self.update()
                return

            # Notify parent dialog for non-recording clicks
            self.sig_canvas_clicked.emit(lx, ly)

            # 1. Hit test existing action markers
            hit_index = -1
            hit_radius = max(10, 14 / self.zoom)
            for idx in reversed(range(len(self.actions))):
                act = self.actions[idx]
                if act.action_type in ("mouse_click", "mouse_drag"):
                    if math.hypot(act.x - lx, act.y - ly) <= hit_radius:
                        hit_index = idx
                        break
                    if act.action_type == "mouse_drag" and math.hypot(act.end_x - lx, act.end_y - ly) <= hit_radius:
                        hit_index = idx
                        break

            if hit_index >= 0 and hit_index != self.selected_action_index:
                self.selected_action_index = hit_index
                self.sig_action_selected.emit(hit_index)
                self.update()
                return

            # 2. Update coordinates of currently selected action
            if 0 <= self.selected_action_index < len(self.actions):
                act = self.actions[self.selected_action_index]
                if act.action_type == "mouse_click":
                    act.x = max(0, lx)
                    act.y = max(0, ly)
                    self.sig_action_modified.emit(self.selected_action_index)
                    self.update()
                elif act.action_type == "mouse_drag":
                    if not self._drag_setting_end:
                        act.x = max(0, lx)
                        act.y = max(0, ly)
                        self._drag_setting_end = True
                    else:
                        act.end_x = max(0, lx)
                        act.end_y = max(0, ly)
                        self._drag_setting_end = False
                    self.sig_action_modified.emit(self.selected_action_index)
                    self.update()

    def mouseMoveEvent(self, event):
        if self._is_panning:
            delta = event.pos() - self._pan_start_pos
            self.pan_x += delta.x()
            self.pan_y += delta.y()
            self._pan_start_pos = event.pos()
            self.update()
            return

        logical_pos = self.screen_to_client_pos(event.x(), event.y())
        lx = int(round(logical_pos.x()))
        ly = int(round(logical_pos.y()))
        self.sig_pixel_hovered.emit(lx, ly)

        if self._is_recording_drag:
            self._record_current_pos = (lx, ly)
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() in (Qt.MiddleButton, Qt.RightButton):
            self._is_panning = False
            self.setCursor(Qt.CrossCursor)
            return

        if event.button() == Qt.LeftButton and self._is_recording_drag:
            self._is_recording_drag = False
            logical_pos = self.screen_to_client_pos(event.x(), event.y())
            rx = int(round(logical_pos.x()))
            ry = int(round(logical_pos.y()))
            start_pos = self._record_press_pos or (rx, ry)
            press_duration = max(0.04, time.time() - self._record_press_time)
            dist = math.hypot(rx - start_pos[0], ry - start_pos[1])
            self._record_press_pos = None
            self._record_current_pos = None
            self.update()

            parent_dlg = self.window()
            if hasattr(parent_dlg, "_on_canvas_action_recorded"):
                parent_dlg._on_canvas_action_recorded(
                    start_x=start_pos[0],
                    start_y=start_pos[1],
                    end_x=rx,
                    end_y=ry,
                    dist=dist,
                    duration=press_duration
                )
            return

    # Paint Rendering
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(16, 16, 20))

        # Live Drag Preview during Recording
        if self._is_recording_drag and self._record_press_pos and self._record_current_pos:
            p1 = self.client_to_screen_pos(self._record_press_pos[0], self._record_press_pos[1])
            p2 = self.client_to_screen_pos(self._record_current_pos[0], self._record_current_pos[1])
            dist = math.hypot(p2.x() - p1.x(), p2.y() - p1.y())
            if dist > 8:
                painter.setPen(QPen(QColor(249, 115, 22), 2, Qt.DashLine))
                painter.drawLine(p1, p2)
                # End circle (red)
                painter.setBrush(QBrush(QColor(239, 68, 68, 220)))
                painter.drawEllipse(p2, 6, 6)
            # Start circle (blue)
            painter.setBrush(QBrush(QColor(59, 130, 246, 220)))
            painter.drawEllipse(p1, 6, 6)

        # 1. Draw Reference Image
        if self.pixmap and not self.pixmap.isNull():
            top_left = self.client_to_screen_pos(0, 0)
            img_w = self.pixmap.width() * self.zoom
            img_h = self.pixmap.height() * self.zoom
            painter.drawPixmap(QRectF(top_left.x(), top_left.y(), img_w, img_h), self.pixmap, QRectF(self.pixmap.rect()))
            painter.setPen(QPen(QColor(100, 116, 139, 140), 1))
            painter.drawRect(QRectF(top_left.x(), top_left.y(), img_w, img_h))
        else:
            # Placeholder frame
            tl = self.client_to_screen_pos(0, 0)
            tw = self.target_width * self.zoom
            th = self.target_height * self.zoom
            painter.setPen(QPen(QColor(71, 85, 105), 1, Qt.DashLine))
            painter.setBrush(QBrush(QColor(24, 30, 42)))
            painter.drawRect(QRectF(tl.x(), tl.y(), tw, th))
            painter.setPen(QColor(148, 163, 184))
            painter.setFont(QFont("Arial", 11))
            painter.drawText(QRectF(tl.x(), tl.y(), tw, th), Qt.AlignCenter, "이미지가 로드되지 않았습니다.\n상단의 [레퍼런스 열기] 또는 [타겟 창 캡처]를 클릭하세요.")

        # 2. Draw Action markers
        for idx, act in enumerate(self.actions):
            is_selected = (idx == self.selected_action_index)
            if act.action_type == "mouse_click":
                self._draw_click_marker(painter, idx + 1, act.x, act.y, is_selected)
            elif act.action_type == "mouse_drag":
                self._draw_drag_marker(painter, idx + 1, act.x, act.y, act.end_x, act.end_y, is_selected)

        # 3. Draw Animated Virtual Cursor (for Simulation Test)
        if self.virtual_cursor_visible and self.virtual_cursor_pos:
            sp = self.client_to_screen_pos(self.virtual_cursor_pos.x(), self.virtual_cursor_pos.y())
            vx, vy = sp.x(), sp.y()

            # Click ripple animation
            if self.virtual_cursor_clicking:
                painter.setPen(QPen(QColor(239, 68, 68, 220), 3))
                painter.setBrush(QBrush(QColor(239, 68, 68, 80)))
                painter.drawEllipse(QPointF(vx, vy), 22, 22)

                painter.setPen(QPen(QColor(245, 158, 11, 180), 2))
                painter.drawEllipse(QPointF(vx, vy), 32, 32)

            # Draw mouse pointer icon (arrow cursor)
            painter.setPen(QPen(QColor(0, 0, 0), 2))
            painter.setBrush(QBrush(QColor(255, 255, 255)))
            poly = QPolygonF([
                QPointF(vx, vy),
                QPointF(vx, vy + 20),
                QPointF(vx + 5, vy + 15),
                QPointF(vx + 11, vy + 24),
                QPointF(vx + 14, vy + 22),
                QPointF(vx + 8, vy + 14),
                QPointF(vx + 15, vy + 14),
            ])
            painter.drawPolygon(poly)

            # Inner click dot
            if self.virtual_cursor_clicking:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(QColor(239, 68, 68)))
                painter.drawEllipse(QPointF(vx, vy), 4, 4)

            # Label box below cursor
            if self.virtual_cursor_label:
                painter.setFont(QFont("Arial", 9, QFont.Bold))
                metrics = painter.fontMetrics()
                tw = metrics.horizontalAdvance(self.virtual_cursor_label) + 14
                th = metrics.height() + 6
                tx = vx + 16
                ty = vy + 16

                painter.fillRect(QRectF(tx, ty, tw, th), QColor(15, 23, 42, 230))
                painter.setPen(QPen(QColor(56, 189, 248), 1))
                painter.drawRect(QRectF(tx, ty, tw, th))
                painter.setPen(QColor(255, 255, 255))
                painter.drawText(QRectF(tx, ty, tw, th), Qt.AlignCenter, self.virtual_cursor_label)

    def _draw_click_marker(self, painter: QPainter, num: int, cx: int, cy: int, is_selected: bool):
        sp = self.client_to_screen_pos(cx, cy)
        sx, sy = sp.x(), sp.y()
        radius = 13 if is_selected else 9

        if is_selected:
            # Outer golden glow
            painter.setPen(QPen(QColor(245, 158, 11, 100), 7))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(sx, sy), radius + 3, radius + 3)

            # Center target ring
            painter.setPen(QPen(QColor(239, 68, 68), 2.5))
            painter.setBrush(QBrush(QColor(239, 68, 68, 170)))
            painter.drawEllipse(QPointF(sx, sy), radius, radius)

            # Crosshairs
            painter.setPen(QPen(QColor(255, 255, 255), 1.5))
            painter.drawLine(int(sx - radius - 5), int(sy), int(sx + radius + 5), int(sy))
            painter.drawLine(int(sx), int(sy - radius - 5), int(sx), int(sy + radius + 5))

            # Label box
            label = f"#{num} 좌클릭 ({cx}, {cy})"
            painter.setFont(QFont("Arial", 8, QFont.Bold))
            metrics = painter.fontMetrics()
            tw = metrics.horizontalAdvance(label) + 12
            th = metrics.height() + 4
            tx = sx + radius + 6
            ty = sy - th / 2

            painter.fillRect(QRectF(tx, ty, tw, th), QColor(15, 23, 42, 220))
            painter.setPen(QPen(QColor(245, 158, 11), 1))
            painter.drawRect(QRectF(tx, ty, tw, th))
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(QRectF(tx, ty, tw, th), Qt.AlignCenter, label)
        else:
            painter.setPen(QPen(QColor(59, 130, 246), 1.5))
            painter.setBrush(QBrush(QColor(37, 99, 235, 130)))
            painter.drawEllipse(QPointF(sx, sy), radius, radius)

            painter.setPen(QPen(QColor(255, 255, 255, 180), 1))
            painter.drawLine(int(sx - radius - 2), int(sy), int(sx + radius + 2), int(sy))
            painter.drawLine(int(sx), int(sy - radius - 2), int(sx), int(sy + radius + 2))

            label = f"#{num} ({cx}, {cy})"
            painter.setFont(QFont("Arial", 8))
            metrics = painter.fontMetrics()
            tw = metrics.horizontalAdvance(label) + 8
            th = metrics.height() + 2
            tx = sx + radius + 4
            ty = sy - th / 2

            painter.fillRect(QRectF(tx, ty, tw, th), QColor(0, 0, 0, 160))
            painter.setPen(QColor(226, 232, 240))
            painter.drawText(QRectF(tx, ty, tw, th), Qt.AlignCenter, label)

    def _draw_drag_marker(self, painter: QPainter, num: int, x1: int, y1: int, x2: int, y2: int, is_selected: bool):
        sp1 = self.client_to_screen_pos(x1, y1)
        sp2 = self.client_to_screen_pos(x2, y2)

        line_color = QColor(245, 158, 11) if is_selected else QColor(16, 185, 129)
        pen_line = QPen(line_color, 2.5 if is_selected else 1.8, Qt.DashLine)
        painter.setPen(pen_line)
        painter.drawLine(sp1, sp2)

        angle = math.atan2(sp2.y() - sp1.y(), sp2.x() - sp1.x())
        arrow_size = 11
        p1 = QPointF(
            sp2.x() - arrow_size * math.cos(angle - math.pi / 6),
            sp2.y() - arrow_size * math.sin(angle - math.pi / 6)
        )
        p2 = QPointF(
            sp2.x() - arrow_size * math.cos(angle + math.pi / 6),
            sp2.y() - arrow_size * math.sin(angle + math.pi / 6)
        )
        painter.setPen(QPen(line_color, 1.5))
        painter.setBrush(QBrush(line_color))
        painter.drawPolygon(QPolygonF([sp2, p1, p2]))

        painter.setPen(QPen(QColor(239, 68, 68), 2))
        painter.setBrush(QBrush(QColor(239, 68, 68, 150)))
        painter.drawEllipse(sp1, 9, 9)

        painter.setPen(QPen(QColor(37, 99, 235), 2))
        painter.setBrush(QBrush(QColor(37, 99, 235, 150)))
        painter.drawEllipse(sp2, 9, 9)

        painter.setFont(QFont("Arial", 8, QFont.Bold if is_selected else QFont.Normal))
        painter.setPen(QColor(255, 255, 255))
        painter.fillRect(QRectF(sp1.x() + 10, sp1.y() - 9, 70, 16), QColor(0, 0, 0, 170))
        painter.drawText(QRectF(sp1.x() + 12, sp1.y() - 9, 66, 16), Qt.AlignVCenter, f"#{num} 시작")

        painter.fillRect(QRectF(sp2.x() + 10, sp2.y() - 9, 70, 16), QColor(0, 0, 0, 170))
        painter.drawText(QRectF(sp2.x() + 12, sp2.y() - 9, 66, 16), Qt.AlignVCenter, f"#{num} 종료")


# Alias for backwards compatibility
CoordinateCanvas = ActionCanvasView


class CoordinatePickerDialog(QDialog):
    """
    액션 시퀀스 이미지로 좌표 지정 작업창
    (Action Sequence Image Coordinate Picker Dialog)
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
        actions: Optional[List[Action]] = None,
        selected_action_index: int = 0,
        action: Optional[Action] = None,
        scenario: Optional[Any] = None,
        project: Optional[Project] = None,
        parent=None
    ):
        super().__init__(parent)
        self.setWindowTitle("액션 시퀀스 이미지로 좌표 지정 작업창")
        self.resize(1260, 820)

        self.target_hwnd = target_hwnd
        self.project = project or Project()
        self.current_image_path = image_path
        self.drag_mode = drag_mode

        # Recording mode on image state
        self.is_recording_mode = False
        self._record_last_click_time = 0.0

        # Simulation test state
        self._is_testing_sequence = False

        # Initialize actions list (deep-copied to allow cancel)
        if actions is not None:
            self.actions: List[Action] = copy.deepcopy(actions)
        elif action is not None:
            self.actions = [copy.deepcopy(action)]
        elif drag_mode:
            self.actions = [Action(action_type="mouse_drag", x=initial_x, y=initial_y, end_x=initial_end_x, end_y=initial_end_y)]
        else:
            self.actions = [Action(action_type="mouse_click", x=initial_x, y=initial_y)]

        self.selected_action_index = max(0, min(selected_action_index, len(self.actions) - 1)) if self.actions else -1

        self._init_ui()
        self._load_initial_image(image_path)
        self._refresh_actions_table()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 8, 10, 8)
        main_layout.setSpacing(6)

        # 1. Top Header Toolbar: Image Loading & View Adjustments
        top_bar_widget = QWidget()
        top_bar_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        top_bar = QHBoxLayout(top_bar_widget)
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(6)

        btn_open_img = QPushButton("📁 레퍼런스 열기")
        btn_open_img.setToolTip("로컬 파일 시스템에서 레퍼런스 이미지 파일을 엽니다.")
        btn_open_img.clicked.connect(self._browse_image)
        top_bar.addWidget(btn_open_img)

        btn_gallery = QPushButton("🖼️ 갤러리에서 선택...")
        btn_gallery.setToolTip("프로젝트 레퍼런스 이미지 갤러리에서 선택합니다.")
        btn_gallery.clicked.connect(self._open_gallery)
        top_bar.addWidget(btn_gallery)

        btn_capture_win = QPushButton("📸 타겟 창 캡처")
        btn_capture_win.setToolTip("현재 타겟 게임 창의 화면을 실시간으로 캡처하여 배경에 로드합니다.")
        btn_capture_win.clicked.connect(lambda: self._capture_target_window(silent=False))
        top_bar.addWidget(btn_capture_win)

        btn_paste_clip = QPushButton("📋 붙여넣기")
        btn_paste_clip.setToolTip("클립보드에 복사된 이미지를 배경으로 붙여넣습니다.")
        btn_paste_clip.clicked.connect(self._paste_clipboard)
        top_bar.addWidget(btn_paste_clip)

        top_bar.addSpacing(15)

        # View Adjustment Controls ("이미지에 따른 화면 조정")
        btn_fit = QPushButton("📐 화면 맞춤")
        btn_fit.setToolTip("캔버스 크기에 맞게 이미지 비율을 자동 조정합니다.")
        btn_fit.clicked.connect(lambda: self.canvas.fit_to_view())
        top_bar.addWidget(btn_fit)

        btn_100 = QPushButton("1:1 원본")
        btn_100.setToolTip("이미지를 100% 1:1 원본 픽셀 크기로 표시합니다.")
        btn_100.clicked.connect(lambda: self.canvas.zoom_100())
        top_bar.addWidget(btn_100)

        self.btn_fullscreen = QPushButton("⛶ 전체 화면")
        self.btn_fullscreen.setToolTip("작업창을 전체 화면으로 확대하거나 이전 크기로 복원합니다.")
        self.btn_fullscreen.clicked.connect(self._toggle_fullscreen)
        top_bar.addWidget(self.btn_fullscreen)

        top_bar.addStretch()

        self.lbl_hover_info = QLabel("커서: (0, 0)")
        self.lbl_hover_info.setStyleSheet("color: #94a3b8; font-size: 8.5pt; font-family: monospace;")
        top_bar.addWidget(self.lbl_hover_info)

        main_layout.addWidget(top_bar_widget)

        # 2. Main Content Splitter: Canvas (Left) + Sidebar (Right)
        self.splitter = QSplitter(Qt.Horizontal)

        # Left Frame: Interactive Canvas
        self.canvas = ActionCanvasView(self)
        self.canvas.sig_pixel_hovered.connect(self._on_pixel_hovered)
        self.canvas.sig_action_selected.connect(self._on_canvas_action_selected)
        self.canvas.sig_action_modified.connect(self._on_canvas_action_modified)
        self.canvas.sig_canvas_clicked.connect(self._on_canvas_clicked_for_recording)
        self.splitter.addWidget(self.canvas)

        # Right Frame: Directional Nudge Pad (방향키만) + Action Sequence Table (길게 표시)
        sidebar = QWidget()
        sidebar.setMinimumWidth(320)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(4, 0, 0, 0)
        side_layout.setSpacing(6)

        # Compact 1px Directional Nudge Pad (돋보기, 색상정보 제거하고 방향키만 컴팩트하게 배치)
        nudge_frame = QFrame()
        nudge_frame.setStyleSheet("""
            QFrame {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 4px;
            }
            QPushButton {
                background-color: #334155;
                color: #f8fafc;
                border: 1px solid #475569;
                border-radius: 4px;
                font-weight: bold;
                font-size: 9.5pt;
            }
            QPushButton:hover {
                background-color: #475569;
                border-color: #38bdf8;
            }
            QPushButton:pressed {
                background-color: #2563eb;
            }
        """)
        nudge_layout = QVBoxLayout(nudge_frame)
        nudge_layout.setContentsMargins(4, 4, 4, 4)
        nudge_layout.setSpacing(2)

        lbl_nudge_title = QLabel("🎯 1픽셀 정밀 미세조정 (방향키)")
        lbl_nudge_title.setStyleSheet("font-size: 8.5pt; font-weight: bold; color: #94a3b8;")
        lbl_nudge_title.setAlignment(Qt.AlignCenter)
        nudge_layout.addWidget(lbl_nudge_title)

        dpad_row = QHBoxLayout()
        dpad_row.setSpacing(4)
        dpad_row.setAlignment(Qt.AlignCenter)

        btn_up = QPushButton("▲")
        btn_up.setFixedSize(38, 26)
        btn_up.setToolTip("선택 액션 좌표 위로 1px 이동")
        btn_up.clicked.connect(lambda: self._on_nudge_action(0, -1))

        btn_left = QPushButton("◀")
        btn_left.setFixedSize(38, 26)
        btn_left.setToolTip("선택 액션 좌표 왼쪽으로 1px 이동")
        btn_left.clicked.connect(lambda: self._on_nudge_action(-1, 0))

        btn_down = QPushButton("▼")
        btn_down.setFixedSize(38, 26)
        btn_down.setToolTip("선택 액션 좌표 아래로 1px 이동")
        btn_down.clicked.connect(lambda: self._on_nudge_action(0, 1))

        btn_right = QPushButton("▶")
        btn_right.setFixedSize(38, 26)
        btn_right.setToolTip("선택 액션 좌표 오른쪽으로 1px 이동")
        btn_right.clicked.connect(lambda: self._on_nudge_action(1, 0))

        dpad_row.addWidget(btn_left)
        dpad_row.addWidget(btn_up)
        dpad_row.addWidget(btn_down)
        dpad_row.addWidget(btn_right)
        nudge_layout.addLayout(dpad_row)

        side_layout.addWidget(nudge_frame)

        # Action Sequence Group ("액션 시퀀스 리스트가 길게 표시됨")
        grp_actions = QGroupBox("✋ 액션 시퀀스 목록")
        grp_layout = QVBoxLayout(grp_actions)
        grp_layout.setContentsMargins(4, 8, 4, 4)
        grp_layout.setSpacing(4)

        # Quick Add & Image Recording Bar
        act_add_bar = QHBoxLayout()
        act_add_bar.setSpacing(4)

        btn_add_click = QPushButton("🖱️+클릭")
        btn_add_click.clicked.connect(lambda: self._on_add_quick_action("mouse_click"))
        act_add_bar.addWidget(btn_add_click)

        btn_add_drag = QPushButton("↔️+드래그")
        btn_add_drag.clicked.connect(lambda: self._on_add_quick_action("mouse_drag"))
        act_add_bar.addWidget(btn_add_drag)

        btn_add_delay = QPushButton("⏳+대기")
        btn_add_delay.clicked.connect(lambda: self._on_add_quick_action("delay"))
        act_add_bar.addWidget(btn_add_delay)

        act_add_bar.addSpacing(4)

        self.btn_record = QPushButton("⏺️ 조작 녹화")
        self.btn_record.setStyleSheet("color: #dc2626; font-weight: bold;")
        self.btn_record.setToolTip("레퍼런스 이미지 상에서 마우스를 직접 클릭하여 좌표 및 클릭 사이 대기 시간을 실시간 녹화합니다. (타겟 창 불필요)")
        self.btn_record.clicked.connect(self._toggle_image_recording)
        act_add_bar.addWidget(self.btn_record)

        grp_layout.addLayout(act_add_bar)

        # Table of Actions (Taking all flexible vertical height!)
        self.tbl_actions = QTableWidget()
        self.tbl_actions.setColumnCount(5)
        self.tbl_actions.setHorizontalHeaderLabels(["#", "유형", "좌표 / 내용", "대기", "삭제"])
        self.tbl_actions.verticalHeader().setVisible(False)
        self.tbl_actions.verticalHeader().setDefaultSectionSize(26)
        self.tbl_actions.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl_actions.itemSelectionChanged.connect(self._on_table_row_selected)
        self.tbl_actions.cellDoubleClicked.connect(lambda r, c: self._on_edit_selected_action())

        hdr = self.tbl_actions.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Fixed)
        self.tbl_actions.setColumnWidth(0, 28)
        hdr.setSectionResizeMode(1, QHeaderView.Fixed)
        self.tbl_actions.setColumnWidth(1, 68)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.Fixed)
        self.tbl_actions.setColumnWidth(3, 48)
        hdr.setSectionResizeMode(4, QHeaderView.Fixed)
        self.tbl_actions.setColumnWidth(4, 28)

        grp_layout.addWidget(self.tbl_actions, 1)

        # Table buttons: Delete, Up, Down
        btn_ctrl_row = QHBoxLayout()
        btn_ctrl_row.setSpacing(4)

        btn_edit = QPushButton("✏️ 수정")
        btn_edit.clicked.connect(self._on_edit_selected_action)
        btn_ctrl_row.addWidget(btn_edit)

        btn_del = QPushButton("🗑️ 삭제")
        btn_del.clicked.connect(self._on_delete_action)
        btn_ctrl_row.addWidget(btn_del)

        btn_up_act = QPushButton("⬆️ 위로")
        btn_up_act.clicked.connect(self._on_move_up)
        btn_ctrl_row.addWidget(btn_up_act)

        btn_down_act = QPushButton("⬇️ 아래로")
        btn_down_act.clicked.connect(self._on_move_down)
        btn_ctrl_row.addWidget(btn_down_act)

        grp_layout.addLayout(btn_ctrl_row)

        # Test execution row (Image simulation with virtual cursor)
        test_row = QHBoxLayout()
        test_row.setSpacing(4)

        self.btn_test_single = QPushButton("⚡ 선택 액션 테스트")
        self.btn_test_single.setStyleSheet("color: #2563eb; font-weight: bold;")
        self.btn_test_single.clicked.connect(self._on_test_single_action)
        test_row.addWidget(self.btn_test_single)

        self.btn_test_all = QPushButton("▶ 전체 시퀀스 테스트")
        self.btn_test_all.setStyleSheet("color: #16a34a; font-weight: bold;")
        self.btn_test_all.setToolTip("이미지 상에서 가상 커서가 순차적으로 액션을 시뮬레이션 테스트합니다.")
        self.btn_test_all.clicked.connect(self._toggle_full_sequence_test)
        test_row.addWidget(self.btn_test_all)

        grp_layout.addLayout(test_row)
        side_layout.addWidget(grp_actions, 1)

        self.splitter.addWidget(sidebar)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([940, 320])
        main_layout.addWidget(self.splitter, 1)

        # 3. Bottom Action Bar: Instructions & Save / Cancel
        bottom_bar_widget = QWidget()
        bottom_bar_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        bottom_bar = QHBoxLayout(bottom_bar_widget)
        bottom_bar.setContentsMargins(0, 0, 0, 0)

        self.lbl_guide = QLabel("💡 캔버스 좌클릭: 선택된 액션 좌표 설정 | 휠: 확대/축소 | 우클릭 드래그: 화면 이동 | 상단 방향키: 1px 미세조정")
        self.lbl_guide.setStyleSheet("color: #64748b; font-size: 8.5pt;")
        bottom_bar.addWidget(self.lbl_guide)

        bottom_bar.addStretch()

        btn_cancel = QPushButton("취소")
        btn_cancel.clicked.connect(self.reject)
        bottom_bar.addWidget(btn_cancel)

        btn_save = QPushButton("💾 액션 시퀀스 저장")
        btn_save.setStyleSheet("background-color: #1b5e20; color: white; font-weight: bold; padding: 6px 18px;")
        btn_save.clicked.connect(self.accept)
        bottom_bar.addWidget(btn_save)

        main_layout.addWidget(bottom_bar_widget)

    def _load_initial_image(self, image_path: Optional[str]):
        loaded = False
        if image_path and os.path.exists(image_path):
            try:
                self.canvas.load_image_from_path(image_path)
                loaded = True
            except Exception:
                pass

        if not loaded and self.target_hwnd:
            loaded = self._capture_target_window(silent=True)

        if not loaded:
            # Create dummy canvas for testing without target window
            w = getattr(self.project, "target_client_width", 0) or 1600
            h = getattr(self.project, "target_client_height", 0) or 900
            dummy_qimg = create_dummy_canvas_qimage(w, h)
            self.canvas.set_qimage(dummy_qimg)
            self.canvas.set_target_resolution(w, h)

    def showEvent(self, event):
        super().showEvent(event)
        self.splitter.setSizes([940, 320])
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

    # Image loading handlers
    def _browse_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "레퍼런스 이미지 열기", "", "이미지 파일 (*.png *.jpg *.jpeg *.bmp)"
        )
        if path and os.path.exists(path):
            self.current_image_path = path
            self.canvas.load_image_from_path(path)

    def _open_gallery(self):
        from ui.reference_gallery_dialog import ReferenceGalleryDialog
        dlg = ReferenceGalleryDialog(self.project, target_hwnd=self.target_hwnd, picker_mode=True, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            sel_path = dlg.get_selected_image_path()
            if sel_path and os.path.exists(sel_path):
                self.current_image_path = sel_path
                self.canvas.load_image_from_path(sel_path)

    def _capture_target_window(self, silent: bool = True):
        if not self.target_hwnd:
            if not silent:
                self.lbl_guide.setText("⚠️ 타겟 게임 창이 선택되어 있지 않습니다.")
            return

        pil_img = ScreenCapture.capture_client_area(self.target_hwnd)
        if pil_img:
            save_dir = os.path.join(os.path.expanduser("~"), ".fgoa_refs")
            os.makedirs(save_dir, exist_ok=True)
            ref_path = os.path.join(save_dir, "capture_action_picker.png")
            try:
                pil_img.save(ref_path)
                self.current_image_path = ref_path
            except Exception:
                pass
            self.canvas.set_pil_image(pil_img)
            if not silent:
                self.lbl_guide.setText("📸 타겟 게임 창의 화면을 새로 캡처하여 배경에 로드했습니다.")
        elif not silent:
            self.lbl_guide.setText("⚠️ 타겟 창의 클라이언트 영역을 캡처할 수 없습니다.")

    def _paste_clipboard(self):
        clipboard = QApplication.clipboard()
        pix = clipboard.pixmap()
        if pix.isNull():
            self.lbl_guide.setText("⚠️ 클립보드에 복사된 이미지가 없습니다.")
            return

        save_dir = os.path.join(os.path.expanduser("~"), ".fgoa_refs")
        os.makedirs(save_dir, exist_ok=True)
        ref_path = os.path.join(save_dir, "clip_action_picker.png")
        pix.save(ref_path, "PNG")
        self.current_image_path = ref_path
        self.canvas.load_image_from_path(ref_path)
        self.lbl_guide.setText("📋 클립보드 이미지를 배경으로 로드했습니다.")

    # Canvas Interaction Callbacks
    def _on_pixel_hovered(self, lx: int, ly: int):
        self.lbl_hover_info.setText(f"커서: ({lx}, {ly})")

    def _on_nudge_action(self, dx: int, dy: int):
        self.canvas.nudge_selected_action(dx, dy)
        self._sync_selected_row_data()

    def _on_canvas_action_selected(self, index: int):
        self.selected_action_index = index
        self.tbl_actions.blockSignals(True)
        self.tbl_actions.selectRow(index)
        self.tbl_actions.blockSignals(False)

    def _on_canvas_action_modified(self, index: int):
        self._sync_selected_row_data()

    # Image-based Operation Recording ("타겟 앱이 지정되지 않아도 레퍼런스 이미지에서 조작 녹화")
    def _toggle_image_recording(self):
        if not self.is_recording_mode:
            # Start Recording on Image
            self.is_recording_mode = True
            self._record_last_click_time = time.time()
            self.btn_record.setText("⏹️ 녹화 완료")
            self.btn_record.setStyleSheet("background-color: #dc2626; color: white; font-weight: bold;")
            self.lbl_guide.setText("🔴 [조작 녹화 중] 마우스로 클릭하거나 드래그하세요. 클릭/드래그 위치 및 대기 시간이 순차 기록됩니다. 완료 시 [녹화 완료]를 누르세요.")
            self.canvas.setCursor(Qt.PointingHandCursor)
        else:
            # Stop Recording on Image
            self.is_recording_mode = False
            self.btn_record.setText("⏺️ 조작 녹화")
            self.btn_record.setStyleSheet("color: #dc2626; font-weight: bold;")
            self.lbl_guide.setText(f"✅ 조작 녹화 완료: 총 {len(self.actions)}개 액션이 시퀀스에 등록되었습니다.")
            self.canvas.setCursor(Qt.CrossCursor)

    def _on_canvas_action_recorded(self, start_x: int, start_y: int, end_x: int, end_y: int, dist: float, duration: float):
        if not self.is_recording_mode:
            return

        now = time.time()
        # If there are existing actions, insert delay action with elapsed time
        if self.actions:
            start_t = (now - duration) if dist > 15 else now
            elapsed = start_t - self._record_last_click_time
            if elapsed >= 0.05:
                delay_sec = round(max(0.05, min(elapsed, 60.0)), 2)
                self.actions.append(Action(action_type="delay", delay_seconds=delay_sec))

        if dist > 15:
            dur_ms = max(100, min(int(duration * 1000), 10000))
            act = Action(
                action_type="mouse_drag",
                x=max(0, start_x),
                y=max(0, start_y),
                end_x=max(0, end_x),
                end_y=max(0, end_y),
                drag_duration_ms=dur_ms
            )
            self.lbl_guide.setText(f"🔴 [녹화 중] 드래그 #{len(self.actions) + 1} 등록: ({act.x}, {act.y}) → ({act.end_x}, {act.end_y}) [{dur_ms}ms]")
        else:
            act = Action(
                action_type="mouse_click",
                x=max(0, start_x),
                y=max(0, start_y),
                delay_seconds=0.2
            )
            self.lbl_guide.setText(f"🔴 [녹화 중] 클릭 #{len(self.actions) + 1} 등록: ({act.x}, {act.y})")

        self.actions.append(act)
        self._record_last_click_time = now

        self.selected_action_index = len(self.actions) - 1
        self._refresh_actions_table()
        self.canvas.update()

    def _on_canvas_clicked_for_recording(self, lx: int, ly: int):
        self._on_canvas_action_recorded(lx, ly, lx, ly, 0.0, 0.1)

    # Table Sync & Manipulation
    def _refresh_actions_table(self):
        self.tbl_actions.blockSignals(True)
        self.tbl_actions.setRowCount(len(self.actions))

        for row, act in enumerate(self.actions):
            # #
            item_num = QTableWidgetItem(str(row + 1))
            item_num.setTextAlignment(Qt.AlignCenter)
            self.tbl_actions.setItem(row, 0, item_num)

            # Type
            type_names = {
                "mouse_click": "클릭",
                "mouse_drag": "드래그",
                "key_press": "키입력",
                "text_type": "텍스트",
                "delay": "대기",
                "sound_beep": "비프음",
                "log_message": "로그"
            }
            item_type = QTableWidgetItem(type_names.get(act.action_type, act.action_type))
            item_type.setTextAlignment(Qt.AlignCenter)
            self.tbl_actions.setItem(row, 1, item_type)

            # Detail / Coordinates
            summary = act.get_summary()
            item_sum = QTableWidgetItem(summary)
            self.tbl_actions.setItem(row, 2, item_sum)

            # Delay
            del_str = f"{act.delay_seconds:.1f}s" if act.delay_seconds > 0 else "-"
            item_del = QTableWidgetItem(del_str)
            item_del.setTextAlignment(Qt.AlignCenter)
            self.tbl_actions.setItem(row, 3, item_del)

            # Delete button
            btn_del = QPushButton("✕")
            btn_del.setStyleSheet("color: #ef4444; font-weight: bold; border: none; padding: 0;")
            btn_del.setToolTip("이 액션 삭제")
            r_idx = row
            btn_del.clicked.connect(lambda checked, r=r_idx: self._delete_row(r))
            self.tbl_actions.setCellWidget(row, 4, btn_del)

        self.tbl_actions.blockSignals(False)

        if 0 <= self.selected_action_index < len(self.actions):
            self.tbl_actions.selectRow(self.selected_action_index)

        self.canvas.set_actions(self.actions, self.selected_action_index)

    def _sync_selected_row_data(self):
        row = self.selected_action_index
        if 0 <= row < len(self.actions):
            act = self.actions[row]
            item_sum = self.tbl_actions.item(row, 2)
            if item_sum:
                item_sum.setText(act.get_summary())

    def _on_table_row_selected(self):
        rows = self.tbl_actions.selectionModel().selectedRows()
        if rows:
            row = rows[0].row()
            self.selected_action_index = row
            self.canvas.set_selected_action_index(row)

    def _on_add_quick_action(self, action_type: str):
        if action_type == "mouse_click":
            center = self.canvas.screen_to_client_pos(self.canvas.width() / 2, self.canvas.height() / 2)
            act = Action(action_type="mouse_click", x=max(0, int(center.x())), y=max(0, int(center.y())))
        elif action_type == "mouse_drag":
            center = self.canvas.screen_to_client_pos(self.canvas.width() / 2, self.canvas.height() / 2)
            cx, cy = max(0, int(center.x())), max(0, int(center.y()))
            act = Action(action_type="mouse_drag", x=cx, y=cy, end_x=cx + 100, end_y=cy + 100)
        elif action_type == "delay":
            act = Action(action_type="delay", delay_seconds=1.0)
        else:
            act = Action(action_type=action_type)

        self.actions.append(act)
        self.selected_action_index = len(self.actions) - 1
        self._refresh_actions_table()

    def _on_edit_selected_action(self):
        if 0 <= self.selected_action_index < len(self.actions):
            from ui.action_editor_dialog import SingleActionDialog
            act = self.actions[self.selected_action_index]
            dlg = SingleActionDialog(
                action=act,
                target_hwnd=self.target_hwnd,
                reference_image_path=self.current_image_path,
                parent=self
            )
            if dlg.exec_() == SingleActionDialog.Accepted:
                self.actions[self.selected_action_index] = dlg.get_action()
                self._refresh_actions_table()

    def _delete_row(self, row: int):
        if 0 <= row < len(self.actions):
            del self.actions[row]
            self.selected_action_index = min(self.selected_action_index, len(self.actions) - 1)
            self._refresh_actions_table()

    def _on_delete_action(self):
        if 0 <= self.selected_action_index < len(self.actions):
            self._delete_row(self.selected_action_index)

    def _on_move_up(self):
        r = self.selected_action_index
        if r > 0:
            self.actions[r - 1], self.actions[r] = self.actions[r], self.actions[r - 1]
            self.selected_action_index = r - 1
            self._refresh_actions_table()

    def _on_move_down(self):
        r = self.selected_action_index
        if 0 <= r < len(self.actions) - 1:
            self.actions[r + 1], self.actions[r] = self.actions[r], self.actions[r + 1]
            self.selected_action_index = r + 1
            self._refresh_actions_table()

    # Visual Simulation & Testing on Image ("가상의 커서를 그려줄것 / 완료 팝업 띄우지 말것")
    def _on_test_single_action(self):
        if not (0 <= self.selected_action_index < len(self.actions)):
            self.lbl_guide.setText("⚠️ 테스트할 액션을 목록에서 선택해주세요.")
            return

        act = self.actions[self.selected_action_index]
        use_anti_ban = getattr(self.project, "anti_ban_enabled", False)
        min_del = getattr(self.project, "anti_ban_min_delay", 0.15)
        max_del = getattr(self.project, "anti_ban_max_delay", 1.0)
        act_anti_ban = getattr(act, "anti_ban", None)
        should_anti_ban = act_anti_ban if act_anti_ban is not None else use_anti_ban

        jitter = round(random.uniform(min_del, max_del), 3) if should_anti_ban else 0.0
        orig_t = act.delay_seconds if act.action_type == "delay" else getattr(act, "delay_seconds", 0.0)
        ab_t = round(orig_t + jitter, 2)
        sleep_total = ab_t if should_anti_ban else orig_t

        if act.action_type == "delay":
            act_msg = f"{sleep_total:.1f}초 (원본{orig_t:.2f}초) 대기"
        else:
            extra_str = f" (안티밴 +{jitter:.2f}초)" if should_anti_ban and jitter > 0 else ""
            act_msg = f"{act.get_summary()}{extra_str}"

        # 1. Visualize on Canvas using Virtual Cursor
        if act.action_type in ("mouse_click", "mouse_drag"):
            self.canvas.set_virtual_cursor((act.x, act.y), visible=True, clicking=True, label=f"#{self.selected_action_index + 1} {act.get_summary()}")
            QApplication.processEvents()
            time.sleep(0.2)
            self.canvas.set_virtual_cursor(None, visible=False)

        # 2. Execute on live window if bound
        if self.target_hwnd:
            try:
                InputController.execute_action(
                    act, self.target_hwnd,
                    apply_anti_ban=use_anti_ban,
                    min_delay=min_del,
                    max_delay=max_del,
                    precomputed_jitter=jitter
                )
            except Exception:
                pass

        # Update guide status without popup!
        self.lbl_guide.setText(f"✅ 선택 액션 테스트 완료: {act_msg}")

    def _toggle_full_sequence_test(self):
        if self._is_testing_sequence:
            # Stop sequence test
            self._is_testing_sequence = False
            self.btn_test_all.setText("▶ 전체 시퀀스 테스트")
            self.btn_test_all.setStyleSheet("color: #16a34a; font-weight: bold;")
            self.canvas.set_virtual_cursor(None, visible=False)
            self.lbl_guide.setText("⏹️ 시퀀스 테스트가 사용자에 의해 중지되었습니다.")
            return

        if not self.actions:
            self.lbl_guide.setText("⚠️ 시퀀스에 실행할 액션이 없습니다.")
            return

        self._is_testing_sequence = True
        self.btn_test_all.setText("⏹️ 테스트 중지")
        self.btn_test_all.setStyleSheet("background-color: #dc2626; color: white; font-weight: bold;")

        total = len(self.actions)
        use_anti_ban = getattr(self.project, "anti_ban_enabled", False)
        min_del = getattr(self.project, "anti_ban_min_delay", 0.15)
        max_del = getattr(self.project, "anti_ban_max_delay", 1.0)

        try:
            for idx, act in enumerate(self.actions):
                if not self._is_testing_sequence:
                    break

                self.tbl_actions.selectRow(idx)
                self.selected_action_index = idx
                QApplication.processEvents()

                act_anti_ban = getattr(act, "anti_ban", None)
                should_anti_ban = act_anti_ban if act_anti_ban is not None else use_anti_ban
                jitter = round(random.uniform(min_del, max_del), 3) if should_anti_ban else 0.0
                orig_t = act.delay_seconds if act.action_type == "delay" else getattr(act, "delay_seconds", 0.0)
                ab_t = round(orig_t + jitter, 2)
                sleep_total = ab_t if should_anti_ban else orig_t

                if act.action_type == "delay":
                    act_msg = f"{sleep_total:.1f}초 (원본{orig_t:.2f}초) 대기"
                else:
                    extra_str = f" (안티밴 +{jitter:.2f}초)" if should_anti_ban and jitter > 0 else ""
                    act_msg = f"{act.get_summary()}{extra_str}"

                self.lbl_guide.setText(f"▶ [{idx + 1}/{total}] 테스트 중: {act_msg}")

                # Image Canvas Animation with Virtual Cursor
                if act.action_type == "mouse_click":
                    # Move to position
                    self.canvas.set_virtual_cursor((act.x, act.y), visible=True, clicking=False, label=f"#{idx + 1} 이동 ({act.x}, {act.y})")
                    QApplication.processEvents()
                    time.sleep(0.08)

                    # Click effect
                    self.canvas.set_virtual_cursor((act.x, act.y), visible=True, clicking=True, label=f"#{idx + 1} 좌클릭!")
                    QApplication.processEvents()
                    time.sleep(0.12)

                    if self.target_hwnd:
                        InputController.execute_action(act, self.target_hwnd, apply_anti_ban=use_anti_ban, precomputed_jitter=jitter)

                elif act.action_type == "mouse_drag":
                    # Interpolated drag animation
                    steps = 6
                    for s in range(steps + 1):
                        if not self._is_testing_sequence:
                            break
                        interp_x = act.x + (act.end_x - act.x) * (s / steps)
                        interp_y = act.y + (act.end_y - act.y) * (s / steps)
                        self.canvas.set_virtual_cursor((interp_x, interp_y), visible=True, clicking=True, label=f"#{idx + 1} 드래그 중...")
                        QApplication.processEvents()
                        time.sleep(0.04)

                    if self.target_hwnd:
                        InputController.execute_action(act, self.target_hwnd, apply_anti_ban=use_anti_ban, precomputed_jitter=jitter)

                elif act.action_type == "delay":
                    sleep_total = ab_t if should_anti_ban else orig_t
                    rem = sleep_total
                    cur_pos = (act.x, act.y) if hasattr(act, "x") and act.x > 0 else (100, 100)
                    while rem > 0 and self._is_testing_sequence:
                        step_s = min(0.08, rem)
                        time.sleep(step_s)
                        rem -= step_s
                        self.canvas.set_virtual_cursor(cur_pos, visible=True, clicking=False, label=f"⏳ #{idx + 1} {rem:.1f}s 대기 중...")
                        QApplication.processEvents()
                else:
                    if self.target_hwnd:
                        InputController.execute_action(act, self.target_hwnd, apply_anti_ban=use_anti_ban, precomputed_jitter=jitter)

                time.sleep(0.04)
                QApplication.processEvents()

            if self._is_testing_sequence:
                self.lbl_guide.setText(f"✅ 전체 액션 시퀀스({total}개) 테스트 실행 완료")
        finally:
            self._is_testing_sequence = False
            self.btn_test_all.setText("▶ 전체 시퀀스 테스트")
            self.btn_test_all.setStyleSheet("color: #16a34a; font-weight: bold;")
            self.canvas.set_virtual_cursor(None, visible=False)

    # Results extraction
    def get_coordinates(self) -> Tuple[int, int, int, int]:
        """Returns (x, y, end_x, end_y) of currently selected or first action."""
        if 0 <= self.selected_action_index < len(self.actions):
            act = self.actions[self.selected_action_index]
            return act.x, act.y, act.end_x, act.end_y
        elif self.actions:
            act = self.actions[0]
            return act.x, act.y, act.end_x, act.end_y
        return 0, 0, 0, 0

    def get_actions(self) -> List[Action]:
        """Returns edited actions list."""
        return self.actions

    def get_action(self) -> Optional[Action]:
        """Returns currently selected Action instance."""
        if 0 <= self.selected_action_index < len(self.actions):
            return self.actions[self.selected_action_index]
        return self.actions[0] if self.actions else None
