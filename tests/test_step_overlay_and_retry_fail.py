"""
Tests for:
1. Single step execution starting from selected scenario node & shortcuts.
2. Action sequence visualization on-screen overlay and execution signals.
3. Recognition condition retry options: stop or jump to specific scenario on failure.
"""
import unittest
from unittest.mock import MagicMock, patch
from PyQt5.QtWidgets import QApplication

# Ensure QApplication instance exists
app = QApplication.instance() or QApplication([])

from core.models import Project, Scenario, Condition, Action, ColorPoint
from core.runner import WorkflowRunner
from ui.action_overlay import ActionOverlayWindow
from ui.inspector_widget import InspectorWidget


class TestStepOverlayAndRetryFail(unittest.TestCase):

    def test_01_single_step_start_from_selected_node(self):
        """Test that runner can start execution from a user-selected scenario node."""
        proj = Project()
        s1 = Scenario(id="scen_1", step_number=1, name="첫번째")
        s2 = Scenario(id="scen_2", step_number=2, name="선택된_두번째")
        s3 = Scenario(id="scen_3", step_number=3, name="세번째")
        proj.scenarios = [s1, s2, s3]

        runner = WorkflowRunner(proj, hwnd=0, start_scenario_id="scen_2")
        runner._step_mode = True
        started_ids = []
        def on_started(sid):
            started_ids.append(sid)
            runner.stop()
        runner.sig_scenario_started.connect(on_started)

        with patch("core.window_manager.WindowManager.get_window_info", return_value=MagicMock(title="Test", client_width=1280, client_height=720)):
            with patch("core.evaluator.ConditionEvaluator.evaluate", return_value=(True, [])):
                runner.run()

        # Started with scen_2, not scen_1!
        self.assertIn("scen_2", started_ids)
        self.assertEqual(started_ids[0], "scen_2")
        self.assertFalse(runner._is_running)

    def test_02_action_visualizer_signals_and_overlay(self):
        """Test that runner emits action executing signals and ActionOverlayWindow accepts them."""
        act_click = Action(action_type="mouse_click", x=150, y=250)
        act_drag = Action(action_type="mouse_drag", x=100, y=100, end_x=300, end_y=300, drag_duration_ms=200)
        scen = Scenario(id="scen_vis", actions=[act_click, act_drag])
        proj = Project(scenarios=[scen])

        runner = WorkflowRunner(proj, hwnd=0)
        executing_actions = []
        finished_actions = []

        runner.sig_action_executing.connect(lambda act, idx, tot: executing_actions.append((act, idx, tot)))
        runner.sig_action_finished.connect(lambda act: finished_actions.append(act))

        overlay = ActionOverlayWindow(target_hwnd=0)

        with patch("core.input_controller.InputController.execute_action"):
            with patch("time.sleep"):
                runner._is_running = True
                runner._execute_actions(scen)

        # 2 actions executed
        self.assertEqual(len(executing_actions), 2)
        self.assertEqual(executing_actions[0][0].action_type, "mouse_click")
        self.assertEqual(executing_actions[0][1], 1)
        self.assertEqual(executing_actions[0][2], 2)
        self.assertEqual(executing_actions[1][0].action_type, "mouse_drag")

        # Test overlay show_action
        overlay.show_action(act_click, index=1, total=2)
        self.assertEqual(overlay.current_action, act_click)
        self.assertEqual(overlay.action_index, 1)

        overlay.show_action(act_drag, index=2, total=2)
        self.assertEqual(overlay.current_action, act_drag)

        overlay.clear_action()
        self.assertIsNone(overlay.current_action)

    def test_03_recognition_condition_retry_fail_stop(self):
        """Test that runner stops automation when condition retries are exhausted and retry_fail_action == 'stop'."""
        cond = Condition(name="TestCond", points=[ColorPoint(x=10, y=10, r=255, g=0, b=0)])
        s1 = Scenario(
            id="scen_retry_stop",
            step_number=1,
            name="재시도_정지",
            condition=cond,
            on_mismatch="retry",
            retry_max_count=2,
            retry_interval_sec=0.01,
            retry_fail_action="stop"
        )
        s2 = Scenario(id="scen_after", step_number=2, name="이후단계")
        proj = Project(scenarios=[s1, s2])

        runner = WorkflowRunner(proj, hwnd=0)
        logs = []
        runner.sig_log.connect(lambda level, msg: logs.append((level, msg)))

        with patch("core.window_manager.WindowManager.get_window_info", return_value=MagicMock(title="Test", client_width=1280, client_height=720)):
            with patch("core.evaluator.ConditionEvaluator.evaluate", return_value=(False, [])):
                runner.run()

        # Ensure error log emitted and stopped before s2
        self.assertTrue(any(level == "ERROR" and "재시도 실패로 오토 실행을 정지합니다" in msg for level, msg in logs))
        self.assertFalse(runner._is_running)

    def test_04_recognition_condition_retry_fail_jump(self):
        """Test that runner jumps to target scenario when condition retries are exhausted and retry_fail_action == 'jump'."""
        cond = Condition(name="TestCond", points=[ColorPoint(x=10, y=10, r=255, g=0, b=0)])
        s1 = Scenario(
            id="scen_retry_jump",
            step_number=1,
            name="재시도_점프",
            condition=cond,
            on_mismatch="retry",
            retry_max_count=1,
            retry_interval_sec=0.01,
            retry_fail_action="jump",
            retry_fail_jump_target="scen_target"
        )
        s2 = Scenario(id="scen_middle", step_number=2, name="중간단계_건너뛰어야함")
        s3 = Scenario(id="scen_target", step_number=3, name="점프대상")
        proj = Project(scenarios=[s1, s2, s3], loop_count=1)

        runner = WorkflowRunner(proj, hwnd=0)
        started_ids = []
        runner.sig_scenario_started.connect(lambda sid: started_ids.append(sid))

        with patch("core.window_manager.WindowManager.get_window_info", return_value=MagicMock(title="Test", client_width=1280, client_height=720)):
            # s1 fails (False), s3 succeeds (True)
            def mock_eval(condition, hwnd):
                if condition == cond:
                    return (False, [])
                return (True, [])

            with patch("core.evaluator.ConditionEvaluator.evaluate", side_effect=mock_eval):
                runner.run()

        # s1 ran, skipped s2, and jumped directly to s3!
        self.assertIn("scen_retry_jump", started_ids)
        self.assertNotIn("scen_middle", started_ids)
        self.assertIn("scen_target", started_ids)

    def test_05_inspector_retry_fail_ui_binding(self):
        """Test that InspectorWidget correctly loads and modifies retry failure options."""
        proj = Project()
        s1 = Scenario(
            id="scen_inspect",
            on_mismatch="retry",
            retry_fail_action="jump",
            retry_fail_jump_target="target_123"
        )
        s_target = Scenario(id="target_123", name="타겟시나리오")
        proj.scenarios = [s1, s_target]

        inspector = InspectorWidget()
        inspector.set_project(proj)
        inspector.set_scenario(s1)

        self.assertEqual(inspector.combo_on_mismatch.currentData(), "retry")
        self.assertEqual(inspector.combo_retry_fail_action.currentData(), "jump")
        self.assertFalse(inspector.row_retry_fail.isHidden())
        self.assertFalse(inspector.combo_retry_fail_jump.isHidden())

        # Change to stop
        idx_stop = inspector.combo_retry_fail_action.findData("stop")
        inspector.combo_retry_fail_action.setCurrentIndex(idx_stop)
        self.assertEqual(inspector.current_scenario.retry_fail_action, "stop")
        inspector._on_save_inspector()
        self.assertEqual(s1.retry_fail_action, "stop")
        self.assertTrue(inspector.combo_retry_fail_jump.isHidden())


if __name__ == "__main__":
    unittest.main()
