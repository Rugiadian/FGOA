"""
Interactive Canvas View for FGOA Color Picker and Condition Editor.
Provides image loading, zoom/pan, target resolution boundary clipping,
and point/line placement tools.
"""
import math
from typing import List, Optional, Tuple
from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPainter, QPixmap, QImage, QColor, QPen, QBrush, QFont, QCursor, QPainterPath
from PyQt5.QtCore import Qt, QRectF, QPointF, pyqtSignal
from core.models import ColorPoint


class CanvasView(QWidget):
    """
    Interactive 2D Canvas with zoom/pan and graphical point/line overlays.
    """
    # Signals
    sig_pixel_hovered = pyqtSignal(int, int)  # (rel_x, rel_y)
    sig_point_added = pyqtSignal(int, int, int, int, int)  # (x, y, r, g, b)
    sig_line_points_added = pyqtSignal(int, int, int, int)  # (x1, y1, x2, y2)
    sig_point_selected = pyqtSignal(str)  # point_id
    sig_nudge_requested = pyqtSignal(int, int)  # (dx, dy)

    MODE_POINT = 0
    MODE_LINE = 1
    MODE_SELECT = 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        # Image & Resolution
        self.pixmap: Optional[QPixmap] = None
        self.qimage: Optional[QImage] = None
        self.target_width: int = 1280
        self.target_height: int = 720

        # Points
        self.points: List[ColorPoint] = []
        self.selected_point_id: Optional[str] = None
        self.dragging_point: Optional[ColorPoint] = None

        # View transform (Zoom & Pan)
        self.zoom: float = 1.0
        self.pan_x: float = 20.0
        self.pan_y: float = 20.0

        # Tool Mode
        self.current_mode = self.MODE_POINT

        # Interaction state
        self._is_panning = False
        self._pan_start_pos = QPointF()

        self._is_drawing_line = False
        self._line_start = QPointF()
        self._line_end = QPointF()

    def set_target_resolution(self, width: int, height: int):
        self.target_width = max(50, width)
        self.target_height = max(50, height)
        self.update()

    def load_image_from_path(self, file_path: str):
        pix = QPixmap(file_path)
        if not pix.isNull():
            self.pixmap = pix
            self.qimage = pix.toImage()
            self.fit_to_view()
            self.update()

    def set_qimage(self, qimg: QImage):
        if not qimg.isNull():
            self.qimage = qimg
            self.pixmap = QPixmap.fromImage(qimg)
            self.fit_to_view()
            self.update()

    def set_points(self, points: List[ColorPoint]):
        self.points = points
        self.update()

    def fit_to_view(self):
        """Fit target resolution or reference image completely into the visible canvas area."""
        img_w = self.pixmap.width() if self.pixmap else self.target_width
        img_h = self.pixmap.height() if self.pixmap else self.target_height

        avail_w = max(50, self.width() - 30)
        avail_h = max(50, self.height() - 30)

        if img_w <= 0 or img_h <= 0 or avail_w <= 50:
            return

        scale_x = avail_w / img_w
        scale_y = avail_h / img_h
        # Fit fully inside canvas
        best_zoom = min(scale_x, scale_y)
        self.zoom = max(0.05, best_zoom)

        # Center in canvas
        self.pan_x = max(10.0, (self.width() - img_w * self.zoom) / 2.0)
        self.pan_y = max(10.0, (self.height() - img_h * self.zoom) / 2.0)
        self.update()

    def zoom_100(self):
        """Reset view to 100% 1:1 pixel scale."""
        self.zoom = 1.0
        self.pan_x = 20.0
        self.pan_y = 20.0
        self.update()

    def reset_view(self):
        """Reset view to fit target resolution."""
        self.fit_to_view()

    # Coordinate mapping
    def client_to_screen_pos(self, cx: float, cy: float) -> QPointF:
        """Canvas logical (X, Y) to widget pixel coordinates."""
        return QPointF(self.pan_x + cx * self.zoom, self.pan_y + cy * self.zoom)

    def screen_to_client_pos(self, sx: float, sy: float) -> QPointF:
        """Widget pixel coordinates to canvas logical (X, Y)."""
        return QPointF((sx - self.pan_x) / self.zoom, (sy - self.pan_y) / self.zoom)

    def get_pixel_color_at(self, cx: int, cy: int) -> Tuple[int, int, int]:
        """Sample RGB from current image or default to dark grey."""
        if self.qimage and not self.qimage.isNull():
            if 0 <= cx < self.qimage.width() and 0 <= cy < self.qimage.height():
                col = QColor(self.qimage.pixel(cx, cy))
                return (col.red(), col.green(), col.blue())
        return (128, 128, 128)

    # Mouse Events
    def wheelEvent(self, event):
        angle = event.angleDelta().y()
        factor = 1.15 if angle > 0 else (1.0 / 1.15)
        
        # Zoom centered on mouse cursor
        mouse_pos = event.pos()
        old_logical = self.screen_to_client_pos(mouse_pos.x(), mouse_pos.y())

        new_zoom = self.zoom * factor
        if 0.1 <= new_zoom <= 20.0:
            self.zoom = new_zoom
            self.pan_x = mouse_pos.x() - old_logical.x() * self.zoom
            self.pan_y = mouse_pos.y() - old_logical.y() * self.zoom
            self.update()

    def mousePressEvent(self, event):
        # Middle click or Right click starts panning
        if event.button() in (Qt.MiddleButton, Qt.RightButton):
            self._is_panning = True
            self._pan_start_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            return

        if event.button() == Qt.LeftButton:
            logical_pos = self.screen_to_client_pos(event.x(), event.y())
            lx = int(round(logical_pos.x()))
            ly = int(round(logical_pos.y()))

            if self.current_mode == self.MODE_POINT:
                r, g, b = self.get_pixel_color_at(lx, ly)
                self.sig_point_added.emit(lx, ly, r, g, b)

            elif self.current_mode == self.MODE_LINE:
                self._is_drawing_line = True
                self._line_start = QPointF(lx, ly)
                self._line_end = QPointF(lx, ly)
                self.update()

            elif self.current_mode == self.MODE_SELECT:
                # Find clicked point
                hit_point = None
                for pt in reversed(self.points):
                    dist = math.hypot(pt.x - lx, pt.y - ly)
                    if dist <= max(8, 12 / self.zoom):
                        hit_point = pt
                        break
                if hit_point:
                    self.selected_point_id = hit_point.id
                    self.dragging_point = hit_point
                    self.sig_point_selected.emit(hit_point.id)
                else:
                    self.selected_point_id = None
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

        if self._is_drawing_line:
            self._line_end = QPointF(lx, ly)
            self.update()

        elif self.dragging_point:
            self.dragging_point.x = lx
            self.dragging_point.y = ly
            r, g, b = self.get_pixel_color_at(lx, ly)
            self.dragging_point.r = r
            self.dragging_point.g = g
            self.dragging_point.b = b
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() in (Qt.MiddleButton, Qt.RightButton):
            self._is_panning = False
            self.setCursor(Qt.ArrowCursor)

        if event.button() == Qt.LeftButton:
            if self._is_drawing_line:
                self._is_drawing_line = False
                x1, y1 = int(round(self._line_start.x())), int(round(self._line_start.y()))
                x2, y2 = int(round(self._line_end.x())), int(round(self._line_end.y()))
                self.sig_line_points_added.emit(x1, y1, x2, y2)
                self.update()

            if self.dragging_point:
                self.dragging_point = None

    # Paint Rendering
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(16, 16, 20))

        # 1. Draw Reference Image (left-top aligned at (0, 0))
        if self.pixmap and not self.pixmap.isNull():
            top_left = self.client_to_screen_pos(0, 0)
            img_w = self.pixmap.width() * self.zoom
            img_h = self.pixmap.height() * self.zoom
            painter.drawPixmap(QRectF(top_left.x(), top_left.y(), img_w, img_h), self.pixmap, QRectF(self.pixmap.rect()))
        else:
            # Draw placeholder grid inside target window rect
            tl = self.client_to_screen_pos(0, 0)
            tw = self.target_width * self.zoom
            th = self.target_height * self.zoom
            painter.fillRect(QRectF(tl.x(), tl.y(), tw, th), QColor(28, 28, 36))

        # 2. Target Window Boundary & Dimming Overlay
        # (타겟 앱 해상도보다 큰 부분은 잘리거나 딤드 처리)
        tl = self.client_to_screen_pos(0, 0)
        tw = self.target_width * self.zoom
        th = self.target_height * self.zoom
        target_screen_rect = QRectF(tl.x(), tl.y(), tw, th)

        # Dim areas outside target resolution if image is larger
        if self.pixmap and not self.pixmap.isNull():
            if self.pixmap.width() > self.target_width or self.pixmap.height() > self.target_height:
                full_rect = QRectF(tl.x(), tl.y(), self.pixmap.width() * self.zoom, self.pixmap.height() * self.zoom)
                path = QPainterPath()
                path.addRect(full_rect)
                path.addRect(target_screen_rect)
                painter.fillPath(path, QBrush(QColor(0, 0, 0, 180)))

        # Target window boundary border (Neon cyan/gold)
        pen_border = QPen(QColor(0, 220, 255), 2, Qt.DashLine)
        painter.setPen(pen_border)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(target_screen_rect)

        # Resolution label at top-left
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        painter.setPen(QColor(0, 220, 255))
        painter.drawText(int(tl.x() + 6), int(tl.y() - 6), f"타겟 앱 활성 영역: {self.target_width} x {self.target_height}")

        # 3. Draw Lines between points in the same line group
        line_groups = {}
        for pt in self.points:
            if pt.line_group_id:
                line_groups.setdefault(pt.line_group_id, []).append(pt)

        for grp_pts in line_groups.values():
            if len(grp_pts) > 1:
                painter.setPen(QPen(QColor(255, 170, 0, 180), 2, Qt.DashDotLine))
                for i in range(len(grp_pts) - 1):
                    p1 = self.client_to_screen_pos(grp_pts[i].x, grp_pts[i].y)
                    p2 = self.client_to_screen_pos(grp_pts[i+1].x, grp_pts[i+1].y)
                    painter.drawLine(p1, p2)

        # 4. Draw preview line while dragging
        if self._is_drawing_line:
            p1 = self.client_to_screen_pos(self._line_start.x(), self._line_start.y())
            p2 = self.client_to_screen_pos(self._line_end.x(), self._line_end.y())
            painter.setPen(QPen(QColor(255, 80, 80), 2, Qt.SolidLine))
            painter.drawLine(p1, p2)
            painter.setBrush(QBrush(QColor(255, 80, 80)))
            painter.drawEllipse(p1, 4, 4)
            painter.drawEllipse(p2, 4, 4)

        # 5. Draw Points / Markers
        for idx, pt in enumerate(self.points, start=1):
            s_pos = self.client_to_screen_pos(pt.x, pt.y)
            is_selected = (pt.id == self.selected_point_id)
            self._draw_point_marker(painter, s_pos, pt, idx, is_selected)

    def _draw_point_marker(self, painter: QPainter, pos: QPointF, pt: ColorPoint, index: int, is_selected: bool):
        x = pos.x()
        y = pos.y()
        radius = 8

        # Outer ring / highlight
        if is_selected:
            painter.setPen(QPen(QColor(255, 215, 0), 3))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(pos, radius + 4, radius + 4)

        # Color swatch fill
        pt_color = QColor(pt.r, pt.g, pt.b)
        painter.setBrush(QBrush(pt_color))
        painter.setPen(QPen(QColor(255, 255, 255) if not is_selected else QColor(255, 215, 0), 2))
        painter.drawEllipse(pos, radius, radius)

        # Crosshair center
        painter.setPen(QPen(QColor(0, 0, 0), 1))
        painter.drawLine(int(x - 3), int(y), int(x + 3), int(y))
        painter.drawLine(int(x), int(y - 3), int(x), int(y + 3))

        # Index label badge
        label_text = str(index)
        painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
        badge_rect = QRectF(x + 8, y - 18, 20, 16)
        painter.setBrush(QBrush(QColor(30, 30, 40, 220)))
        painter.setPen(QPen(QColor(180, 180, 200), 1))
        painter.drawRoundedRect(badge_rect, 3, 3)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(badge_rect, Qt.AlignCenter, label_text)

    def keyPressEvent(self, event):
        step = 5 if (event.modifiers() & Qt.ShiftModifier) else 1
        if event.key() == Qt.Key_Left:
            self.sig_nudge_requested.emit(-step, 0)
            event.accept()
        elif event.key() == Qt.Key_Right:
            self.sig_nudge_requested.emit(step, 0)
            event.accept()
        elif event.key() == Qt.Key_Up:
            self.sig_nudge_requested.emit(0, -step)
            event.accept()
        elif event.key() == Qt.Key_Down:
            self.sig_nudge_requested.emit(0, step)
            event.accept()
        else:
            super().keyPressEvent(event)
