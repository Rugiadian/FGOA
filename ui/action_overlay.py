"""
Action Sequence Visualizer Overlay for FGOA.
Displays a transparent, click-through overlay on top of the target application window,
visualizing the currently executing action (clicks, drags, keys, delays) with dotted
rectangles, lines, and informative badges in real-time.
"""
import math
from typing import Optional
from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPolygonF
from PyQt5.QtCore import Qt, QRect, QPointF, QTimer

from core.models import Action
from core.window_manager import WindowManager


class ActionOverlayWindow(QWidget):
    """
    Transparent, click-through overlay window positioned over the target game/app window.
    Draws dotted boxes and paths where actions are operating on screen.
    """

    def __init__(self, target_hwnd: int = 0, parent=None):
        super().__init__(parent, Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        self.target_hwnd = target_hwnd
        self.current_action: Optional[Action] = None
        self.action_index: int = 1
        self.total_actions: int = 1
        self.scenario_name: str = ""
        self.is_overlay_enabled: bool = True

        # Clear timer to fade/hide markers after action finishes
        self._clear_timer = QTimer(self)
        self._clear_timer.setSingleShot(True)
        self._clear_timer.timeout.connect(self.clear_action)

    def set_target_hwnd(self, hwnd: int):
        self.target_hwnd = hwnd
        self.update_geometry()

    def update_geometry(self):
        """Align overlay window geometry with the target window's client area."""
        if not self.target_hwnd:
            return
        win_info = WindowManager.get_window_info(self.target_hwnd)
        if win_info and win_info.client_width > 50 and win_info.client_height > 50:
            self.setGeometry(
                win_info.screen_x,
                win_info.screen_y,
                win_info.client_width,
                win_info.client_height
            )

    def show_action(self, action: Action, index: int = 1, total: int = 1, scenario_name: str = ""):
        """Display dotted indicators for the given executing action."""
        if not self.is_overlay_enabled:
            return

        self._clear_timer.stop()
        self.current_action = action
        self.action_index = index
        self.total_actions = total
        self.scenario_name = scenario_name

        self.update_geometry()
        if not self.isVisible():
            self.show()
        self.update()

    def hide_action_delayed(self, delay_ms: int = 600):
        """Schedule clearing the current action visualization."""
        self._clear_timer.start(delay_ms)

    def clear_action(self):
        """Clear action display and hide overlay."""
        self.current_action = None
        self.update()
        self.hide()

    def paintEvent(self, event):
        if not self.current_action or not self.is_overlay_enabled:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        act = self.current_action
        idx = self.action_index
        tot = self.total_actions

        if act.action_type == "mouse_click":
            self._draw_click_visualization(painter, act.x, act.y, idx, tot, act.get_summary())
        elif act.action_type == "mouse_drag":
            self._draw_drag_visualization(
                painter, act.x, act.y, act.end_x, act.end_y,
                act.drag_duration_ms, idx, tot
            )
        elif act.action_type in ("key_press", "text_type", "delay"):
            self._draw_banner_visualization(painter, act, idx, tot)

    def _draw_click_visualization(self, painter: QPainter, x: int, y: int, idx: int, tot: int, summary: str):
        # 1. Outer animated-style dotted bounding box (Cyan)
        box_size = 46
        rect = QRect(x - box_size // 2, y - box_size // 2, box_size, box_size)

        dash_pen = QPen(QColor(6, 182, 212, 240), 2.5, Qt.DashLine)
        dash_pen.setDashPattern([4, 3])
        painter.setPen(dash_pen)
        painter.setBrush(QBrush(QColor(6, 182, 212, 40)))
        painter.drawRect(rect)

        # 2. Concentric ring
        ring_pen = QPen(QColor(255, 255, 255, 220), 1.5, Qt.DotLine)
        ring_pen.setDashPattern([2, 3])
        painter.setPen(ring_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(x, y), 14, 14)

        # 3. Center precision crosshair
        cross_pen = QPen(QColor(239, 68, 68, 240), 2.0, Qt.SolidLine)
        painter.setPen(cross_pen)
        painter.drawLine(x - 7, y, x + 7, y)
        painter.drawLine(x, y - 7, x, y + 7)

        # 4. Floating Badge with step number & coords
        badge_text = f"#{idx}/{tot} 클릭 ({x}, {y})"
        self._draw_floating_badge(painter, x + 28, y - 12, badge_text, QColor(6, 182, 212))

    def _draw_drag_visualization(self, painter: QPainter, x1: int, y1: int, x2: int, y2: int,
                                 duration_ms: int, idx: int, tot: int):
        # 1. Start point dotted box (Emerald)
        start_rect = QRect(x1 - 18, y1 - 18, 36, 36)
        start_pen = QPen(QColor(16, 185, 129, 230), 2.0, Qt.DashLine)
        start_pen.setDashPattern([3, 2])
        painter.setPen(start_pen)
        painter.setBrush(QBrush(QColor(16, 185, 129, 45)))
        painter.drawRect(start_rect)

        # 2. End point dotted box (Amber/Orange)
        end_rect = QRect(x2 - 18, y2 - 18, 36, 36)
        end_pen = QPen(QColor(245, 158, 11, 240), 2.5, Qt.DashLine)
        end_pen.setDashPattern([4, 2])
        painter.setPen(end_pen)
        painter.setBrush(QBrush(QColor(245, 158, 11, 45)))
        painter.drawRect(end_rect)

        # 3. Dotted connecting line with arrow
        line_pen = QPen(QColor(245, 158, 11, 240), 2.8, Qt.DashLine)
        line_pen.setDashPattern([5, 3])
        painter.setPen(line_pen)
        painter.drawLine(x1, y1, x2, y2)

        # 4. Arrow head
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy)
        if length > 5:
            ux = dx / length
            uy = dy / length
            arrow_size = 14
            p1 = QPointF(x2 - arrow_size * ux + arrow_size * 0.5 * uy,
                         y2 - arrow_size * uy - arrow_size * 0.5 * ux)
            p2 = QPointF(x2 - arrow_size * ux - arrow_size * 0.5 * uy,
                         y2 - arrow_size * uy + arrow_size * 0.5 * ux)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(245, 158, 11, 240)))
            painter.drawPolygon(QPolygonF([QPointF(x2, y2), p1, p2]))

        # 5. Badges
        self._draw_floating_badge(painter, x1 + 22, y1 - 10, f"#{idx} 드래그 시작 ({x1}, {y1})", QColor(16, 185, 129))
        self._draw_floating_badge(painter, x2 + 22, y2 - 10, f"끝 ({x2}, {y2}) [{duration_ms}ms]", QColor(245, 158, 11))

    def _draw_banner_visualization(self, painter: QPainter, act: Action, idx: int, tot: int):
        """Top-centered floating pill banner for non-coordinate actions."""
        if act.action_type == "delay":
            text = f"⏱️ #{idx}/{tot} 대기 진행 중 ({act.delay_seconds:.1f}초)"
            accent = QColor(147, 51, 234)
        elif act.action_type == "key_press":
            text = f"⌨️ #{idx}/{tot} 키 입력: [{act.key_name}]"
            accent = QColor(59, 130, 246)
        else:
            text = f"✍️ #{idx}/{tot} 텍스트 입력: '{act.text_content}'"
            accent = QColor(59, 130, 246)

        w = 320
        h = 36
        x = (self.width() - w) // 2
        y = 20

        # Dotted border pill container
        banner_rect = QRect(x, y, w, h)
        pen = QPen(accent, 2.0, Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(15, 23, 42, 215)))
        painter.drawRoundedRect(banner_rect, 8, 8)

        # Text
        painter.setPen(QColor(255, 255, 255))
        font = QFont("Malgun Gothic", 9, QFont.Bold)
        painter.setFont(font)
        painter.drawText(banner_rect, Qt.AlignCenter, text)

    def _draw_floating_badge(self, painter: QPainter, x: int, y: int, text: str, border_color: QColor):
        """Draws a compact floating pill badge with dark background and vibrant dotted border."""
        font = QFont("Malgun Gothic", 8, QFont.Bold)
        painter.setFont(font)
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(text) + 16
        th = 22

        # Clamp inside window boundaries
        bx = min(max(x, 4), max(4, self.width() - tw - 4))
        by = min(max(y, 4), max(4, self.height() - th - 4))

        badge_rect = QRect(bx, by, tw, th)

        # Background
        painter.setPen(QPen(border_color, 1.5, Qt.DashLine))
        painter.setBrush(QBrush(QColor(15, 23, 42, 225)))
        painter.drawRoundedRect(badge_rect, 4, 4)

        # Text
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(badge_rect, Qt.AlignCenter, text)
