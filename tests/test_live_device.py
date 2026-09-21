"""
Live Device Automated Integration Test for FGOA.
Tests all color detection conditions, window tracking, screen capture,
evaluator, and UI components against live 'Android Device' window.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
import unittest
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from core.models import Condition, ColorPoint, Project, Scenario, Action
from core.window_manager import WindowManager, WindowInfo
from core.screen_capture import ScreenCapture
from core.evaluator import ConditionEvaluator
from ui.inspector_widget import InspectorWidget
from ui.condition_editor_dialog import ConditionEditorDialog
from ui.main_window import MainWindow


class TestLiveAndroidDevice(unittest.TestCase):
    app = None
    target_win = None

    @classmethod
    def setUpClass(cls):
        # Create Qt app if not already running
        if QApplication.instance() is None:
            cls.app = QApplication(sys.argv)
        else:
            cls.app = QApplication.instance()

        windows = WindowManager.get_all_visible_windows()

        # Prioritize exact 'Android Device' window
        for w in windows:
            if "android device" in w.title.lower():
                cls.target_win = w
                break

        if not cls.target_win:
            for w in windows:
                if "android" in w.title.lower() and w.client_width >= 400:
                    cls.target_win = w
                    break

        if not cls.target_win:
            raise unittest.SkipTest("No live Android Device window found on desktop.")
        print(f"\n[LIVE TEST] Using Target Window: '{cls.target_win.title}' (HWND: 0x{cls.target_win.hwnd:X}, {cls.target_win.client_width}x{cls.target_win.client_height})")

    def test_01_target_window_properties(self):
        """Verify target window info can be queried dynamically."""
        win_info = WindowManager.get_window_info(self.target_win.hwnd)
        self.assertIsNotNone(win_info)
        self.assertGreater(win_info.client_width, 0)
        self.assertGreater(win_info.client_height, 0)
        print(f"  [PASS] Target window active: {win_info.client_width}x{win_info.client_height}")

    def test_02_pixel_reading(self):
        """Verify reading pixels from live target window."""
        color = ScreenCapture.get_client_pixel_color(self.target_win.hwnd, 100, 100)
        self.assertIsNotNone(color)
        self.assertEqual(len(color), 3)
        print(f"  [PASS] Read pixel at (100, 100): RGB{color}")

    def test_03_screen_capture_client_area(self):
        """Verify full client area snapshotting from target window."""
        img = ScreenCapture.capture_client_area(self.target_win.hwnd)
        self.assertIsNotNone(img)
        self.assertEqual(img.size, (self.target_win.client_width, self.target_win.client_height))
        print(f"  [PASS] Captured client area image: {img.size}")

    def test_04_condition_evaluation_match(self):
        """Sample a real pixel and evaluate condition - must MATCH."""
        px = min(200, self.target_win.client_width // 2)
        py = min(200, self.target_win.client_height // 2)
        real_color = ScreenCapture.get_client_pixel_color(self.target_win.hwnd, px, py)
        self.assertIsNotNone(real_color)

        cond = Condition(
            name="실시간 일치 테스트",
            logic_operator="AND",
            points=[
                ColorPoint(x=px, y=py, r=real_color[0], g=real_color[1], b=real_color[2], tolerance=15)
            ]
        )

        matched, details = ConditionEvaluator.evaluate(cond, self.target_win.hwnd)
        self.assertTrue(matched)
        self.assertEqual(len(details), 1)
        self.assertTrue(details[0]["passed"])
        print(f"  [PASS] Live color match test succeeded at ({px}, {py}): Target RGB{real_color} vs Actual RGB{details[0]['actual_rgb']}")

    def test_05_condition_evaluation_mismatch(self):
        """Inverted color - must NOT match."""
        px = min(200, self.target_win.client_width // 2)
        py = min(200, self.target_win.client_height // 2)
        real_color = ScreenCapture.get_client_pixel_color(self.target_win.hwnd, px, py)
        self.assertIsNotNone(real_color)

        # Opposite color
        inv_r = (real_color[0] + 128) % 256
        cond = Condition(
            name="실시간 불일치 테스트",
            logic_operator="AND",
            points=[
                ColorPoint(x=px, y=py, r=inv_r, g=real_color[1], b=real_color[2], tolerance=10)
            ]
        )

        matched, details = ConditionEvaluator.evaluate(cond, self.target_win.hwnd)
        self.assertFalse(matched)
        self.assertFalse(details[0]["passed"])
        print(f"  [PASS] Live color mismatch detection succeeded: Target R={inv_r} vs Actual RGB{details[0]['actual_rgb']}")

    def test_06_condition_editor_dialog_no_crash(self):
        """Verify ConditionEditorDialog can be opened and capture without crashing."""
        proj = Project(scenarios=[Scenario(id="scen_live", name="라이브 시나리오")])
        cond = Condition(name="테스트 조건", points=[ColorPoint(x=200, y=200, r=255, g=255, b=255)])
        
        dlg = ConditionEditorDialog(
            condition=cond,
            project=proj,
            current_scenario_id="scen_live",
            target_hwnd=self.target_win.hwnd
        )
        self.assertIsNotNone(dlg)
        dlg._on_capture_target_window(silent=True)
        self.assertIsNotNone(dlg.condition.reference_image_path)
        self.assertTrue(os.path.exists(dlg.condition.reference_image_path))
        print(f"  [PASS] ConditionEditorDialog auto-capture verified without crash: {dlg.condition.reference_image_path}")

    def test_07_inspector_widget_live_test_button(self):
        """Verify clicking Inspector's [⚡ 판정 테스트] works seamlessly."""
        widget = InspectorWidget()
        proj = Project(scenarios=[
            Scenario(
                id="scen_inspect",
                step_number=1,
                scenario_number=1,
                name="인스펙터 검증",
                condition=Condition(
                    name="라이브 조건",
                    points=[ColorPoint(x=100, y=100, r=0, g=0, b=0, tolerance=255)]
                )
            )
        ])
        widget.show()
        self.app.processEvents()
        widget.set_scenario(proj.scenarios[0], self.target_win.hwnd, proj)
        widget._on_test_condition_now()
        self.assertFalse(widget.lbl_cond_test_result.isHidden())
        self.assertIn("일치", widget.lbl_cond_test_result.text())
        print(f"  [PASS] Inspector test condition button executed successfully: {widget.lbl_cond_test_result.text()}")

    def test_08_main_window_target_binding(self):
        """Verify MainWindow correctly attaches to Android Device window."""
        win = MainWindow()
        win.target_hwnd = self.target_win.hwnd
        win.project.target_window_title = self.target_win.title
        win._update_target_label(self.target_win)
        self.assertIn(self.target_win.title, win.lbl_target_info.text())
        print(f"  [PASS] MainWindow bound target window: {win.lbl_target_info.text()}")


def main():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestLiveAndroidDevice)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
