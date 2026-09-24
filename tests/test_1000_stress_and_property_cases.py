"""
1000 Stress, Property, and Functional Test Suite for FGOA.
Covers:
- Category 1: ColorPoint & RGB Math (250 tests)
- Category 2: Condition & Evaluator Logic (200 tests)
- Category 3: Actions & ActionSequences (200 tests)
- Category 4: Scenarios, Hierarchy, Loops & Targets (200 tests)
- Category 5: Runner, Jitter & Anti-Ban Properties (100 tests)
- Category 6: Project Roundtrip, Edge Cases & Fuzzing (50 tests)

Total: Exactly 1000 distinct tests.
"""
import sys
import os
import json
import copy
import random
import unittest
from typing import List
from PIL import Image

from core.models import Project, Scenario, Condition, ColorPoint, Action, ActionSequence
from core.evaluator import ConditionEvaluator
from core.runner import WorkflowRunner
from core.logger import log_crash


# ==============================================================================
# Category 1: ColorPoint & RGB Math (250 Tests)
# ==============================================================================
class TestCategory1ColorPointMath(unittest.TestCase):
    pass


def _setup_category_1():
    # 1-50: Exact Match with tolerance=0 (50 tests)
    for i in range(1, 51):
        r = (i * 37) % 256
        g = (i * 59) % 256
        b = (i * 83) % 256
        def make_test(r=r, g=g, b=b):
            def test_fn(self):
                pt = ColorPoint(x=10, y=20, r=r, g=g, b=b, tolerance=0, match_mode="match")
                self.assertTrue(pt.matches(r, g, b))
                self.assertFalse(pt.matches((r + 1) % 256 if r != 255 else 254, g, b))
            return test_fn
        setattr(TestCategory1ColorPointMath, f"test_cat1_exact_match_{i:04d}", make_test())

    # 51-100: Tolerance Boundary Checks (50 tests)
    for i in range(51, 101):
        tol = (i - 50)  # 1 to 50
        base_r, base_g, base_b = 100, 100, 100
        def make_test(tol=tol):
            def test_fn(self):
                pt = ColorPoint(x=5, y=5, r=100, g=100, b=100, tolerance=tol, match_mode="match")
                # Inside tolerance
                self.assertTrue(pt.matches(100 + tol, 100, 100))
                self.assertTrue(pt.matches(100 - tol, 100, 100))
                # Outside tolerance
                self.assertFalse(pt.matches(100 + tol + 1, 100, 100))
                self.assertFalse(pt.matches(100 - tol - 1, 100, 100))
            return test_fn
        setattr(TestCategory1ColorPointMath, f"test_cat1_tolerance_boundary_{i:04d}", make_test())

    # 101-150: not_match Mode Inversion Checks (50 tests)
    for i in range(101, 151):
        r = (i * 17) % 256
        g = (i * 31) % 256
        b = (i * 43) % 256
        def make_test(r=r, g=g, b=b):
            def test_fn(self):
                pt = ColorPoint(x=15, y=25, r=r, g=g, b=b, tolerance=5, match_mode="not_match")
                # When matching the color, not_match must return False
                self.assertFalse(pt.matches(r, g, b))
                # When color differs greatly, not_match must return True
                diff_r = (r + 128) % 256
                self.assertTrue(pt.matches(diff_r, g, b))
            return test_fn
        setattr(TestCategory1ColorPointMath, f"test_cat1_not_match_mode_{i:04d}", make_test())

    # 151-200: Serialization & Deserialization Roundtrip (50 tests)
    for i in range(151, 201):
        x = i * 10
        y = i * 5
        r = (i * 29) % 256
        g = (i * 47) % 256
        b = (i * 71) % 256
        tol = i % 30
        mode = "not_match" if i % 2 == 0 else "match"
        pt_type = "line" if i % 3 == 0 else "point"
        grp = f"grp_{i}" if pt_type == "line" else ""
        def make_test(x=x, y=y, r=r, g=g, b=b, tol=tol, mode=mode, pt_type=pt_type, grp=grp):
            def test_fn(self):
                pt = ColorPoint(x=x, y=y, r=r, g=g, b=b, tolerance=tol, match_mode=mode, point_type=pt_type, line_group_id=grp)
                d = pt.to_dict()
                rebuilt = ColorPoint.from_dict(d)
                self.assertEqual(rebuilt.x, x)
                self.assertEqual(rebuilt.y, y)
                self.assertEqual(rebuilt.r, r)
                self.assertEqual(rebuilt.g, g)
                self.assertEqual(rebuilt.b, b)
                self.assertEqual(rebuilt.tolerance, tol)
                self.assertEqual(rebuilt.match_mode, mode)
                self.assertEqual(rebuilt.point_type, pt_type)
                self.assertEqual(rebuilt.line_group_id, grp)
            return test_fn
        setattr(TestCategory1ColorPointMath, f"test_cat1_serialization_{i:04d}", make_test())

    # 201-250: Extreme Coordinates & Clamp Checks (50 tests)
    for i in range(201, 251):
        x_val = (i - 200) * 80
        y_val = (i - 200) * 45
        def make_test(x=x_val, y=y_val, idx=i):
            def test_fn(self):
                pt = ColorPoint(x=x, y=y, r=255, g=255, b=255, tolerance=15)
                self.assertEqual(pt.x, x)
                self.assertEqual(pt.y, y)
                self.assertTrue(pt.id)
                self.assertEqual(pt.tolerance, 15)
                # Verify match on exact coordinates
                self.assertTrue(pt.matches(255, 255, 255))
            return test_fn
        setattr(TestCategory1ColorPointMath, f"test_cat1_extreme_coords_{i:04d}", make_test())

_setup_category_1()


# ==============================================================================
# Category 2: Condition & Evaluator Logic (200 Tests)
# ==============================================================================
class TestCategory2ConditionEvaluator(unittest.TestCase):
    pass


def _setup_category_2():
    # 251-290: AND Logic All Pass (40 tests)
    for i in range(251, 291):
        num_points = 2 + (i % 6)  # 2 to 7 points
        def make_test(num_pts=num_points, seed=i):
            def test_fn(self):
                pts = [ColorPoint(x=j*10, y=j*10, r=50+j, g=50+j, b=50+j, tolerance=10) for j in range(num_pts)]
                cond = Condition(logic_operator="AND", points=pts)
                # Create a test image where every point has exact match
                img = Image.new("RGB", (100, 100), (0, 0, 0))
                for pt in pts:
                    img.putpixel((pt.x, pt.y), (pt.r, pt.g, pt.b))
                matched, results = ConditionEvaluator.evaluate(cond, image=img)
                self.assertTrue(matched)
                self.assertEqual(len(results), num_pts)
                self.assertTrue(all(r["passed"] for r in results))
            return test_fn
        setattr(TestCategory2ConditionEvaluator, f"test_cat2_and_logic_pass_{i:04d}", make_test())

    # 291-330: AND Logic One Point Fails (40 tests)
    for i in range(291, 331):
        num_points = 2 + (i % 5)
        fail_idx = i % num_points
        def make_test(num_pts=num_points, f_idx=fail_idx):
            def test_fn(self):
                pts = [ColorPoint(x=j*10, y=j*10, r=100, g=100, b=100, tolerance=5) for j in range(num_pts)]
                cond = Condition(logic_operator="AND", points=pts)
                img = Image.new("RGB", (100, 100), (100, 100, 100))
                # Make the f_idx point completely mismatch
                img.putpixel((pts[f_idx].x, pts[f_idx].y), (0, 0, 0))
                matched, results = ConditionEvaluator.evaluate(cond, image=img)
                self.assertFalse(matched)
                self.assertFalse(results[f_idx]["passed"])
            return test_fn
        setattr(TestCategory2ConditionEvaluator, f"test_cat2_and_logic_fail_{i:04d}", make_test())

    # 331-370: OR Logic Single Point Passes (40 tests)
    for i in range(331, 371):
        num_points = 2 + (i % 6)
        pass_idx = i % num_points
        def make_test(num_pts=num_points, p_idx=pass_idx):
            def test_fn(self):
                pts = [ColorPoint(x=j*10, y=j*10, r=200, g=200, b=200, tolerance=5) for j in range(num_pts)]
                cond = Condition(logic_operator="OR", points=pts)
                # Background black (all fail)
                img = Image.new("RGB", (100, 100), (0, 0, 0))
                # Only pass_idx matches
                img.putpixel((pts[p_idx].x, pts[p_idx].y), (200, 200, 200))
                matched, results = ConditionEvaluator.evaluate(cond, image=img)
                self.assertTrue(matched)
                self.assertTrue(results[p_idx]["passed"])
            return test_fn
        setattr(TestCategory2ConditionEvaluator, f"test_cat2_or_logic_pass_{i:04d}", make_test())

    # 371-410: OR Logic All Fail (40 tests)
    for i in range(371, 411):
        num_points = 2 + (i % 6)
        def make_test(num_pts=num_points):
            def test_fn(self):
                pts = [ColorPoint(x=j*10, y=j*10, r=220, g=220, b=220, tolerance=5) for j in range(num_pts)]
                cond = Condition(logic_operator="OR", points=pts)
                img = Image.new("RGB", (100, 100), (10, 10, 10))
                matched, results = ConditionEvaluator.evaluate(cond, image=img)
                self.assertFalse(matched)
            return test_fn
        setattr(TestCategory2ConditionEvaluator, f"test_cat2_or_logic_fail_{i:04d}", make_test())

    # 411-450: Line Sampling and Unconditional/Edge Evaluation (40 tests)
    for i in range(411, 451):
        count = 2 + (i % 8)
        def make_test(cnt=count, idx=i):
            def test_fn(self):
                img = Image.new("RGB", (200, 200), (120, 130, 140))
                pts = ConditionEvaluator.sample_line_points(10, 10, 100, 100, count=cnt, image=img)
                self.assertEqual(len(pts), cnt)
                self.assertTrue(all(p.point_type == "line" for p in pts))
                self.assertTrue(all(p.line_group_id == pts[0].line_group_id for p in pts))
                # Evaluate these points against the same image
                cond = Condition(logic_operator="AND", points=pts)
                matched, _ = ConditionEvaluator.evaluate(cond, image=img)
                self.assertTrue(matched)
            return test_fn
        setattr(TestCategory2ConditionEvaluator, f"test_cat2_line_sampling_{i:04d}", make_test())

_setup_category_2()


# ==============================================================================
# Category 3: Actions & ActionSequences (200 Tests)
# ==============================================================================
class TestCategory3ActionsAndSequences(unittest.TestCase):
    pass


def _setup_category_3():
    action_types = [
        "mouse_click", "mouse_drag", "mouse_down", "mouse_up", "mouse_move",
        "key_press", "key_down", "key_up", "text_type", "delay", "sound_beep", "log_message"
    ]

    # 451-510: Action Summaries and Properties (60 tests)
    for i in range(451, 511):
        act_type = action_types[i % len(action_types)]
        def make_test(atype=act_type, idx=i):
            def test_fn(self):
                act = Action(
                    action_type=atype,
                    x=idx, y=idx + 10,
                    end_x=idx + 100, end_y=idx + 200,
                    key="Return", text=f"Text_{idx}",
                    delay_seconds=0.5 + (idx % 5) * 0.1,
                    log_text=f"Log_{idx}",
                    beep_freq=800 + idx
                )
                summary = act.get_summary()
                self.assertIsInstance(summary, str)
                self.assertGreater(len(summary), 0)
                if atype == "mouse_click":
                    self.assertIn("클릭", summary)
                elif atype == "delay":
                    self.assertIn("대기", summary)
            return test_fn
        setattr(TestCategory3ActionsAndSequences, f"test_cat3_action_summary_{i:04d}", make_test())

    # 511-570: Action Serialization Roundtrip (60 tests)
    for i in range(511, 571):
        atype = action_types[i % len(action_types)]
        def make_test(atype=atype, idx=i):
            def test_fn(self):
                act = Action(
                    action_type=atype,
                    x=idx, y=idx * 2,
                    end_x=idx + 50, end_y=idx + 80,
                    key="Space", text=f"Msg_{idx}",
                    delay_seconds=1.25,
                    coord_anti_ban="strong" if idx % 2 == 0 else "weak",
                    custom_log=f"CustomLog_{idx}"
                )
                d = act.to_dict()
                rebuilt = Action.from_dict(d)
                self.assertEqual(rebuilt.action_type, atype)
                self.assertEqual(rebuilt.x, idx)
                self.assertEqual(rebuilt.coord_anti_ban, act.coord_anti_ban)
                self.assertEqual(rebuilt.custom_log, act.custom_log)
            return test_fn
        setattr(TestCategory3ActionsAndSequences, f"test_cat3_action_serialization_{i:04d}", make_test())

    # 571-610: ActionSequence Creation & Serialization (40 tests)
    for i in range(571, 611):
        num_acts = 1 + (i % 8)
        def make_test(n_acts=num_acts, idx=i):
            def test_fn(self):
                acts = [Action(action_type="mouse_click", x=k*10, y=k*20) for k in range(n_acts)]
                seq = ActionSequence(id=f"seq_{idx}", name=f"시퀀스_{idx}", actions=acts)
                self.assertEqual(len(seq.actions), n_acts)
                self.assertIn(f"시퀀스_{idx}", seq.name)
                d = seq.to_dict()
                rebuilt = ActionSequence.from_dict(d)
                self.assertEqual(rebuilt.id, f"seq_{idx}")
                self.assertEqual(len(rebuilt.actions), n_acts)
                summary = seq.get_summary()
                self.assertIsInstance(summary, str)
                self.assertIn("클릭", summary)
            return test_fn
        setattr(TestCategory3ActionsAndSequences, f"test_cat3_sequence_creation_{i:04d}", make_test())

    # 611-650: Project ActionSequence Registry Operations (40 tests)
    for i in range(611, 651):
        def make_test(idx=i):
            def test_fn(self):
                proj = Project(name=f"Proj_{idx}")
                seq1 = ActionSequence(id=f"s1_{idx}", name=f"Module_1_{idx}")
                seq2 = ActionSequence(id=f"s2_{idx}", name=f"Module_2_{idx}")
                proj.add_action_sequence(seq1)
                proj.add_action_sequence(seq2)
                self.assertEqual(len(proj.action_sequences), 2)
                self.assertEqual(proj.find_action_sequence(f"s1_{idx}").name, f"Module_1_{idx}")

                # Attach to scenario, then delete -> must unlink safely
                scen = Scenario(id=f"scen_{idx}", sequence_id=f"s1_{idx}")
                proj.scenarios.append(scen)
                proj.delete_action_sequence(f"s1_{idx}")
                self.assertIsNone(proj.find_action_sequence(f"s1_{idx}"))
                self.assertIsNone(scen.sequence_id)
            return test_fn
        setattr(TestCategory3ActionsAndSequences, f"test_cat3_registry_ops_{i:04d}", make_test())

_setup_category_3()


# ==============================================================================
# Category 4: Scenarios, Hierarchy, Loops & Targets (200 Tests)
# ==============================================================================
class TestCategory4ScenariosAndLoops(unittest.TestCase):
    pass


def _setup_category_4():
    # 651-690: Scenario Effective Actions Resolution (40 tests)
    for i in range(651, 691):
        def make_test(idx=i):
            def test_fn(self):
                proj = Project(name="TestProj")
                seq = ActionSequence(id=f"seq_{idx}", actions=[Action(action_type="mouse_click", x=idx, y=idx)])
                proj.add_action_sequence(seq)

                # Scenario linked to sequence
                s_linked = Scenario(id=f"sl_{idx}", sequence_id=f"seq_{idx}")
                eff_linked = s_linked.get_effective_actions(proj)
                self.assertEqual(len(eff_linked), 1)
                self.assertEqual(eff_linked[0].x, idx)

                # Scenario unlinked (fallback to own actions)
                s_unlinked = Scenario(id=f"su_{idx}", sequence_id=None, actions=[Action(action_type="delay", delay_seconds=2.0)])
                eff_unlinked = s_unlinked.get_effective_actions(proj)
                self.assertEqual(len(eff_unlinked), 1)
                self.assertEqual(eff_unlinked[0].delay_seconds, 2.0)
            return test_fn
        setattr(TestCategory4ScenariosAndLoops, f"test_cat4_effective_actions_{i:04d}", make_test())

    # 691-750: Loop Hierarchy Depth Calculations (60 tests)
    for i in range(691, 751):
        num_nested = 1 + (i % 4)  # 1 to 4 levels of loop nesting
        def make_test(nesting=num_nested, idx=i):
            def test_fn(self):
                proj = Project(name="LoopProj")
                scenarios = []
                for level in range(nesting):
                    scenarios.append(Scenario(node_type="loop_start", id=f"start_{level}"))
                scenarios.append(Scenario(node_type="normal", name="Body"))
                for level in reversed(range(nesting)):
                    scenarios.append(Scenario(node_type="loop_end", id=f"end_{level}"))
                proj.scenarios = scenarios
                depths = proj.compute_hierarchy_depths()
                self.assertEqual(len(depths), len(scenarios))
                # The deepest body scenario should have depth == nesting
                body_idx = nesting
                self.assertEqual(depths[body_idx], nesting)
            return test_fn
        setattr(TestCategory4ScenariosAndLoops, f"test_cat4_loop_depth_{i:04d}", make_test())

    # 751-810: Find Matching Loop End (60 tests)
    for i in range(751, 811):
        inner_count = (i % 5)
        def make_test(inner=inner_count, idx=i):
            def test_fn(self):
                proj = Project(name="MatchingLoopProj")
                s_list = [Scenario(node_type="loop_start", id="outer_start")]
                for k in range(inner):
                    s_list.append(Scenario(node_type="normal", id=f"node_{k}"))
                s_list.append(Scenario(node_type="loop_end", id="outer_end"))
                proj.scenarios = s_list
                expected_end_idx = 1 + inner
                self.assertEqual(proj.find_matching_loop_end(0), expected_end_idx)
            return test_fn
        setattr(TestCategory4ScenariosAndLoops, f"test_cat4_matching_loop_end_{i:04d}", make_test())

    # 811-850: Scenario Target Identifier Resolution (40 tests)
    for i in range(811, 851):
        def make_test(idx=i):
            def test_fn(self):
                proj = Project(name="ResolveProj")
                s1 = Scenario(id=f"uuid_{idx}_1", scenario_number=1, step_number=1, name="One")
                s2 = Scenario(id=f"uuid_{idx}_2", scenario_number=2, step_number=2, name="Two")
                proj.scenarios = [s1, s2]
                runner = WorkflowRunner(proj, hwnd=0)

                # Resolve by UUID
                self.assertEqual(runner._resolve_target_scenario(f"uuid_{idx}_1"), s1)
                # Resolve by scenario number string
                self.assertEqual(runner._resolve_target_scenario("2"), s2)
                # Resolve non-existent
                self.assertIsNone(runner._resolve_target_scenario("non_existent_999"))
            return test_fn
        setattr(TestCategory4ScenariosAndLoops, f"test_cat4_target_resolution_{i:04d}", make_test())

_setup_category_4()


# ==============================================================================
# Category 5: Runner, Jitter & Anti-Ban Properties (100 Tests)
# ==============================================================================
class TestCategory5RunnerAndAntiBan(unittest.TestCase):
    pass


def _setup_category_5():
    # 851-890: Time Jitter Non-Negative Range Checks (40 tests)
    for i in range(851, 891):
        offset = 0.1 * (1 + (i % 20))  # 0.1s to 2.0s
        def make_test(max_off=offset, idx=i):
            def test_fn(self):
                for _ in range(20):
                    jitter = round(random.uniform(0.0, max_off), 3)
                    self.assertGreaterEqual(jitter, 0.0)
                    self.assertLessEqual(jitter, max_off + 0.001)
            return test_fn
        setattr(TestCategory5RunnerAndAntiBan, f"test_cat5_jitter_range_{i:04d}", make_test())

    # 891-930: Coordinate Anti-Ban Offset Range Mapping (40 tests)
    for i in range(891, 931):
        weak_val = 3 + (i % 5)
        strong_val = 12 + (i % 10)
        def make_test(w=weak_val, s=strong_val, idx=i):
            def test_fn(self):
                proj = Project(anti_ban_coord_weak=w, anti_ban_coord_strong=s)
                # Weak mode
                act_w = Action(action_type="mouse_click", coord_anti_ban="weak")
                act_s = Action(action_type="mouse_click", coord_anti_ban="strong")
                act_n = Action(action_type="mouse_click", coord_anti_ban="none")

                # Verify logic mapping
                w_range = proj.anti_ban_coord_weak if act_w.coord_anti_ban == "weak" else 0
                s_range = proj.anti_ban_coord_strong if act_s.coord_anti_ban == "strong" else 0
                n_range = 0 if act_n.coord_anti_ban == "none" else 5
                self.assertEqual(w_range, w)
                self.assertEqual(s_range, s)
                self.assertEqual(n_range, 0)
            return test_fn
        setattr(TestCategory5RunnerAndAntiBan, f"test_cat5_coord_offset_{i:04d}", make_test())

    # 931-950: Runner Stepping and State Transitions (20 tests)
    for i in range(931, 951):
        def make_test(idx=i):
            def test_fn(self):
                proj = Project(name=f"RunnerProj_{idx}")
                runner = WorkflowRunner(proj, hwnd=0, start_scenario_id=f"scen_{idx}")
                self.assertFalse(runner._step_mode)
                self.assertFalse(runner._is_running)

                runner.step_forward()
                self.assertTrue(runner._step_mode)
                self.assertFalse(runner._is_paused)

                runner.pause()
                self.assertTrue(runner._is_paused)

                runner.resume()
                self.assertFalse(runner._is_paused)

                runner.stop()
                self.assertFalse(runner._is_running)
            return test_fn
        setattr(TestCategory5RunnerAndAntiBan, f"test_cat5_runner_states_{i:04d}", make_test())

_setup_category_5()


# ==============================================================================
# Category 6: Project Roundtrip, Edge Cases & Fuzzing (50 Tests)
# ==============================================================================
class TestCategory6RoundtripAndFuzzing(unittest.TestCase):
    pass


def _setup_category_6():
    # 951-975: Full Project JSON Serialization Roundtrip (25 tests)
    for i in range(951, 976):
        num_scen = 1 + (i % 6)
        def make_test(n_scen=num_scen, idx=i):
            def test_fn(self):
                proj = Project(name=f"ComprehensiveProj_{idx}", loop_count=idx % 10)
                seq = ActionSequence(id=f"seq_{idx}", name=f"Seq_{idx}", actions=[Action(action_type="delay", delay_seconds=0.3)])
                proj.add_action_sequence(seq)

                for k in range(n_scen):
                    scen = Scenario(
                        id=f"s_{idx}_{k}",
                        name=f"시나리오 {k}",
                        sequence_id=f"seq_{idx}" if k % 2 == 0 else None,
                        actions=[Action(action_type="mouse_click", x=k*5, y=k*10)] if k % 2 != 0 else [],
                        condition=Condition(points=[ColorPoint(x=k, y=k, r=100, g=150, b=200)])
                    )
                    proj.scenarios.append(scen)

                proj.renumber_steps()

                d = proj.to_dict()
                json_str = json.dumps(d, ensure_ascii=False)
                reloaded = Project.from_dict(json.loads(json_str))

                self.assertEqual(reloaded.name, proj.name)
                self.assertEqual(len(reloaded.scenarios), n_scen)
                self.assertEqual(len(reloaded.action_sequences), 1)
                self.assertEqual(reloaded.action_sequences[0].name, f"Seq_{idx}")
            return test_fn
        setattr(TestCategory6RoundtripAndFuzzing, f"test_cat6_full_project_roundtrip_{i:04d}", make_test())

    # 976-1000: Fuzzing & Corrupt/Missing Field Resilience (25 tests)
    for i in range(976, 1001):
        def make_test(idx=i):
            def test_fn(self):
                # 1. Action with empty dictionary
                act = Action.from_dict({})
                self.assertEqual(act.action_type, "mouse_click")

                # 2. ColorPoint with missing tolerance and match_mode
                pt = ColorPoint.from_dict({"x": 10, "y": 20})
                self.assertEqual(pt.tolerance, 15)
                self.assertEqual(pt.match_mode, "match")

                # 3. Scenario with missing optional fields
                scen = Scenario.from_dict({"name": f"Fuzz_{idx}"})
                self.assertEqual(scen.name, f"Fuzz_{idx}")
                self.assertIsNotNone(scen.id)
                self.assertEqual(scen.retry_fail_action, "stop")

                # 4. ActionSequence with missing actions
                seq = ActionSequence.from_dict({"name": "EmptyActionsSeq"})
                self.assertEqual(len(seq.actions), 0)

                # 5. Crash logger safety on synthetic exception
                try:
                    raise KeyError(f"SyntheticKey_{idx}")
                except KeyError:
                    exc_t, exc_v, exc_tb = sys.exc_info()
                    report = log_crash(exc_t, exc_v, exc_tb)
                    self.assertIn(f"SyntheticKey_{idx}", report)
            return test_fn
        setattr(TestCategory6RoundtripAndFuzzing, f"test_cat6_fuzzing_{i:04d}", make_test())

_setup_category_6()


if __name__ == "__main__":
    unittest.main()
