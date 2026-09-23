"""
Test suite for FGOA Version Management and Window Title Display.
"""
import re
import unittest
from PyQt5.QtWidgets import QApplication

import core
from core.version import __version__
from ui.main_window import MainWindow

# Ensure single QApplication instance for tests
app = QApplication.instance()
if app is None:
    app = QApplication([])


class TestVersionManagement(unittest.TestCase):
    """Verifies version formatting, packaging exports, and window title display."""

    def test_version_format_and_export(self):
        """Version must follow YYYY.MM.DD.HHMM simple date-time format."""
        self.assertIsInstance(__version__, str)
        self.assertEqual(core.__version__, __version__)

        pattern = r"^\d{4}\.\d{2}\.\d{2}\.\d{4}$"
        self.assertRegex(
            __version__,
            pattern,
            f"Version '{__version__}' does not match expected YYYY.MM.DD.HHMM format."
        )

    def test_window_title_displays_version(self):
        """MainWindow title must display the app version."""
        window = MainWindow()
        title = window.windowTitle()

        expected_prefix = f"FGOA v{__version__}"
        self.assertTrue(
            title.startswith(expected_prefix),
            f"Expected window title to start with '{expected_prefix}', got '{title}'"
        )
        self.assertIn("화면 인식 스마트 윈도우 오토 툴", title)

    def test_window_title_with_project_path(self):
        """MainWindow title should update to include project file name."""
        window = MainWindow()
        window.current_project_path = r"C:\path\to\my_custom_project.json"
        window._update_window_title()

        title = window.windowTitle()
        self.assertIn(f"FGOA v{__version__}", title)
        self.assertIn("[my_custom_project.json]", title)

        window.current_project_path = None
        window._update_window_title()
        self.assertEqual(window.windowTitle(), f"FGOA v{__version__} - 화면 인식 스마트 윈도우 오토 툴")


if __name__ == "__main__":
    unittest.main()
