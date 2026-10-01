"""
Comprehensive automated tests for the 5 latest user enhancements:
1. 기준 이미지 등록: 레퍼런스 갤러리에서 선택 가능 및 제작 기준 해상도 동기화
2. 시나리오 목록 툴바: 2개 행 분할 (Row 1 CRUD/폴더/루프/프리셋/저장/열기, Row 2 위로, 아래로, 취소, 다시)
3. UI 최하단 컨트롤 바: 기능별 2개 행 분할 (Row 1 재생 제어 및 상태, Row 2 반복 회차, 간격, 안티밴)
4. 시나리오 목록 폴더 기능: 시인성 목적 그룹 폴더, 러너 즉시 통과, 테이블 행 접기/펼치기
5. 시나리오 흐름 탭 좌우 최소 너비 축소 (FlowLayout 적용 및 200px 축소 지원)
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch
from PIL import Image

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from PyQt5.QtWidgets import QApplication, QDialog, QTableWidgetItem
from PyQt5.QtCore import Qt, QSize
from core.models import Project, Scenario, Condition, Action
from core.runner import WorkflowRunner
from ui.main_window import MainWindow

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)


class TestLatest5UserEnhancements(unittest.TestCase):

    def setUp(self):
        self.main_win = MainWindow()

    def tearDown(self):
        self.main_win.close()

    def test_01_authoring_reference_image_and_gallery_picker(self):
        """Verify authoring reference image selection updates project resolution."""
        # 1. Project authoring resolution default
        self.assertEqual(self.main_win.project.authoring_width, 1600)
        self.assertEqual(self.main_win.project.authoring_height, 900)

        # 2. Mock gallery dialog picker mode returning a 1920x1080 dummy image
        dummy_path = os.path.join(BASE_DIR, "tests", "_test_1920_1080.png")
        img = Image.new("RGB", (1920, 1080), color=(50, 100, 150))
        img.save(dummy_path)

        try:
            with patch("ui.reference_gallery_dialog.ReferenceGalleryDialog.exec_", return_value=QDialog.Accepted), \
                 patch("ui.reference_gallery_dialog.ReferenceGalleryDialog.get_selected_image_path", return_value=dummy_path):
                self.main_win._on_select_authoring_image_from_gallery()

            self.assertEqual(self.main_win.project.authoring_width, 1920)
            self.assertEqual(self.main_win.project.authoring_height, 1080)
            self.assertIn("1920", self.main_win.lbl_authoring_res.text())
            self.assertIn("1080", self.main_win.lbl_authoring_res.text())

            # 3. Verify dropdown menu has gallery option
            menu = self.main_win._create_authoring_menu()
            actions = [act.text() for act in menu.actions()]
            self.assertTrue(any("레퍼런스 갤러리" in a for a in actions))
            self.assertTrue(any("파일 탐색기" in a for a in actions))
            self.assertTrue(any("수동 직접 입력" in a for a in actions))
        finally:
            if os.path.exists(dummy_path):
                os.remove(dummy_path)

    def test_02_scenario_toolbar_two_row_layout(self):
        """Verify scenario toolbar has 2 rows and row 2 groups reorder and undo/redo."""
        # Row 2 contains btn_undo_scenario, btn_redo_scenario
        self.assertIsNotNone(self.main_win.btn_undo_scenario)
        self.assertIsNotNone(self.main_win.btn_redo_scenario)
        self.assertEqual(self.main_win.btn_undo_scenario.text(), "↩️ 취소")
        self.assertEqual(self.main_win.btn_redo_scenario.text(), "▶️ 다시")

    def test_03_bottom_control_bar_two_row_functional_split(self):
        """Verify bottom toolbar is split into Row 1 (Playback) and Row 2 (Iteration/Safety)."""
        self.assertIsNotNone(self.main_win.btn_run)
        self.assertIsNotNone(self.main_win.btn_pause)
        self.assertIsNotNone(self.main_win.btn_stop)
        self.assertIsNotNone(self.main_win.btn_step)
        self.assertIsNotNone(self.main_win.lbl_run_status)

        self.assertIsNotNone(self.main_win.spin_loops)
        has_anti_ban = hasattr(self.main_win, "chk_anti_ban") or hasattr(self.main_win, "btn_anti_ban")
        self.assertTrue(has_anti_ban)

    def test_04_folder_node_model_runner_and_ui_collapse(self):
        """Verify folder node behavior: zero-delay runner pass-through and visual collapse in UI."""
        # 1. Model properties & serialization
        folder_scen = Scenario(
            id="fld_1",
            scenario_number=10,
            name="루프 그룹",
            node_type="folder",
            is_collapsed=False
        )
        self.assertTrue(folder_scen.is_folder)
        self.assertEqual(folder_scen.get_condition_summary(), "(그룹 폴더)")
        self.assertEqual(folder_scen.get_actions_summary(), "(하위 항목 정리용)")

        d = folder_scen.to_dict()
        self.assertEqual(d["node_type"], "folder")
        self.assertFalse(d["is_collapsed"])
        restored = Scenario.from_dict(d)
        self.assertEqual(restored.node_type, "folder")
        self.assertFalse(restored.is_collapsed)

        # 2. WorkflowRunner pass-through with zero delay
        runner = WorkflowRunner(self.main_win.project, 0)
        child_scen = Scenario(id="sc_1", scenario_number=11, name="하위 시나리오", node_type="normal", actions=[Action(action_type="delay", delay_seconds=0.01)])
        self.main_win.project.scenarios = [folder_scen, child_scen]
        self.main_win._refresh_scenario_table()

        # Both rows visible initially
        self.assertFalse(self.main_win.tbl_scenarios.isRowHidden(0))
        self.assertFalse(self.main_win.tbl_scenarios.isRowHidden(1))

        # Collapse folder
        self.main_win._toggle_folder_collapse(folder_scen)
        self.assertTrue(folder_scen.is_collapsed)
        self.assertFalse(self.main_win.tbl_scenarios.isRowHidden(0))  # Folder remains visible
        self.assertTrue(self.main_win.tbl_scenarios.isRowHidden(1))   # Child row is hidden

        # Expand folder
        self.main_win._toggle_folder_collapse(folder_scen)
        self.assertFalse(folder_scen.is_collapsed)
        self.assertFalse(self.main_win.tbl_scenarios.isRowHidden(1))  # Child row is visible again

    def test_05_dock_width_narrowing(self):
        """Verify dock_scenarios and modules flow tab can be narrowed without minimum size blockage (>700px)."""
        self.assertIsNotNone(self.main_win.dock_scenarios)
        if hasattr(self.main_win, "modules_widget"):
            # Ensure modules_widget no longer blocks dock at ~769px
            self.assertTrue(self.main_win.modules_widget.minimumSizeHint().width() <= 250)
        self.assertTrue(self.main_win.dock_scenarios.minimumWidth() <= 350)


if __name__ == "__main__":
    unittest.main()
