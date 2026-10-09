import unittest
from PyQt5.QtWidgets import QApplication, QWidget
from ui.anti_burn_in_overlay import AntiBurnInOverlay, DesktopScreenOverlayWindow
from core.runner import WorkflowRunner
from core.models import Project, Scenario, Condition, ColorPoint

app = QApplication.instance() or QApplication([])


class TestAntiBurnRunnerSafeWait(unittest.TestCase):
    """Tests to verify that anti-burn-in transitions do not cause false condition evaluations."""

    def test_anti_burn_overlay_tracking_and_wait(self):
        """Verify AntiBurnInOverlay.is_any_transitioning tracks status and runner waits safely."""
        parent = QWidget()
        overlay = AntiBurnInOverlay(parent)
        self.assertFalse(overlay.is_transitioning())
        self.assertFalse(AntiBurnInOverlay.is_any_transitioning())

        # Start transition
        overlay.start_transition()
        self.assertTrue(overlay.is_transitioning())
        self.assertTrue(AntiBurnInOverlay.is_any_transitioning())

        # Create runner
        project = Project()
        runner = WorkflowRunner(project, 0, anti_burn_overlay=overlay)
        runner._is_running = True

        # Stop transition right away from background or directly
        overlay.stop_transition()
        self.assertFalse(overlay.is_transitioning())
        self.assertFalse(AntiBurnInOverlay.is_any_transitioning())

        # Runner wait should return immediately now
        runner._wait_for_anti_burn()
        overlay.cleanup()
        parent.close()

    def test_runner_waits_during_condition_evaluation_when_burn_in_active(self):
        """Verify runner delays evaluation while burn-in overlay is transitioning."""
        parent = QWidget()
        overlay = AntiBurnInOverlay(parent)
        project = Project()

        scen = Scenario(
            id="scen_1",
            name="테스트 시나리오",
            condition=Condition(points=[ColorPoint(x=10, y=10, r=255, g=255, b=255, tolerance=10)])
        )
        project.scenarios = [scen]

        runner = WorkflowRunner(project, 0, anti_burn_overlay=overlay)
        runner._is_running = True

        waited_events = []

        def on_log(lvl, msg):
            if "번인 방지 대기" in msg:
                waited_events.append(msg)

        runner.sig_log.connect(on_log)

        # Trigger burn-in transition
        overlay.start_transition()
        self.assertTrue(overlay.is_transitioning())

        # Asynchronously stop transition after 100ms
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(100, overlay.stop_transition)

        # Calling _wait_for_anti_burn should wait and emit log
        runner._wait_for_anti_burn()
        self.assertFalse(overlay.is_transitioning())
        self.assertGreaterEqual(len(waited_events), 1)
        self.assertIn("오판정 방지", waited_events[0])

        overlay.cleanup()
        parent.close()

    def test_desktop_screen_overlay_window_initialization(self):
        """Verify DesktopScreenOverlayWindow initializes with click-through and without errors."""
        win = DesktopScreenOverlayWindow()
        self.assertIsNotNone(win)
        win.close()


if __name__ == "__main__":
    unittest.main()
