"""
Image Preview Dialog for FGOA.
Displays reference snapshots or captured images at full size / responsive high resolution.
Closes automatically when clicking anywhere (inside or outside the window),
with zero impact on mouse cursor movement or system responsiveness,
and provides a button to open the image's folder.
"""
import os
import subprocess
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QApplication, QScrollBar, QWidget
)
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt, QEvent, QPoint, QRect, QTimer, QEventLoop

_active_preview_dialog = None


class ImagePreviewDialog(QDialog):
    """
    Modeless popup dialog that displays an image enlarged with zoom/scroll capabilities,
    showing resolution and file info.
    Closes automatically on click anywhere - both inside and outside the window
    (except the Open Folder button and scrollbars), with zero mouse-hook lag.
    """
    def __init__(self, image_path: str, title: str = "📸 이미지 크게 보기", parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.setWindowTitle(title)
        self.resize(880, 640)
        self.setMinimumSize(400, 300)

        self._is_opening_folder = False

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

        lbl_hint = QLabel("(아무 곳이나 클릭하면 닫힙니다)")
        lbl_hint.setStyleSheet("color: #94a3b8; font-size: 8.5pt;")
        hdr_layout.addWidget(lbl_hint)

        hdr_layout.addStretch()

        self.btn_open_folder = QPushButton("📁 폴더 열기")
        self.btn_open_folder.setToolTip("이 스크린샷 이미지가 저장된 폴더를 탐색기에서 엽니다.")
        self.btn_open_folder.clicked.connect(self._open_folder)
        hdr_layout.addWidget(self.btn_open_folder)

        btn_close = QPushButton("✕ 닫기")
        btn_close.clicked.connect(self.accept)
        btn_close.setFixedWidth(80)
        hdr_layout.addWidget(btn_close)

        layout.addLayout(hdr_layout)

        # Scroll area containing the enlarged image
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setAlignment(Qt.AlignCenter)
        self.scroll.setStyleSheet("QScrollArea { background-color: #0b0f19; border: 1px solid #334155; border-radius: 4px; }")

        self.lbl_image = QLabel()
        self.lbl_image.setAlignment(Qt.AlignCenter)
        self.lbl_image.setStyleSheet("background-color: transparent;")
        self.lbl_image.setCursor(Qt.PointingHandCursor)

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

        self.scroll.setWidget(self.lbl_image)
        if self.scroll.viewport():
            self.scroll.viewport().setCursor(Qt.PointingHandCursor)
        layout.addWidget(self.scroll, 1)

        # Install application-wide event filter to close dialog on any click in the app
        app = QApplication.instance()
        if app:
            app.installEventFilter(self)

    def changeEvent(self, event):
        """Close automatically when clicking outside the application (window loses activation)."""
        if event.type() in (QEvent.ActivationChange, QEvent.WindowDeactivate):
            if not self.isActiveWindow() and not getattr(self, "_is_opening_folder", False):
                self.accept()
        super().changeEvent(event)

    def eventFilter(self, obj, event):
        """Handle mouse clicks anywhere inside the application to close automatically."""
        if not self.isVisible():
            self._remove_filter()
            return False

        if event.type() == QEvent.MouseButtonPress:
            # 1. Allow clicking the "Open Folder" button without closing prematurely
            if hasattr(self, "btn_open_folder") and not self.btn_open_folder.isHidden():
                try:
                    g_pos = event.globalPos() if hasattr(event, "globalPos") else None
                    if g_pos is not None:
                        btn_rect = QRect(self.btn_open_folder.mapToGlobal(QPoint(0, 0)), self.btn_open_folder.size())
                        if btn_rect.contains(g_pos):
                            return False
                except Exception:
                    pass

                if obj == self.btn_open_folder or (isinstance(obj, QWidget) and self.btn_open_folder.isAncestorOf(obj)):
                    return False

            # 2. Allow dragging/clicking scrollbars
            if isinstance(obj, QScrollBar):
                return False

            # 3. Clicking anywhere else closes the dialog automatically
            self.accept()
            return True

        return super().eventFilter(obj, event)

    def mousePressEvent(self, event):
        self.accept()
        super().mousePressEvent(event)

    def hideEvent(self, event):
        self._remove_filter()
        super().hideEvent(event)

    def closeEvent(self, event):
        self._remove_filter()
        super().closeEvent(event)

    def done(self, r):
        self._remove_filter()
        super().done(r)

    def exec_(self):
        """
        Modeless event-loop wrapper that blocks caller until closed,
        without locking the parent window into Win32 modal state.
        This allows clicking outside on the main window to immediately close the popup.
        """
        self.show()
        self.raise_()
        self.activateWindow()
        loop = QEventLoop()
        self.finished.connect(loop.quit)
        loop.exec_()
        return self.result()

    def _remove_filter(self):
        app = QApplication.instance()
        if app:
            try:
                app.removeEventFilter(self)
            except Exception:
                pass

    def _open_folder(self):
        """Open the folder containing the current screenshot in Windows Explorer."""
        if not self.image_path:
            return
        self._is_opening_folder = True
        QTimer.singleShot(2000, lambda: setattr(self, "_is_opening_folder", False))
        abs_path = os.path.abspath(self.image_path)
        folder = os.path.dirname(abs_path)
        try:
            if os.path.isfile(abs_path):
                subprocess.Popen(f'explorer /select,"{abs_path}"')
            elif os.path.isdir(folder):
                os.startfile(folder)
        except Exception:
            if os.path.isdir(folder):
                try:
                    os.startfile(folder)
                except Exception:
                    pass


def show_image_preview(image_path: str, title: str = "📸 이미지 크게 보기", parent=None):
    """Convenience helper to show enlarged image in an auto-closing popup dialog."""
    global _active_preview_dialog
    if _active_preview_dialog is not None:
        try:
            _active_preview_dialog.close()
        except Exception:
            pass
    dlg = ImagePreviewDialog(image_path, title=title, parent=parent)
    _active_preview_dialog = dlg
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
    return None
