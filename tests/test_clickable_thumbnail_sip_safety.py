"""
Test SIP Catcher Safety for Clickable Labels and Image Preview.
Verifies that clicking thumbnails in the scenario table or previews
does not trigger 'TypeError: invalid argument to sipBadCatcherResult()'.
"""
import os
import unittest
from unittest.mock import MagicMock, patch

from PyQt5.QtWidgets import QApplication, QLabel, QWidget
from PyQt5.QtCore import Qt, QPointF, QEvent
from PyQt5.QtGui import QMouseEvent, QPixmap

from ui.clickable_thumbnail import ClickableLabel, ClickableThumbnailLabel
from ui.image_preview_dialog import show_image_preview, ImagePreviewDialog


class TestClickableThumbnailSipSafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def setUp(self):
        import ui.image_preview_dialog as ipd
        if ipd._active_preview_dialog is not None:
            try:
                ipd._active_preview_dialog._remove_filter()
                ipd._active_preview_dialog.close()
            except Exception:
                pass
            ipd._active_preview_dialog = None

    def test_clickable_label_inherits_qlabel(self):
        """ClickableLabel should inherit from QLabel and have clicked signal."""
        self.assertTrue(issubclass(ClickableLabel, QLabel))
        self.assertTrue(issubclass(ClickableThumbnailLabel, ClickableLabel))

    def test_clickable_label_emits_clicked_and_returns_none(self):
        """Clicking ClickableLabel emits clicked signal and mousePressEvent returns None."""
        lbl = ClickableLabel()
        clicked_fired = []
        lbl.clicked.connect(lambda: clicked_fired.append(True))

        ev = QMouseEvent(QEvent.MouseButtonPress, QPointF(10, 10), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)

        # Dispatch via Qt event system - must NOT raise TypeError: invalid argument to sipBadCatcherResult()
        self.app.sendEvent(lbl, ev)

        self.assertEqual(len(clicked_fired), 1)

    def test_show_image_preview_returns_none(self):
        """show_image_preview helper should return None to prevent bad catcher return values."""
        with patch.object(ImagePreviewDialog, "show"), \
             patch.object(ImagePreviewDialog, "raise_"), \
             patch.object(ImagePreviewDialog, "activateWindow"):
            ret = show_image_preview("non_existent_dummy_path.png")
            self.assertIsNone(ret)

    def test_clickable_label_with_preview_slot_no_sip_bad_catcher(self):
        """Simulate table controller scenario: ClickableLabel connected to show_image_preview."""
        lbl = ClickableLabel()
        opened_paths = []

        def mock_show(p, **kwargs):
            opened_paths.append(p)
            return None

        with patch("ui.main_window_parts.table_controller.show_image_preview", side_effect=mock_show):
            lbl.clicked.connect(lambda: mock_show("test_img.png"))

            ev = QMouseEvent(QEvent.MouseButtonPress, QPointF(10, 10), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
            self.app.sendEvent(lbl, ev)

        self.assertEqual(opened_paths, ["test_img.png"])

    def test_table_controller_cell_thumbnail_uses_clickable_label(self):
        """Verify that table controller uses ClickableLabel instead of monkey-patching mousePressEvent."""
        from ui.main_window_parts.table_controller import MainWindowTableMixin
        import inspect

        source = inspect.getsource(MainWindowTableMixin)
        # Ensure monkey-patching mousePressEvent = lambda is NOT present
        self.assertNotIn("lbl_thumb.mousePressEvent = lambda", source)
        self.assertIn("lbl_thumb = ClickableLabel()", source)
        self.assertIn("lbl_thumb.clicked.connect", source)


if __name__ == "__main__":
    unittest.main()
