"""
Anti-Burn-In Overlay Widget for FGOA.
Periodically and gradually transitions the screen across Black ~ White ~ Rainbow
gradient spectrum to prevent monitor/display burn-in without interfering with operations.

Supports two modes:
- Mode 1 (MODE_APP_WINDOW): Applies overlay only to the FGOA application window.
- Mode 2 (MODE_DESKTOP_FULLSCREEN): Applies overlay across the entire desktop screens
  (regardless of display resolution or multi-monitor topology).
"""
import sys
from typing import List, Optional
from PyQt5.QtWidgets import QWidget, QApplication
from PyQt5.QtGui import QPainter, QColor, QLinearGradient
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QRect


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
            except Exception:
                pass

    def update_render_state(self, stage: int, color: QColor, alpha: int, hue: float, sat: int):
        self._stage = stage
        self._color = color
        self._alpha = alpha
        self._rainbow_hue = hue
        self._rainbow_sat = sat

        if alpha > 0 and stage > 0:
            if not self.isVisible():
                self.show()
                self.raise_()
                self._apply_win32_clickthrough()
            self.update()
        else:
            if self.isVisible():
                self.hide()

    def paintEvent(self, event):
        if self._alpha <= 0:
            return
        painter = QPainter(self)
        if self._stage in (5, 6):
            w = max(1, self.width())
            h = max(1, self.height())
            gradient = QLinearGradient(0, 0, w, h)
            stops = [0.0, 0.16, 0.33, 0.50, 0.66, 0.83, 1.0]
            for i, pos in enumerate(stops):
                hue = int((self._rainbow_hue + i * 60) % 360)
                col = QColor.fromHsv(hue, self._rainbow_sat, 250, self._alpha)
                gradient.setColorAt(pos, col)
            painter.fillRect(self.rect(), gradient)
        else:
            c = QColor(self._color)
            c.setAlpha(self._alpha)
            painter.fillRect(self.rect(), c)


class AntiBurnInOverlay(QWidget):
    """
    Transparent overlay controller that performs a smooth Black -> White -> Rainbow
    color transition to prevent monitor/display burn-in.

    Supports:
    - Mode 1: App window overlay (parent-bounded)
    - Mode 2: Fullscreen desktop overlay (all displays, resolution-independent)
    """
    MODE_APP_WINDOW = 1
    MODE_DESKTOP_FULLSCREEN = 2

    sig_transition_started = pyqtSignal()
    sig_transition_finished = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.hide()

        self._mode: int = self.MODE_APP_WINDOW
        self._desktop_windows: List[DesktopScreenOverlayWindow] = []

        self._color = QColor(0, 0, 0)
        self._alpha = 0  # 0 to 255
        self._stage = 0  # 0: idle, 1: fade-in black, 2: hold black, 3: lerp to white, 4: hold white, 5: bloom & cycle rainbow, 6: fade-out rainbow
        self._hold_ticks = 0
        self._lerp_step = 0
        self._rainbow_hue = 0.0
        self._rainbow_sat = 0

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
        """Starts the gradual Black -> White -> Rainbow spectrum transition."""
        self.update_geometry()
        self._stage = 1
        self._color = QColor(0, 0, 0)
        self._alpha = 0
        self._hold_ticks = 0
        self._lerp_step = 0
        self._rainbow_hue = 0.0
        self._rainbow_sat = 0

        if self._mode == self.MODE_APP_WINDOW:
            for win in self._desktop_windows:
                win.hide()
            self.show()
            self.raise_()
        elif self._mode == self.MODE_DESKTOP_FULLSCREEN:
            self.hide()
            self._ensure_desktop_windows()
            for win in self._desktop_windows:
                win.update_render_state(self._stage, self._color, self._alpha, self._rainbow_hue, self._rainbow_sat)

        self._anim_timer.start()
        self.sig_transition_started.emit()

    def stop_transition(self):
        """Immediately aborts transition and hides overlays."""
        self._anim_timer.stop()
        self._stage = 0
        self._alpha = 0
        self.hide()
        for win in self._desktop_windows:
            win.update_render_state(0, self._color, 0, 0.0, 0)
            win.hide()
        self.sig_transition_finished.emit()

    def cleanup(self):
        """Closes all desktop overlay windows and cleans up resources."""
        self.stop_transition()
        for win in self._desktop_windows:
            win.close()
        self._desktop_windows.clear()

    def _on_anim_step(self):
        fade_step = 6  # ~1.1s for 200 alpha at 33ms/step
        max_black_alpha = 210
        max_white_alpha = 195

        if self._stage == 1:
            # 1. Fade in Black (흑색 페이드인)
            self._color = QColor(0, 0, 0)
            self._alpha = min(max_black_alpha, self._alpha + fade_step)
            if self._alpha >= max_black_alpha:
                self._stage = 2
                self._hold_ticks = 12  # ~0.4s

        elif self._stage == 2:
            # 2. Hold Black (흑색 유지)
            self._hold_ticks -= 1
            if self._hold_ticks <= 0:
                self._stage = 3
                self._lerp_step = 0

        elif self._stage == 3:
            # 3. Smooth Lerp Black -> White (흑 ~ 백 그라데이션 전환)
            self._lerp_step += 1
            total_lerp = 25  # ~0.8s
            ratio = min(1.0, self._lerp_step / total_lerp)
            gray = int(255 * ratio)
            self._color = QColor(gray, gray, gray)
            self._alpha = int(max_black_alpha + (max_white_alpha - max_black_alpha) * ratio)
            if ratio >= 1.0:
                self._stage = 4
                self._hold_ticks = 12  # ~0.4s

        elif self._stage == 4:
            # 4. Hold White (백색 유지)
            self._color = QColor(255, 255, 255)
            self._hold_ticks -= 1
            if self._hold_ticks <= 0:
                self._stage = 5
                self._hold_ticks = 50  # ~1.65s rainbow cycling
                self._rainbow_hue = 0.0
                self._rainbow_sat = 0

        elif self._stage == 5:
            # 5. Bloom from White into flowing Rainbow spectrum gradient (무지개색 스펙트럼 회전)
            self._hold_ticks -= 1
            # Smoothly ramp saturation from 0 (white) to 225 (vivid rainbow) over first 12 ticks
            self._rainbow_sat = min(225, self._rainbow_sat + 18)
            self._rainbow_hue = (self._rainbow_hue + 7.0) % 360.0
            if self._hold_ticks <= 0:
                self._stage = 6

        elif self._stage == 6:
            # 6. Fade out Rainbow to normal UI (무지개색 페이드아웃)
            self._rainbow_hue = (self._rainbow_hue + 5.0) % 360.0
            self._alpha = max(0, self._alpha - fade_step)
            if self._alpha <= 0:
                self.stop_transition()
                return

        if self._mode == self.MODE_APP_WINDOW:
            self.update()
        elif self._mode == self.MODE_DESKTOP_FULLSCREEN:
            for win in self._desktop_windows:
                win.update_render_state(self._stage, self._color, self._alpha, self._rainbow_hue, self._rainbow_sat)

    def paintEvent(self, event):
        if self._alpha <= 0 or self._mode != self.MODE_APP_WINDOW:
            return
        painter = QPainter(self)

        if self._stage in (5, 6):
            # Rainbow gradient mode (무지개색 스펙트럼 대각선 그라데이션)
            w = max(1, self.width())
            h = max(1, self.height())
            gradient = QLinearGradient(0, 0, w, h)
            # 7 spectral stops across 360 degrees HSV
            stops = [0.0, 0.16, 0.33, 0.50, 0.66, 0.83, 1.0]
            for i, pos in enumerate(stops):
                hue = int((self._rainbow_hue + i * 60) % 360)
                col = QColor.fromHsv(hue, self._rainbow_sat, 250, self._alpha)
                gradient.setColorAt(pos, col)
            painter.fillRect(self.rect(), gradient)
        else:
            # Solid color mode (Black, Black-to-White lerp, White)
            c = QColor(self._color)
            c.setAlpha(self._alpha)
            painter.fillRect(self.rect(), c)
