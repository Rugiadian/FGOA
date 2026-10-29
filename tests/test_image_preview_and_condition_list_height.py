"""
Unit tests for:
1. Image preview dialog auto-closing when clicking anywhere (inside or outside).
2. Recognition condition table dynamic height sizing to match the number of conditions.
"""
import unittest
import os
import tempfile
import sys
from unittest.mock import patch, MagicMock
from PyQt5.QtWidgets import QApplication, QWidget, QPushButton
from PyQt5.QtCore import Qt, QPoint, QRect, QEvent
from PyQt5.QtGui import QMouseEvent, QPixmap

from core.models import Scenario, Condition, ColorPoint, Project
from ui.image_preview_dialog import ImagePreviewDialog, show_image_preview
from ui.inspector_widget import InspectorWidget
from ui.condition_editor_dialog import ConditionEditorDialog
from ui.widgets.dynamic_table import DynamicPointsTableWidget


class TestImagePreviewAndConditionListHeight(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_01_image_preview_dialog_lifecycle_and_main_window_click_close(self):
        """Verify preview dialog closes when clicking main window, without WH_MOUSE_LL cursor freezing."""
        win = QWidget()
        win.resize(400, 300)
        btn = QPushButton("Target Button", win)
        btn.setGeometry(20, 20, 100, 30)
        win.show()
        self.app.processEvents()

        dlg = ImagePreviewDialog("", parent=win)
        dlg.show()
        self.app.processEvents()

        self.assertTrue(dlg.isVisible())
        # Verify no low-level mouse hook to ensure native cursor smoothness
        self.assertFalse(hasattr(dlg, "_hook") and dlg._hook is not None)

        # Simulate click on main window button -> closes dialog
        click_ev = QMouseEvent(QEvent.MouseButtonPress, QPoint(10, 10), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        self.app.sendEvent(btn, click_ev)
        self.app.processEvents()

        self.assertFalse(dlg.isVisible())
        self.assertEqual(dlg.result(), 1)
        win.close()

    def test_02_image_preview_deactivation_closes_dialog(self):
        """Verify window deactivation event triggers accept/close."""
        dlg = ImagePreviewDialog("")
        dlg.show()
        self.app.processEvents()

        # Activating another window deactivates dlg
        other = QWidget()
        other.show()
        other.activateWindow()
        self.app.processEvents()

        self.assertEqual(dlg.result(), 1)  # QDialog.Accepted is 1
        other.close()

    def test_03_image_preview_open_folder_button_keeps_dialog_open(self):
        """Verify clicking the Open Folder button does not close dialog prematurely."""
        dlg = ImagePreviewDialog("")
        dlg.show()
        self.app.processEvents()

        btn = dlg.btn_open_folder
        self.assertIsNotNone(btn)

        # Mouse click directly on btn_open_folder
        ev = QMouseEvent(QEvent.MouseButtonPress, QPoint(5, 5), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        handled = dlg.eventFilter(btn, ev)
        # Should return False (not absorbed, allowed to execute click)
        self.assertFalse(handled)
        self.assertFalse(dlg.isHidden())

        dlg.accept()

    def test_04_dynamic_points_table_widget_calculations(self):
        """Verify DynamicPointsTableWidget calculates correct ideal heights for various row counts."""
        tbl = DynamicPointsTableWidget()
        tbl.setColumnCount(6)
        tbl.verticalHeader().setDefaultSectionSize(24)

        # 0 rows
        tbl.setRowCount(0)
        h0 = tbl.calculate_ideal_height()
        self.assertGreater(h0, 20)
        self.assertLess(h0, 45)

        # 1 row
        tbl.setRowCount(1)
        h1 = tbl.calculate_ideal_height()
        self.assertEqual(h1, h0 + 24)

        # 3 rows
        tbl.setRowCount(3)
        h3 = tbl.calculate_ideal_height()
        self.assertEqual(h3, h0 + 72)

        # Verify update_dynamic_height sets minimumHeight
        tbl.update_dynamic_height()
        self.assertEqual(tbl.minimumHeight(), h3)
        self.assertGreater(tbl.maximumHeight(), 1000)

    def test_05_inspector_condition_table_height_scales_with_conditions(self):
        """Verify InspectorWidget tbl_points height is compact for 1 point and grows with 3 points."""
        proj = Project()
        scen = Scenario(id="s1", scenario_number=1, name="Test Scenario")
        cond = Condition(id="c1", name="Test Condition")
        cond.points = [ColorPoint(x=100, y=100, r=255, g=0, b=0)]
        scen.condition = cond
        proj.scenarios = [scen]

        inspector = InspectorWidget()
        inspector.set_project(proj)
        inspector.set_scenario(scen)
        inspector.resize(400, 800)
        inspector.show()
        self.app.processEvents()

        h_single = inspector.tbl_points.height()
        # Single point condition should be very compact (~53px), definitely < 80px
        self.assertLess(h_single, 80, f"Expected height < 80px for 1 point, got {h_single}")
        self.assertGreater(inspector.tbl_points.maximumHeight(), 1000)

        # Add 2 more points
        inspector.current_scenario.condition.points.append(ColorPoint(x=150, y=150, r=0, g=255, b=0))
        inspector.current_scenario.condition.points.append(ColorPoint(x=200, y=200, r=0, g=0, b=255))
        inspector._refresh_points_table()
        self.app.processEvents()

        h_triple = inspector.tbl_points.height()
        self.assertGreater(h_triple, h_single, f"Expected h_triple ({h_triple}) > h_single ({h_single})")
        self.assertLess(h_triple, 160)

        # Remove points back to 1
        inspector.current_scenario.condition.points.pop()
        inspector.current_scenario.condition.points.pop()
        inspector._refresh_points_table()
        self.app.processEvents()

        h_reduced = inspector.tbl_points.height()
        self.assertEqual(h_reduced, h_single)

    def test_06_condition_editor_dialog_table_height_scales_with_conditions(self):
        """Verify ConditionEditorDialog tbl_points height is compact for 1 point and grows with 3 points."""
        proj = Project()
        cond = Condition(id="c2", name="Dialog Condition")
        cond.points = [ColorPoint(x=50, y=50, r=100, g=150, b=200)]

        dlg = ConditionEditorDialog(condition=cond, project=proj, current_scenario_id="s1", target_hwnd=0)
        dlg.show()
        self.app.processEvents()

        h_single = dlg.tbl_points.height()
        self.assertLess(h_single, 90, f"Expected height < 90px for 1 point, got {h_single}")

        # Add 2 points
        dlg.condition.points.append(ColorPoint(x=60, y=60, r=10, g=20, b=30))
        dlg.condition.points.append(ColorPoint(x=70, y=70, r=40, g=50, b=60))
        dlg._refresh_points_table()
        self.app.processEvents()

        h_triple = dlg.tbl_points.height()
        self.assertGreater(h_triple, h_single, f"Expected h_triple ({h_triple}) > h_single ({h_single})")

        dlg.reject()


if __name__ == "__main__":
    unittest.main()
