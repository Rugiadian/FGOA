"""
Unit tests for Reference Gallery resolution classification & filtering.
"""
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from PIL import Image
from PyQt5.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from core.models import Project, Scenario, Condition
from ui.reference_gallery_dialog import ReferenceGalleryDialog


class TestReferenceGalleryResolution(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        # Create 3 images with different resolutions
        self.p_1600 = os.path.join(self.tmp_dir, "ref_1600x900.png")
        self.p_1920 = os.path.join(self.tmp_dir, "ref_1920x1080.png")
        self.p_1280 = os.path.join(self.tmp_dir, "ref_1280x720.png")

        Image.new("RGB", (1600, 900), color="blue").save(self.p_1600)
        Image.new("RGB", (1920, 1080), color="red").save(self.p_1920)
        Image.new("RGB", (1280, 720), color="green").save(self.p_1280)

    def tearDown(self):
        for p in (self.p_1600, self.p_1920, self.p_1280):
            if os.path.exists(p):
                os.remove(p)
        if os.path.exists(self.tmp_dir):
            os.rmdir(self.tmp_dir)

    def test_resolution_classification_and_filtering(self):
        proj = Project()
        # Scenario using the 1600x900 image
        scen = Scenario(id="s1", condition=Condition(reference_image_path=self.p_1600))
        proj.scenarios = [scen]

        # Mock REFS_DIR to point to tmp_dir
        with patch("ui.reference_gallery_dialog.REFS_DIR", self.tmp_dir):
            with patch("core.window_manager.WindowManager.get_window_info", return_value=MagicMock(client_width=1600, client_height=900)):
                dlg = ReferenceGalleryDialog(project=proj, target_hwnd=9999)

                # 1. Check combo_resolution population
                res_items = [dlg.combo_resolution.itemData(i) for i in range(dlg.combo_resolution.count())]
                self.assertIn("all", res_items)
                self.assertIn("1600×900", res_items)
                self.assertIn("1920×1080", res_items)
                self.assertIn("1280×720", res_items)

                # Check label has [현재 타겟] for 1600x900
                idx_1600 = dlg.combo_resolution.findData("1600×900")
                self.assertIn("현재 타겟", dlg.combo_resolution.itemText(idx_1600))

                # 2. Check total items when 'all' is selected
                self.assertEqual(dlg.list_widget.count(), 3)

                # 3. Filter by 1920x1080
                idx_1920 = dlg.combo_resolution.findData("1920×1080")
                dlg.combo_resolution.setCurrentIndex(idx_1920)
                self.assertEqual(dlg.list_widget.count(), 1)
                entry = dlg.list_widget.item(0).data(0x0100) # Qt.UserRole
                self.assertEqual(entry["width"], 1920)
                self.assertEqual(entry["height"], 1080)
                self.assertIn("[1920×1080]", dlg.list_widget.item(0).text())

                # 4. Filter by 1600x900 (matches target)
                dlg.combo_resolution.setCurrentIndex(idx_1600)
                self.assertEqual(dlg.list_widget.count(), 1)
                self.assertIn("일치 ✅", dlg.lbl_res_banner.text())
                self.assertIn("일치 ✅", dlg.lbl_info.text())

                # 5. Filter by used images within 1600x900
                idx_used = dlg.combo_filter.findData("used")
                dlg.combo_filter.setCurrentIndex(idx_used)
                self.assertEqual(dlg.list_widget.count(), 1)

                # Filter by unused within 1600x900 -> 0
                idx_unused = dlg.combo_filter.findData("unused")
                dlg.combo_filter.setCurrentIndex(idx_unused)
                self.assertEqual(dlg.list_widget.count(), 0)

                dlg.close()


if __name__ == "__main__":
    unittest.main()
