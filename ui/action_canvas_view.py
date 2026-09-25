"""
Action Canvas View for FGOA.
(액션 시퀀스 2D 캔버스 뷰 위젯)

Interactive 2D Canvas for displaying reference images,
navigating with zoom/pan, placing action waypoints,
drawing a virtual cursor for simulation, and recording clicks/drags.
"""
import os
import math
import time
from typing import Optional, Tuple, List, Dict, Any
from PIL import Image

from PyQt5.QtWidgets import QWidget, QApplication, QSizePolicy
from PyQt5.QtCore import Qt, QPoint, QPointF, QRectF, pyqtSignal, QTimer
from PyQt5.QtGui import (
    QPixmap, QPainter, QPen, QColor, QBrush, QCursor, QFont,
    QImage, QPolygonF
)

from core.models import Action
from ui.qt_image_utils import pil_to_qpixmap


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
