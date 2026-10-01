"""
Tests for new user requested enhancements:
1. Reference image capture timestamp naming format (capture_%Y%m%d_%H%M%S.png)
2. CoordinatePickerDialog initial image from condition and last used image memory
3. Action & Scenario custom log output options
4. Scenario table duplicate condition badge removal
"""
import os
import re
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from PIL import Image

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from PyQt5.QtWidgets import QApplication
from core.models import Project, Scenario, Condition, ColorPoint, Action
from core.runner import WorkflowRunner
from ui.coordinate_picker_dialog import CoordinatePickerDialog
from ui.reference_gallery_dialog import ReferenceGalleryDialog
from ui.main_window import MainWindow

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)


class TestNewEnhancements(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.dummy_img_path = os.path.join(self.tmp_dir, "test_ref.png")
        img = Image.new("RGB", (200, 100), color=(128, 64, 32))
        img.save(self.dummy_img_path)

        self.second_img_path = os.path.join(self.tmp_dir, "second_ref.png")
        img2 = Image.new("RGB", (300, 150), color=(10, 20, 30))
        img2.save(self.second_img_path)

    def test_01_capture_timestamp_naming_format(self):
        """Verify captured image filenames use timestamp format: capture_YYYYMMDD_HHMMSS.png"""
        pattern = re.compile(r"^capture_\d{8}_\d{6}(\_\d+)?\.png$")

        with patch("ui.reference_gallery_dialog.ScreenCapture.capture_client_area", return_value=Image.new("RGB", (50, 50))), \
             patch("ui.reference_gallery_dialog.QMessageBox.information"), \
             patch("ui.reference_gallery_dialog.REFS_DIR", self.tmp_dir):
            dlg = ReferenceGalleryDialog(project=Project(), target_hwnd=12345)
            dlg._on_capture_current_window()
            dlg.close()

            saved_files = [f for f in os.listdir(self.tmp_dir) if f.startswith("capture_")]
            self.assertTrue(len(saved_files) >= 1)
            for f in saved_files:
                self.assertTrue(pattern.match(f), f"Filename {f} does not match timestamp pattern")

    def test_02_coordinate_picker_initial_image_and_memory(self):
        """Verify CoordinatePickerDialog decouples condition image by default and allows explicit import via button."""
        # Clear any cached image path
        CoordinatePickerDialog.set_last_used_image_path(None)

        # 1. Scenario with condition image
        cond = Condition(reference_image_path=self.dummy_img_path)
        scenario = Scenario(id="sc1", scenario_number=1, name="테스트", condition=cond)

        # Launch dialog with scenario: condition image is decoupled by default (dummy canvas initialized)
        dlg = CoordinatePickerDialog(scenario=scenario, target_hwnd=0)
        self.assertIsNone(dlg.current_image_path)
        self.assertEqual(dlg.canvas.pixmap.width(), 1600)

        # User clicks "연결된 인식조건 레퍼런스 이미지 가져오기"
        dlg._on_import_linked_condition_image()
        self.assertEqual(dlg.current_image_path, self.dummy_img_path)
        self.assertIsNotNone(dlg.canvas.pixmap)
        self.assertEqual(dlg.canvas.pixmap.width(), 200)
        self.assertEqual(dlg.canvas.pixmap.height(), 100)
        dlg.close()

        # 2. Memory persistence: update scenario last_action_image_path
        scenario.last_action_image_path = self.second_img_path
        dlg2 = CoordinatePickerDialog(scenario=scenario, target_hwnd=0)
        self.assertEqual(dlg2.current_image_path, self.second_img_path)
        self.assertIsNotNone(dlg2.canvas.pixmap)
        self.assertEqual(dlg2.canvas.pixmap.width(), 300)
        self.assertEqual(dlg2.canvas.pixmap.height(), 150)
        dlg2.close()

        # 3. Global class-level memory
        CoordinatePickerDialog.set_last_used_image_path(self.second_img_path)
        self.assertEqual(CoordinatePickerDialog.get_last_used_image_path(), self.second_img_path)

    def test_03_action_and_scenario_custom_log_execution(self):
        """Verify custom_log on Scenario and Action correctly emit log messages in WorkflowRunner."""
        proj = Project(name="Log Test", loop_count=1)
        scenario = Scenario(
            id="s_log",
            scenario_number=1,
            name="로그 테스트 시나리오",
            custom_log="시나리오 시작 알림 커스텀 로그",
            actions=[
                Action(action_type="delay", delay_seconds=0.01, custom_log="대기 직전 커스텀 액션 로그"),
                Action(action_type="log_message", log_text="전용 로그 액션 메시지")
            ]
        )
        proj.scenarios = [scenario]

        runner = WorkflowRunner(proj, hwnd=0)
        logs = []
        runner.sig_log.connect(lambda level, msg: logs.append(msg))
        runner._is_running = True

        # Directly run scenario actions
        runner._execute_actions(scenario)

        # Check that scenario custom log was emitted
        scenario_log_found = any("시나리오 시작 알림 커스텀 로그" in m for m in logs)
        self.assertTrue(scenario_log_found, f"Scenario custom log not found in logs: {logs}")

        # Check that action custom log was emitted
        act_custom_log_found = any("대기 직전 커스텀 액션 로그" in m for m in logs)
        self.assertTrue(act_custom_log_found, f"Action custom log not found in logs: {logs}")

        # Check that dedicated log_message action was emitted
        log_act_found = any("전용 로그 액션 메시지" in m for m in logs)
        self.assertTrue(log_act_found, f"Log message action not found in logs: {logs}")

    def test_04_scenario_table_no_duplicate_condition_badge(self):
        """Verify scenario table row does not contain duplicate condition warning badge."""
        main_win = MainWindow()
        # Add two scenarios with identical condition points
        p1 = ColorPoint(x=10, y=10, r=255, g=0, b=0)
        sc1 = Scenario(id="sc1", scenario_number=1, name="시나리오 1", condition=Condition(points=[p1]))
        sc2 = Scenario(id="sc2", scenario_number=2, name="시나리오 2", condition=Condition(points=[p1]))
        main_win.project.scenarios = [sc1, sc2]

        main_win._refresh_scenario_table()

        # Check Column 4 (Condition column) of table widget
        for row in range(main_win.tbl_scenarios.rowCount()):
            cell_widget = main_win.tbl_scenarios.cellWidget(row, 4)
            cell_item = main_win.tbl_scenarios.item(row, 4)
            text = cell_item.text() if cell_item else ""
            if cell_widget:
                for child in cell_widget.findChildren(object):
                    if hasattr(child, "text"):
                        self.assertNotIn("중복 조건", child.text())
            self.assertNotIn("중복 조건", text)

        main_win.close()

    def test_05_authoring_resolution_display_and_reference_image(self):
        """Verify authoring resolution display, reference image registration, and serialization."""
        main_win = MainWindow()
        self.assertIn("1600 × 900", main_win.lbl_authoring_res.text())

        # Test registration of reference image and resolution change
        main_win.project.authoring_width = 1920
        main_win.project.authoring_height = 1080
        main_win.project.reference_image_path = self.dummy_img_path
        main_win._update_authoring_resolution_display()

        self.assertIn("1920 × 1080", main_win.lbl_authoring_res.text())
        self.assertIn("test_ref.png", main_win.lbl_authoring_res.text())

        # Test project serialization & deserialization
        p_dict = main_win.project.to_dict()
        self.assertEqual(p_dict.get("authoring_width"), 1920)
        self.assertEqual(p_dict.get("authoring_height"), 1080)
        self.assertIsNotNone(p_dict.get("reference_image_path"))

        restored = Project.from_dict(p_dict)
        self.assertEqual(restored.authoring_width, 1920)
        self.assertEqual(restored.authoring_height, 1080)
        self.assertIn("test_ref.png", restored.reference_image_path)
        main_win.close()

    def test_06_top_toolbar_two_row_wrapping(self):
        """Verify top toolbar is wrapped into a clean multi-line (2-row) layout."""
        main_win = MainWindow()
        card_frames = [w for w in main_win.top_toolbar.findChildren(object) if getattr(w, "objectName", lambda: "")() == "card_frame"]
        self.assertTrue(len(card_frames) >= 1)
        target_frame = card_frames[0]
        layout = target_frame.layout()
        # Must be a QVBoxLayout with multiple child row layouts
        from PyQt5.QtWidgets import QVBoxLayout
        self.assertIsInstance(layout, QVBoxLayout)
        self.assertGreaterEqual(layout.count(), 2)

        # Check presence of authoring resolution widgets in toolbar
        self.assertTrue(hasattr(main_win, "lbl_authoring_res"))
        self.assertTrue(hasattr(main_win, "btn_register_ref_img"))
        self.assertEqual(main_win.btn_register_ref_img.parent(), target_frame)
        main_win.close()

    def test_07_inspector_hidden_at_top_left(self):
        """Verify inspector widget does not float as an unmanaged child at (0, 0)."""
        main_win = MainWindow()
        if hasattr(main_win, "dock_actions"):
            # FGOA dual-dock architecture: parent container must be hidden
            self.assertTrue(main_win.inspector.isHidden())
        else:
            # Single dock architecture: inspector must be properly managed inside dock
            self.assertEqual(main_win.dock_inspector.widget(), main_win.inspector)
        main_win.close()


if __name__ == "__main__":
    unittest.main()
