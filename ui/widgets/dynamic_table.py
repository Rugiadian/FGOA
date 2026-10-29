"""
Dynamic Height Table Widget for FGOA.
Adapts vertical height to match the exact number of rows (condition points),
eliminating wasted blank space.
"""
from PyQt5.QtWidgets import QTableWidget, QSizePolicy
from PyQt5.QtCore import Qt, QSize


class DynamicPointsTableWidget(QTableWidget):
    """
    QTableWidget that dynamically adapts its vertical sizeHint and height
    to match the exact number of rows (condition points), avoiding empty blank space
    while retaining scrollability when row count exceeds max_dynamic_height.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.max_dynamic_height = 360

    def calculate_ideal_height(self) -> int:
        hdr = self.horizontalHeader()
        hdr_h = hdr.height() if (hdr and hdr.isVisible()) else 0
        if hdr_h <= 0 and hdr:
            hdr_h = hdr.sizeHint().height()
        if hdr_h <= 0:
            hdr_h = 24

        row_h = self.verticalHeader().defaultSectionSize() or 24
        count = self.rowCount()
        frame = self.frameWidth() * 2

        if count == 0:
            return int(hdr_h + frame + 4)
        return int(hdr_h + count * row_h + frame + 4)

    def sizeHint(self) -> QSize:
        s = super().sizeHint()
        ideal = self.calculate_ideal_height()
        max_h = int(getattr(self, "max_dynamic_height", 360))
        return QSize(int(s.width()), int(min(ideal, max_h)))

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def update_dynamic_height(self):
        """Refreshes geometry and updates minimum height / scrollbar policy based on row count."""
        ideal = self.calculate_ideal_height()
        target_h = min(ideal, getattr(self, "max_dynamic_height", 360))
        self.setMinimumHeight(target_h)
        self.updateGeometry()
        if ideal > getattr(self, "max_dynamic_height", 360):
            self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        else:
            self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        p = self.parentWidget()
        if p and p.layout():
            p.layout().activate()
