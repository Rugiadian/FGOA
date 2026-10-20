"""
Image Preview Dialog for FGOA.
Displays reference snapshots or captured images at full size / responsive high resolution.
"""
import os
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy
)
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt


class ImagePreviewDialog(QDialog):
    """
    Modal dialog that displays an image enlarged with zoom/scroll capabilities,
    showing resolution and file info.
    """
    def __init__(self, image_path: str, title: str = "📸 이미지 크게 보기", parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.setWindowTitle(title)
        self.resize(880, 640)
        self.setMinimumSize(400, 300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Header bar: filename and resolution
        hdr_layout = QHBoxLayout()
        hdr_layout.setSpacing(8)

        filename = os.path.basename(image_path) if image_path else "이미지"
        self.lbl_title = QLabel(f"<b>파일명:</b> {filename}")
        self.lbl_title.setStyleSheet("font-size: 9.5pt;")
        hdr_layout.addWidget(self.lbl_title)

        self.lbl_res = QLabel("")
        self.lbl_res.setStyleSheet("color: #64748b; font-size: 9pt;")
        hdr_layout.addWidget(self.lbl_res)

        hdr_layout.addStretch()

        btn_close = QPushButton("✕ 닫기")
        btn_close.clicked.connect(self.accept)
        btn_close.setFixedWidth(80)
        hdr_layout.addWidget(btn_close)

        layout.addLayout(hdr_layout)

        # Scroll area containing the enlarged image
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setAlignment(Qt.AlignCenter)
        scroll.setStyleSheet("QScrollArea { background-color: #0b0f19; border: 1px solid #334155; border-radius: 4px; }")

        self.lbl_image = QLabel()
        self.lbl_image.setAlignment(Qt.AlignCenter)
        self.lbl_image.setStyleSheet("background-color: transparent;")

        if image_path and os.path.isfile(image_path):
            pix = QPixmap(image_path)
            if not pix.isNull():
                self.lbl_res.setText(f"({pix.width()} × {pix.height()} px)")
                self.lbl_image.setPixmap(pix)
            else:
                self.lbl_image.setText("이미지를 불러올 수 없습니다.")
                self.lbl_image.setStyleSheet("color: #ef4444; font-size: 10pt;")
        else:
            self.lbl_image.setText("등록된 이미지 파일이 존재하지 않습니다.")
            self.lbl_image.setStyleSheet("color: #64748b; font-size: 10pt;")

        scroll.setWidget(self.lbl_image)
        layout.addWidget(scroll, 1)


def show_image_preview(image_path: str, title: str = "📸 이미지 크게 보기", parent=None):
    """Convenience helper to show enlarged image in a non-blocking modal dialog."""
    dlg = ImagePreviewDialog(image_path, title=title, parent=parent)
    dlg.exec_()
