"""
Magnifier / Loupe widget for FGOA.
Displays an enlarged pixel grid around the mouse cursor with RGB details.
"""
from typing import Optional, Tuple
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QFrame
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPixmap, QImage
from PyQt5.QtCore import Qt, QRect


class MagnifierCanvas(QWidget):
    """Draws an enlarged grid of pixels centered on a target pixel."""

    def __init__(self, grid_size: int = 11, zoom: int = 14, parent=None):
        super().__init__(parent)
        self.grid_size = grid_size  # Must be odd (e.g. 11, 15)
        self.zoom = zoom
        dim = self.grid_size * self.zoom
        self.setFixedSize(dim, dim)

        self.current_image: Optional[QImage] = None
        self.center_x: int = 0
        self.center_y: int = 0
        self.center_rgb: Tuple[int, int, int] = (0, 0, 0)

    def update_pixel_data(self, image: Optional[QImage], cx: int, cy: int):
        self.current_image = image
        self.center_x = cx
        self.center_y = cy
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(20, 20, 24))

        half = self.grid_size // 2

        if self.current_image and not self.current_image.isNull():
            img_w = self.current_image.width()
            img_h = self.current_image.height()

            for gy in range(self.grid_size):
                for gx in range(self.grid_size):
                    ix = self.center_x - half + gx
                    iy = self.center_y - half + gy

                    if 0 <= ix < img_w and 0 <= iy < img_h:
                        col = QColor(self.current_image.pixel(ix, iy))
                    else:
                        col = QColor(10, 10, 14)

                    if gx == half and gy == half:
                        self.center_rgb = (col.red(), col.green(), col.blue())

                    painter.fillRect(
                        gx * self.zoom, gy * self.zoom,
                        self.zoom, self.zoom,
                        col
                    )
                    # Grid lines
                    painter.setPen(QPen(QColor(40, 40, 50, 100), 1))
                    painter.drawRect(gx * self.zoom, gy * self.zoom, self.zoom, self.zoom)

        # Draw center pixel crosshair / highlight
        center_rect = QRect(half * self.zoom, half * self.zoom, self.zoom, self.zoom)
        painter.setPen(QPen(QColor(255, 60, 60), 2))
        painter.drawRect(center_rect)


class MagnifierWidget(QFrame):
    """Complete magnifier panel with enlarged canvas and coordinate/RGB readout."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("background-color: #23232b; border: 1px solid #3d3d4b; border-radius: 6px; padding: 4px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        title = QLabel("🔍 정밀 돋보기 (Loupe)")
        title.setStyleSheet("font-weight: bold; font-size: 9pt; color: #7aa2f7;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        self.canvas = MagnifierCanvas(grid_size=11, zoom=14)
        layout.addWidget(self.canvas, 0, Qt.AlignCenter)

        # Readout labels
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        self.lbl_coord = QLabel("좌표: (0, 0)")
        self.lbl_coord.setStyleSheet("font-size: 8.5pt; color: #cfcbe6; font-family: monospace;")
        self.lbl_coord.setAlignment(Qt.AlignCenter)

        self.lbl_rgb = QLabel("RGB: (0, 0, 0)")
        self.lbl_rgb.setStyleSheet("font-size: 8.5pt; font-weight: bold; color: #ffffff; font-family: monospace;")
        self.lbl_rgb.setAlignment(Qt.AlignCenter)

        self.lbl_hex = QLabel("HEX: #000000")
        self.lbl_hex.setStyleSheet("font-size: 8pt; color: #a9b1d6; font-family: monospace;")
        self.lbl_hex.setAlignment(Qt.AlignCenter)

        info_layout.addWidget(self.lbl_coord)
        info_layout.addWidget(self.lbl_rgb)
        info_layout.addWidget(self.lbl_hex)

        layout.addLayout(info_layout)

    def set_position(self, image: Optional[QImage], x: int, y: int):
        self.canvas.update_pixel_data(image, x, y)
        r, g, b = self.canvas.center_rgb
        self.lbl_coord.setText(f"상대 좌표: ({x}, {y})")
        self.lbl_rgb.setText(f"RGB: ({r}, {g}, {b})")
        self.lbl_hex.setText(f"HEX: #{r:02X}{g:02X}{b:02X}")
