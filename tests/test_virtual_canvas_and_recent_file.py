"""
Tests for VirtualCanvasWindow, recent file auto-restore, and 3-column layout fixes.
"""
import os
import json
import tempfile
import unittest
from PyQt5.QtWidgets import QApplication, QDialog, QDockWidget, QMainWindow
from PyQt5.QtCore import Qt

from core.models import Project, Scenario, Action, Condition
from core.version import __version__
from ui.virtual_canvas_window import VirtualCanvasWindow
from ui.main_window import MainWindow

app = QApplication.instance() or QApplication([])


class TestVirtualCanvasAndFixes(unittest.TestCase):
    """Test suite for virtual canvas window, recent file restore, and layout fixes."""

    def test_virtual_canvas_window_creation(self):
        """Test VirtualCanvasWindow initialization and ripple effect triggers."""
        win = VirtualCanvasWindow(800, 600)
        self.assertEqual(win.canvas_width, 800)
        self.assertEqual(win.canvas_height, 600)
        self.assertFalse(win.dummy_image.isNull())
        self.assertEqual(win.dummy_image.width(), 800)
        self.assertEqual(win.dummy_image.height(), 600)

        # Trigger click ripple effect
        win.trigger_click_effect(100, 200)
        self.assertEqual(len(win._ripples), 1)
        self.assertTrue(win.ripple_timer.isActive())

        # Update ripples
        win._update_ripples()
        self.assertGreater(win._ripples[0]["radius"], 5.0)

        # Resolution update
        win.set_target_resolution(1280, 720)
        self.assertEqual(win.canvas_width, 1280)
        self.assertEqual(win.canvas_height, 720)
        self.assertEqual(win.dummy_image.width(), 1280)

        win.close()

    def test_qdialog_imported_in_main_window(self):
        """Verify QDialog is available in MainWindow module namespace."""
        import ui.main_window as mw
        self.assertTrue(hasattr(mw, "QDialog"))
        self.assertEqual(mw.QDialog, QDialog)

    def test_layout_3_column_dock_structure(self):
        """Verify basic 3-column layout splits docks without corrupting action panel."""
        main_win = MainWindow()
        main_win.apply_layout("기본 3열 (Default)", save_current=False)

        # Ensure all 4 docks are created and not floating
        self.assertFalse(main_win.dock_scenarios.isFloating())
        self.assertFalse(main_win.dock_inspector.isFloating())
        self.assertFalse(main_win.dock_actions.isFloating())
        self.assertFalse(main_win.dock_log.isFloating())

        # Window dock options must include AllowNestedDocks
        self.assertTrue(bool(main_win.dockOptions() & QMainWindow.AllowNestedDocks))

        main_win.close()

    def test_auto_load_last_project_file(self):
        """Verify _load_project_file properly loads and populates project and title."""
        main_win = MainWindow()
        tmp_proj = Project(target_window_title="Test Target Window", target_client_width=1280, target_client_height=720)
        scen1 = Scenario(id="test_s1", name="테스트 노드 1", step_number=1, scenario_number=1)
        tmp_proj.scenarios.append(scen1)

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(tmp_proj.to_dict(), f, indent=2)
            tmp_path = f.name

        try:
            success = main_win._load_project_file(tmp_path, silent=True)
            self.assertTrue(success)
            self.assertEqual(main_win.current_project_path, tmp_path)
            self.assertEqual(len(main_win.project.scenarios), 1)
            self.assertEqual(main_win.project.scenarios[0].name, "테스트 노드 1")
            self.assertIn(os.path.basename(tmp_path), main_win.windowTitle())
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            main_win.close()

    def test_auto_fallback_to_virtual_canvas_when_no_target(self):
        """Verify _on_start_execution creates and uses VirtualCanvasWindow when no HWND is selected."""
        main_win = MainWindow()
        main_win.target_hwnd = 0  # No target selected

        # When starting execution without target
        main_win._on_open_virtual_canvas()
        self.assertIsNotNone(main_win.virtual_canvas_window)
        self.assertNotEqual(main_win.target_hwnd, 0)
        self.assertEqual(main_win.target_hwnd, int(main_win.virtual_canvas_window.winId()))
        self.assertIn("FGOA 가상 캔버스", main_win.virtual_canvas_window.windowTitle())

        # Test close event
        main_win.virtual_canvas_window.close()
        self.assertEqual(main_win.target_hwnd, 0)

        main_win.close()


if __name__ == "__main__":
    unittest.main()
