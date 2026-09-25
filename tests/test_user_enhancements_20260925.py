import unittest
from unittest.mock import MagicMock, patch
from PIL import Image

from core.models import Condition, ColorPoint, Scenario, Project, Action
from core.evaluator import ConditionEvaluator
from core.screen_capture import ScreenCapture


class TestNewEnhancements(unittest.TestCase):
    def test_format_mismatch_log(self):
        # Setup point results with a mismatch
        point_results = [
            {
                "point_id": "pt_1",
                "x": 100,
                "y": 200,
                "target_rgb": (255, 255, 255),
                "actual_rgb": (200, 250, 100),
                "tolerance": 15,
                "match_mode": "match",
                "passed": False
            },
            {
                "point_id": "pt_2",
                "x": 300,
                "y": 400,
                "target_rgb": (10, 20, 30),
                "actual_rgb": (10, 20, 30),
                "tolerance": 15,
                "match_mode": "match",
                "passed": True
            }
        ]
        log_str = ConditionEvaluator.format_mismatch_log(point_results)
        self.assertIn("#1 기준: RGB 255,255,255 / 감지: RGB 200,250,100 / 오차 55,5,155", log_str)
        self.assertIn("[불일치]", log_str)
        # Verify that even when partially mismatched, the matched point is also output
        self.assertIn("#2 기준: RGB 10,20,30 / 감지: RGB 10,20,30 / 오차 0,0,0", log_str)
        self.assertIn("[일치]", log_str)

    def test_format_mismatch_log_user_example(self):
        # Exact format test as requested by user
        point_results = [
            {
                "point_id": "pt_1",
                "x": 50,
                "y": 60,
                "target_rgb": (255, 255, 255),
                "actual_rgb": (200, 200, 200),
                "tolerance": 15,
                "match_mode": "match",
                "passed": False
            },
            {
                "point_id": "pt_2",
                "x": 70,
                "y": 80,
                "target_rgb": (100, 100, 100),
                "actual_rgb": (100, 100, 100),
                "tolerance": 15,
                "match_mode": "match",
                "passed": True
            }
        ]
        log_str = ConditionEvaluator.format_mismatch_log(point_results)
        self.assertIn("• #1 기준: RGB 255,255,255 / 감지: RGB 200,200,200 / 오차 55,55,55 [불일치]", log_str)
        self.assertIn("• #2 기준: RGB 100,100,100 / 감지: RGB 100,100,100 / 오차 0,0,0 [일치]", log_str)

    def test_screen_capture_display_priority(self):
        # Verify prefer_display argument exists and mss is tried first
        with patch.object(ScreenCapture, "get_sct") as mock_sct:
            with patch("core.screen_capture.win32gui.IsWindow", return_value=True):
                with patch("core.screen_capture.WindowManager.get_window_info") as mock_info:
                    mock_win = MagicMock()
                    mock_win.client_width = 100
                    mock_win.client_height = 100
                    mock_win.screen_x = 0
                    mock_win.screen_y = 0
                    mock_win.is_minimized = False
                    mock_info.return_value = mock_win

                    mock_grab = MagicMock()
                    mock_grab.size = (100, 100)
                    mock_grab.bgra = b"\x00" * (100 * 100 * 4)
                    mock_sct.return_value.grab.return_value = mock_grab

                    img = ScreenCapture.capture_client_area(12345, prefer_display=True)
                    self.assertIsNotNone(img)
                    self.assertEqual(img.size, (100, 100))
                    mock_sct.return_value.grab.assert_called_once()

    def test_inspector_points_table_and_action_log(self):
        from PyQt5.QtWidgets import QApplication
        import sys
        app = QApplication.instance() or QApplication(sys.argv)

        from ui.inspector_widget import InspectorWidget

        inspector = InspectorWidget()
        scen = Scenario(
            name="테스트 시나리오",
            custom_log="초기 로그",
            condition=Condition(
                points=[
                    ColorPoint(x=10, y=20, r=255, g=0, b=0),
                    ColorPoint(x=30, y=40, r=0, g=255, b=0)
                ]
            ),
            actions=[Action(action_type="delay", delay_seconds=0.1)]
        )
        inspector.set_scenario(scen)

        # 1. Check custom log input field
        self.assertEqual(inspector.txt_action_log.text(), "초기 로그")
        self.assertTrue(inspector.txt_action_log.isEnabled())

        # Typing in txt_action_log updates current_scenario.custom_log
        inspector.txt_action_log.setText("새로운 액션 로그 문장")
        self.assertEqual(inspector.current_scenario.custom_log, "새로운 액션 로그 문장")

        # Emptying txt_action_log sets custom_log to ""
        inspector.txt_action_log.setText("")
        self.assertEqual(inspector.current_scenario.custom_log, "")

        # 2. Check points table column count and x delete button
        self.assertEqual(inspector.tbl_points.columnCount(), 6)
        self.assertEqual(inspector.tbl_points.rowCount(), 2)

        # Delete column (column 5) has delete button
        btn_del_0 = inspector.tbl_points.cellWidget(0, 5)
        self.assertIsNotNone(btn_del_0)
        self.assertEqual(btn_del_0.text(), "✕")

        # Trigger single point delete via method
        pt_to_del = inspector.current_scenario.condition.points[0]
        inspector._on_delete_single_point(pt_to_del)
        self.assertEqual(len(inspector.current_scenario.condition.points), 1)
        self.assertEqual(inspector.tbl_points.rowCount(), 1)


if __name__ == "__main__":
    unittest.main()
