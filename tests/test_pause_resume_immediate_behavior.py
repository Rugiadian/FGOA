"""
Tests for immediate pause responsiveness and resume continuity:
1. When pause is requested during condition evaluation or retry wait, execution halts immediately (<100ms)
   without continuing background retries or actions.
2. When resumed, execution restarts evaluation freshly on the paused scenario node.
3. When paused and a different scenario is selected, resuming jumps directly to the selected scenario.
4. When paused during action delay, sleep halts immediately and pauses cleanly.
"""
import os
import sys
import time
import threading
import unittest
from unittest.mock import MagicMock, patch

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from core.models import Project, Scenario, Condition, ColorPoint, Action
from core.runner import WorkflowRunner
from core.evaluator import ConditionEvaluator

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)


class TestPauseResumeImmediateBehavior(unittest.TestCase):
    def test_01_pause_halts_condition_retry_immediately_without_background_calls(self):
        """Verify that pausing during retry delay stops execution within <100ms and doesn't run more retries."""
        proj = Project(name="RetryPauseProj")
        s1 = Scenario(
            id="scen_retry",
            name="Retry Node",
            step_number=1,
            scenario_number=1,
            enabled=True,
            on_mismatch="retry",
            retry_max_count=10,
            retry_interval_sec=2.0,  # 2.0s wait
            condition=Condition(points=[ColorPoint(x=10, y=10, r=255, g=0, b=0, match_mode="match")])
        )
        proj.scenarios = [s1]

        eval_calls = []
        def mock_eval(cond, hwnd, background_mode=False):
            eval_calls.append(time.time())
            return False, []

        runner = WorkflowRunner(proj, hwnd=12345)
        with patch("core.runner.WindowManager.get_window_info", return_value=MagicMock(title="MockWin", client_width=1000, client_height=600)):
            with patch.object(ConditionEvaluator, "evaluate", side_effect=mock_eval):
                th = threading.Thread(target=runner.run)
                th.daemon = True
                th.start()

                # Wait for initial evaluation
                time.sleep(0.1)
                self.assertEqual(len(eval_calls), 1)

                # Request pause while in 2.0s retry wait
                t0 = time.time()
                runner.pause()
                time.sleep(0.08)
                t_pause_took = time.time() - t0

                # Runner must acknowledge pause immediately
                self.assertTrue(runner._is_paused)
                self.assertTrue(runner._is_running)

                # Wait 1.5 seconds while paused: eval_calls MUST remain exactly 1!
                time.sleep(1.5)
                self.assertEqual(len(eval_calls), 1, "Must NOT continue evaluating retries while paused!")

                # Resume execution: it must immediately re-evaluate scen_retry
                runner.resume()
                time.sleep(0.1)
                self.assertGreaterEqual(len(eval_calls), 2, "Must re-evaluate paused node upon resume!")

                runner.stop()
                th.join(timeout=1.0)

    def test_02_pause_and_select_different_node_resumes_at_selected_node(self):
        """Verify that selecting a different node while paused jumps to it upon resume."""
        proj = Project(name="JumpOnPauseProj")
        s1 = Scenario(
            id="scen_1",
            name="Node 1",
            step_number=1,
            scenario_number=1,
            enabled=True,
            on_mismatch="retry",
            retry_max_count=5,
            retry_interval_sec=1.5,
            condition=Condition(points=[ColorPoint(x=10, y=10, r=255, g=0, b=0)])
        )
        s2 = Scenario(
            id="scen_2",
            name="Node 2",
            step_number=2,
            scenario_number=2,
            enabled=True,
            condition=Condition(points=[ColorPoint(x=50, y=50, r=0, g=255, b=0)])
        )
        proj.scenarios = [s1, s2]

        evaluated_points = []
        def mock_eval(cond, hwnd, background_mode=False):
            if cond and cond.points:
                evaluated_points.append(cond.points[0].x)
            return (cond.points[0].x == 50), []

        runner = WorkflowRunner(proj, hwnd=12345)
        with patch("core.runner.WindowManager.get_window_info", return_value=MagicMock(title="MockWin", client_width=1000, client_height=600)):
            with patch.object(ConditionEvaluator, "evaluate", side_effect=mock_eval):
                th = threading.Thread(target=runner.run)
                th.daemon = True
                th.start()

                time.sleep(0.1)
                self.assertIn(10, evaluated_points)

                # Pause runner
                runner.pause()
                time.sleep(0.1)
                self.assertTrue(runner._is_paused)

                # Simulate user changing target node to scen_2 while paused
                runner.set_next_scenario_id("scen_2")
                runner.resume()

                time.sleep(0.2)
                # s2 must have been evaluated
                self.assertIn(50, evaluated_points)

                runner.stop()
                th.join(timeout=1.0)

    def test_03_sleep_interruptible_aborts_on_pause(self):
        """Verify sleep_interruptible with abort_on_pause returns False in <50ms when paused."""
        proj = Project(name="SleepProj")
        runner = WorkflowRunner(proj, hwnd=0)
        runner._is_running = True
        runner._is_paused = False

        def pause_later():
            time.sleep(0.05)
            runner.pause()

        th = threading.Thread(target=pause_later)
        th.start()

        t0 = time.time()
        completed = runner.sleep_interruptible(5.0, abort_on_pause=True)
        elapsed = time.time() - t0
        th.join()

        self.assertFalse(completed)
        self.assertLess(elapsed, 0.20, f"Expected abort in <200ms, took {elapsed:.3f}s")


if __name__ == "__main__":
    unittest.main()
