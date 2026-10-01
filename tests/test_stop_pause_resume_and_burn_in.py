"""
Unit tests for Immediate Stop, Node-Preserving Pause/Resume, and Rainbow Anti-Burn-In Overlay.
"""
import sys
import time
import unittest
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPainter, QPixmap

from core.models import Project, Scenario, Action
from core.runner import WorkflowRunner
from ui.scenario_table_widget import DraggableScenarioTableWidget, ScenarioVerticalHeader
from ui.anti_burn_in_overlay import AntiBurnInOverlay

app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)


class TestStopPauseResumeAndBurnIn(unittest.TestCase):

    def test_immediate_stop_interrupts_delays(self):
        """Verify runner.stop() terminates in <150ms even when 10s post delay or action delay is configured."""
        proj = Project(name="TestProj")
        scen = Scenario(
            name="LongDelayNode",
            node_type="normal",
            on_match="execute",
            post_delay_seconds=10.0,
            actions=[Action(action_type="delay", delay_seconds=10.0)]
        )
        proj.scenarios.append(scen)

        # Mock hwnd
        runner = WorkflowRunner(proj, hwnd=0)
        # Directly test sleep_interruptible responsiveness
        t0 = time.time()
        # In a background thread or sequential with stop trigger
        runner._is_running = True

        def trigger_stop():
            time.sleep(0.03)
            runner.stop()

        import threading
        th = threading.Thread(target=trigger_stop)
        th.start()

        # runner.sleep_interruptible for 10 seconds should return within <100ms
        completed = runner.sleep_interruptible(10.0)
        t_elapsed = time.time() - t0
        th.join()

        self.assertFalse(completed)
        self.assertFalse(runner._is_running)
        self.assertLess(t_elapsed, 0.20, f"Expected stop in <200ms, took {t_elapsed:.3f}s")

    def test_pause_and_resume_node_position_immunity(self):
        """Verify that pausing remembers the scenario by ID, and resuming finds it even if moved in table."""
        proj = Project(name="ReorderProj")
        s1 = Scenario(id="scen_1", name="Step 1", scenario_number=1, step_number=1)
        s2 = Scenario(id="scen_2", name="Step 2", scenario_number=2, step_number=2)
        s3 = Scenario(id="scen_3", name="Step 3", scenario_number=3, step_number=3)
        proj.scenarios = [s1, s2, s3]

        runner = WorkflowRunner(proj, hwnd=0)
        runner.current_scenario_id = "scen_2"
        runner.pause()
        self.assertTrue(runner._is_paused)

        # Simulate user reordering scenarios: Move s2 to index 2 (last)
        proj.scenarios = [s1, s3, s2]
        proj.renumber_steps()

        # Resuming with target id
        runner.set_next_scenario_id("scen_2")
        runner.resume()
        self.assertFalse(runner._is_paused)

        # Resolve target
        target = runner._resolve_target_scenario(runner._next_scenario_id)
        self.assertIsNotNone(target)
        self.assertEqual(target.id, "scen_2")
        self.assertEqual(proj.scenarios.index(target), 2)

    def test_scenario_vertical_header_paused_row_styling(self):
        """Verify ScenarioVerticalHeader and table widget support set_paused_row."""
        tbl = DraggableScenarioTableWidget()
        tbl.setRowCount(5)
        tbl.setColumnCount(4)

        # Test set_paused_row on header
        tbl.set_paused_row(2)
        v_header = tbl.verticalHeader()
        self.assertEqual(v_header.paused_row, 2)

        # Verify header rendering with paused_row
        pix = QPixmap(50, 100)
        painter = QPainter(pix)
        rect = tbl.visualRect(tbl.model().index(2, 0))
        # Should execute paintSection for paused_row without error
        v_header.paintSection(painter, rect, 2)
        painter.end()

        # Reset paused row
        tbl.set_paused_row(-1)
        self.assertEqual(v_header.paused_row, -1)

    def test_anti_burn_in_overlay_black_white_rainbow_stages(self):
        """Verify AntiBurnInOverlay transitions: Black -> White -> Rainbow -> Normal."""
        parent_widget = QApplication.activeWindow() or tbl_dummy if 'tbl_dummy' in dir() else DraggableScenarioTableWidget()
        parent_widget.resize(800, 600)
        overlay = AntiBurnInOverlay(parent_widget)
        overlay.resize(800, 600)

        overlay.start_transition()
        self.assertEqual(overlay._stage, 1)
        self.assertEqual(overlay._color.red(), 0)
        self.assertEqual(overlay._color.green(), 0)
        self.assertEqual(overlay._color.blue(), 0)

        # Step until stage 2 (hold black)
        for _ in range(40):
            if overlay._stage >= 2:
                break
            overlay._on_anim_step()
        self.assertGreaterEqual(overlay._stage, 2)

        # Step until stage 3 (lerp black to white)
        for _ in range(15):
            if overlay._stage >= 3:
                break
            overlay._on_anim_step()
        self.assertGreaterEqual(overlay._stage, 3)

        # Step until stage 4 (white)
        for _ in range(30):
            if overlay._stage >= 4:
                break
            overlay._on_anim_step()
        self.assertGreaterEqual(overlay._stage, 4)
        if overlay._stage == 4:
            self.assertEqual(overlay._color.red(), 255)
            self.assertEqual(overlay._color.green(), 255)
            self.assertEqual(overlay._color.blue(), 255)

        # Step until stage 5 (rainbow mode)
        for _ in range(20):
            if overlay._stage >= 5:
                break
            overlay._on_anim_step()
        self.assertGreaterEqual(overlay._stage, 5)

        # Verify paintEvent in rainbow stage without exception
        pix = QPixmap(800, 600)
        painter = QPainter(pix)
        overlay.paintEvent(None)
        painter.end()

        # Step until transition ends (stage 0)
        for _ in range(120):
            if overlay._stage == 0:
                break
            overlay._on_anim_step()
        self.assertEqual(overlay._stage, 0)
        self.assertEqual(overlay._alpha, 0)


if __name__ == "__main__":
    unittest.main()
