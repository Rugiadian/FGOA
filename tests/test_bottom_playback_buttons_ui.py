"""
Tests for bottom scenario playback buttons UI styling and interactivity:
1. Playback buttons (btn_run, btn_run_selected, btn_pause, btn_stop, btn_step)
   have substantial click targets (min-height >= 30px) and PointingHandCursor.
2. btn_step has objectName "btn_step" and dedicated styling in both light and dark themes.
3. Theme stylesheet contains full hover/pressed/disabled states for all playback buttons.
4. Secondary controls (checkboxes, anti-ban, anti-burn test) have PointingHandCursor.
"""
import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from ui.main_window import MainWindow
from ui.theme import get_stylesheet

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)


class TestBottomPlaybackButtonsUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.win = MainWindow()

    @classmethod
    def tearDownClass(cls):
        cls.win.close()

    def test_01_playback_button_sizes_and_cursors(self):
        """Verify playback buttons have prominent minimum height and pointing hand cursor."""
        playback_buttons = [
            self.win.btn_run,
            self.win.btn_run_selected,
            self.win.btn_pause,
            self.win.btn_stop,
            self.win.btn_step,
        ]
        for btn in playback_buttons:
            self.assertGreaterEqual(
                btn.minimumHeight(), 30,
                f"Button {btn.objectName() or btn.text()} minimum height should be at least 30px"
            )
            self.assertEqual(
                btn.cursor().shape(), Qt.PointingHandCursor,
                f"Button {btn.objectName() or btn.text()} should have PointingHandCursor"
            )

    def test_02_btn_step_object_name(self):
        """Verify btn_step has explicit objectName for theme styling."""
        self.assertEqual(self.win.btn_step.objectName(), "btn_step")

    def test_03_theme_styles_include_playback_buttons(self):
        """Verify theme stylesheet contains complete styles for btn_step and playback buttons."""
        for mode in ("light", "dark"):
            css = get_stylesheet(mode)
            self.assertIn("QPushButton#btn_run", css)
            self.assertIn("QPushButton#btn_run_selected", css)
            self.assertIn("QPushButton#btn_pause", css)
            self.assertIn("QPushButton#btn_stop", css)
            self.assertIn("QPushButton#btn_step", css)
            self.assertIn("QPushButton#btn_step:hover", css)
            self.assertIn("QPushButton#btn_step:pressed", css)
            self.assertIn("QPushButton#btn_step:disabled", css)
            self.assertIn("QPushButton#btn_prevent_screensaver", css)

    def test_04_bottom_bar_secondary_controls_cursor(self):
        """Verify checkboxes and secondary buttons have interactive hand cursors."""
        self.assertEqual(self.win.chk_action_overlay.cursor().shape(), Qt.PointingHandCursor)
        self.assertEqual(self.win.chk_floating_stop.cursor().shape(), Qt.PointingHandCursor)
        self.assertEqual(self.win.chk_background_mode.cursor().shape(), Qt.PointingHandCursor)
        self.assertEqual(self.win.chk_anti_burn.cursor().shape(), Qt.PointingHandCursor)
        self.assertEqual(self.win.btn_anti_ban.cursor().shape(), Qt.PointingHandCursor)
        self.assertEqual(self.win.btn_test_anti_burn.cursor().shape(), Qt.PointingHandCursor)
        self.assertEqual(self.win.btn_prevent_screensaver.cursor().shape(), Qt.PointingHandCursor)


if __name__ == "__main__":
    unittest.main()
