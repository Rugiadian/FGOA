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

    def test_pure_black_alpha_reaches_255(self):
        """Verify that fade-in reaches pure black (alpha 255) and holds."""
        parent = QWidget()
        overlay = AntiBurnInOverlay(parent)
        overlay.set_hold_minutes(0.1)
        overlay.start_transition()
        self.assertEqual(overlay._stage, 1)

        # Step animation until stage 2 (hold black)
        for _ in range(50):
            overlay._on_anim_step()
            if overlay._stage == 2:
                break

        self.assertEqual(overlay._stage, 2)
        self.assertEqual(overlay._alpha, 255)
        self.assertGreater(overlay.get_remaining_hold_seconds(), 0)

        overlay.stop_transition()
        overlay.cleanup()
        parent.close()

    def test_black_hold_duration_and_remaining_time(self):
        """Verify that hold duration progresses and transitions back to idle."""
        import time
        parent = QWidget()
        overlay = AntiBurnInOverlay(parent)
        # Set a very short hold duration (0.001 min ~ 0.06s)
        overlay.set_hold_minutes(0.001)
        overlay.start_transition()

        # Step into stage 2
        for _ in range(50):
            overlay._on_anim_step()
            if overlay._stage == 2:
                break
        self.assertEqual(overlay._stage, 2)

        # Wait for hold duration to elapse
        time.sleep(0.12)
        overlay._on_anim_step()
        self.assertEqual(overlay._stage, 3)

        # Step until fade-out completes
        for _ in range(60):
            overlay._on_anim_step()
            if not overlay.is_transitioning():
                break

        self.assertFalse(overlay.is_transitioning())
        self.assertEqual(overlay._alpha, 0)
        overlay.cleanup()
        parent.close()


    def test_desktop_screen_overlay_window_initialization(self):
        """Verify DesktopScreenOverlayWindow initializes with click-through and without errors."""
        win = DesktopScreenOverlayWindow()
        self.assertIsNotNone(win)
    def test_anti_burn_escape_all_and_f12_key(self):
        """Verify AntiBurnInOverlay.escape_all() and F12 instantly terminate transitions."""
        from PyQt5.QtGui import QKeyEvent
        from PyQt5.QtCore import QEvent, Qt

        parent = QWidget()
        overlay = AntiBurnInOverlay(parent)
        overlay.start_transition()
        self.assertTrue(overlay.is_transitioning())

        # Test escape_all classmethod
        res = AntiBurnInOverlay.escape_all()
        self.assertTrue(res)
        self.assertFalse(overlay.is_transitioning())

        # Test F12 key press event
        overlay.start_transition()
        self.assertTrue(overlay.is_transitioning())
        key_event = QKeyEvent(QEvent.KeyPress, Qt.Key_F12, Qt.NoModifier)
        overlay.keyPressEvent(key_event)
        self.assertFalse(overlay.is_transitioning())

        overlay.cleanup()
        parent.close()

    def test_floating_screen_guard_text(self):
        """Verify FloatingTextTracker moves and bounces inside bounds."""
        from ui.anti_burn_in_overlay import FloatingTextTracker
        tracker = FloatingTextTracker("스크린 가드 중. 긴급탈출 f12")
        self.assertEqual(tracker.text, "스크린 가드 중. 긴급탈출 f12")

        tracker.reset(800, 600)
        init_x, init_y = tracker.x, tracker.y
        tracker.update(800, 600, 200, 30)
        self.assertNotEqual(tracker.x, init_x)
        self.assertNotEqual(tracker.y, init_y)

        # Force near right boundary and verify bounce
        tracker.x = 790.0
        tracker.vx = 2.0
        tracker.update(800, 600, 200, 30)
        self.assertLess(tracker.vx, 0)


if __name__ == "__main__":
    unittest.main()

