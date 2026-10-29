"""
Unit tests verifying pause/resume node memory behavior:
1. When pause is clicked, execution pauses at the active scenario node and remembers it.
2. When the user selects/clicks another node in the table while paused, the paused node memory
   (_paused_scenario_id) remains untouched.
3. When resuming via pause button ("▶ 재개"), execution resumes strictly from the paused node,
   not resetting to beginning or jumping to selected node.
4. When resuming via "▶ 선택부터 시작", execution resumes from the newly selected node.
5. Calling _refresh_scenario_table() while paused does not reset selection to row 0.
"""
import sys
import unittest
from unittest.mock import MagicMock, patch

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from core.models import Project, Scenario, Condition, ColorPoint, Action
from core.runner import WorkflowRunner
from ui.main_window import MainWindow

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)


class TestPauseResumeNodeMemory(unittest.TestCase):
    def setUp(self):
        self.win = MainWindow()
        self.win.target_hwnd = 12345

        # Create 3 test scenarios
        s1 = Scenario(id="scen_1", name="Step 1", scenario_number=1, step_number=1)
        s2 = Scenario(id="scen_2", name="Step 2", scenario_number=2, step_number=2)
        s3 = Scenario(id="scen_3", name="Step 3", scenario_number=3, step_number=3)
        self.win.project.scenarios = [s1, s2, s3]
        self.win._refresh_scenario_table()

    def tearDown(self):
        if hasattr(self.win, "runner") and self.win.runner:
            self.win.runner.stop()
        self.win.close()

    def test_01_pause_remembers_current_running_node(self):
        """Verifies pausing records and remembers the currently active scenario node."""
        runner = WorkflowRunner(self.win.project, hwnd=12345)
        runner.isRunning = MagicMock(return_value=True)
        runner._is_running = True
        runner._is_paused = False
        runner.current_scenario_id = "scen_2"
        self.win.runner = runner

        # Trigger pause
        self.win._on_pause_execution()

        self.assertTrue(runner._is_paused)
        self.assertEqual(self.win._paused_scenario_id, "scen_2")
        self.assertEqual(self.win.btn_pause.text(), "▶ 재개 (Shift+F6)")
        self.assertTrue(self.win.btn_run_selected.isEnabled(), "btn_run_selected must be enabled while paused")

    def test_02_selecting_different_node_while_paused_does_not_overwrite_paused_node(self):
        """Verifies selecting another row while paused preserves _paused_scenario_id."""
        runner = WorkflowRunner(self.win.project, hwnd=12345)
        runner.isRunning = MagicMock(return_value=True)
        runner._is_running = True
        runner._is_paused = False
        runner.current_scenario_id = "scen_2"
        self.win.runner = runner

        # Pause at scen_2 (row 1)
        self.win._on_pause_execution()
        self.assertEqual(self.win._paused_scenario_id, "scen_2")

        # User clicks row 0 (scen_1) or row 2 (scen_3)
        self.win.tbl_scenarios.selectRow(0)
        self.win._on_table_selection_changed()

        # Paused scenario MUST remain scen_2!
        self.assertEqual(self.win._paused_scenario_id, "scen_2",
                         "Selecting another node while paused must NOT overwrite _paused_scenario_id")
        self.assertIsNone(runner._next_scenario_id,
                          "Selecting another node while paused must NOT set runner._next_scenario_id")

        # Select row 2 (scen_3)
        self.win.tbl_scenarios.selectRow(2)
        self.win._on_table_selection_changed()
        self.assertEqual(self.win._paused_scenario_id, "scen_2")

    def test_03_resume_from_pause_resumes_at_paused_node_even_if_another_node_is_selected(self):
        """Verifies clicking Resume restarts from the paused node regardless of table selection."""
        runner = WorkflowRunner(self.win.project, hwnd=12345)
        runner.isRunning = MagicMock(return_value=True)
        runner._is_running = True
        runner._is_paused = True
        runner.current_scenario_id = "scen_2"
        self.win.runner = runner
        self.win._set_paused_state("scen_2")

        # User has row 0 (scen_1) selected in UI table
        self.win.tbl_scenarios.selectRow(0)

        # Click resume (btn_pause)
        self.win._on_pause_execution()

        # Runner is resumed
        self.assertFalse(runner._is_paused)
        # Should clear paused state
        self.assertIsNone(self.win._paused_scenario_id)
        # Next scenario id must NOT be scen_1 (it stays on scen_2)
        self.assertNotEqual(runner._next_scenario_id, "scen_1")
        self.assertFalse(self.win.btn_run_selected.isEnabled(),
                         "btn_run_selected must be disabled when actively running")

    def test_04_run_selected_while_paused_jumps_to_selected_node(self):
        """Verifies clicking '선택부터 시작' while paused jumps to the selected node."""
        runner = WorkflowRunner(self.win.project, hwnd=12345)
        runner.isRunning = MagicMock(return_value=True)
        runner._is_running = True
        runner._is_paused = True
        runner.current_scenario_id = "scen_2"
        self.win.runner = runner
        self.win._set_paused_state("scen_2")

        # User selects row 2 (scen_3)
        self.win.tbl_scenarios.selectRow(2)

        # Click '선택부터 시작' (btn_run_selected)
        with patch("core.runner.WindowManager.get_window_info", return_value=MagicMock()):
            self.win._on_start_selected_execution()

        # Runner must be resumed and directed to jump to scen_3
        self.assertFalse(runner._is_paused)
        self.assertEqual(runner._next_scenario_id, "scen_3")
        self.assertIsNone(self.win._paused_scenario_id)

    def test_05_refresh_table_while_paused_does_not_reset_to_step_zero(self):
        """Verifies _refresh_scenario_table while paused preserves the paused node selection."""
        self.win._set_paused_state("scen_2")
        self.win.tbl_scenarios.clearSelection()

        # Refresh table
        self.win._refresh_scenario_table()

        # Selected row must be row 1 (scen_2), NOT row 0
        selected_rows = [idx.row() for idx in self.win.tbl_scenarios.selectionModel().selectedRows()]
        self.assertIn(1, selected_rows)
        self.assertEqual(self.win._paused_scenario_id, "scen_2")

    def test_06_bottom_right_playback_status_labels(self):
        """Verifies status badge next to background button correctly indicates: 대기중 / 재생중 / 일시 정지중 / 단일스탭 실행중."""
        # 1. Idle (대기중)
        self.win._update_playback_status("idle")
        self.assertIn("대기중", self.win.lbl_run_status.text())
        self.assertFalse(hasattr(self.win, "lbl_status_badge"))

        # 2. Running (재생중)
        self.win._update_playback_status("running")
        self.assertIn("재생중", self.win.lbl_run_status.text())

        # 3. Paused (일시 정지중)
        self.win._update_playback_status("paused")
        self.assertIn("일시 정지중", self.win.lbl_run_status.text())

        # 4. Stepping (단일스탭 실행중)
        self.win._update_playback_status("stepping")
        self.assertIn("단일스탭 실행중", self.win.lbl_run_status.text())

        # 5. Stop returns to 대기중
        self.win._on_stop_execution()
        self.assertIn("대기중", self.win.lbl_run_status.text())


if __name__ == "__main__":
    unittest.main()
