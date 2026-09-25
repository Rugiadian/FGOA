"""
Unit tests for loop node warnings, paired coloring, playback start buttons,
single-step pointer advancement, and running row header cell coloring.
"""
import sys
import unittest
from unittest.mock import patch
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QColor, QPixmap
from PyQt5.QtCore import Qt

from core.models import Project, Scenario
from ui.main_window import MainWindow, ScenarioVerticalHeader, DraggableScenarioTableWidget
from ui.reference_gallery_dialog import ReferenceGalleryDialog


class TestLoopPlaybackAndPointer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if not cls.app:
            cls.app = QApplication(sys.argv)

    def test_reference_gallery_focus_on_select_path(self):
        """Verify that refresh_gallery focuses and selects the requested select_path."""
        proj = Project()
        dummy_path = "C:/fake/path/test_img_focus.png"
        mock_entries = [
            {"path": "C:/fake/path/img1.png", "filename": "img1.png", "width": 1600, "height": 900, "size_kb": 120.0, "is_used": False, "usages": []},
            {"path": dummy_path, "filename": "test_img_focus.png", "width": 1600, "height": 900, "size_kb": 150.0, "is_used": True, "usages": []},
            {"path": "C:/fake/path/img3.png", "filename": "img3.png", "width": 1600, "height": 900, "size_kb": 110.0, "is_used": False, "usages": []},
        ]
        with patch.object(ReferenceGalleryDialog, "get_all_gallery_entries", return_value=mock_entries):
            dlg = ReferenceGalleryDialog(proj)
            dlg.refresh_gallery(select_path=dummy_path)
            selected_items = dlg.list_widget.selectedItems()
            self.assertEqual(len(selected_items), 1)
            item_entry = selected_items[0].data(Qt.UserRole)
            self.assertEqual(item_entry["path"], dummy_path)

    def test_loop_pairing_and_warning_detection(self):
        """Verify loop pairing, distinct coloring, and missing pair warning generation."""
        proj = Project()
        # Nested loops:
        # 0: outer_start
        # 1: inner_start
        # 2: inner_end (paired with 1)
        # 3: outer_end (paired with 0)
        # 4: orphan_end (missing start)
        # 5: orphan_start (missing end)
        s0 = Scenario(id="outer_start", node_type="loop_start", name="외곽 루프 시작")
        s1 = Scenario(id="inner_start", node_type="loop_start", name="내부 루프 시작")
        s2 = Scenario(id="inner_end", node_type="loop_end", name="내부 루프 종료")
        s3 = Scenario(id="outer_end", node_type="loop_end", name="외곽 루프 종료")
        s4 = Scenario(id="orphan_end", node_type="loop_end", name="짝 없는 종료")
        s5 = Scenario(id="orphan_start", node_type="loop_start", name="짝 없는 시작")

        proj.scenarios = [s0, s1, s2, s3, s4, s5]
        analysis = proj.analyze_loops()

        # s0 (index 0) and s3 (index 3) should be paired (outer pair)
        info_s0 = analysis[0]
        self.assertTrue(info_s0["has_pair"])
        self.assertEqual(info_s0["partner_index"], 3)
        self.assertTrue(bool(info_s0["color_light"]))
        self.assertIsNone(info_s0["warning"])

        # s1 (index 1) and s2 (index 2) should be paired (inner pair)
        info_s1 = analysis[1]
        self.assertTrue(info_s1["has_pair"])
        self.assertEqual(info_s1["partner_index"], 2)
        self.assertTrue(bool(info_s1["color_light"]))
        self.assertIsNone(info_s1["warning"])

        # Colors for different pairs should be distinct
        self.assertNotEqual(info_s0["color_light"], info_s1["color_light"])

        # s4 (index 4: orphan_end) is missing start pair
        info_s4 = analysis[4]
        self.assertFalse(info_s4["has_pair"])
        self.assertIn("시작 노드 없음", info_s4["warning"])

        # s5 (index 5: orphan_start) is missing end pair
        info_s5 = analysis[5]
        self.assertFalse(info_s5["has_pair"])
        self.assertIn("종료 노드 없음", info_s5["warning"])

    def test_scenario_table_loop_rendering(self):
        """Verify scenario table displays loop colors and warning indicators."""
        win = MainWindow()
        s_start = Scenario(id="s_start", node_type="loop_start", name="루프1")
        s_end = Scenario(id="s_end", node_type="loop_end", name="루프1종료")
        s_unmatched = Scenario(id="s_orphan", node_type="loop_end", name="고아루프")
        win.project.scenarios = [s_start, s_end, s_unmatched]
        win.project.renumber_steps()
        win._refresh_scenario_table()

        # Row 2 (orphan) should display warning
        item_orphan = win.tbl_scenarios.item(2, 3)
        self.assertIn("루프 짝 없음", item_orphan.text())

    def test_playback_buttons_and_signals(self):
        """Verify presence and wiring of Full Start and Selected Start buttons."""
        win = MainWindow()
        self.assertTrue(hasattr(win, "btn_run"))
        self.assertTrue(hasattr(win, "btn_run_selected"))
        self.assertEqual(win.btn_run.text(), "▶ 전체 시작 (F5)")
        self.assertEqual(win.btn_run_selected.text(), "▶ 선택부터 시작 (Shift+F5)")

    def test_step_pointer_advancement(self):
        """Verify that _on_step_completed advances table row selection and header highlight."""
        win = MainWindow()
        s1 = Scenario(id="s1", name="Step 1")
        s2 = Scenario(id="s2", name="Step 2")
        s3 = Scenario(id="s3", name="Step 3")
        win.project.scenarios = [s1, s2, s3]
        win.project.renumber_steps()
        win._refresh_scenario_table()

        win.tbl_scenarios.selectRow(0)
        self.assertEqual(win.tbl_scenarios.currentRow(), 0)

        # Trigger step completion pointing to next index (1)
        win._on_step_completed(1)
        self.assertEqual(win.tbl_scenarios.currentRow(), 1)
        self.assertEqual(win._current_running_row, 1)

        # Step to index 2
        win._on_step_completed(2)
        self.assertEqual(win.tbl_scenarios.currentRow(), 2)
        self.assertEqual(win._current_running_row, 2)

    def test_vertical_header_highlight_cell_color(self):
        """Verify custom ScenarioVerticalHeader renders emerald green (#16a34a) when highlighted."""
        tbl = DraggableScenarioTableWidget()
        tbl.setRowCount(3)
        tbl.setColumnCount(2)
        hdr = tbl.verticalHeader()
        self.assertIsInstance(hdr, ScenarioVerticalHeader)

        tbl.set_highlight_row(1)
        self.assertEqual(hdr.highlight_row, 1)

        tbl.show()
        pix = QPixmap(hdr.size())
        hdr.render(pix)
        img = pix.toImage()

        found_emerald = False
        for y in range(img.height()):
            for x in range(img.width()):
                if img.pixelColor(x, y).name() == "#16a34a":
                    found_emerald = True
                    break
            if found_emerald:
                break
        self.assertTrue(found_emerald, "Emerald green color #16a34a should be painted on running header row.")


if __name__ == "__main__":
    unittest.main()
