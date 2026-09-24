"""
Unit tests for FGOA Core functionality.
"""
import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.models import ColorPoint, Condition, Action, Scenario, Project
from core.evaluator import ConditionEvaluator


class TestCoreModels(unittest.TestCase):

    def test_color_point_matching(self):
        # Point with target RGB(100, 150, 200) and tolerance 10
        pt = ColorPoint(x=50, y=80, r=100, g=150, b=200, tolerance=10, match_mode="match")

        # Exact match
        self.assertTrue(pt.matches(100, 150, 200))
        # Within tolerance
        self.assertTrue(pt.matches(105, 145, 208))
        # Outside tolerance
        self.assertFalse(pt.matches(100, 150, 215))

        # Test not_match mode
        pt_not = ColorPoint(x=50, y=80, r=100, g=150, b=200, tolerance=10, match_mode="not_match")
        self.assertFalse(pt_not.matches(100, 150, 200))
        self.assertTrue(pt_not.matches(100, 150, 250))

    def test_line_point_sampling(self):
        # Sample 5 points from (0, 0) to (100, 200)
        points = ConditionEvaluator.sample_line_points(
            start_x=0, start_y=0,
            end_x=100, end_y=200,
            count=5
        )
        self.assertEqual(len(points), 5)
        self.assertEqual((points[0].x, points[0].y), (0, 0))
        self.assertEqual((points[-1].x, points[-1].y), (100, 200))
        self.assertEqual((points[2].x, points[2].y), (50, 100))
        self.assertTrue(all(p.point_type == "line" for p in points))
        self.assertTrue(all(p.line_group_id == points[0].line_group_id for p in points))

    def test_condition_duplicate_detection(self):
        cond1 = Condition(
            name="C1",
            points=[
                ColorPoint(x=10, y=20, r=255, g=0, b=0),
                ColorPoint(x=50, y=60, r=0, g=255, b=0)
            ]
        )
        cond2 = Condition(
            name="C2",
            points=[
                ColorPoint(x=10, y=20, r=255, g=0, b=0),
                ColorPoint(x=50, y=60, r=0, g=255, b=0)
            ]
        )
        cond3 = Condition(
            name="C3",
            points=[
                ColorPoint(x=10, y=20, r=255, g=0, b=0),
                ColorPoint(x=50, y=60, r=0, g=0, b=255)  # Blue instead of green
            ]
        )

        self.assertTrue(ConditionEvaluator.are_conditions_duplicate(cond1, cond2))
        self.assertFalse(ConditionEvaluator.are_conditions_duplicate(cond1, cond3))

    def test_project_uniqueness_checker(self):
        proj = Project(name="Test Proj")
        s1 = Scenario(
            id="s1", step_number=1, name="첫번째",
            condition=Condition(points=[ColorPoint(x=100, y=200, r=50, g=60, b=70)])
        )
        s2 = Scenario(
            id="s2", step_number=2, name="두번째 (동일)",
            condition=Condition(points=[ColorPoint(x=100, y=200, r=50, g=60, b=70)])
        )
        s3 = Scenario(
            id="s3", step_number=3, name="세번째 (고유)",
            condition=Condition(points=[ColorPoint(x=300, y=400, r=10, g=20, b=30)])
        )
        proj.scenarios = [s1, s2, s3]

        warnings = ConditionEvaluator.check_project_uniqueness(proj)
        self.assertIn("s1", warnings)
        self.assertIn("s2", warnings)
        self.assertNotIn("s3", warnings)
        self.assertIn("시나리오 #2", warnings["s1"][0])

    def test_scenario_serialization(self):
        scen = Scenario(
            step_number=1,
            name="테스트 시나리오",
            enabled=True,
            on_match="jump",
            jump_target_on_match="target_123",
            actions=[
                Action(action_type="mouse_click", x=123, y=456, mouse_button="right"),
                Action(action_type="delay", delay_seconds=3.0)
            ]
        )
        data = scen.to_dict()
        reconstructed = Scenario.from_dict(data)

        self.assertEqual(reconstructed.name, "테스트 시나리오")
        self.assertEqual(reconstructed.scenario_number, 1)
        self.assertEqual(reconstructed.on_match, "jump")
        self.assertEqual(reconstructed.jump_target_on_match, "target_123")
        self.assertEqual(len(reconstructed.actions), 2)
        self.assertEqual(reconstructed.actions[0].mouse_button, "right")
        self.assertEqual(reconstructed.actions[1].delay_seconds, 3.0)

    def test_scenario_unique_number_and_lookup(self):
        proj = Project(name="Lookup Test")
        s1 = Scenario(id="scen_a", step_number=1, scenario_number=101, name="Step A")
        s2 = Scenario(id="scen_b", step_number=2, scenario_number=102, name="Step B")
        proj.scenarios = [s1, s2]

        self.assertEqual(proj.get_next_scenario_number(), 103)
        self.assertEqual(proj.find_scenario_by_number(101), s1)
    def test_loop_hierarchy_depths(self):
        proj = Project(name="Loop Test")
        s1 = Scenario(id="s1", name="루프1 시작", node_type="loop_start", loop_mode="count", loop_count=3)
        s2 = Scenario(id="s2", name="자식 1")
        s3 = Scenario(id="s3", name="자식 2")
        s4 = Scenario(id="s4", name="루프1 종료", node_type="loop_end")
        s5 = Scenario(id="s5", name="외부 시나리오")
        proj.scenarios = [s1, s2, s3, s4, s5]

        depths = proj.compute_hierarchy_depths()
        self.assertEqual(depths, [0, 1, 1, 0, 0])

        self.assertEqual(proj.find_matching_loop_end(0), 3)
        self.assertEqual(proj.find_matching_loop_start(3), 0)

    def test_gallery_usage_computation(self):
        from ui.reference_gallery_dialog import ReferenceGalleryDialog
        proj = Project(name="Gallery Test")
        ref_path = "C:/fake/test_ref.png"
        s1 = Scenario(
            id="s1", scenario_number=1, name="배틀 시작",
            condition=Condition(reference_image_path=ref_path, points=[ColorPoint(x=10, y=20)]),
            actions=[Action(action_type="mouse_click", x=100, y=200)]
        )
        s2 = Scenario(id="s2", scenario_number=2, name="스킬")
        proj.scenarios = [s1, s2]

        usages = ReferenceGalleryDialog.compute_image_usages(ref_path, proj)
        self.assertGreaterEqual(len(usages), 1)
        self.assertTrue(any("배틀 시작" in u["scenario_name"] for u in usages))

    def test_antiban_settings_and_positive_offset(self):
        # 1. Project model serialization includes anti_ban_offset_seconds
        proj = Project(name="AntiBan Test", anti_ban_enabled=True, anti_ban_offset_seconds=2.5)
        d = proj.to_dict()
        self.assertTrue(d["anti_ban_enabled"])
        self.assertEqual(d["anti_ban_offset_seconds"], 2.5)

        proj_loaded = Project.from_dict(d)
        self.assertTrue(proj_loaded.anti_ban_enabled)
        self.assertEqual(proj_loaded.anti_ban_offset_seconds, 2.5)

        # 2. InputController delay jitter is strictly positive (+n seconds, never negative)
        from core.input_controller import InputController
        act_delay = Action(action_type="delay", delay_seconds=1.5)
        _, _, orig_t, final_t = InputController.execute_action(
            act_delay, hwnd=0, apply_anti_ban=True, max_delay=0.5
        )
        self.assertEqual(orig_t, 1.5)
        self.assertGreaterEqual(final_t, 1.5)  # strictly +n seconds, never minus!


if __name__ == "__main__":
    unittest.main()
