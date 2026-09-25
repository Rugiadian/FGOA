"""
Unit tests for log level width equalization and [#number] column alignment.
"""
import unittest
import sys
from unittest.mock import patch, MagicMock
from PyQt5.QtWidgets import QApplication

from core.models import Project, Scenario, Condition, ColorPoint, Action
from core.runner import WorkflowRunner
from core.window_manager import WindowInfo
from ui.main_window import MainWindow
from ui.theme import get_theme_colors


class TestLogAlignment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_01_log_level_equal_widths_in_main_window(self):
        """Verify that INFO, SUCCESS, ACTION, WARN, ERROR tags are padded to equal width (7 chars)."""
        win = MainWindow()
        pal = get_theme_colors("dark")
        color = pal["text_primary"]
        prefix_color = "#8da4c4"

        levels = ["INFO", "SUCCESS", "ACTION", "WARN", "ERROR"]
        html_outputs = {}
        for lvl in levels:
            record = {
                "id": len(html_outputs),
                "level": lvl,
                "raw_msg": f"[#1] '{lvl}' 테스트 메시지",
                "expanded": False,
                "has_mismatch": False
            }
            html = win._format_log_record_html(record, pal, color, prefix_color)
            html_outputs[lvl] = html

        # Verify all level tags have 7 characters inside brackets
        # INFO -> [INFO&nbsp;&nbsp;&nbsp;]
        # SUCCESS -> [SUCCESS]
        # ACTION -> [ACTION&nbsp;]
        # WARN -> [WARN&nbsp;&nbsp;&nbsp;]
        # ERROR -> [ERROR&nbsp;&nbsp;]
        self.assertIn("[INFO&nbsp;&nbsp;&nbsp;]", html_outputs["INFO"])
        self.assertIn("[SUCCESS]", html_outputs["SUCCESS"])
        self.assertIn("[ACTION&nbsp;]", html_outputs["ACTION"])
        self.assertIn("[WARN&nbsp;&nbsp;&nbsp;]", html_outputs["WARN"])
        self.assertIn("[ERROR&nbsp;&nbsp;]", html_outputs["ERROR"])

        # Append to txt_log and verify plain text column alignment
        win.txt_log.clear()
        for lvl in ["INFO", "SUCCESS", "ACTION"]:
            win._append_log(lvl, "[#1] 정렬 테스트")

        plain_text = win.txt_log.toPlainText().strip()
        lines = [line.strip() for line in plain_text.splitlines() if line.strip()]
        self.assertEqual(len(lines), 3)

        # In plain text, non-breaking spaces appear as spaces or unicode spaces
        # All three tags should start at index 0 and end bracket at index 8
        for line in lines:
            self.assertTrue(line.startswith("["), f"Line must start with bracket: {line}")
            close_idx = line.find("]")
            self.assertEqual(close_idx, 8, f"Closing bracket should be at index 8: {line}")
            # The [#1] tag must begin at index 10 (after bracket and 1 space)
            hash_idx = line.find("[#1]")
            self.assertEqual(hash_idx, 10, f"'[#1]' should start at index 10: {line}")

        win.close()

    def test_02_runner_emits_step_number_for_actions(self):
        """Verify runner emits [#scenario.step_number] for action execution logs."""
        proj = Project()
        scen = Scenario(
            id="s1",
            scenario_number=1,
            step_number=5,
            name="액션 스텝 테스트",
            enabled=True,
            actions=[Action(action_type="delay", delay_seconds=0.01)]
        )
        proj.scenarios = [scen]

        runner = WorkflowRunner(proj, hwnd=0)
        emitted_logs = []
        runner.sig_log.connect(lambda lvl, msg: emitted_logs.append((lvl, msg)))
        runner._is_running = True

        with patch("core.input_controller.InputController.execute_action"):
            runner._execute_actions(scen)

        action_logs = [msg for lvl, msg in emitted_logs if lvl == "ACTION"]
        self.assertTrue(len(action_logs) >= 1)
        self.assertTrue(action_logs[0].startswith("[#5] ▶"), f"Action log must start with '[#5] ▶', got: {action_logs[0]}")

    def test_03_runner_condition_mismatch_retry_starts_with_step_number(self):
        """Verify runner condition mismatch retry log starts with [#step_number]."""
        proj = Project()
        scen = Scenario(
            id="s_mismatch",
            step_number=3,
            scenario_number=3,
            name="불일치 정렬 테스트",
            enabled=True,
            condition=Condition(name="더미 조건", points=[ColorPoint(x=5, y=5, r=1, g=2, b=3)]),
            on_match="execute",
            on_mismatch="retry",
            retry_max_count=1,
            retry_interval_sec=0.01,
            retry_fail_action="stop"
        )
        proj.scenarios = [scen]

        runner = WorkflowRunner(proj, hwnd=100)
        emitted_logs = []
        runner.sig_log.connect(lambda lvl, msg: emitted_logs.append((lvl, msg)))

        mock_win = WindowInfo(hwnd=100, title="Win", client_width=800, client_height=600, screen_x=0, screen_y=0)
        with patch("core.evaluator.ConditionEvaluator.evaluate", return_value=(False, [])):
            with patch("core.window_manager.WindowManager.get_window_info", return_value=mock_win):
                runner._is_running = True
                runner.run()

        retry_logs = [msg for lvl, msg in emitted_logs if "재시도 대기" in msg]
        self.assertTrue(len(retry_logs) >= 1)
        self.assertTrue(retry_logs[0].startswith("[#3] ⏳"), f"Retry log must start with '[#3] ⏳', got: {retry_logs[0]}")


if __name__ == "__main__":
    unittest.main()
