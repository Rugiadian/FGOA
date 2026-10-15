"""
Unit tests for Log Management, Crash Classification, and Error Dialog Bug Fixes.
"""
import os
import sys
import unittest
import tempfile
from PyQt5.QtWidgets import QApplication

from core.log_manager import (
    CrashEntry,
    parse_crash_log,
    classify_crashes,
    archive_and_clean_crash_log,
)
from core.logger import log_crash
from ui.main_window import MainWindow
from ui.preset_dialog import SavePresetDialog
from core.models import Scenario

app = QApplication.instance()
if app is None:
    app = QApplication([])


class TestLogManagerAndFixes(unittest.TestCase):
    def test_crash_entry_parsing(self):
        sample = (
            "======================================================================\n"
            "[FGOA CRASH REPORT - 2026-10-15 12:00:00]\n"
            "FGOA Version: 261015.1200\n"
            "Python: 3.12.0\n"
            "Executable: python.exe\n"
            "Base Dir: G:\\Git\\FGOA\n"
            "Error Type: ValueError\n"
            "Error Message: Sample error message\n"
            "----------------------------------------------------------------------\n"
            "Stack Trace:\n"
            '  File "G:\\Git\\FGOA\\ui\\sample_widget.py", line 42, in sample_func\n'
            "    raise ValueError('Sample error message')\n"
            "======================================================================\n"
        )
        entry = CrashEntry(sample)
        self.assertEqual(entry.error_type, "ValueError")
        self.assertEqual(entry.error_message, "Sample error message")
        self.assertEqual(entry.last_file, "sample_widget.py")
        self.assertEqual(entry.last_line, 42)
        self.assertEqual(entry.last_func, "sample_func")
        self.assertFalse(entry.is_synthetic_test)
        self.assertEqual(entry.signature, "ValueError::sample_widget.py::sample_func")

    def test_classification_synthetic_and_resolved(self):
        synthetic_sample = (
            "[FGOA CRASH REPORT - 2026-10-15 12:00:00]\n"
            "Error Type: KeyError\n"
            "Error Message: 'SyntheticKey_1'\n"
            "Stack Trace:\n"
            '  File "G:\\Git\\FGOA\\tests\\test_dummy.py", line 10, in test_fn\n'
        )
        resolved_sample = (
            "[FGOA CRASH REPORT - 2026-10-15 12:00:00]\n"
            "Error Type: AttributeError\n"
            "Error Message: 'tuple' object has no attribute 'red'\n"
            "Stack Trace:\n"
            '  File "G:\\Git\\FGOA\\ui\\condition_editor_dialog.py", line 399, in _on_nudge_point\n'
        )
        unresolved_sample = (
            "[FGOA CRASH REPORT - 2026-10-15 12:00:00]\n"
            "Error Type: ZeroDivisionError\n"
            "Error Message: division by zero\n"
            "Stack Trace:\n"
            '  File "G:\\Git\\FGOA\\ui\\some_widget.py", line 100, in do_calc\n'
        )

        entries = [CrashEntry(synthetic_sample), CrashEntry(resolved_sample), CrashEntry(unresolved_sample)]
        classified = classify_crashes(entries)
        self.assertEqual(len(classified["synthetic_test"]), 1)
        self.assertEqual(len(classified["resolved"]), 1)
        self.assertEqual(len(classified["unresolved"]), 1)

    def test_archive_and_clean_temp_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            crash_file = os.path.join(tmpdir, "fgoa_crash.log")
            history_dir = os.path.join(tmpdir, "history")
            with open(crash_file, "w", encoding="utf-8") as f:
                f.write(
                    "======================================================================\n"
                    "[FGOA CRASH REPORT - 2026-10-15 12:00:00]\n"
                    "Error Type: KeyError\n"
                    "Error Message: 'SyntheticKey_99'\n"
                    "Stack Trace:\n"
                    '  File "G:\\Git\\FGOA\\tests\\test_fuzz.py", line 5, in run\n'
                    "======================================================================\n"
                    "======================================================================\n"
                    "[FGOA CRASH REPORT - 2026-10-15 12:00:00]\n"
                    "Error Type: RuntimeError\n"
                    "Error Message: Active Unresolved Bug\n"
                    "Stack Trace:\n"
                    '  File "G:\\Git\\FGOA\\ui\\active.py", line 12, in active_fn\n'
                    "======================================================================\n"
                )

            res = archive_and_clean_crash_log(crash_file, history_dir)
            self.assertEqual(res["total_count"], 2)
            self.assertEqual(res["synthetic_count"], 1)
            self.assertEqual(res["unresolved_count"], 1)

            # Check that clean file only has the unresolved error
            with open(crash_file, "r", encoding="utf-8") as f:
                cleaned_text = f.read()
            self.assertIn("Active Unresolved Bug", cleaned_text)
            self.assertNotIn("SyntheticKey_99", cleaned_text)

    def test_save_preset_dialog_resize_section_fix(self):
        """Verify SavePresetDialog initializes without AttributeError on resizeSection."""
        scen = Scenario(name="TestScen")
        dlg = SavePresetDialog([scen])
        self.assertIsNotNone(dlg.tbl_scenarios)
        self.assertEqual(dlg.tbl_scenarios.columnCount(), 4)

    def test_main_window_mark_dirty_fix(self):
        """Verify MainWindow._mark_dirty() executes safely without AttributeError."""
        win = MainWindow()
        # Must not raise AttributeError
        win._mark_dirty()
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
