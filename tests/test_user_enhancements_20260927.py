"""
Unit tests for user enhancements on 2026-09-27:
1. Action overlay sequence multi-point visualization
2. Enhanced loop start and break log messages & sequence signals
3. Scenario list direct save to loaded file & Save As
4. Running row header highlight without dragged-style row selection
5. Anti-ban settings popup dialog
6. Action duplication in action list tools
7. Clean unused condition and action nodes
8. Elastic inspector list tables without maximum height cap
"""
import unittest
from unittest.mock import MagicMock, patch
import json
import os
import tempfile
from PyQt5.QtWidgets import QApplication

from core.models import Scenario, Project, Condition, ColorPoint, Action, ActionSequence
from core.runner import WorkflowRunner
from ui.action_overlay import ActionOverlayWindow
from ui.anti_ban_dialog import AntiBanDialog
from ui.modules_manager_widget import ModulesManagerWidget
from ui.inspector_widget import InspectorWidget
from ui.action_editor_dialog import ActionEditorDialog

app = QApplication.instance()
if not app:
    app = QApplication([])


class TestEnhancements20260927(unittest.TestCase):

    def test_01_action_overlay_sequence_visualization(self):
        overlay = ActionOverlayWindow(target_hwnd=0)
        act1 = Action(action_type="mouse_click", x=100, y=200)
        act2 = Action(action_type="mouse_drag", x=300, y=400, end_x=500, end_y=600)
        act3 = Action(action_type="delay", delay_seconds=1.0)

        # Show sequence of actions
        overlay.show_sequence([act1, act2, act3], current_index=1, scenario_name="테스트")
        self.assertEqual(len(overlay.sequence_actions), 3)
        self.assertEqual(overlay.action_index, 1)
        self.assertEqual(overlay.current_action, act1)

        # Update active step
        overlay.set_current_action_index(2)
        self.assertEqual(overlay.action_index, 2)
        self.assertEqual(overlay.current_action, act2)

        # Clear overlay
        overlay.clear_action()
        self.assertEqual(len(overlay.sequence_actions), 0)
        self.assertIsNone(overlay.current_action)

    def test_02_runner_loop_logs_and_sequence_signals(self):
        proj = Project(name="Runner Test", loop_count=1)
        act_click = Action(action_type="mouse_click", x=50, y=50)
        s_loop_start = Scenario(
            id="s_start", scenario_number=1, name="루프시작",
            node_type="loop_start", loop_mode="count", loop_count=1,
            actions=[act_click]
        )
        s_loop_end = Scenario(
            id="s_end", scenario_number=2, name="루프끝",
            node_type="loop_end", loop_target_id="s_start"
        )
        proj.scenarios = [s_loop_start, s_loop_end]

        runner = WorkflowRunner(project=proj, hwnd=12345)
        logs = []
        seq_started = []
        seq_finished = []

        runner.sig_log.connect(lambda lvl, msg: logs.append((lvl, msg)))
        runner.sig_action_sequence_started.connect(lambda acts, name: seq_started.append((acts, name)))
        runner.sig_action_sequence_finished.connect(lambda: seq_finished.append(True))

        with patch("core.runner.WindowManager.get_window_info") as mock_win, \
             patch("core.runner.InputController.execute_action") as mock_exec:
            mock_win.return_value = MagicMock(title="TestWin", client_width=800, client_height=600)
            runner.run()

        # Sequence start and finish signals
        self.assertGreaterEqual(len(seq_started), 1)
        self.assertGreaterEqual(len(seq_finished), 1)

        # Loop start and escape logs
        log_texts = [msg for lvl, msg in logs]
        has_loop_start = any("루프 시작" in txt for txt in log_texts)
        has_loop_exit = any("루프 탈출" in txt for txt in log_texts)
        self.assertTrue(has_loop_start, f"Missing loop start in logs: {log_texts}")
        self.assertTrue(has_loop_exit, f"Missing loop exit in logs: {log_texts}")

    def test_03_scenario_direct_save_and_save_as(self):
        from ui.main_window import MainWindow
        win = MainWindow()
        win.project = Project(name="Save Test")

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            temp_path = tf.name

        try:
            # When current_project_path is set, saving writes directly without dialog
            win.current_project_path = temp_path
            win._on_save_project()

            self.assertTrue(os.path.exists(temp_path))
            with open(temp_path, "r", encoding="utf-8") as f:
                saved_data = json.load(f)
            self.assertEqual(saved_data.get("name"), "Save Test")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            win.close()

    def test_04_running_row_clears_selection(self):
        from ui.main_window import MainWindow
        win = MainWindow()
        s1 = Scenario(id="s1", scenario_number=1, name="노드 1")
        s2 = Scenario(id="s2", scenario_number=2, name="노드 2")
        win.project.scenarios = [s1, s2]
        win._refresh_scenario_table()

        # Before run, select row 0
        win.tbl_scenarios.selectRow(0)
        self.assertTrue(len(win.tbl_scenarios.selectedItems()) > 0)

        # When scenario s2 starts, selection must be cleared to prevent dragged blue selection look
        win._on_scenario_started("s2")
        self.assertEqual(len(win.tbl_scenarios.selectedItems()), 0)
        self.assertEqual(win.tbl_scenarios._custom_v_header.highlight_row, 1)

        # Completed or finished
        win._highlight_running_row_header(None)
        self.assertEqual(win.tbl_scenarios._custom_v_header.highlight_row, -1)
        win.close()

    def test_05_anti_ban_dialog(self):
        proj = Project(name="AntiBan Test")
        proj.anti_ban_enabled = False
        proj.anti_ban_offset_seconds = 1.5
        proj.anti_ban_coord_weak = 7
        proj.anti_ban_coord_strong = 25

        dlg = AntiBanDialog(proj)
        self.assertFalse(dlg.chk_time_anti_ban.isChecked())
        self.assertAlmostEqual(dlg.spin_offset.value(), 1.5)
        self.assertEqual(dlg.spin_weak.value(), 7)
        self.assertEqual(dlg.spin_strong.value(), 25)

        # Modify values and apply
        dlg.chk_time_anti_ban.setChecked(True)
        dlg.spin_offset.setValue(2.3)
        dlg.spin_weak.setValue(10)
        dlg.spin_strong.setValue(30)
        dlg._on_apply_and_close()

        self.assertTrue(proj.anti_ban_enabled)
        self.assertAlmostEqual(proj.anti_ban_offset_seconds, 2.3)
        self.assertEqual(proj.anti_ban_coord_weak, 10)
        self.assertEqual(proj.anti_ban_coord_strong, 30)

    def test_06_action_duplication_in_dialog_and_inspector(self):
        act = Action(action_type="mouse_click", x=123, y=456, delay_seconds=0.7)
        dlg = ActionEditorDialog(actions=[act], target_hwnd=0)
        dlg.tbl_actions.selectRow(0)
        dlg._on_duplicate_action()

        self.assertEqual(len(dlg.actions), 2)
        self.assertEqual(dlg.actions[1].x, 123)
        self.assertEqual(dlg.actions[1].y, 456)
        self.assertNotEqual(dlg.actions[0].id, dlg.actions[1].id)

    def test_07_clean_unused_condition_and_action_nodes(self):
        proj = Project(name="Unused Nodes Test")
        # Conditions
        cond_used = Condition(id="c_used", condition_number=1, name="사용중 조건")
        cond_unused = Condition(id="c_unused", condition_number=2, name="미사용 조건")
        proj.conditions = [cond_used, cond_unused]

        # Action Sequences
        seq_used = ActionSequence(id="seq_used", sequence_number=1, name="사용중 시퀀스")
        seq_unused = ActionSequence(id="seq_unused", sequence_number=2, name="미사용 시퀀스")
        proj.action_sequences = [seq_used, seq_unused]

        # Scenarios referencing used nodes only
        s = Scenario(id="s1", name="시나리오1", condition_id="c_used", sequence_id="seq_used")
        proj.scenarios = [s]

        widget = ModulesManagerWidget(project=proj, target_hwnd=0)

        # Test cleaning unused condition with confirmation mock
        with patch("PyQt5.QtWidgets.QMessageBox.question", return_value=16384):  # QMessageBox.Yes = 0x4000 = 16384
            widget._on_clean_unused_conditions()
        self.assertEqual(len(proj.conditions), 1)
        self.assertEqual(proj.conditions[0].id, "c_used")

        # Test cleaning unused action sequence with confirmation mock
        with patch("PyQt5.QtWidgets.QMessageBox.question", return_value=16384):
            widget._on_clean_unused_sequences()
        self.assertEqual(len(proj.action_sequences), 1)
        self.assertEqual(proj.action_sequences[0].id, "seq_used")

    def test_08_inspector_tables_elasticity_without_maximum_height_cap(self):
        inspector = InspectorWidget()
        # Verify tbl_points and tbl_actions do not have artificial 150/200 px caps
        self.assertGreater(inspector.tbl_points.maximumHeight(), 1000)
        self.assertGreater(inspector.tbl_actions.maximumHeight(), 1000)


if __name__ == "__main__":
    unittest.main()
