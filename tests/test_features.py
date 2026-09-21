"""
Integration and regression tests for new features:
1. Scenario Loop Nodes & Condition Break
2. Action Sequence Recorder
3. Reference Coordinate Picker
4. Reference Gallery & Usage Detection
5. Scenario List Hierarchy Formatting
"""
import unittest
import time
from unittest.mock import MagicMock, patch
from core.models import Project, Scenario, Condition, ColorPoint, Action
from core.runner import WorkflowRunner
from core.recorder import ActionRecorder
from ui.reference_gallery_dialog import ReferenceGalleryDialog


class TestNewFeatures(unittest.TestCase):

    def test_loop_node_count_execution(self):
        """Test loop node executes the specified count of iterations then completes."""
        proj = Project(name="Loop Count Test", loop_count=1)
        s_start = Scenario(id="l_start", scenario_number=1, name="루프시작", node_type="loop_start", loop_mode="count", loop_count=2)
        s_work = Scenario(id="l_work", scenario_number=2, name="작업", node_type="normal", actions=[Action(action_type="delay", delay_seconds=0.01)])
        s_end = Scenario(id="l_end", scenario_number=3, name="루프끝", node_type="loop_end", loop_target_id="l_start")
        s_after = Scenario(id="l_after", scenario_number=4, name="루프이후", node_type="normal")
        proj.scenarios = [s_start, s_work, s_end, s_after]

        runner = WorkflowRunner(project=proj, hwnd=12345)
        # Mock window manager so it doesn't fail on hwnd
        with patch("core.runner.WindowManager.get_window_info") as mock_win:
            mock_win.return_value = MagicMock(title="TestWin", client_width=800, client_height=600)
            runner.run()

        # Should finish cleanly
        self.assertFalse(runner._is_running)

    def test_loop_node_until_match_break(self):
        """Test until_match loop exits when condition matches."""
        proj = Project(name="Loop Break Test", loop_count=1)
        cond = Condition(points=[ColorPoint(x=10, y=10, r=255, g=0, b=0)])
        s_start = Scenario(
            id="l_start", scenario_number=1, name="루프시작",
            node_type="loop_start", loop_mode="until_match", loop_count=10,
            condition=cond
        )
        s_work = Scenario(id="l_work", scenario_number=2, name="작업", node_type="normal")
        s_end = Scenario(id="l_end", scenario_number=3, name="루프끝", node_type="loop_end", loop_target_id="l_start")
        proj.scenarios = [s_start, s_work, s_end]

        runner = WorkflowRunner(project=proj, hwnd=12345)
        with patch("core.runner.WindowManager.get_window_info") as mock_win, \
             patch("core.runner.ConditionEvaluator.evaluate") as mock_eval:
            mock_win.return_value = MagicMock(title="TestWin", client_width=800, client_height=600)
            # Condition matches on first evaluation
            mock_eval.return_value = (True, {s_start.condition.points[0].id: True})
            runner.run()

        self.assertFalse(runner._is_running)

    def test_action_recorder_delay_insert(self):
        """Test ActionRecorder manual delay insertion and action models."""
        recorder = ActionRecorder(target_hwnd=0)
        recorder.insert_delay(1.5)
        self.assertEqual(len(recorder.recorded_actions), 1)
        self.assertEqual(recorder.recorded_actions[0].action_type, "delay")
        self.assertEqual(recorder.recorded_actions[0].delay_seconds, 1.5)

    def test_reference_gallery_usage_detection(self):
        """Test that ReferenceGallery correctly detects usages across Eye and Hand."""
        proj = Project(name="Gallery Detect Test")
        ref_image = "C:/refs/test_card.png"
        s1 = Scenario(
            id="s1", scenario_number=1, name="카드 선택",
            condition=Condition(reference_image_path=ref_image, points=[ColorPoint(x=50, y=50)]),
            actions=[Action(action_type="mouse_click", x=200, y=300)]
        )
        proj.scenarios = [s1]

        usages = ReferenceGalleryDialog.compute_image_usages(ref_image, proj)
        self.assertEqual(len(usages), 2)  # 1 Eye condition + 1 Hand action
        types = [u["type"] for u in usages]
        self.assertIn("👁️ Eye 색상 조건", types)
        self.assertIn("✋ Hand 액션", types)

    def test_nested_loop_hierarchy_depths(self):
        """Test nested loops compute correct hierarchy depths."""
        proj = Project(name="Nested Loop Test")
        s1 = Scenario(id="s1", name="루프1 시작", node_type="loop_start")
        s2 = Scenario(id="s2", name="루프2 시작", node_type="loop_start")
        s3 = Scenario(id="s3", name="내부작업")
        s4 = Scenario(id="s4", name="루프2 종료", node_type="loop_end")
        s5 = Scenario(id="s5", name="루프1 종료", node_type="loop_end")
        proj.scenarios = [s1, s2, s3, s4, s5]

        depths = proj.compute_hierarchy_depths()
        self.assertEqual(depths, [0, 1, 2, 1, 0])


if __name__ == "__main__":
    unittest.main()
