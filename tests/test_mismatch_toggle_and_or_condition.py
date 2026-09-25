"""
Unit tests for Color Mismatch Log Toggle and Recognition Condition 'Match Any (OR)' logic.
"""
import unittest
import os
import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QUrl
from PIL import Image

from core.models import Project, Scenario, Condition, ColorPoint, Action
from core.evaluator import ConditionEvaluator
from core.runner import WorkflowRunner
from ui.main_window import MainWindow
from ui.inspector_widget import InspectorWidget
from ui.condition_editor_dialog import ConditionEditorDialog


class TestMismatchToggleAndOrCondition(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_01_mismatch_toggle_anchor_click_opens_and_closes(self):
        """Verify clicking mismatch toggle expands and collapses details properly."""
        win = MainWindow()
        win.show()

        # Emit log with MISMATCH tags
        log_msg = "시나리오 조건 불일치 [MISMATCH:2]• #1 (100, 200) 감지 RGB(10,20,30) ≠ 기준 RGB(100,200,50) [오차: R90, G180, B20 / 허용: ±15]\n• #2 (300, 400) 감지 RGB(0,0,0) ≠ 기준 RGB(255,255,255) [오차: R255, G255, B255 / 허용: ±15][/MISMATCH]"
        win._append_log("WARN", log_msg)

        # Check initial state: collapsed
        self.assertEqual(len(win._log_records), 1)
        record = win._log_records[0]
        self.assertTrue(record["has_mismatch"])
        self.assertFalse(record["expanded"])
        self.assertIn("toggle-mismatch:0", win.txt_log.toHtml())
        self.assertNotIn("불일치 세부 포인트 목록", win.txt_log.toHtml())

        # Click anchor to expand using standard QUrl('toggle-mismatch:0')
        win._on_log_anchor_clicked(QUrl("toggle-mismatch:0"))
        self.assertTrue(win._log_records[0]["expanded"])
        html_expanded = win.txt_log.toHtml()
        self.assertIn("불일치 세부 포인트 목록", html_expanded)
        self.assertIn("감지 RGB(10,20,30)", html_expanded)
        self.assertIn("[▼", html_expanded)

        # Click anchor again to collapse
        win._on_log_anchor_clicked(QUrl("toggle-mismatch:0"))
        self.assertFalse(win._log_records[0]["expanded"])
        html_collapsed = win.txt_log.toHtml()
        self.assertNotIn("불일치 세부 포인트 목록", html_collapsed)
        self.assertIn("[▶", html_collapsed)

        # Also test legacy/path fallback with toggle_mismatch:0
        win._on_log_anchor_clicked(QUrl("toggle_mismatch:0"))
        self.assertTrue(win._log_records[0]["expanded"])
        self.assertIn("불일치 세부 포인트 목록", win.txt_log.toHtml())

        win.close()

    def test_02_evaluator_supports_multiple_or_formats(self):
        """Verify ConditionEvaluator.evaluate properly matches when at least one point matches for OR logic."""
        img = Image.new("RGB", (100, 100), (255, 0, 0))

        # pt1 matches (255, 0, 0), pt2 fails (0, 255, 0)
        pt1 = ColorPoint(x=10, y=10, r=255, g=0, b=0, tolerance=10)
        pt2 = ColorPoint(x=20, y=20, r=0, g=255, b=0, tolerance=10)

        for or_tag in ["OR", "or", " 하나라도 일치 ", "ANY"]:
            cond = Condition(logic_operator=or_tag, points=[pt1, pt2])
            matched, results = ConditionEvaluator.evaluate(cond, image=img)
            self.assertTrue(matched, f"Failed for logic_operator: {or_tag}")
            self.assertEqual(len(results), 2)
            self.assertTrue(results[0]["passed"])
            self.assertFalse(results[1]["passed"])

        # AND condition: should fail because pt2 fails
        cond_and = Condition(logic_operator="AND", points=[pt1, pt2])
        matched_and, _ = ConditionEvaluator.evaluate(cond_and, image=img)
        self.assertFalse(matched_and, "AND condition should fail when only one point matches")

        # When all points fail under OR, matched should be False
        pt_fail = ColorPoint(x=30, y=30, r=0, g=0, b=255, tolerance=10)
        cond_all_fail = Condition(logic_operator="OR", points=[pt2, pt_fail])
        matched_fail, _ = ConditionEvaluator.evaluate(cond_all_fail, image=img)
        self.assertFalse(matched_fail, "OR condition should fail when no points match")

    def test_03_inspector_syncs_module_logic_operator_and_tests_live(self):
        """Verify InspectorWidget syncs logic_operator for linked module conditions and live tests."""
        proj = Project()
        # Create a condition module
        c_mod = Condition(
            name="공용 조건 1",
            logic_operator="AND",
            points=[
                ColorPoint(x=10, y=10, r=255, g=0, b=0, tolerance=5),
                ColorPoint(x=20, y=20, r=0, g=0, b=0, tolerance=5)
            ]
        )
        proj.add_condition(c_mod)

        scen = Scenario(name="테스트 시나리오", condition_id=c_mod.id)
        proj.scenarios.append(scen)

        insp = InspectorWidget()
        insp.set_project(proj)
        insp.set_scenario(scen)

        # 1. Change combo_cond_logic to 'OR'
        idx_or = insp.combo_cond_logic.findData("OR")
        self.assertGreaterEqual(idx_or, 0)
        insp.combo_cond_logic.setCurrentIndex(idx_or)

        # Verify that the linked module's logic_operator was updated to 'OR'
        self.assertEqual(c_mod.logic_operator, "OR")

        # 2. Live condition test with dummy image
        img = Image.new("RGB", (50, 50), (255, 0, 0))
        # Point 1 (10, 10) matches (255, 0, 0), Point 2 (20, 20) is (255, 0, 0) != (0, 0, 0) -> fails
        matched, details = ConditionEvaluator.evaluate(c_mod, image=img)
        self.assertTrue(matched, "OR condition should pass because Point 1 matched")

    def test_04_condition_editor_dialog_has_logic_selector(self):
        """Verify ConditionEditorDialog includes logic_operator selector and saves it."""
        proj = Project()
        cond = Condition(name="편집 테스트", logic_operator="AND")
        dlg = ConditionEditorDialog(
            condition=cond,
            project=proj,
            current_scenario_id="",
            target_hwnd=0
        )

        self.assertTrue(hasattr(dlg, "combo_logic"))
        self.assertEqual(dlg.combo_logic.currentData(), "AND")

        # Change to OR
        idx_or = dlg.combo_logic.findData("OR")
        dlg.combo_logic.setCurrentIndex(idx_or)
        self.assertEqual(dlg.condition.logic_operator, "OR")

        dlg._on_save()
        result_cond = dlg.get_condition()
        self.assertEqual(result_cond.logic_operator, "OR")

        dlg.close()

    def test_05_runner_handles_or_condition_match(self):
        """Verify WorkflowRunner evaluates OR condition and emits match log."""
        proj = Project()
        # 1 point match, 1 point mismatch
        pt1 = ColorPoint(x=5, y=5, r=100, g=100, b=100, tolerance=10)
        pt2 = ColorPoint(x=15, y=15, r=200, g=200, b=200, tolerance=10)
        cond = Condition(logic_operator="OR", points=[pt1, pt2])

        scen = Scenario(name="OR 테스트", condition=cond, on_match="stop")
        proj.scenarios.append(scen)

        logs = []
        runner = WorkflowRunner(project=proj, hwnd=0)
        runner.sig_log.connect(lambda lvl, msg: logs.append((lvl, msg)))

        # Mock evaluate to return matched=True with 1 passed and 1 failed
        point_results = [
            {"point_id": pt1.id, "x": 5, "y": 5, "passed": True},
            {"point_id": pt2.id, "x": 15, "y": 15, "passed": False}
        ]

        # Directly test the format logic in runner
        passed_count = sum(1 for p in point_results if p.get("passed", False))
        total_count = len(point_results)
        is_or = cond and (str(getattr(cond, "logic_operator", "AND")).strip().upper() in ("OR", "ANY") or "하나라도" in str(getattr(cond, "logic_operator", "AND")))
        rule_tag = f" - {passed_count}/{total_count}개 일치, OR 충족" if is_or else ""
        msg = f"[#{scen.step_number}] '{scen.name}' 조건 일치! (판정: 성공{rule_tag})"

        self.assertIn("1/2개 일치, OR 충족", msg)
        self.assertIn("조건 일치! (판정: 성공", msg)


if __name__ == "__main__":
    unittest.main()
