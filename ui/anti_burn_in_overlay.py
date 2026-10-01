"""
Anti-Burn-In Overlay Widget for FGOA.
Periodically and gradually transitions the entire UI across Black ~ White ~ Rainbow
gradient spectrum to prevent monitor/display burn-in without interfering with operations.
"""
from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPainter, QColor, QLinearGradient
from PyQt5.QtCore import Qt, QTimer, pyqtSignal


class AntiBurnInOverlay(QWidget):
    """
    Full-window transparent overlay that performs a smooth Black -> White -> Rainbow
    color transition to prevent monitor/display burn-in.

    Attribute Qt.WA_TransparentForMouseEvents ensures zero interference with mouse clicks/drags.
    """
    sig_transition_started = pyqtSignal()
    sig_transition_finished = pyqtSignal()

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.hide()

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

    def update_geometry(self):
        if self.parent():
            p = self.parent()
            self.setGeometry(0, 0, p.width(), p.height())
            self.raise_()

    def start_transition(self):
        """Starts the gradual Black -> White -> Rainbow spectrum transition."""
        self.update_geometry()
        self.show()
        self.raise_()
        self._stage = 1
        self._color = QColor(0, 0, 0)
        self._alpha = 0
        self._hold_ticks = 0
        self._lerp_step = 0
        self._rainbow_hue = 0.0
        self._rainbow_sat = 0
        self._anim_timer.start()
        self.sig_transition_started.emit()

    def stop_transition(self):
        """Immediately aborts transition and hides overlay."""
        self._anim_timer.stop()
        self._stage = 0
        self._alpha = 0
        self.hide()
        self.sig_transition_finished.emit()

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

        self.update()

    def paintEvent(self, event):
        if self._alpha <= 0:
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
