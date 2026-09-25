"""
Unit tests for independent Action Sequence & Condition Dock separation,
retry log emission during evaluation, and global stop / floating stop widget.
"""
import sys
import unittest
from unittest.mock import patch, MagicMock
from PyQt5.QtWidgets import QApplication, QDockWidget
from PyQt5.QtCore import Qt

from core.models import Project, Scenario, Condition, ColorPoint, Action
from core.runner import WorkflowRunner
from core.window_manager import WindowInfo
from ui.main_window import MainWindow
from ui.floating_stop_widget import GlobalFloatingStopWidget


class TestDockSplitRetryLogAndGlobalStop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if not cls.app:
            cls.app = QApplication(sys.argv)

    def test_retry_log_emission(self):
        """Verify that condition mismatch with retry outputs retry progress logs."""
        proj = Project()
        scen = Scenario(
            step_number=1,
            scenario_number=1,
            name="재시도 테스트 시나리오",
            enabled=True,
            condition=Condition(name="더미 조건", points=[ColorPoint(x=10, y=10, r=0, g=0, b=0)]),
            on_match="execute",
            on_mismatch="retry",
            retry_max_count=2,
            retry_interval_sec=0.01,
            retry_fail_action="stop"
        )
        proj.scenarios = [scen]

        runner = WorkflowRunner(proj, hwnd=12345)
        emitted_logs = []
        runner.sig_log.connect(lambda lvl, msg: emitted_logs.append((lvl, msg)))

        mock_win = WindowInfo(hwnd=12345, title="Test Window", client_width=1600, client_height=900, screen_x=0, screen_y=0)
        with patch("core.evaluator.ConditionEvaluator.evaluate", return_value=(False, [])):
            with patch("core.window_manager.WindowManager.get_window_info", return_value=mock_win):
                runner._is_running = True
                runner.run()

        # Check that retry progress log was emitted at least once
        retry_logs = [msg for lvl, msg in emitted_logs if "조건 불일치 - 재시도 대기" in msg]
        self.assertTrue(len(retry_logs) >= 1, f"Expected retry logs, got: {emitted_logs}")
        self.assertIn("1/2회", retry_logs[0])

    def test_dock_inspector_and_actions_separation(self):
        """Verify that condition inspector and action sequence inspector are separate docks."""
        win = MainWindow()
        try:
            self.assertTrue(hasattr(win, "dock_inspector"))
            self.assertTrue(hasattr(win, "dock_actions"))
            self.assertIsInstance(win.dock_inspector, QDockWidget)
            self.assertIsInstance(win.dock_actions, QDockWidget)
            self.assertNotEqual(win.dock_inspector, win.dock_actions)

            # Check widget assignment
            self.assertEqual(win.dock_inspector.widget(), win.inspector.condition_panel)
            self.assertEqual(win.dock_actions.widget(), win.inspector.action_panel)

            # Verify layout switcher contains Side-by-Side preset
            items = [win.combo_layout.itemText(i) for i in range(win.combo_layout.count())]
            self.assertIn("인식 조건 / 액션 나란히 (Side-by-Side)", items)

            # Apply Side-by-Side layout
            win.apply_layout("인식 조건 / 액션 나란히 (Side-by-Side)")
            self.assertEqual(win.current_layout_name, "인식 조건 / 액션 나란히 (Side-by-Side)")

            # Reapply Default 3-column layout
            win.apply_layout("기본 3열 (Default)")
            self.assertEqual(win.current_layout_name, "기본 3열 (Default)")
        finally:
            win.close()

    def test_inspector_panels_synchronization(self):
        """Verify both condition and action panels synchronize content on scenario selection."""
        win = MainWindow()
        try:
            s1 = Scenario(id="test_sync_1", name="동기화 1", scenario_number=1)
            win.project.scenarios = [s1]

            # Empty selection
            win.inspector.set_scenario(None)
            self.assertEqual(win.inspector.condition_stack.currentIndex(), 0)
            self.assertEqual(win.inspector.action_stack.currentIndex(), 0)

            # Valid selection
            win.inspector.set_scenario(s1, target_hwnd=0, project=win.project)
            self.assertEqual(win.inspector.condition_stack.currentIndex(), 1)
            self.assertEqual(win.inspector.action_stack.currentIndex(), 1)
            self.assertIn("s1", win.inspector.lbl_action_status.text())
        finally:
            win.close()

    def test_floating_stop_widget(self):
        """Verify GlobalFloatingStopWidget functions and signal emission."""
        widget = GlobalFloatingStopWidget()
        try:
            self.assertTrue(bool(widget.windowFlags() & Qt.WindowStaysOnTopHint))

            stop_emitted = []
            pause_emitted = []
            widget.sig_stop_requested.connect(lambda: stop_emitted.append(True))
            widget.sig_pause_requested.connect(lambda: pause_emitted.append(True))

            widget.btn_stop.click()
            self.assertEqual(len(stop_emitted), 1)

            widget.btn_pause.click()
            self.assertEqual(len(pause_emitted), 1)

            widget.set_status("테스트 실행 중...")
            self.assertEqual(widget.lbl_status.text(), "테스트 실행 중...")

            widget.set_paused_state(True)
            self.assertIn("재개", widget.btn_pause.text())

            widget.set_paused_state(False)
            self.assertIn("일시정지", widget.btn_pause.text())
        finally:
            widget.close()

    def test_global_hotkey_stop_trigger(self):
        """Verify that _on_global_hotkey_stop stops active runner."""
        win = MainWindow()
        try:
            mock_runner = MagicMock()
            mock_runner.isRunning.return_value = True
            win.runner = mock_runner

            with patch.object(win, "_on_stop_execution") as mock_stop:
                win._on_global_hotkey_stop()
                mock_stop.assert_called_once()
        finally:
            win.close()


if __name__ == "__main__":
    unittest.main()
