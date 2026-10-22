"""
Unit tests for Robust Trace Logger mode, per-loop directory organization,
fast low-overhead screenshot capture, UI trace toggle, and bulk cleanup.
"""
import unittest
import sys
import os
import time
import shutil
import tempfile
from unittest.mock import patch, MagicMock
from PIL import Image

from PyQt5.QtWidgets import QApplication
from core.models import Project, Scenario, Action
from core.runner import WorkflowRunner
from core.trace_logger import TraceLogger
from ui.main_window import MainWindow
from ui.theme import get_theme_colors


class TestRobustTraceLogger(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="fgoa_test_trace_")

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_trace_logger_interval_enforcement_and_loop_folders(self):
        """Verify TraceLogger creates per-loop directory and enforces >= 1.0s interval strictly."""
        logger = TraceLogger(trace_base_dir=self.temp_dir, min_interval_sec=1.0)

        # Loop 1 directory creation
        loop1_dir = logger.start_loop(1)
        self.assertTrue(os.path.isdir(loop1_dir))
        self.assertIn("loop_001_", os.path.basename(loop1_dir))

        # Mock ScreenCapture to return a test image (1280x720)
        dummy_img = Image.new("RGB", (1280, 720), color=(100, 150, 200))
        with patch("core.trace_logger.ScreenCapture.capture_client_area", return_value=dummy_img):
            # 1st capture: must succeed
            shot1 = logger.capture_screenshot_if_eligible(hwnd=1234)
            self.assertIsNotNone(shot1)
            self.assertTrue(os.path.isfile(shot1))
            self.assertTrue(shot1.startswith(loop1_dir))

            # Verify image was downscaled to max width 640
            with Image.open(shot1) as saved_img:
                self.assertEqual(saved_img.width, 640)
                self.assertEqual(saved_img.height, 360)

            # 2nd capture immediately (< 1s): must return None (skip capture)
            shot2 = logger.capture_screenshot_if_eligible(hwnd=1234)
            self.assertIsNone(shot2, "Capture within 1s must be skipped")

            # Simulate 1.05s elapsed
            logger.last_capture_time -= 1.1
            shot3 = logger.capture_screenshot_if_eligible(hwnd=1234)
            self.assertIsNotNone(shot3, "Capture after >= 1.0s must succeed")
            self.assertTrue(os.path.isfile(shot3))

        # Loop 2 directory creation
        loop2_dir = logger.start_loop(2)
        self.assertTrue(os.path.isdir(loop2_dir))
        self.assertIn("loop_002_", os.path.basename(loop2_dir))
        self.assertNotEqual(loop1_dir, loop2_dir)

        with patch("core.trace_logger.ScreenCapture.capture_client_area", return_value=dummy_img):
            logger.last_capture_time -= 1.1
            shot_loop2 = logger.capture_screenshot_if_eligible(hwnd=1234)
            self.assertIsNotNone(shot_loop2)
            self.assertTrue(shot_loop2.startswith(loop2_dir))

    def test_02_bulk_cleanup_trace_logs(self):
        """Verify clean_all_trace_logs deletes all loop folders and files cleanly."""
        logger = TraceLogger(trace_base_dir=self.temp_dir)
        loop_dir = logger.start_loop(1)
        test_file = os.path.join(loop_dir, "test.jpg")
        with open(test_file, "w") as f:
            f.write("fake_jpeg_content")

        self.assertTrue(os.path.isfile(test_file))

        res = TraceLogger.clean_all_trace_logs(self.temp_dir)
        self.assertGreaterEqual(res["deleted_dirs"], 1)
        self.assertGreaterEqual(res["deleted_files"], 1)
        self.assertGreaterEqual(res["freed_bytes"], len("fake_jpeg_content"))

        # Base dir should exist, but be empty
        self.assertTrue(os.path.exists(self.temp_dir))
        self.assertEqual(len(os.listdir(self.temp_dir)), 0)

    def test_03_runner_trace_integration(self):
        """Verify WorkflowRunner emits [TRACE_SHOT:path] tag when robust trace is active."""
        proj = Project()
        runner = WorkflowRunner(proj, hwnd=1234, robust_trace_enabled=True)
        runner.trace_logger.trace_base_dir = self.temp_dir

        dummy_img = Image.new("RGB", (800, 600), color=(50, 100, 150))
        with patch("core.trace_logger.ScreenCapture.capture_client_area", return_value=dummy_img):
            emitted = []
            runner.sig_log.connect(lambda lvl, msg: emitted.append((lvl, msg)))

            # Loop started
            runner.trace_logger.start_loop(1)

            # 1st log: should attach screenshot
            runner._log("INFO", "테스트 로그 1")
            self.assertEqual(len(emitted), 1)
            self.assertIn("[TRACE_SHOT:", emitted[0][1])

            # 2nd log immediately (< 1s): should NOT attach screenshot
            runner._log("INFO", "테스트 로그 2 (1초 미만)")
            self.assertEqual(len(emitted), 2)
            self.assertNotIn("[TRACE_SHOT:", emitted[1][1])

            # After 1.1s: should attach screenshot again
            runner.trace_logger.last_capture_time -= 1.1
            runner._log("INFO", "테스트 로그 3 (1초 경과)")
            self.assertEqual(len(emitted), 3)
            self.assertIn("[TRACE_SHOT:", emitted[2][1])

    def test_04_ui_log_parsing_and_clickable_link(self):
        """Verify MainWindow parses [TRACE_SHOT:path] and renders clickable [📸 화면] anchor."""
        win = MainWindow()
        pal = get_theme_colors("dark")

        # Create a real dummy file so os.path.exists passes
        dummy_shot = os.path.join(self.temp_dir, "test_shot.jpg")
        with open(dummy_shot, "w") as f:
            f.write("img")

        win.txt_log.clear()
        win._append_log("INFO", f"[#1] 화면 캡처 로그 [TRACE_SHOT:{dummy_shot}]")

        record = win._log_records[-1]
        self.assertEqual(record["screenshot_path"], dummy_shot)
        self.assertEqual(record["raw_msg"], "[#1] 화면 캡처 로그")

        html_out = win._format_log_record_html(record, pal, pal["text_primary"], "#8da4c4")
        self.assertIn("view-screenshot:", html_out)
        self.assertIn("[📸 화면]", html_out)

        # Test clicking the anchor triggers show_image_preview
        with patch("ui.image_preview_dialog.show_image_preview") as mock_preview:
            win._on_log_anchor_clicked(f"view-screenshot:{dummy_shot}")
            mock_preview.assert_called_once()
            self.assertIn(dummy_shot, mock_preview.call_args[0][0])

        win.close()

    def test_05_ui_robust_trace_controls_and_config_persistence(self):
        """Verify UI checkbox, bulk delete button, and config persistence for robust trace mode."""
        win = MainWindow()
        self.assertTrue(hasattr(win, "chk_robust_trace"))
        self.assertTrue(hasattr(win, "btn_delete_trace"))

        # Test toggling
        win.chk_robust_trace.setChecked(True)
        self.assertTrue(win.chk_robust_trace.isChecked())

        cfg = {}
        with patch("ui.main_window.get_config_filepath", return_value=os.path.join(self.temp_dir, "test_cfg.json")):
            win._save_app_config()
            self.assertTrue(win._cached_config.get("robust_trace_enabled"))

            # Test applying config
            win.chk_robust_trace.setChecked(False)
            win._apply_ui_config({"robust_trace_enabled": True})
            self.assertTrue(win.chk_robust_trace.isChecked())

        win.close()


if __name__ == "__main__":
    unittest.main()
