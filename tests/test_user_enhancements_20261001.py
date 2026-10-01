"""
Unit tests for user requested enhancements:
1. Target window auto-tracking based on last recorded window title.
2. Scenario list snapshot linked to condition recognition reference image by default.
3. Total loop duration calculation, logging, and status bar label display.
4. Monitor anti-burn-in overlay with zero user interaction interference and on/off controls.
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtCore import Qt

from core.models import Project, Scenario, Condition, ColorPoint, Action
from core.runner import WorkflowRunner
from core.window_manager import WindowInfo
from ui.anti_burn_in_overlay import AntiBurnInOverlay


class TestUserEnhancements20261001(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if not cls.app:
            cls.app = QApplication(sys.argv)

    # -------------------------------------------------------------
    # 1. Target Window Auto-Tracking Tests
    # -------------------------------------------------------------
    def test_target_window_auto_tracking(self):
        """Verify MainWindow automatically searches and tracks target window from last_target_title."""
        from ui.main_window import MainWindow

        win = MainWindow()
        win.hide()

        dummy_win = WindowInfo(hwnd=2002, title="BlueStacks App Player 1", client_width=1280, client_height=720, screen_x=0, screen_y=0)

        def mock_find(title_query):
            if not title_query:
                return None
            if title_query.lower() in dummy_win.title.lower() or dummy_win.title.lower() in title_query.lower():
                return dummy_win
            return None

        with patch("core.window_manager.WindowManager.find_window_by_title", side_effect=mock_find):
            # Case 1: Exact / partial match with last_config_target_title
            win._last_config_target_title = "BlueStacks App Player 1"
            win.project.target_window_title = ""
            win.target_hwnd = 0
            found = win._auto_track_target_window()
            self.assertTrue(found)
            self.assertEqual(win.target_hwnd, 2002)

            # Case 2: Partial substring match via project target_window_title
            win.project.target_window_title = "BlueStacks"
            win.target_hwnd = 0
            found = win._auto_track_target_window()
            self.assertTrue(found)
            self.assertEqual(win.target_hwnd, 2002)

            # Case 3: Title not found
            win.project.target_window_title = "UnknownGameWindow"
            win._last_config_target_title = ""
            win.target_hwnd = 0
            found = win._auto_track_target_window()
            self.assertFalse(found)
            self.assertEqual(win.target_hwnd, 0)

        win.close()

    # -------------------------------------------------------------
    # 2. Scenario Snapshot Condition Linking Tests (Default Behavior)
    # -------------------------------------------------------------
    def test_scenario_snapshot_condition_linking_default(self):
        """Verify scenario list snapshot defaults to condition reference image and updates dynamically."""
        proj = Project()
        cond = Condition(name="메인 인식 조건", reference_image_path="refs/boss_screen.png")
        scen = Scenario(
            step_number=1,
            scenario_number=1,
            name="보스 전투 진입",
            condition=cond,
            reference_image_path=None  # Default: None (linked to condition)
        )
        proj.scenarios = [scen]

        # 1. Effective image should default to condition reference image
        self.assertEqual(scen.get_effective_reference_image(proj), "refs/boss_screen.png")

        # 2. When condition reference image changes, effective snapshot reflects it automatically
        cond.reference_image_path = "refs/boss_rage_phase.png"
        self.assertEqual(scen.get_effective_reference_image(proj), "refs/boss_rage_phase.png")

        # 3. If scenario has an explicit isolated snapshot, it takes precedence
        scen.reference_image_path = "refs/isolated_snapshot.png"
        self.assertEqual(scen.get_effective_reference_image(proj), "refs/isolated_snapshot.png")

        # 4. If reset to default (None), it falls back to condition image again
        scen.reference_image_path = None
        self.assertEqual(scen.get_effective_reference_image(proj), "refs/boss_rage_phase.png")

    def test_inspector_set_condition_reference_image(self):
        """Verify InspectorWidget._set_condition_reference_image updates condition and preserves None linking."""
        from ui.inspector_widget import InspectorWidget

        parent = QWidget()
        inspector = InspectorWidget(parent)
        proj = Project()
        cond = Condition(name="진입 조건", reference_image_path=None)
        scen = Scenario(step_number=1, scenario_number=1, name="노드 1", condition=cond)
        proj.scenarios = [scen]

        inspector.set_scenario(scen, 0, proj)

        # Set reference image via helper
        inspector._set_condition_reference_image("refs/auto_saved_capture.png")

        # Current scenario's condition should have the image, scenario.reference_image_path must remain None (default link)
        self.assertIsNone(inspector.current_scenario.reference_image_path)
        eff_cond = inspector._get_active_condition()
        self.assertIsNotNone(eff_cond)
        self.assertEqual(eff_cond.reference_image_path, "refs/auto_saved_capture.png")
        self.assertEqual(inspector.current_scenario.get_effective_reference_image(proj), "refs/auto_saved_capture.png")

    # -------------------------------------------------------------
    # 3. Loop Duration Calculation, Format, and Display Tests
    # -------------------------------------------------------------
    def test_workflow_runner_format_duration(self):
        """Verify human-readable format of loop duration."""
        self.assertEqual(WorkflowRunner._format_duration(0), "0.0초")
        self.assertEqual(WorkflowRunner._format_duration(5.4), "5.4초")
        self.assertEqual(WorkflowRunner._format_duration(59.9), "59.9초")
        self.assertEqual(WorkflowRunner._format_duration(65), "1분 5초")
        self.assertEqual(WorkflowRunner._format_duration(125.8), "2분 5초")
        self.assertEqual(WorkflowRunner._format_duration(3665), "1시간 1분 5초")

    def test_runner_loop_duration_signal_and_ui_display(self):
        """Verify WorkflowRunner emits sig_loop_completed with duration and MainWindow displays it."""
        from ui.main_window import MainWindow

        win = MainWindow()
        win.hide()

        # Check MainWindow._on_loop_completed updates _last_loop_duration and label
        win._on_loop_completed(1, 5, 135.0)
        self.assertEqual(win._last_loop_duration, 135.0)
        self.assertIn("2분 15초", win.lbl_loop_progress.text())
        self.assertIn("1 / 5", win.lbl_loop_progress.text())

        # Check MainWindow._on_loop_progress preserves loop duration text
        win._on_loop_progress(2, 5)
        self.assertIn("2 / 5", win.lbl_loop_progress.text())
        self.assertIn("2분 15초", win.lbl_loop_progress.text())

        win.close()

    # -------------------------------------------------------------
    # 4. Anti-Burn-In Overlay Tests
    # -------------------------------------------------------------
    def test_anti_burn_in_overlay_properties_and_events(self):
        """Verify AntiBurnInOverlay has mouse transparency, timer settings, and state cycle."""
        parent = QWidget()
        overlay = AntiBurnInOverlay(parent)

        # 1. Verification of zero interference with user operations
        self.assertTrue(overlay.testAttribute(Qt.WA_TransparentForMouseEvents))
        self.assertTrue(overlay.testAttribute(Qt.WA_NoSystemBackground))
        self.assertEqual(overlay.focusPolicy(), Qt.NoFocus)

        # 2. Interval configuration
        overlay.set_interval_minutes(7)
        self.assertEqual(overlay.get_interval_minutes(), 7)
        overlay.set_enabled(True)
        self.assertTrue(overlay.is_enabled())
        self.assertEqual(overlay._interval_timer.interval(), 7 * 60 * 1000)

        # 3. Transition start and stages
        overlay.start_transition()
        self.assertFalse(overlay.isHidden())
        self.assertEqual(overlay._stage, 1)

        # Step animation manually until stage reaches 2 (hold black)
        for _ in range(50):
            overlay._on_anim_step()
            if overlay._stage == 2:
                break
        self.assertEqual(overlay._stage, 2)
        self.assertGreater(overlay._alpha, 150)

        # Stop transition resets state
        overlay.stop_transition()
        self.assertEqual(overlay._stage, 0)
        self.assertEqual(overlay._alpha, 0)
        self.assertFalse(overlay.isVisible())

        overlay.set_enabled(False)
        self.assertFalse(overlay.is_enabled())


if __name__ == "__main__":
    unittest.main()
