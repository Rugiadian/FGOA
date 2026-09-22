"""
Tests for ui/qt_image_utils.py and CoordinatePickerDialog image loading.
"""
import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from PIL import Image
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QImage, QPixmap
from unittest.mock import patch

from ui.qt_image_utils import (
    pil_to_qimage,
    pil_to_qpixmap,
    qimage_to_pil,
    qpixmap_to_pil,
    ImageQt,
    toqimage,
    toqpixmap,
    fromqimage,
    fromqpixmap,
)
from ui.coordinate_picker_dialog import CoordinatePickerDialog

# Ensure single QApplication instance for tests
app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)


class TestQtImageUtils(unittest.TestCase):
    def test_pil_to_qimage_and_qpixmap(self):
        pil_img = Image.new("RGB", (64, 48), color=(255, 128, 0))
        qimg = pil_to_qimage(pil_img)
        self.assertFalse(qimg.isNull())
        self.assertEqual(qimg.width(), 64)
        self.assertEqual(qimg.height(), 48)

        pixmap = pil_to_qpixmap(pil_img)
        self.assertFalse(pixmap.isNull())
        self.assertEqual(pixmap.width(), 64)
        self.assertEqual(pixmap.height(), 48)

    def test_qimage_to_pil(self):
        qimg = QImage(32, 24, QImage.Format_RGB32)
        qimg.fill(0xFF112233)
        pil_img = qimage_to_pil(qimg)
        self.assertIsNotNone(pil_img)
        self.assertEqual(pil_img.size, (32, 24))

        pixmap = QPixmap.fromImage(qimg)
        pil_img_from_pix = qpixmap_to_pil(pixmap)
        self.assertIsNotNone(pil_img_from_pix)
        self.assertEqual(pil_img_from_pix.size, (32, 24))

    def test_roundtrip_color_fidelity(self):
        orig_img = Image.new("RGBA", (10, 10), color=(100, 150, 200, 255))
        qimg = pil_to_qimage(orig_img)
        recovered_img = qimage_to_pil(qimg)
        self.assertEqual(recovered_img.size, (10, 10))
        self.assertEqual(recovered_img.getpixel((5, 5)), (100, 150, 200, 255))

    def test_dropin_compatibility_functions(self):
        pil_img = Image.new("RGB", (20, 20), color=(0, 255, 0))
        # ImageQt class
        iq = ImageQt(pil_img)
        self.assertFalse(iq.isNull())
        self.assertEqual(iq.width(), 20)

        # Static methods
        back_pil = ImageQt.fromqimage(iq)
        self.assertIsNotNone(back_pil)
        self.assertEqual(back_pil.size, (20, 20))

        # Module-level aliases
        tq = toqimage(pil_img)
        tqp = toqpixmap(pil_img)
        self.assertFalse(tq.isNull())
        self.assertFalse(tqp.isNull())
        fq = fromqimage(tq)
        fqp = fromqpixmap(tqp)
        self.assertEqual(fq.size, (20, 20))
        self.assertEqual(fqp.size, (20, 20))

    def test_coordinate_picker_dialog_set_image(self):
        dlg = CoordinatePickerDialog(target_hwnd=0)
        test_img = Image.new("RGB", (800, 600), color=(50, 100, 150))
        dlg.canvas.set_image(test_img)
        self.assertIsNotNone(dlg.canvas.pixmap)
        self.assertEqual(dlg.canvas.pixmap.width(), 800)
        self.assertEqual(dlg.canvas.pixmap.height(), 600)

    def test_coordinate_picker_dialog_capture_window(self):
        dlg = CoordinatePickerDialog(target_hwnd=0)
        dlg.target_hwnd = 99999
        with patch("core.screen_capture.ScreenCapture.capture_client_area", return_value=Image.new("RGB", (1280, 720))):
            dlg._capture_target_window()
            self.assertIsNotNone(dlg.canvas.pixmap)
            self.assertEqual(dlg.canvas.pixmap.width(), 1280)
            self.assertEqual(dlg.canvas.pixmap.height(), 720)


if __name__ == "__main__":
    unittest.main()
