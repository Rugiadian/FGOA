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

import win32gui
import win32con
from core.models import Action
from core.window_manager import WindowManager


class ActionOverlayWindow(QWidget):
    """
    Transparent, click-through overlay window positioned over the target game/app window.
    Draws dotted boxes and paths where actions are operating on screen.
    Guaranteed zero click interception via native Windows WS_EX_TRANSPARENT and HTTRANSPARENT.
    """

    def __init__(self, target_hwnd: int = 0, parent=None):
        super().__init__(parent, Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        self.target_hwnd = target_hwnd
        self.current_action: Optional[Action] = None
        self.sequence_actions: list = []
        self.action_index: int = 1
        self.total_actions: int = 1
        self.scenario_name: str = ""
        self.is_overlay_enabled: bool = True

        # Clear timer to fade/hide markers after action finishes
        self._clear_timer = QTimer(self)
        self._clear_timer.setSingleShot(True)
        self._clear_timer.timeout.connect(self.clear_action)

    def _apply_native_click_through(self):
        """Enforces OS-level click-through so SendInput/mouse_event bypasses this window completely."""
        try:
            hwnd = int(self.winId())
            if hwnd:
                style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                # WS_EX_TRANSPARENT (0x20): pass-through mouse input to underlying windows
                # WS_EX_LAYERED (0x80000): required for transparency and per-pixel alpha
                # WS_EX_NOACTIVATE (0x08000000): prevent taking focus when displayed
                style |= (win32con.WS_EX_TRANSPARENT | win32con.WS_EX_LAYERED | win32con.WS_EX_NOACTIVATE)
                win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, style)
        except Exception:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_native_click_through()

    def nativeEvent(self, eventType, message):
        """Intercepts WM_NCHITTEST (0x0084) to return HTTRANSPARENT (-1) for 100% click pass-through."""
        try:
            if eventType == "windows_generic_MSG":
                import ctypes
                from ctypes import wintypes
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == 0x0084:  # WM_NCHITTEST
                    return True, -1  # HTTRANSPARENT: let clicks fall through to underlying window
        except Exception:
            pass
        return super().nativeEvent(eventType, message)

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

    def show_sequence(self, actions: list, current_index: int = 1, scenario_name: str = ""):
        """Display all points and paths of the executing action sequence."""
        if not self.is_overlay_enabled:
            return

        self._clear_timer.stop()
        self.sequence_actions = list(actions) if actions else []
        self.action_index = current_index
        self.total_actions = len(self.sequence_actions)
        self.scenario_name = scenario_name
        if 0 < current_index <= len(self.sequence_actions):
            self.current_action = self.sequence_actions[current_index - 1]
        elif self.sequence_actions:
            self.current_action = self.sequence_actions[0]
        else:
            self.current_action = None

        self.update_geometry()
        if not self.isVisible():
            self.show()
        self._apply_native_click_through()
        self.update()

    def set_current_action_index(self, index: int, action: Optional[Action] = None):
        """Updates which action in the playing sequence is currently executing."""
        self.action_index = index
        if action:
            self.current_action = action
        elif self.sequence_actions and 0 < index <= len(self.sequence_actions):
            self.current_action = self.sequence_actions[index - 1]
        self.update()

    def show_action(self, action: Action, index: int = 1, total: int = 1, scenario_name: str = ""):
        """Display dotted indicators for the given executing action, retaining sequence."""
        if not self.is_overlay_enabled:
            return

        self._clear_timer.stop()
        if not self.sequence_actions:
            self.sequence_actions = [action]
        self.current_action = action
        self.action_index = index
        self.total_actions = total or len(self.sequence_actions)
        self.scenario_name = scenario_name

        self.update_geometry()
        if not self.isVisible():
            self.show()
        self._apply_native_click_through()
        self.update()

    def hide_action_delayed(self, delay_ms: int = 600):
        """Schedule clearing the action sequence visualization."""
        self._clear_timer.start(delay_ms)

    def clear_action(self):
        """Clear action display and hide overlay."""
        self.current_action = None
        self.sequence_actions = []
        self.update()
        self.hide()

    def paintEvent(self, event):
        if not self.is_overlay_enabled:
            return

        actions_to_render = self.sequence_actions if self.sequence_actions else ([self.current_action] if self.current_action else [])
        if not actions_to_render:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 1. Collect coordinate points for connecting flow lines
        coord_points = []
        for idx, act in enumerate(actions_to_render):
            if act.action_type == "mouse_click":
                coord_points.append((idx + 1, act.x, act.y))
            elif act.action_type == "mouse_drag":
                coord_points.append((idx + 1, act.x, act.y))
                coord_points.append((idx + 1, act.end_x, act.end_y))

        # 2. Draw connecting inter-action flow path lines between sequential points
        if len(coord_points) > 1:
            flow_pen = QPen(QColor(148, 163, 184, 110), 1.5, Qt.DotLine)
            flow_pen.setDashPattern([3, 4])
            painter.setPen(flow_pen)
            for i in range(len(coord_points) - 1):
                p1 = QPointF(coord_points[i][1], coord_points[i][2])
                p2 = QPointF(coord_points[i + 1][1], coord_points[i + 1][2])
                painter.drawLine(p1, p2)

        # 3. Draw each action's markers
        tot = len(actions_to_render)
        for idx_zero, act in enumerate(actions_to_render):
            step_idx = idx_zero + 1
            is_active = (step_idx == self.action_index)

            if act.action_type == "mouse_click":
                self._draw_click_visualization(painter, act.x, act.y, step_idx, tot, act.get_summary(), is_active)
            elif act.action_type == "mouse_drag":
                self._draw_drag_visualization(
                    painter, act.x, act.y, act.end_x, act.end_y,
                    act.drag_duration_ms, step_idx, tot, is_active
                )
        # Note: Non-coordinate actions (delay, key, text) are shown in PopupPlayBar, not on target screen


    def _draw_click_visualization(self, painter: QPainter, x: int, y: int, idx: int, tot: int, summary: str, is_active: bool = True):
        # 1. Outer animated-style dotted bounding box
        box_size = 48 if is_active else 38
        rect = QRect(x - box_size // 2, y - box_size // 2, box_size, box_size)

        box_color = QColor(6, 182, 212, 255) if is_active else QColor(14, 165, 233, 150)
        box_fill = QColor(6, 182, 212, 55) if is_active else QColor(14, 165, 233, 20)
        dash_pen = QPen(box_color, 2.5 if is_active else 1.5, Qt.DashLine)
        dash_pen.setDashPattern([4, 3] if is_active else [3, 3])
        painter.setPen(dash_pen)
        painter.setBrush(QBrush(box_fill))
        painter.drawRect(rect)

        # 2. Concentric ring
        ring_color = QColor(255, 255, 255, 240) if is_active else QColor(255, 255, 255, 120)
        ring_pen = QPen(ring_color, 1.5 if is_active else 1.0, Qt.DotLine)
        ring_pen.setDashPattern([2, 3])
        painter.setPen(ring_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(x, y), 14 if is_active else 10, 14 if is_active else 10)

        # 3. Center precision crosshair
        cross_color = QColor(239, 68, 68, 250) if is_active else QColor(148, 163, 184, 160)
        cross_pen = QPen(cross_color, 2.0 if is_active else 1.5, Qt.SolidLine)
        painter.setPen(cross_pen)
        c_len = 8 if is_active else 5
        painter.drawLine(x - c_len, y, x + c_len, y)
        painter.drawLine(x, y - c_len, x, y + c_len)

        # 4. Floating Badge with step number & coords
        if is_active:
            badge_text = f"#{idx}/{tot} ▶ 클릭 ({x}, {y})"
            self._draw_floating_badge(painter, x + 28, y - 12, badge_text, QColor(6, 182, 212))
        else:
            badge_text = f"#{idx} ({x}, {y})"
            self._draw_floating_badge(painter, x + 24, y - 10, badge_text, QColor(100, 116, 139))

    def _draw_drag_visualization(self, painter: QPainter, x1: int, y1: int, x2: int, y2: int,
                                 duration_ms: int, idx: int, tot: int, is_active: bool = True):
        # 1. Start point dotted box (Emerald)
        start_rect = QRect(x1 - 18, y1 - 18, 36, 36)
        s_color = QColor(16, 185, 129, 240) if is_active else QColor(16, 185, 129, 140)
        start_pen = QPen(s_color, 2.2 if is_active else 1.5, Qt.DashLine)
        start_pen.setDashPattern([3, 2])
        painter.setPen(start_pen)
        painter.setBrush(QBrush(QColor(16, 185, 129, 45 if is_active else 18)))
        painter.drawRect(start_rect)

        # 2. End point dotted box (Amber/Orange)
        end_rect = QRect(x2 - 18, y2 - 18, 36, 36)
        e_color = QColor(245, 158, 11, 240) if is_active else QColor(245, 158, 11, 140)
        end_pen = QPen(e_color, 2.5 if is_active else 1.5, Qt.DashLine)
        end_pen.setDashPattern([4, 2])
        painter.setPen(end_pen)
        painter.setBrush(QBrush(QColor(245, 158, 11, 45 if is_active else 18)))
        painter.drawRect(end_rect)

        # 3. Dotted connecting line with arrow
        line_pen = QPen(e_color, 2.8 if is_active else 1.8, Qt.DashLine)
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
            arrow_size = 14 if is_active else 10
            p1 = QPointF(x2 - arrow_size * ux + arrow_size * 0.5 * uy,
                         y2 - arrow_size * uy - arrow_size * 0.5 * ux)
            p2 = QPointF(x2 - arrow_size * ux - arrow_size * 0.5 * uy,
                         y2 - arrow_size * uy + arrow_size * 0.5 * ux)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(e_color))
            painter.drawPolygon(QPolygonF([QPointF(x2, y2), p1, p2]))

        # 5. Badges
        if is_active:
            self._draw_floating_badge(painter, x1 + 22, y1 - 10, f"#{idx} ▶ 드래그 시작 ({x1}, {y1})", QColor(16, 185, 129))
            self._draw_floating_badge(painter, x2 + 22, y2 - 10, f"끝 ({x2}, {y2}) [{duration_ms}ms]", QColor(245, 158, 11))
        else:
            self._draw_floating_badge(painter, x1 + 20, y1 - 8, f"#{idx} 시작", QColor(100, 116, 139))
            self._draw_floating_badge(painter, x2 + 20, y2 - 8, f"끝 [{duration_ms}ms]", QColor(100, 116, 139))

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
