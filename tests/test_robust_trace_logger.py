"""
Unit tests for Robust Trace Logger mode, per-loop directory organization,
fast low-overhead screenshot capture, cross-computer path portability, numbering stamp, UI trace toggle, and bulk cleanup.
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
from core.path_utils import get_trace_dir, to_trace_relative_path, to_trace_absolute_path, get_project_root
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
            # 1st capture: must succeed (returns portable relative path with NUM tag)
            shot1 = logger.capture_screenshot_if_eligible(hwnd=1234)
            self.assertIsNotNone(shot1)
            self.assertIn("|NUM:0001", shot1)
            shot1_path = shot1.split("|")[0]
            self.assertTrue(os.path.isfile(os.path.join(self.temp_dir, os.path.basename(loop1_dir), os.path.basename(shot1_path))))

            # Check absolute capture directly
            shot1_full = logger.capture_screenshot_if_eligible(hwnd=1234, as_relative=False)
            self.assertIsNone(shot1_full, "Within 1s must skip")

            # Simulate 1.05s elapsed
            logger.last_capture_time -= 1.1
            shot2_full = logger.capture_screenshot_if_eligible(hwnd=1234, as_relative=False)
            self.assertIsNotNone(shot2_full)
            self.assertIn("|NUM:0002", shot2_full)
            shot2_path = shot2_full.split("|")[0]
            self.assertTrue(os.path.isfile(shot2_path))

            # Verify image was downscaled to max width 640 and has watermark stamp
            with Image.open(shot2_path) as saved_img:
                self.assertEqual(saved_img.width, 640)
                self.assertEqual(saved_img.height, 360)

        # Loop 2 directory creation
        loop2_dir = logger.start_loop(2)
        self.assertTrue(os.path.isdir(loop2_dir))
        self.assertIn("loop_002_", os.path.basename(loop2_dir))
        self.assertNotEqual(loop1_dir, loop2_dir)

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
        """Verify WorkflowRunner emits [TRACE_SHOT:path|NUM:xxxx] tag when robust trace is active."""
        proj = Project()
        runner = WorkflowRunner(proj, hwnd=1234, robust_trace_enabled=True)
        runner.trace_logger.trace_base_dir = self.temp_dir

        dummy_img = Image.new("RGB", (800, 600), color=(50, 100, 150))
        with patch("core.trace_logger.ScreenCapture.capture_client_area", return_value=dummy_img):
            emitted = []
            runner.sig_log.connect(lambda lvl, msg: emitted.append((lvl, msg)))

            # Loop started
            runner.trace_logger.start_loop(1)

            # 1st log: should attach screenshot with numbering
            runner._log("INFO", "테스트 로그 1")
            self.assertEqual(len(emitted), 1)
            self.assertIn("[TRACE_SHOT:", emitted[0][1])
            self.assertIn("|NUM:0001", emitted[0][1])

            # 2nd log immediately (< 1s): should NOT attach screenshot
            runner._log("INFO", "테스트 로그 2 (1초 미만)")
            self.assertEqual(len(emitted), 2)
            self.assertNotIn("[TRACE_SHOT:", emitted[1][1])

            # After 1.1s: should attach screenshot again with incremented numbering
            runner.trace_logger.last_capture_time -= 1.1
            runner._log("INFO", "테스트 로그 3 (1초 경과)")
            self.assertEqual(len(emitted), 3)
            self.assertIn("[TRACE_SHOT:", emitted[2][1])
            self.assertIn("|NUM:0002", emitted[2][1])

    def test_04_ui_log_parsing_and_clickable_link(self):
        """Verify MainWindow parses [TRACE_SHOT:path|NUM:0001] and renders clickable [📸 #0001 화면] anchor with log_id."""
        win = MainWindow()
        pal = get_theme_colors("dark")

        # Create a real dummy file inside repo trace_logs
        trace_dir = get_trace_dir()
        dummy_loop = os.path.join(trace_dir, "test_ui_loop")
        os.makedirs(dummy_loop, exist_ok=True)
        dummy_shot = os.path.join(dummy_loop, "shot_0001_120000.jpg")
        with open(dummy_shot, "w") as f:
            f.write("img")

        try:
            rel_shot = to_trace_relative_path(dummy_shot)
            win.txt_log.clear()
            win._append_log("INFO", f"[#1] 화면 캡처 로그 [TRACE_SHOT:{rel_shot}|NUM:0001]")

            record = win._log_records[-1]
            self.assertEqual(record["screenshot_path"], rel_shot)
            self.assertEqual(record["screenshot_number"], "0001")
            self.assertEqual(record["raw_msg"], "[#1] 화면 캡처 로그")

            html_out = win._format_log_record_html(record, pal, pal["text_primary"], "#8da4c4")
            # Anchor must use view-screenshot:{log_id} to prevent foreign PC path encoding bugs
            self.assertIn(f"view-screenshot:{record['id']}", html_out)
            self.assertIn("[📸 #0001 화면]", html_out)

            # Test clicking the anchor triggers show_image_preview with correct title and resolved path
            with patch("ui.image_preview_dialog.show_image_preview") as mock_preview:
                win._on_log_anchor_clicked(f"view-screenshot:{record['id']}")
                mock_preview.assert_called_once()
                self.assertEqual(os.path.abspath(mock_preview.call_args[0][0]), os.path.abspath(dummy_shot))
                self.assertIn("#0001", mock_preview.call_args[1]["title"])
        finally:
            if os.path.exists(dummy_shot):
                os.remove(dummy_shot)
            if os.path.exists(dummy_loop):
                os.rmdir(dummy_loop)
            win.close()

    def test_05_ui_robust_trace_controls_and_config_persistence(self):
        """Verify UI checkbox, bulk delete button, and config persistence for robust trace mode."""
        win = MainWindow()
        self.assertTrue(hasattr(win, "chk_robust_trace"))
        self.assertTrue(hasattr(win, "btn_delete_trace"))

        # Test toggling
        win.chk_robust_trace.setChecked(True)
        self.assertTrue(win.chk_robust_trace.isChecked())

        with patch("ui.main_window.get_config_filepath", return_value=os.path.join(self.temp_dir, "test_cfg.json")):
            win._save_app_config()
            self.assertTrue(win._cached_config.get("robust_trace_enabled"))

            # Test applying config
            win.chk_robust_trace.setChecked(False)
            win._apply_ui_config({"robust_trace_enabled": True})
            self.assertTrue(win.chk_robust_trace.isChecked())

        win.close()

    def test_06_cross_computer_trace_path_portability(self):
        """Verify trace paths from foreign computers or relative paths re-anchor to local project root."""
        root = get_project_root()
        trace_dir = get_trace_dir()

        # 1. to_trace_relative_path test
        abs_p = os.path.join(trace_dir, "loop_001_20261022", "shot_0001_120000.jpg")
        rel_p = to_trace_relative_path(abs_p)
        self.assertEqual(rel_p, "trace_logs/loop_001_20261022/shot_0001_120000.jpg")

        # 2. Foreign PC absolute path re-anchoring test
        foreign_pc_path = "D:/OldGamingLaptop/UserA/FGOA/trace_logs/loop_005_20261022/shot_0003_120000.jpg"
        resolved_local = to_trace_absolute_path(foreign_pc_path)
        expected_local = os.path.abspath(os.path.join(root, "trace_logs", "loop_005_20261022", "shot_0003_120000.jpg"))
        self.assertEqual(resolved_local, expected_local)

        # 3. Relative path resolving
        rel_input = "trace_logs/loop_002_20261022/shot_0001.jpg"
        resolved_from_rel = to_trace_absolute_path(rel_input)
        expected_from_rel = os.path.abspath(os.path.join(root, "trace_logs", "loop_002_20261022", "shot_0001.jpg"))
        self.assertEqual(resolved_from_rel, expected_from_rel)

        # 4. Verify MainWindow UI handles foreign PC path when image exists locally
        dummy_loop = os.path.join(trace_dir, "loop_005_20261022")
        os.makedirs(dummy_loop, exist_ok=True)
        dummy_file = os.path.join(dummy_loop, "shot_0003_120000.jpg")
        with open(dummy_file, "w") as f:
            f.write("image_data")

        try:
            win = MainWindow()
            pal = get_theme_colors("dark")
            win.txt_log.clear()
            # Foreign PC log line with foreign path and numbering
            win._append_log("INFO", f"[#2] 타 PC에서 가져온 로그 [TRACE_SHOT:{foreign_pc_path}|NUM:0003]")
            record = win._log_records[-1]

            # HTML formatting must detect that file exists in local re-anchored path and show [📸 #0003 화면]
            html_out = win._format_log_record_html(record, pal, pal["text_primary"], "#8da4c4")
            self.assertIn("[📸 #0003 화면]", html_out)

            # Click handler using log_id must resolve the local re-anchored file preview
            with patch("ui.image_preview_dialog.show_image_preview") as mock_preview:
                win._on_log_anchor_clicked(f"view-screenshot:{record['id']}")
                mock_preview.assert_called_once()
                self.assertEqual(os.path.abspath(mock_preview.call_args[0][0]), os.path.abspath(dummy_file))
                self.assertIn("#0003", mock_preview.call_args[1]["title"])

            win.close()
        finally:
            if os.path.exists(dummy_file):
                os.remove(dummy_file)
            if os.path.exists(dummy_loop):
                os.rmdir(dummy_loop)

    def test_07_scenario_execution_folder_creation(self):
        """Verify each scenario execution creates a new unique directory."""
        logger = TraceLogger(trace_base_dir=self.temp_dir)
        d1 = logger.start_scenario_execution("test_scenario")
        self.assertTrue(os.path.isdir(d1))
        self.assertIn("scenario_test_scenario_", os.path.basename(d1))

        # 2nd run: must create distinct directory even in the same second
        d2 = logger.start_scenario_execution("test_scenario")
        self.assertTrue(os.path.isdir(d2))
        self.assertNotEqual(d1, d2)

        # WorkflowRunner execution integration
        proj = Project(name="AutoBattle")
        runner = WorkflowRunner(proj, hwnd=1234, robust_trace_enabled=True)
        runner.trace_logger.trace_base_dir = self.temp_dir
        dummy_img = Image.new("RGB", (640, 360), color=(10, 20, 30))
        with patch("core.trace_logger.ScreenCapture.capture_client_area", return_value=dummy_img), \
             patch("core.runner.WindowManager.get_window_info", return_value=None):
            runner.run()  # Ends quickly because window not found, but scenario execution started
            self.assertIsNotNone(runner.trace_logger.current_loop_dir)
            self.assertTrue(os.path.isdir(runner.trace_logger.current_loop_dir))
            self.assertIn("scenario_AutoBattle_", os.path.basename(runner.trace_logger.current_loop_dir))

    def test_08_image_preview_dialog_auto_close_and_open_folder(self):
        """Verify ImagePreviewDialog auto-closes on click and has working folder open button."""
        from ui.image_preview_dialog import ImagePreviewDialog
        from PyQt5.QtCore import QEvent, QPoint, Qt
        from PyQt5.QtGui import QMouseEvent

        test_img_path = os.path.join(self.temp_dir, "preview_test.jpg")
        with open(test_img_path, "w") as f:
            f.write("test_content")

        dlg = ImagePreviewDialog(test_img_path)
        dlg.show()
        self.assertTrue(hasattr(dlg, "btn_open_folder"))

        # Test folder open button triggers subprocess or os.startfile
        with patch("subprocess.Popen") as mock_popen:
            dlg._open_folder()
            mock_popen.assert_called_once()
            self.assertIn("/select,", mock_popen.call_args[0][0])
            self.assertIn(os.path.basename(test_img_path), mock_popen.call_args[0][0])

        # Test clicking on the open folder button does not close dialog
        btn_event = QMouseEvent(QEvent.MouseButtonPress, QPoint(5, 5), dlg.btn_open_folder.mapToGlobal(QPoint(5, 5)), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        handled = dlg.eventFilter(dlg.btn_open_folder, btn_event)
        self.assertFalse(handled)

        # Test clicking anywhere else (e.g. image or dialog) closes dialog
        accepted = []
        dlg.accept = lambda: accepted.append(True)
        click_event = QMouseEvent(QEvent.MouseButtonPress, QPoint(10, 10), dlg.lbl_image.mapToGlobal(QPoint(10, 10)), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        dlg.eventFilter(dlg.lbl_image, click_event)
        self.assertTrue(len(accepted) > 0)

        # Regression test: verify QWindow object does not cause TypeError in isAncestorOf
        from PyQt5.QtGui import QWindow
        dummy_win = QWindow()
        handled_win_btn = dlg.eventFilter(dummy_win, btn_event)
        self.assertFalse(handled_win_btn)
        accepted.clear()
        handled_win_outside = dlg.eventFilter(dummy_win, click_event)
        self.assertTrue(handled_win_outside)
        self.assertTrue(len(accepted) > 0)

        dlg.close()

    def test_09_skip_to_next_scenario(self):
        """Verify skip_to_next button has been removed from playback toolbar."""
        win = MainWindow()
        self.assertFalse(hasattr(win, "btn_skip_scenario"), "btn_skip_scenario button must be removed")
        self.assertFalse(hasattr(win, "sc_f9"), "F9 shortcut must be removed")

        # Verify runner skip flag handling if called internally
        runner = WorkflowRunner(win.project, hwnd=1234)
        self.assertFalse(runner._skip_requested)
        runner.skip_to_next()
        self.assertTrue(runner._skip_requested)
        win.close()

    def test_10_power_manager_screensaver_lifecycle(self):
        """Verify PowerManager controls OS execution state and screensaver prevention without input hijacking."""
        from core.power_manager import PowerManager, WM_SYSCOMMAND, SC_SCREENSAVE, SC_MONITORPOWER
        import ctypes
        from ctypes import wintypes

        # 1. State changes
        PowerManager.allow_screensaver()
        self.assertFalse(PowerManager.is_preventing())
        self.assertFalse(PowerManager.should_block_syscommand(WM_SYSCOMMAND, SC_SCREENSAVE))
        self.assertFalse(PowerManager.should_block_syscommand(WM_SYSCOMMAND, SC_MONITORPOWER))

        PowerManager.prevent_screensaver()
        self.assertTrue(PowerManager.is_preventing())
        self.assertTrue(PowerManager.should_block_syscommand(WM_SYSCOMMAND, SC_SCREENSAVE))
        self.assertTrue(PowerManager.should_block_syscommand(WM_SYSCOMMAND, SC_MONITORPOWER))
        # Non-screensaver syscommands must not be blocked
        self.assertFalse(PowerManager.should_block_syscommand(WM_SYSCOMMAND, 0xF010))  # SC_MOVE
        self.assertFalse(PowerManager.should_block_syscommand(0x000F, 0))  # WM_PAINT

        # 2. Window nativeEvent filtering
        win = MainWindow()
        self.assertTrue(hasattr(win, "btn_prevent_screensaver"))
        self.assertTrue(win.btn_prevent_screensaver.isCheckable())
        self.assertTrue(win.btn_prevent_screensaver.isChecked())
        self.assertIn("ON", win.btn_prevent_screensaver.text())

        msg_ss = wintypes.MSG()
        msg_ss.message = WM_SYSCOMMAND
        msg_ss.wParam = SC_SCREENSAVE
        addr_ss = ctypes.addressof(msg_ss)

        # While preventing and button ON: blocked
        res_blocked = win.nativeEvent(b"windows_generic_MSG", addr_ss)
        self.assertEqual(res_blocked, (True, 0))

        # When button is toggled to OFF: not blocked even if PowerManager._is_preventing was True
        win.btn_prevent_screensaver.setChecked(False)
        self.assertIn("OFF", win.btn_prevent_screensaver.text())
        res_off = win.nativeEvent(b"windows_generic_MSG", addr_ss)
        self.assertNotEqual(res_off, (True, 0))

        # Toggle back to ON
        win.btn_prevent_screensaver.setChecked(True)
        self.assertIn("ON", win.btn_prevent_screensaver.text())

        # While allowed: not blocked
        PowerManager.allow_screensaver()
        self.assertFalse(PowerManager.is_preventing())
        res_allowed = win.nativeEvent(b"windows_generic_MSG", addr_ss)
        self.assertNotEqual(res_allowed, (True, 0))

        # 3. Runner lifecycle integration
        proj = Project(name="PowerTest")
        runner = WorkflowRunner(proj, hwnd=1234)

        # Pause and resume
        PowerManager.prevent_screensaver()
        runner.pause()
        self.assertFalse(PowerManager.is_preventing())
        runner.resume()
        self.assertTrue(PowerManager.is_preventing())
        runner.stop()
        self.assertFalse(PowerManager.is_preventing())

        # Runner run execution lifecycle (ensures allow_screensaver in finally block)
        with patch.object(runner, "_run_internal") as mock_internal:
            def run_side_effect():
                self.assertTrue(PowerManager.is_preventing())
            mock_internal.side_effect = run_side_effect
            runner.run()
            # After run finishes, screensaver must be allowed again
            self.assertFalse(PowerManager.is_preventing())

        # Runner with prevent_screensaver_enabled = False
        runner_disabled = WorkflowRunner(proj, hwnd=1234, prevent_screensaver_enabled=False)
        with patch.object(runner_disabled, "_run_internal") as mock_internal2:
            def run_side_effect2():
                # Should stay False because screensaver prevention is disabled
                self.assertFalse(PowerManager.is_preventing())
            mock_internal2.side_effect = run_side_effect2
            runner_disabled.run()
            self.assertFalse(PowerManager.is_preventing())

        win.close()


if __name__ == "__main__":
    unittest.main()
