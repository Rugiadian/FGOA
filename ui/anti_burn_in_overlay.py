"""
Anti-Burn-In Overlay Widget for FGOA.
Periodically and gradually transitions the entire UI between black and white
to prevent monitor burn-in without interfering with user or macro operations.
"""
from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPainter, QColor
from PyQt5.QtCore import Qt, QTimer, pyqtSignal


class AntiBurnInOverlay(QWidget):
    """
    Full-window transparent overlay that performs a smooth black-to-white-to-normal
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
        self._stage = 0  # 0: idle, 1: fade-in black, 2: hold black, 3: fade-out black, 4: fade-in white, 5: hold white, 6: fade-out white
        self._hold_ticks = 0

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
        """Starts the gradual black -> white -> normal transition."""
        self.update_geometry()
        self.show()
        self.raise_()
        self._stage = 1
        self._color = QColor(0, 0, 0)
        self._alpha = 0
        self._hold_ticks = 0
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
            # Fade in black
            self._color = QColor(0, 0, 0)
            self._alpha = min(max_black_alpha, self._alpha + fade_step)
            if self._alpha >= max_black_alpha:
                self._stage = 2
                self._hold_ticks = 12  # ~0.4s
        elif self._stage == 2:
            # Hold black
            self._hold_ticks -= 1
            if self._hold_ticks <= 0:
                self._stage = 3
        elif self._stage == 3:
            # Fade out black
            self._alpha = max(0, self._alpha - fade_step)
            if self._alpha <= 0:
                self._stage = 4
                self._color = QColor(255, 255, 255)
        elif self._stage == 4:
            # Fade in white
            self._color = QColor(255, 255, 255)
            self._alpha = min(max_white_alpha, self._alpha + fade_step)
            if self._alpha >= max_white_alpha:
                self._stage = 5
                self._hold_ticks = 12  # ~0.4s
        elif self._stage == 5:
            # Hold white
            self._hold_ticks -= 1
            if self._hold_ticks <= 0:
                self._stage = 6
        elif self._stage == 6:
            # Fade out white
            self._alpha = max(0, self._alpha - fade_step)
            if self._alpha <= 0:
                self.stop_transition()
                return

        self.update()

    def paintEvent(self, event):
        if self._alpha <= 0:
            return
        painter = QPainter(self)
        c = QColor(self._color)
        c.setAlpha(self._alpha)
        painter.fillRect(self.rect(), c)
