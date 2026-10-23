"""
Unit and Integration Tests for Background Control Mode (PostMessage & Background Capture) in FGOA.
"""
import sys
import os
import unittest
from unittest.mock import MagicMock, patch, call
from PIL import Image

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from PyQt5.QtWidgets import QApplication
import win32con

from core.models import Project, Scenario, Condition, ColorPoint, Action
from core.input_controller import InputController
from core.screen_capture import ScreenCapture
from core.evaluator import ConditionEvaluator
from core.runner import WorkflowRunner


class TestBackgroundMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication.instance() is None:
            cls.app = QApplication(sys.argv)
        else:
            cls.app = QApplication.instance()

    def test_make_lparam(self):
        """Verify (x, y) coordinates pack into loword/hiword lParam."""
        lparam = InputController.make_lparam(100, 200)
        self.assertEqual(lparam & 0xFFFF, 100)
        self.assertEqual((lparam >> 16) & 0xFFFF, 200)

    @patch("core.input_controller.win32gui.IsWindow", return_value=True)
    @patch("core.input_controller.win32gui.ChildWindowFromPoint", return_value=0)
    @patch("core.input_controller.win32api.PostMessage")
    @patch("core.input_controller.ctypes.windll.user32.SetCursorPos")
    @patch("core.input_controller.win32api.mouse_event")
    def test_post_click_at_no_physical_cursor(self, mock_mouse_event, mock_set_cursor, mock_post, mock_child, mock_is_win):
        """Verify post_click_at uses PostMessage without touching physical cursor."""
        res = InputController.post_click_at(hwnd=1234, rel_x=150, rel_y=250, button="left", click_type="single", repeat=1)
        self.assertTrue(res)
        
        # Physical mouse APIs should NOT be called
        mock_set_cursor.assert_not_called()
        mock_mouse_event.assert_not_called()

        # PostMessage should have received WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP
        posted_msgs = [c[0][1] for c in mock_post.call_args_list]
        self.assertIn(win32con.WM_MOUSEMOVE, posted_msgs)
        self.assertIn(win32con.WM_LBUTTONDOWN, posted_msgs)
        self.assertIn(win32con.WM_LBUTTONUP, posted_msgs)

    @patch("core.input_controller.win32gui.IsWindow", return_value=True)
    @patch("core.input_controller.win32gui.ChildWindowFromPoint", return_value=0)
    @patch("core.input_controller.win32api.PostMessage")
    @patch("core.input_controller.ctypes.windll.user32.SetCursorPos")
    @patch("core.input_controller.win32api.mouse_event")
    def test_post_drag_and_drop(self, mock_mouse_event, mock_set_cursor, mock_post, mock_child, mock_is_win):
        """Verify post_drag_and_drop interpolates move messages via PostMessage."""
        res = InputController.post_drag_and_drop(hwnd=1234, start_x=10, start_y=20, end_x=100, end_y=200, duration_ms=50)
        self.assertTrue(res)

        mock_set_cursor.assert_not_called()
        mock_mouse_event.assert_not_called()

        posted_msgs = [c[0][1] for c in mock_post.call_args_list]
        self.assertIn(win32con.WM_LBUTTONDOWN, posted_msgs)
        self.assertIn(win32con.WM_LBUTTONUP, posted_msgs)
        # Should have multiple WM_MOUSEMOVE steps
        move_count = posted_msgs.count(win32con.WM_MOUSEMOVE)
        self.assertGreaterEqual(move_count, 10)

    @patch("core.input_controller.InputController.post_click_at", return_value=True)
    @patch("core.input_controller.win32api.mouse_event")
    def test_execute_action_background_delegation(self, mock_mouse_event, mock_post_click):
        """Verify execute_action delegates to post_click_at when background=True."""
        act = Action(action_type="mouse_click", x=100, y=200, mouse_button="left")
        InputController.execute_action(act, hwnd=1234, offset_range=0, background=True)

        mock_post_click.assert_called_once_with(1234, 100, 200, button="left", click_type="single", repeat=1)
        mock_mouse_event.assert_not_called()

    @patch("core.screen_capture.ScreenCapture.capture_client_area_background")
    def test_condition_evaluator_background_snapshot(self, mock_capture_bg):
        """Verify ConditionEvaluator takes 1 background snapshot for multiple points in background mode."""
        dummy_img = Image.new("RGB", (200, 200), (255, 0, 0))
        mock_capture_bg.return_value = dummy_img

        cond = Condition(
            points=[
                ColorPoint(x=10, y=10, r=255, g=0, b=0, tolerance=5),
                ColorPoint(x=20, y=20, r=255, g=0, b=0, tolerance=5),
            ],
            logic_operator="AND"
        )

        matched, results = ConditionEvaluator.evaluate(cond, hwnd=9999, background_mode=True)
        self.assertTrue(matched)
        self.assertEqual(len(results), 2)
        # capture_client_area_background should be called exactly once per evaluate()
        mock_capture_bg.assert_called_once_with(9999)

    @patch("core.runner.ConditionEvaluator.evaluate")
    @patch("core.runner.InputController.execute_action")
    @patch("core.runner.WindowManager.get_window_info")
    def test_runner_background_mode_flow(self, mock_win_info, mock_exec_action, mock_evaluate):
        """Verify WorkflowRunner passes background_mode to ConditionEvaluator and InputController."""
        mock_win_info.return_value = MagicMock(is_minimized=False)
        mock_evaluate.return_value = (True, [])

        proj = Project(name="TestProj")
        scen = Scenario(
            name="Scen1",
            step_number=1,
            condition=Condition(points=[ColorPoint(x=5, y=5, r=10, g=20, b=30)]),
            actions=[Action(action_type="mouse_click", x=50, y=60)],
            on_match="execute"
        )
        proj.scenarios.append(scen)

        runner = WorkflowRunner(proj, hwnd=8888, background_mode=True)
        self.assertTrue(runner.background_mode)

        # Run one step
        runner._step_mode = True
        runner._is_running = True
        
        # Test direct execution of actions
        runner._execute_actions(scen)
        mock_exec_action.assert_called_once()
        self.assertTrue(mock_exec_action.call_args[1].get("background"))

    def test_main_window_config_persistence(self):
        """Verify MainWindow correctly loads and saves background_mode_enabled setting."""
        from ui.main_window import MainWindow
        win = MainWindow()
        try:
            self.assertTrue(hasattr(win, "chk_background_mode"))

            # Toggle True
            win.chk_background_mode.setChecked(True)
            win._save_app_config()
            self.assertTrue(win._cached_config.get("background_mode_enabled"))

            # Toggle False
            win.chk_background_mode.setChecked(False)
            win._save_app_config()
            self.assertFalse(win._cached_config.get("background_mode_enabled"))
        finally:
            win.close()

    @patch("core.input_controller.win32gui.IsWindow", return_value=True)
    @patch("core.input_controller.win32gui.ChildWindowFromPoint", return_value=0)
    @patch("core.input_controller.win32api.PostMessage")
    @patch("core.input_controller.InputController.restore_foreground_window")
    @patch("core.input_controller.win32gui.GetForegroundWindow")
    def test_post_click_preserves_foreground_window(self, mock_get_fg, mock_restore_fg, mock_post, mock_child, mock_is_win):
        """Verify that if foreground changes during click delivery, focus is restored to user's window."""
        # First call (before click) returns 9999 (e.g. Chat window)
        # Second call (after click) returns 1234 (Target app tried to steal focus)
        mock_get_fg.side_effect = [9999, 1234]

        res = InputController.post_click_at(hwnd=1234, rel_x=100, rel_y=200)
        self.assertTrue(res)
        mock_restore_fg.assert_called_once_with(9999)

    def test_background_mode_suppresses_action_overlay(self):
        """Verify that action visual overlay popup is suppressed during background mode to prevent focus theft."""
        from ui.main_window import MainWindow
        win = MainWindow()
        try:
            win.chk_action_overlay.setChecked(True)
            win.chk_background_mode.setChecked(True)
            mock_overlay = MagicMock()
            win.action_overlay = mock_overlay

            win._on_action_sequence_started_visual([Action(action_type="mouse_click")], "테스트 시나리오")
            # Should NOT show overlay in background mode
            mock_overlay.show_sequence.assert_not_called()

            # When background mode is unchecked, overlay is shown
            win.chk_background_mode.setChecked(False)
            win._on_action_sequence_started_visual([Action(action_type="mouse_click")], "테스트 시나리오")
            mock_overlay.show_sequence.assert_called_once()
        finally:
            win.close()


if __name__ == "__main__":
    unittest.main()
