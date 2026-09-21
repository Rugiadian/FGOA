"""
Color badge and status indicator widgets for FGOA.
"""
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt5.QtGui import QColor, QPainter, QBrush, QPen
from PyQt5.QtCore import Qt, QSize


class ColorChipWidget(QWidget):
    """Small square showing a color swatch with border visible on both light & dark themes."""

    def __init__(self, r: int, g: int, b: int, size: int = 18, parent=None):
        super().__init__(parent)
        self.r = r
        self.g = g
        self.b = b
        self.chip_size = size
        self.setFixedSize(size, size)

    def set_color(self, r: int, g: int, b: int):
        self.r = r
        self.g = g
        self.b = b
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Fill color
        color = QColor(self.r, self.g, self.b)
        painter.setBrush(QBrush(color))
        # Clear contrasting border (dark grey if bright, light grey if dark)
        luminance = 0.299 * self.r + 0.587 * self.g + 0.114 * self.b
        border_color = QColor(160, 160, 170) if luminance > 128 else QColor(200, 200, 210)
        painter.setPen(QPen(border_color, 1))
        painter.drawRoundedRect(1, 1, self.chip_size - 2, self.chip_size - 2, 3, 3)


class ColorBadge(QWidget):
    """Composite widget displaying a color chip and RGB text string."""

    def __init__(self, r: int, g: int, b: int, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        self.chip = ColorChipWidget(r, g, b, 16)
        self.lbl_text = QLabel(f"RGB({r},{g},{b})")
        self.lbl_text.setStyleSheet("font-family: monospace; font-size: 9pt; font-weight: bold;")

        layout.addWidget(self.chip)
        layout.addWidget(self.lbl_text)
        layout.addStretch()


class WarningBadge(QWidget):
    """Warning badge shown when duplicate condition or preset is detected."""

    def __init__(self, tooltip_text: str = "", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)

        self.lbl_icon = QLabel("⚠️")
        self.lbl_text = QLabel("중복 조건")
        self.lbl_text.setStyleSheet("color: #d97706; font-size: 8.5pt; font-weight: bold;")
        self.setToolTip(tooltip_text)

        layout.addWidget(self.lbl_icon)
        layout.addWidget(self.lbl_text)
