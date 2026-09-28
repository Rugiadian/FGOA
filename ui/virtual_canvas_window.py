"""
Virtual Canvas Target Window for FGOA.
Provides a live test window with coordinates grid and visual click feedback
when a target application window is not selected.
"""
import time
from typing import Optional, List, Dict, Any
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt5.QtGui import QPainter, QImage, QColor, QPen, QBrush, QFont, QPaintEvent, QMouseEvent
from PyQt5.QtCore import Qt, QTimer, QRect, QPoint, pyqtSignal

from core.dummy_canvas import create_dummy_canvas_qimage


class VirtualCanvasWindow(QWidget):
    """
    Dedicated virtual canvas window that can act as a live Win32 HWND target for FGOA automation.
    Displays coordinate grid, target dummy elements, and renders ripple animations on mouse click.
    """
    sig_closed = pyqtSignal()
    sig_clicked = pyqtSignal(int, int)

    def __init__(self, width: int = 1600, height: int = 900, parent: Optional[QWidget] = None):
        super().__init__(parent, Qt.Window)
        self.canvas_width = max(400, int(width) if width else 1600)
        self.canvas_height = max(300, int(height) if height else 900)
        self._ripples: List[Dict[str, Any]] = []

        self.setWindowTitle(f"[FGOA 가상 캔버스] {self.canvas_width}x{self.canvas_height} (가상 타깃 윈도우)")
        self.resize(self.canvas_width, self.canvas_height)

        # Pre-render dummy canvas image
        self.dummy_image: QImage = create_dummy_canvas_qimage(self.canvas_width, self.canvas_height)

        # Ripple animation timer (60 FPS)
        self.ripple_timer = QTimer(self)
        self.ripple_timer.setInterval(16)
        self.ripple_timer.timeout.connect(self._update_ripples)

        self.setAttribute(Qt.WA_OpaquePaintEvent, True)

    def set_target_resolution(self, width: int, height: int):
        """Update virtual resolution and regenerate dummy canvas image."""
        w = max(400, int(width) if width else 1600)
        h = max(300, int(height) if height else 900)
        if w != self.canvas_width or h != self.canvas_height:
            self.canvas_width = w
            self.canvas_height = h
            self.dummy_image = create_dummy_canvas_qimage(w, h)
            self.resize(w, h)
            self.setWindowTitle(f"[FGOA 가상 캔버스] {self.canvas_width}x{self.canvas_height} (가상 타깃 윈도우)")
            self.update()

    def trigger_click_effect(self, x: int, y: int):
        """Triggers a ripple click animation at the specified relative coordinate."""
        self._ripples.append({
            "x": x,
            "y": y,
            "radius": 5.0,
            "max_radius": 36.0,
            "alpha": 240,
            "speed": 2.2
        })
        if not self.ripple_timer.isActive():
            self.ripple_timer.start()
        self.update()

    def _update_ripples(self):
        """Advances ripple animation frames and repaints."""
        active = []
        for r in self._ripples:
            r["radius"] += r["speed"]
            r["alpha"] = max(0, int(240 * (1.0 - (r["radius"] / r["max_radius"]))))
            if r["radius"] < r["max_radius"] and r["alpha"] > 0:
                active.append(r)
        self._ripples = active
        if not self._ripples:
            self.ripple_timer.stop()
        self.update()

    def mousePressEvent(self, event: QMouseEvent):
        pos = event.pos()
        self.trigger_click_effect(pos.x(), pos.y())
        self.sig_clicked.emit(pos.x(), pos.y())
        super().mousePressEvent(event)

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        # Draw dummy canvas background
        if not self.dummy_image.isNull():
            # If window size matches canvas image size, draw directly
            if self.width() == self.canvas_width and self.height() == self.canvas_height:
                painter.drawImage(0, 0, self.dummy_image)
            else:
                painter.drawImage(self.rect(), self.dummy_image)
        else:
            painter.fillRect(self.rect(), QColor(30, 41, 59))

        # Render click ripples
        for r in self._ripples:
            alpha = r["alpha"]
            radius = r["radius"]
            cx = int(r["x"] * (self.width() / self.canvas_width)) if self.canvas_width > 0 else r["x"]
            cy = int(r["y"] * (self.height() / self.canvas_height)) if self.canvas_height > 0 else r["y"]

            # Outer ripple ring
            pen = QPen(QColor(56, 189, 248, alpha), 2.5)  # Sky blue
            painter.setPen(pen)
            painter.setBrush(QBrush(QColor(56, 189, 248, int(alpha * 0.15))))
            painter.drawEllipse(QPoint(cx, cy), int(radius), int(radius))

            # Inner bright core
            if radius < 18:
                pen_core = QPen(QColor(255, 255, 255, min(255, alpha + 30)), 2)
                painter.setPen(pen_core)
                painter.drawEllipse(QPoint(cx, cy), 3, 3)

        painter.end()

    def closeEvent(self, event):
        self.sig_closed.emit()
        super().closeEvent(event)
