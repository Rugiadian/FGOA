"""
Anti-Burn-In Overlay Widget for FGOA.
Periodically and gradually transitions the screen into complete black and smoothly returns
to prevent monitor/display burn-in without interfering with operations.

Supports two modes:
- Mode 1 (MODE_APP_WINDOW): Applies overlay only to the FGOA application window.
- Mode 2 (MODE_DESKTOP_FULLSCREEN): Applies overlay across the entire desktop screens
  (regardless of display resolution or multi-monitor topology).
"""
import sys
import time
from typing import List, Optional
from PyQt5.QtWidgets import QWidget, QApplication
from PyQt5.QtGui import QPainter, QColor, QFont, QFontMetrics, QPainterPath, QPen
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QRect, QRectF


class FloatingTextTracker:
    """
    Tracks floating 2D badge position with bounce reflection inside a given bounding rect.
    Renders high-visibility screen guard badge to prevent burn-in and clearly notify user.
    """
    def __init__(self, text: str = "스크린 가드 중. 긴급탈출 f12"):
        self.text = text
        self.x = 80.0
        self.y = 80.0
        self.vx = 3.0
        self.vy = 2.2
        self.initialized = False

    def reset(self, width: int, height: int):
        self.x = max(40.0, float(width) * 0.25)
        self.y = max(60.0, float(height) * 0.25)
        self.vx = 3.0
        self.vy = 2.2
        self.initialized = True

    def update(self, width: int, height: int, box_w: float, box_h: float):
        if width <= 0 or height <= 0:
            return
        if not self.initialized:
            self.reset(width, height)

        self.x += self.vx
        self.y += self.vy

        min_x = 20.0
        max_x = max(min_x, float(width) - box_w - 20.0)
        min_y = 20.0
        max_y = max(min_y, float(height) - box_h - 20.0)

        if self.x <= min_x:
            self.x = min_x
            self.vx = abs(self.vx)
        elif self.x >= max_x:
            self.x = max_x
            self.vx = -abs(self.vx)

        if self.y <= min_y:
            self.y = min_y
            self.vy = abs(self.vy)
        elif self.y >= max_y:
            self.y = max_y
            self.vy = -abs(self.vy)

    def draw(self, painter: QPainter, width: int, height: int, alpha: int):
        if alpha <= 0 or width <= 0 or height <= 0:
            return
        font = QFont("Malgun Gothic", 18)
        font.setBold(True)
        fm = QFontMetrics(font)
        tw = fm.horizontalAdvance(self.text) if hasattr(fm, "horizontalAdvance") else fm.width(self.text)
        th = fm.height()

        pad_x = 24.0
        pad_y = 12.0
        box_w = float(tw) + pad_x * 2.0
        box_h = float(th) + pad_y * 2.0

        self.update(width, height, box_w, box_h)

        # Enable Antialiasing for crisp badge rendering
        painter.setRenderHint(QPainter.Antialiasing, True)

        # 1. Floating Badge Background Container
        badge_rect = QRectF(self.x, self.y, box_w, box_h)
        bg_alpha = min(235, max(120, int(alpha * 0.92)))
        border_alpha = min(255, max(150, alpha))
        painter.setBrush(QColor(18, 22, 32, bg_alpha))
        painter.setPen(QPen(QColor(90, 150, 240, border_alpha), 2.0))
        painter.drawRoundedRect(badge_rect, 10.0, 10.0)

        # 2. Crisp, pure-white text using QPainterPath (bypasses ClearType alpha loss on Windows DWM)
        path = QPainterPath()
        text_x = self.x + pad_x
        text_y = self.y + pad_y + float(fm.ascent())
        path.addText(text_x, text_y, font, self.text)

        text_alpha = min(255, max(180, alpha))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, text_alpha))
        painter.drawPath(path)


class DesktopScreenOverlayWindow(QWidget):
    """
    Transparent, frameless, click-through overlay window covering a single display screen
    or virtual desktop area for burn-in prevention without interfering with user interaction.
    """
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(
            parent,
            Qt.Window
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.hide()

        self._stage = 0
        self._color = QColor(0, 0, 0)
        self._alpha = 0
        self._rainbow_hue = 0.0
        self._rainbow_sat = 0
        self._floating_tracker = FloatingTextTracker("스크린 가드 중. 긴급탈출 f12")

        self._apply_win32_clickthrough()

    def _apply_win32_clickthrough(self):
        """Enforces OS-level mouse click-through and non-activation on Windows."""
        if sys.platform == "win32":
            try:
                import ctypes
                hwnd = int(self.winId())
                user32 = ctypes.windll.user32
                GWL_EXSTYLE = -20
                WS_EX_TRANSPARENT = 0x00000020
                WS_EX_LAYERED = 0x00080000
                WS_EX_NOACTIVATE = 0x08000000
                WS_EX_TOOLWINDOW = 0x00000080
                style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                user32.SetWindowLongW(
                    hwnd,
                    GWL_EXSTYLE,
                    style | WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
                )
                # WDA_EXCLUDEFROMCAPTURE = 0x00000011 (Win10 2004+):
                # Excludes overlay from OS screen capture / DWM grabs so underlying content remains clear
                try:
                    user32.SetWindowDisplayAffinity(hwnd, 0x00000011)
                except Exception:
                    pass
            except Exception:
                pass

    def update_render_state(self, stage: int, color: Optional[QColor] = None, alpha: int = 0, hue: float = 0.0, sat: int = 0, **kwargs):
        self._stage = stage
        self._color = color if color is not None else QColor(0, 0, 0)
        self._alpha = alpha
        self._rainbow_hue = hue
        self._rainbow_sat = sat

        if stage > 0:
            if not self.isVisible():
                self.show()
                self.raise_()
                self._apply_win32_clickthrough()
            self.update()
        else:
            if self.isVisible():
                self.hide()

    def paintEvent(self, event):
        if self._stage == 0 and self._alpha <= 0:
            return
        painter = QPainter(self)
        if self._alpha > 0:
            painter.fillRect(self.rect(), QColor(0, 0, 0, self._alpha))
        if self._stage > 0:
            self._floating_tracker.draw(painter, self.width(), self.height(), max(180, self._alpha))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F12:
            AntiBurnInOverlay.escape_all()
            event.accept()
            return
        super().keyPressEvent(event)


class AntiBurnInOverlay(QWidget):
    """
    Transparent overlay controller that performs a smooth Black fade-in, hold, and fade-out
    color transition to prevent monitor/display burn-in.


    Supports:
    - Mode 1: App window overlay (parent-bounded)
    - Mode 2: Fullscreen desktop overlay (all displays, resolution-independent)
    """
    MODE_APP_WINDOW = 1
    MODE_DESKTOP_FULLSCREEN = 2

    _active_instances: List["AntiBurnInOverlay"] = []

    sig_transition_started = pyqtSignal()
    sig_transition_finished = pyqtSignal()

    @classmethod
    def is_any_transitioning(cls) -> bool:
        """Checks if any AntiBurnInOverlay instance is currently animating screen colors."""
        return any(inst.is_transitioning() for inst in cls._active_instances if inst)

    @classmethod
    def escape_all(cls) -> bool:
        """
        Emergency escape: immediately stops and hides all active anti-burn overlay instances.
        Returns True if any transitioning overlay was aborted, False otherwise.
        """
        aborted = False
        for inst in list(cls._active_instances):
            if inst and inst.is_transitioning():
                inst.stop_transition()
                aborted = True
        return aborted

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        if self not in AntiBurnInOverlay._active_instances:
            AntiBurnInOverlay._active_instances.append(self)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.hide()

        self._mode: int = self.MODE_APP_WINDOW
        self._desktop_windows: List[DesktopScreenOverlayWindow] = []

        self._color = QColor(0, 0, 0)
        self._alpha = 0  # 0 to 255
        self._stage = 0  # 0: idle, 1: fade-in black, 2: hold black, 3: fade-out black
        self._hold_ticks = 0
        self._lerp_step = 0
        self._rainbow_hue = 0.0
        self._rainbow_sat = 0

        self._hold_minutes = 1.0  # Duration in minutes to stay in complete black
        self._hold_start_time = 0.0
        self._floating_tracker = FloatingTextTracker("스크린 가드 중. 긴급탈출 f12")

        # Animation step timer (~30 FPS, 33ms)
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(33)
        self._anim_timer.timeout.connect(self._on_anim_step)

        # Interval timer for triggering every N minutes
        self._interval_timer = QTimer(self)
        self._interval_timer.timeout.connect(self.start_transition)

        self._interval_minutes = 5
        self._is_enabled = False

        self._connect_screen_signals()

    def _connect_screen_signals(self):
        """Monitors display geometry/screen changes to keep fullscreen overlays aligned."""
        app = QApplication.instance()
        if app:
            if hasattr(app, "screenAdded"):
                try:
                    app.screenAdded.connect(self._on_screens_changed)
                except Exception:
                    pass
            if hasattr(app, "screenRemoved"):
                try:
                    app.screenRemoved.connect(self._on_screens_changed)
                except Exception:
                    pass
            desktop = app.desktop()
            if desktop and hasattr(desktop, "resized"):
                try:
                    desktop.resized.connect(self._on_screens_changed)
                except Exception:
                    pass

    def _on_screens_changed(self, *args):
        if self._mode == self.MODE_DESKTOP_FULLSCREEN:
            self.update_geometry()

    def set_mode(self, mode: int):
        """Switches between Mode 1 (App Window) and Mode 2 (Desktop Fullscreen)."""
        valid_mode = self.MODE_DESKTOP_FULLSCREEN if mode == self.MODE_DESKTOP_FULLSCREEN else self.MODE_APP_WINDOW
        if self._mode == valid_mode:
            return
        was_running = self.is_transitioning()
        self.stop_transition()
        self._mode = valid_mode
        if was_running:
            self.start_transition()

    def get_mode(self) -> int:
        return self._mode

    def is_transitioning(self) -> bool:
        return self._stage > 0

    def set_enabled(self, enabled: bool):
        self._is_enabled = enabled
        if enabled:
            self._interval_timer.setInterval(self._interval_minutes * 60 * 1000)
            self._interval_timer.start()
        else:
            self._interval_timer.stop()
            self.stop_transition()

    def is_enabled(self) -> bool:
        return self._is_enabled

    def set_interval_minutes(self, minutes: int):
        self._interval_minutes = max(1, minutes)
        if self._is_enabled:
            self._interval_timer.setInterval(self._interval_minutes * 60 * 1000)
            self._interval_timer.start()

    def get_interval_minutes(self) -> int:
        return self._interval_minutes

    def set_hold_minutes(self, minutes: float):
        """Sets the duration in minutes to remain in pure black state."""
        self._hold_minutes = max(0.0, float(minutes))

    def get_hold_minutes(self) -> float:
        return self._hold_minutes

    def get_remaining_hold_seconds(self) -> float:
        """Returns remaining seconds in pure black hold state (Stage 2)."""
        if self._stage == 2 and self._hold_start_time > 0:
            elapsed = time.time() - self._hold_start_time
            rem = (self._hold_minutes * 60.0) - elapsed
            return max(0.0, rem)
        return 0.0

    def _ensure_desktop_windows(self):
        """Creates or aligns DesktopScreenOverlayWindow instances for all display screens."""
        app = QApplication.instance()
        geometries: List[QRect] = []

        if app and hasattr(app, "screens"):
            screens = app.screens()
            for scr in screens:
                geo = scr.geometry()
                if geo.isValid() and geo.width() > 0 and geo.height() > 0:
                    geometries.append(geo)

        if not geometries and app:
            desktop = app.desktop()
            if desktop:
                count = desktop.screenCount()
                for i in range(count):
                    geo = desktop.screenGeometry(i)
                    if geo.isValid() and geo.width() > 0 and geo.height() > 0:
                        geometries.append(geo)
                if not geometries:
                    v_geo = desktop.virtualGeometry()
                    if v_geo.isValid():
                        geometries.append(v_geo)

        if not geometries:
            geometries = [QRect(0, 0, 1920, 1080)]

        # Adjust overlay window pool size
        while len(self._desktop_windows) < len(geometries):
            self._desktop_windows.append(DesktopScreenOverlayWindow())
        while len(self._desktop_windows) > len(geometries):
            w = self._desktop_windows.pop()
            w.hide()
            w.close()

        # Update geometries
        for win, geo in zip(self._desktop_windows, geometries):
            win.setGeometry(geo)

    def update_geometry(self):
        """Updates geometry for the current mode."""
        if self._mode == self.MODE_APP_WINDOW:
            if self.parent():
                p = self.parent()
                self.setGeometry(0, 0, p.width(), p.height())
                self.raise_()
        elif self._mode == self.MODE_DESKTOP_FULLSCREEN:
            self._ensure_desktop_windows()

    def start_transition(self):
        """Starts the gradual fade-in to pure Black, hold, and fade-out transition."""
        self.update_geometry()
        self._stage = 1
        self._color = QColor(0, 0, 0)
        self._alpha = 0
        self._hold_start_time = 0.0
        self._hold_ticks = 0
        self._lerp_step = 0
        self._rainbow_hue = 0.0
        self._rainbow_sat = 0

        if self._mode == self.MODE_APP_WINDOW:
            self._floating_tracker.reset(self.width(), self.height())
            for win in self._desktop_windows:
                win.hide()
            self.show()
            self.raise_()
        elif self._mode == self.MODE_DESKTOP_FULLSCREEN:
            self.hide()
            self._ensure_desktop_windows()
            for win in self._desktop_windows:
                win._floating_tracker.reset(win.width(), win.height())
                win.update_render_state(self._stage, self._color, self._alpha, 0.0, 0)

        self._anim_timer.start()
        self.sig_transition_started.emit()

    def stop_transition(self):
        """Immediately aborts transition and hides overlays."""
        self._anim_timer.stop()
        self._stage = 0
        self._alpha = 0
        self._hold_start_time = 0.0
        self.hide()
        for win in self._desktop_windows:
            win.update_render_state(0, self._color, 0, 0.0, 0)
            win.hide()
        self.sig_transition_finished.emit()

    def cleanup(self):
        """Closes all desktop overlay windows and cleans up resources."""
        self.stop_transition()
        if self in AntiBurnInOverlay._active_instances:
            AntiBurnInOverlay._active_instances.remove(self)
        for win in self._desktop_windows:
            win.close()
        self._desktop_windows.clear()

    def _on_anim_step(self):
        fade_step = 6  # ~1.4s for 255 alpha at 33ms/step
        max_black_alpha = 255

        if self._stage == 1:
            # 1. Fade-in pure Black (완전한 블랙으로 서서히 페이드인)
            self._color = QColor(0, 0, 0)
            self._alpha = min(max_black_alpha, self._alpha + fade_step)
            if self._alpha >= max_black_alpha:
                self._alpha = max_black_alpha
                self._stage = 2
                self._hold_start_time = time.time()

        elif self._stage == 2:
            # 2. Hold pure Black (설정된 분 단위 시간 동안 완전한 블랙 상태 유지)
            self._alpha = max_black_alpha
            elapsed = time.time() - self._hold_start_time
            if elapsed >= (self._hold_minutes * 60.0):
                self._stage = 3

        elif self._stage == 3:
            # 3. Fade-out from Black (서서히 원래 화면으로 복귀)
            self._alpha = max(0, self._alpha - fade_step)
            if self._alpha <= 0:
                self._alpha = 0
                self.stop_transition()
                return

        if self._mode == self.MODE_APP_WINDOW:
            self.update()
        elif self._mode == self.MODE_DESKTOP_FULLSCREEN:
            for win in self._desktop_windows:
                win.update_render_state(self._stage, self._color, self._alpha, 0.0, 0)

    def paintEvent(self, event):
        if (self._stage == 0 and self._alpha <= 0) or self._mode != self.MODE_APP_WINDOW:
            return
        painter = QPainter(self)
        if self._alpha > 0:
            painter.fillRect(self.rect(), QColor(0, 0, 0, self._alpha))
        if self._stage > 0:
            self._floating_tracker.draw(painter, self.width(), self.height(), max(180, self._alpha))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F12:
            self.stop_transition()
            event.accept()
            return
        super().keyPressEvent(event)
