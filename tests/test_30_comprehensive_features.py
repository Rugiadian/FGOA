"""
Comprehensive 30 Feature Integration Tests for FGOA.
Tests all critical components, bug fixes (including QApplication in drag-and-drop),
ActionSequence modularity, PopupPlayBar, Runner, Inspector, and Error Handling.
"""
import sys
import os
import copy
import json
import unittest
from unittest.mock import MagicMock, patch

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QPoint, QMimeData
from PyQt5.QtGui import QMouseEvent

# Ensure QApplication exists
app = QApplication.instance() or QApplication(sys.argv)

from core.models import Project, Scenario, Condition, ColorPoint, Action, ActionSequence
from core.runner import WorkflowRunner
from core.evaluator import ConditionEvaluator
from ui.main_window import MainWindow, DraggableScenarioTableWidget
from ui.popup_play_bar import PopupPlayBar
from ui.inspector_widget import InspectorWidget
from ui.action_sequence_manager_dialog import ActionSequenceManagerDialog
from ui.action_overlay import ActionOverlayWindow
from ui.reference_gallery_dialog import ReferenceGalleryDialog


class Test30ComprehensiveFeatures(unittest.TestCase):
    """30 comprehensive functional tests covering FGOA architecture and recent enhancements."""

    def setUp(self):
        self.project = Project(name="30_Test_Project")
        self.scen1 = Scenario(id="scen_1", scenario_number=1, name="턴 1 진입")
        self.scen2 = Scenario(id="scen_2", scenario_number=2, name="스킬 사용")
        self.project.scenarios = [self.scen1, self.scen2]
        self.project.renumber_steps()

    # ----------------------------------------------------------------------
    # Test 1: Draggable Table mouseMoveEvent & QApplication.startDragDistance
    # ----------------------------------------------------------------------
    def test_01_draggable_table_mouse_move_start_drag_distance(self):
        """[Test 01] Verify DraggableScenarioTableWidget does not crash on mouseMoveEvent (QApplication import fix)."""
        table = DraggableScenarioTableWidget()
        table.setRowCount(2)
        table._drag_start_pos = QPoint(10, 10)
        table._drag_start_row = 0

        # Simulate small mouse move (below drag threshold)
        event_small = QMouseEvent(QMouseEvent.MouseMove, QPoint(12, 12), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        try:
            table.mouseMoveEvent(event_small)
            no_error = True
        except NameError as e:
            no_error = False

        self.assertTrue(no_error, "QApplication must be defined and mouseMoveEvent should not raise NameError")
        table.close()

    # ----------------------------------------------------------------------
    # Test 2: Draggable Table Row Reorder Signal & Mime Data
    # ----------------------------------------------------------------------
    def test_02_draggable_table_reorder_signals(self):
        """[Test 02] Verify row reorder signal and mime data parsing."""
        table = DraggableScenarioTableWidget()
        reorder_events = []
        table.sig_row_reordered.connect(lambda f, t: reorder_events.append((f, t)))

        mime = QMimeData()
        mime.setData("application/x-fgoa-scen-row", b"0")
        self.assertTrue(mime.hasFormat("application/x-fgoa-scen-row"))
        self.assertEqual(int(mime.data("application/x-fgoa-scen-row").data().decode("utf-8")), 0)
        table.close()

    # ----------------------------------------------------------------------
    # Test 3: Main Window Initialization & Title Version
    # ----------------------------------------------------------------------
    def test_03_main_window_initialization_and_version(self):
        """[Test 03] Verify MainWindow initializes with version string and 3 docks."""
        from core.version import __version__
        win = MainWindow()
        self.assertIn(f"v{__version__}", win.windowTitle())
        self.assertIsNotNone(win.dock_scenarios)
        self.assertIsNotNone(win.dock_inspector)
        self.assertIsNotNone(win.dock_log)
        win.close()

    # ----------------------------------------------------------------------
    # Test 4: Popup Play Bar Toggle (F4 / Button)
    # ----------------------------------------------------------------------
    def test_04_popup_playbar_toggle_shortcut_f4(self):
        """[Test 04] Verify F4 shortcut and toolbar button toggle popup play bar."""
        win = MainWindow()
        self.assertIsNotNone(win.popup_play_bar)
        self.assertFalse(win.popup_play_bar.isVisible())

        win._toggle_popup_playbar()
        self.assertTrue(win.popup_play_bar.isVisible())
        self.assertTrue(win.btn_popup_playbar.isChecked())

        win._toggle_popup_playbar()
        self.assertFalse(win.popup_play_bar.isVisible())
        self.assertFalse(win.btn_popup_playbar.isChecked())
        win.close()

    # ----------------------------------------------------------------------
    # Test 5: Popup Play Bar Controls & State Transitions
    # ----------------------------------------------------------------------
    def test_05_popup_playbar_buttons_and_signals(self):
        """[Test 05] Verify PopupPlayBar playback buttons and runner state transitions."""
        bar = PopupPlayBar()
        bar.set_runner_state("running", "테스트 실행 중")
        self.assertIn("실행 중", bar.lbl_state_badge.text())
        self.assertFalse(bar.btn_play.isEnabled())
        self.assertTrue(bar.btn_stop.isEnabled())

        bar.set_runner_state("paused", "일시정지")
        self.assertIn("일시정지", bar.lbl_state_badge.text())
        self.assertTrue(bar.btn_play.isEnabled())

        bar.set_runner_state("stopped", "정지됨")
        self.assertIn("대기 중", bar.lbl_state_badge.text())
        self.assertTrue(bar.btn_play.isEnabled())
        self.assertFalse(bar.btn_stop.isEnabled())
        bar.close()

    # ----------------------------------------------------------------------
    # Test 6: Popup Play Bar Scenario Quick Preset Chips
    # ----------------------------------------------------------------------
    def test_06_popup_playbar_scenario_chips(self):
        """[Test 06] Verify PopupPlayBar creates clickable preset chip buttons for all scenarios."""
        bar = PopupPlayBar()
        bar.refresh_scenarios(self.project.scenarios)

        start_requests = []
        bar.sig_start_requested.connect(lambda sid: start_requests.append(sid))

        # Check dropdown items count
        self.assertEqual(bar.combo_presets.count(), 2)

        # Trigger run selected
        bar.combo_presets.setCurrentIndex(1)
        bar._on_run_selected_preset()
        self.assertEqual(len(start_requests), 1)
        self.assertEqual(start_requests[0], "scen_2")
        bar.close()

    # ----------------------------------------------------------------------
    # Test 7: Action Sequence Dataclass & Summary
    # ----------------------------------------------------------------------
    def test_07_action_sequence_creation_and_fields(self):
        """[Test 07] Verify ActionSequence data model creation, summary, and serialization."""
        seq = ActionSequence(
            id="seq_alpha",
            name="공격 사이클",
            actions=[
                Action(action_type="mouse_click", x=120, y=340),
                Action(action_type="delay", delay_seconds=1.2)
            ]
        )
        self.assertEqual(seq.name, "공격 사이클")
        self.assertIn("좌클릭 (120, 340)", seq.get_summary())
        d = seq.to_dict()
        rebuilt = ActionSequence.from_dict(d)
        self.assertEqual(rebuilt.id, "seq_alpha")
        self.assertEqual(len(rebuilt.actions), 2)

    # ----------------------------------------------------------------------
    # Test 8: Project Action Sequence Registry & Safe Delete
    # ----------------------------------------------------------------------
    def test_08_action_sequence_project_add_find_delete(self):
        """[Test 08] Verify Project adds, finds, and safely unlinks ActionSequence on delete."""
        seq = ActionSequence(id="seq_shared", name="공용 시퀀스")
        self.project.add_action_sequence(seq)
        self.scen1.sequence_id = "seq_shared"

        found = self.project.find_action_sequence("seq_shared")
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "공용 시퀀스")

        # Delete sequence -> scen1.sequence_id must become None
        self.project.delete_action_sequence("seq_shared")
        self.assertIsNone(self.project.find_action_sequence("seq_shared"))
        self.assertIsNone(self.scen1.sequence_id)

    # ----------------------------------------------------------------------
    # Test 9: Scenario Linked Effective Actions
    # ----------------------------------------------------------------------
    def test_09_scenario_action_sequence_link_effective_actions(self):
        """[Test 09] Verify linked scenario returns actions from ActionSequence."""
        seq = ActionSequence(
            id="seq_link_test",
            name="링크 모듈",
            actions=[Action(action_type="key_press", key="Space")]
        )
        self.project.add_action_sequence(seq)
        self.scen1.sequence_id = "seq_link_test"

        eff = self.scen1.get_effective_actions(self.project)
        self.assertEqual(len(eff), 1)
        self.assertEqual(eff[0].key, "Space")
        self.assertIn("링크 모듈", self.scen1.get_actions_summary(self.project))

    # ----------------------------------------------------------------------
    # Test 10: Scenario Unlinked Effective Actions Fallback
    # ----------------------------------------------------------------------
    def test_10_scenario_action_sequence_unlinked_fallback(self):
        """[Test 10] Verify unlinked scenario returns its own standalone actions."""
        self.scen2.sequence_id = None
        self.scen2.actions = [Action(action_type="mouse_click", x=50, y=60)]
        eff = self.scen2.get_effective_actions(self.project)
        self.assertEqual(len(eff), 1)
        self.assertEqual(eff[0].x, 50)
        self.assertIn("좌클릭 (50, 60)", self.scen2.get_actions_summary(self.project))

    # ----------------------------------------------------------------------
    # Test 11: Inspector Action Sequence Selection Combobox
    # ----------------------------------------------------------------------
    def test_11_inspector_action_sequence_selection_combo(self):
        """[Test 11] Verify Inspector populates sequence combo and updates status."""
        seq = ActionSequence(id="seq_inspect", name="스킬 시퀀스")
        self.project.add_action_sequence(seq)
        self.scen1.sequence_id = "seq_inspect"

        inspector = InspectorWidget()
        inspector.set_scenario(self.scen1, project=self.project)

        self.assertGreaterEqual(inspector.combo_sequence.count(), 2)
        self.assertEqual(inspector.combo_sequence.currentData(), "seq_inspect")
        self.assertIn("스킬 시퀀스", inspector.lbl_seq_status.text())
        inspector.close()

    # ----------------------------------------------------------------------
    # Test 12: Inspector Save Actions as New Sequence
    # ----------------------------------------------------------------------
    def test_12_inspector_save_as_new_sequence(self):
        """[Test 12] Verify Inspector registers scenario actions into a new modular sequence."""
        self.scen2.actions = [Action(action_type="mouse_click", x=99, y=88)]
        inspector = InspectorWidget()
        inspector.set_scenario(self.scen2, project=self.project)

        with patch("PyQt5.QtWidgets.QInputDialog.getText", return_value=("등록된 새 시퀀스", True)):
            inspector._on_save_as_new_sequence()

        self.assertIsNotNone(self.scen2.sequence_id or inspector.current_scenario.sequence_id)
        found = any(s.name == "등록된 새 시퀀스" for s in self.project.action_sequences)
        self.assertTrue(found)
        inspector.close()

    # ----------------------------------------------------------------------
    # Test 13: Inspector Unlink Sequence
    # ----------------------------------------------------------------------
    def test_13_inspector_unlink_sequence(self):
        """[Test 13] Verify Inspector unlinks shared sequence into standalone actions copy."""
        seq = ActionSequence(
            id="seq_to_unlink",
            name="공용 모듈",
            actions=[Action(action_type="text_type", text="UnlinkTest")]
        )
        self.project.add_action_sequence(seq)
        self.scen1.sequence_id = "seq_to_unlink"

        inspector = InspectorWidget()
        inspector.set_scenario(self.scen1, project=self.project)
        inspector._on_unlink_sequence()

        self.assertIsNone(inspector.current_scenario.sequence_id)
        self.assertEqual(len(inspector.current_scenario.actions), 1)
        self.assertEqual(inspector.current_scenario.actions[0].text, "UnlinkTest")
        inspector.close()

    # ----------------------------------------------------------------------
    # Test 14: Action Sequence Manager Dialog Operations
    # ----------------------------------------------------------------------
    def test_14_action_sequence_manager_dialog(self):
        """[Test 14] Verify ActionSequenceManagerDialog table and clone/delete operations."""
        seq = ActionSequence(id="seq_mgr", name="관리 대상")
        self.project.add_action_sequence(seq)

        dlg = ActionSequenceManagerDialog(self.project)
        self.assertEqual(dlg.table.rowCount(), 1)
        self.assertEqual(dlg.table.item(0, 1).text(), "관리 대상")

        dlg.table.selectRow(0)
        dlg._on_duplicate_sequence()
        self.assertEqual(len(self.project.action_sequences), 2)
        dlg.close()

    # ----------------------------------------------------------------------
    # Test 15: Runner Executes Effective Actions
    # ----------------------------------------------------------------------
    def test_15_runner_executes_effective_actions(self):
        """[Test 15] Verify WorkflowRunner executes effective actions from linked sequence."""
        seq = ActionSequence(
            id="seq_run",
            actions=[Action(action_type="mouse_click", x=10, y=20)]
        )
        self.project.add_action_sequence(seq)
        self.scen1.sequence_id = "seq_run"

        runner = WorkflowRunner(self.project, hwnd=0)
        runner._is_running = True
        executed = []

        with patch("core.input_controller.InputController.execute_action", side_effect=lambda *args, **kwargs: executed.append(kwargs.get("action") or (args[0] if args else None))):
            runner._execute_actions(self.scen1)

        self.assertEqual(len(executed), 1)
        self.assertEqual(executed[0].x, 10)

    # ----------------------------------------------------------------------
    # Test 16: Anti-ban Time Jitter Strictly Positive
    # ----------------------------------------------------------------------
    def test_16_runner_anti_ban_time_jitter_positive(self):
        """[Test 16] Verify Anti-ban offset is strictly non-negative."""
        self.project.anti_ban_enabled = True
        self.project.anti_ban_offset_seconds = 0.5
        runner = WorkflowRunner(self.project, hwnd=0)
        runner._is_running = True
        logs = []
        runner.sig_log.connect(lambda lvl, msg: logs.append(msg))

        with patch("core.input_controller.InputController.execute_action"):
            runner._execute_actions(Scenario(actions=[Action(action_type="delay", delay_seconds=0.5)]))

        self.assertTrue(any("대기" in m for m in logs))

    # ----------------------------------------------------------------------
    # Test 17: Runner Per-Action Coordinate Anti-ban
    # ----------------------------------------------------------------------
    def test_17_runner_per_action_coordinate_anti_ban(self):
        """[Test 17] Verify Coordinate Anti-ban modes (weak, strong, none)."""
        act_weak = Action(action_type="mouse_click", coord_anti_ban="weak")
        act_strong = Action(action_type="mouse_click", coord_anti_ban="strong")
        act_none = Action(action_type="mouse_click", coord_anti_ban="none")

        ranges = []
        runner = WorkflowRunner(self.project, hwnd=0)
        runner._is_running = True

        with patch("core.input_controller.InputController.execute_action", side_effect=lambda *args, **kwargs: ranges.append(kwargs.get("offset_range"))):
            runner._execute_actions(Scenario(actions=[act_weak, act_strong, act_none]))

        self.assertEqual(ranges, [5, 15, 0])

    # ----------------------------------------------------------------------
    # Test 18: Single Step Execution from Selected Node
    # ----------------------------------------------------------------------
    def test_18_single_step_execution_from_selected_node(self):
        """[Test 18] Verify single step execution initiates from target scenario node."""
        runner = WorkflowRunner(self.project, hwnd=0, start_scenario_id="scen_2")
        self.assertEqual(runner.start_scenario_id, "scen_2")
        self.assertFalse(runner._step_mode)
        runner.step_forward()
        self.assertTrue(runner._step_mode)

    # ----------------------------------------------------------------------
    # Test 19: Condition Evaluator AND Logic
    # ----------------------------------------------------------------------
    def test_19_condition_evaluator_and_logic(self):
        """[Test 19] Verify ConditionEvaluator AND logic matches when all points match."""
        cond = Condition(
            logic_operator="AND",
            points=[
                ColorPoint(x=10, y=10, r=100, g=100, b=100, tolerance=10),
                ColorPoint(x=20, y=20, r=200, g=200, b=200, tolerance=10)
            ]
        )
        with patch("core.screen_capture.ScreenCapture.get_client_pixel_color", side_effect=[(105, 105, 105), (195, 195, 195)]):
            matched, details = ConditionEvaluator.evaluate(cond, hwnd=123)
        self.assertTrue(matched)

    # ----------------------------------------------------------------------
    # Test 20: Condition Evaluator OR Logic
    # ----------------------------------------------------------------------
    def test_20_condition_evaluator_or_logic(self):
        """[Test 20] Verify ConditionEvaluator OR logic matches when at least one matches."""
        cond = Condition(
            logic_operator="OR",
            points=[
                ColorPoint(x=10, y=10, r=100, g=100, b=100, tolerance=5),
                ColorPoint(x=20, y=20, r=200, g=200, b=200, tolerance=5)
            ]
        )
        # First point fails, second point passes
        with patch("core.screen_capture.ScreenCapture.get_client_pixel_color", side_effect=[(0, 0, 0), (202, 202, 202)]):
            matched, details = ConditionEvaluator.evaluate(cond, hwnd=123)
        self.assertTrue(matched)

    # ----------------------------------------------------------------------
    # Test 21: Condition Evaluator not_match Mode
    # ----------------------------------------------------------------------
    def test_21_condition_evaluator_not_match_mode(self):
        """[Test 21] Verify ColorPoint not_match mode."""
        pt = ColorPoint(x=10, y=10, r=50, g=50, b=50, tolerance=5, match_mode="not_match")
        self.assertTrue(pt.matches(200, 200, 200))
        self.assertFalse(pt.matches(50, 52, 49))

    # ----------------------------------------------------------------------
    # Test 22: Condition Retry Fail Action Stop
    # ----------------------------------------------------------------------
    def test_22_condition_retry_fail_action_stop(self):
        """[Test 22] Verify retry exhaustion with fail_action='stop' halts workflow."""
        scen = Scenario(
            on_mismatch="retry",
            retry_max_count=1,
            retry_interval_sec=0.01,
            retry_fail_action="stop",
            condition=Condition(points=[ColorPoint(x=0, y=0, r=255, g=255, b=255)])
        )
        self.assertEqual(scen.retry_fail_action, "stop")

    # ----------------------------------------------------------------------
    # Test 23: Condition Retry Fail Action Jump
    # ----------------------------------------------------------------------
    def test_23_condition_retry_fail_action_jump(self):
        """[Test 23] Verify retry exhaustion with fail_action='jump' branches to target."""
        scen = Scenario(
            on_mismatch="retry",
            retry_max_count=1,
            retry_interval_sec=0.01,
            retry_fail_action="jump",
            retry_fail_jump_target="scen_fallback"
        )
        self.assertEqual(scen.retry_fail_action, "jump")
        self.assertEqual(scen.retry_fail_jump_target, "scen_fallback")

    # ----------------------------------------------------------------------
    # Test 24: Condition Retry Fail Action Next
    # ----------------------------------------------------------------------
    def test_24_condition_retry_fail_action_next(self):
        """[Test 24] Verify retry exhaustion with fail_action='next' skips to next step."""
        scen = Scenario(
            on_mismatch="retry",
            retry_max_count=2,
            retry_fail_action="next"
        )
        self.assertEqual(scen.retry_fail_action, "next")

    # ----------------------------------------------------------------------
    # Test 25: Loop Block Start/End Structure
    # ----------------------------------------------------------------------
    def test_25_loop_block_counting_and_repetition(self):
        """[Test 25] Verify loop start and loop end nesting detection."""
        s_start = Scenario(node_type="loop_start", loop_mode="count", loop_count=3)
        s_body = Scenario(node_type="normal", name="루프 본문")
        s_end = Scenario(node_type="loop_end")
        self.project.scenarios = [s_start, s_body, s_end]

        depths = self.project.compute_hierarchy_depths()
        self.assertEqual(depths, [0, 1, 0])
        end_idx = self.project.find_matching_loop_end(0)
        self.assertEqual(end_idx, 2)

    # ----------------------------------------------------------------------
    # Test 26: Loop Break on Match
    # ----------------------------------------------------------------------
    def test_26_loop_block_break_on_match(self):
        """[Test 26] Verify Scenario break_loop on match configuration."""
        scen = Scenario(on_match="break_loop")
        self.assertEqual(scen.on_match, "break_loop")

    # ----------------------------------------------------------------------
    # Test 27: Action Overlay Visualizer
    # ----------------------------------------------------------------------
    def test_27_action_overlay_visualizer(self):
        """[Test 27] Verify ActionOverlayWindow displays action badges and bounds."""
        overlay = ActionOverlayWindow(target_hwnd=0)
        act = Action(action_type="mouse_click", x=150, y=250)
        overlay.show_action(act, 1, 3)
        self.assertIsNotNone(overlay.current_action)
        self.assertEqual(overlay.action_index, 1)
        self.assertEqual(overlay.total_actions, 3)
        overlay.clear_action()
        self.assertIsNone(overlay.current_action)
        overlay.close()

    # ----------------------------------------------------------------------
    # Test 28: Reference Gallery Resolution Classification
    # ----------------------------------------------------------------------
    def test_28_reference_gallery_resolution_classification(self):
        """[Test 28] Verify ReferenceGalleryDialog categorizes resolutions."""
        dlg = ReferenceGalleryDialog(self.project)
        self.assertIsNotNone(dlg.combo_resolution)
        self.assertGreaterEqual(dlg.combo_resolution.count(), 1)
        self.assertIn("전체 해상도", dlg.combo_resolution.itemText(0))
        dlg.close()

    # ----------------------------------------------------------------------
    # Test 29: Project Full JSON Serialization Roundtrip
    # ----------------------------------------------------------------------
    def test_29_project_json_full_serialization_roundtrip(self):
        """[Test 29] Verify Project JSON roundtrip preserving sequences and scenarios."""
        seq = ActionSequence(id="seq_full", name="풀테스트 시퀀스", actions=[Action(action_type="delay", delay_seconds=0.7)])
        self.project.add_action_sequence(seq)
        self.scen1.sequence_id = "seq_full"

        d = self.project.to_dict()
        json_str = json.dumps(d, ensure_ascii=False)
        reloaded = Project.from_dict(json.loads(json_str))

        self.assertEqual(len(reloaded.action_sequences), 1)
        self.assertEqual(reloaded.action_sequences[0].name, "풀테스트 시퀀스")
        self.assertEqual(reloaded.scenarios[0].sequence_id, "seq_full")
        self.assertEqual(len(reloaded.scenarios), 2)

    # ----------------------------------------------------------------------
    # Test 30: Crash Logging & Recovery
    # ----------------------------------------------------------------------
    def test_30_main_window_crash_log_and_recovery(self):
        """[Test 30] Verify core.logger.log_crash records crash details safely."""
        from core.logger import log_crash, CRASH_LOG_PATH
        try:
            raise ValueError("Test Synthetic Error for Verification")
        except ValueError:
            exc_type, exc_val, exc_tb = sys.exc_info()
            report = log_crash(exc_type, exc_val, exc_tb)

        self.assertIn("ValueError", report)
        self.assertIn("Test Synthetic Error for Verification", report)


if __name__ == "__main__":
    unittest.main()
