"""
Clickable Thumbnail Label Widget for FGOA.
(레퍼런스 이미지 클릭 가능한 썸네일 위젯)
"""
import os
from typing import Optional

from PyQt5.QtWidgets import QLabel
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap


class ClickableThumbnailLabel(QLabel):
    """
    Compact clickable 50px thumbnail widget for reference images.
    Preserves aspect ratio and scales smoothly to width 50px.
    """
    clicked = pyqtSignal()

    def __init__(self, border_color: str = "#3b82f6", tooltip: str = "", parent=None):
        super().__init__(parent)
        self.border_color = border_color
        self.setFixedWidth(50)
        self.setFixedHeight(30)
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(tooltip)
        self.setStyleSheet(
            f"QLabel {{ border: 1.5px solid {self.border_color}; border-radius: 4px; background-color: #0f172a; }} "
            f"QLabel:hover {{ border: 2px solid #60a5fa; background-color: #1e293b; }}"
        )
        self.image_path: Optional[str] = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def set_image(self, path: Optional[str], hide_on_empty: bool = True, max_w: Optional[int] = None, max_h: Optional[int] = None) -> bool:
        """Sets and scales reference image. If hide_on_empty is False, displays a clean placeholder when empty."""
        self.image_path = path
        target_w = max_w if max_w else (self.width() if self.width() > 0 else 50)
        target_h = max_h if max_h else (self.height() if self.height() > 0 else 30)

        if path and os.path.isfile(path):
            pix = QPixmap(path)
            if not pix.isNull():
                scaled = pix.scaled(target_w, target_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.setPixmap(scaled)
                self.setStyleSheet(
                    f"QLabel {{ border: 1.5px solid {self.border_color}; border-radius: 4px; background-color: #0f172a; }} "
                    f"QLabel:hover {{ border: 2px solid #60a5fa; background-color: #1e293b; }}"
                )
                self.show()
                return True

        self.clear()
        if hide_on_empty:
            self.hide()
            return False
        else:
            self.setStyleSheet(
                f"QLabel {{ border: 1.5px dashed #475569; border-radius: 4px; background-color: #0f172a; color: #64748b; font-size: 8pt; }} "
                f"QLabel:hover {{ border: 1.5px dashed #94a3b8; background-color: #1e293b; color: #94a3b8; }}"
            )
            self.setText("빈칸")
            self.show()
            return False
