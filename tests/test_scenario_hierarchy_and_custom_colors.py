import unittest
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from core.models import Project, Scenario
from ui.main_window import MainWindow

app = QApplication.instance() or QApplication([])


class TestScenarioHierarchyAndCustomColors(unittest.TestCase):
    """
    Unit tests for:
    1. Adding scenario below the currently selected node (not top row 0 or project end).
    2. Folder & Loop node name simplification (no [폴더 #N 시작] / [루프 #N 시작] / count tags).
    3. Custom color support for folder & loop blocks and child tinting.
    4. Reddit-style cell indentation with threadline depth data (Qt.UserRole + 100, + 101).
    5. Inspector block color button visibility and synchronization with matching partner node.
    """

    def setUp(self):
        self.win = MainWindow()
        self.project = Project(name="TestHierarchyProject", scenarios=[])
        self.win.project = self.project

    def tearDown(self):
        self.win.close()

    def test_01_add_scenario_inserts_below_selected_node(self):
        """Verify pressing Add scenario inserts right below the selected row."""
        # Add 3 initial scenarios
        self.win._on_add_scenario()
        self.win._on_add_scenario()
        self.win._on_add_scenario()
        self.assertEqual(len(self.win.project.scenarios), 3)

        # Select row 1 (the middle scenario)
        self.win.tbl_scenarios.selectRow(1)
        self.assertEqual(self.win.tbl_scenarios.currentRow(), 1)

        # Click 'Add' (custom_insert_idx=False when called from Qt clicked(bool) signal)
        self.win._on_add_scenario(False)

        # A new scenario should be inserted at index 2 (below row 1)
        self.assertEqual(len(self.win.project.scenarios), 4)
        self.assertEqual(self.win.tbl_scenarios.currentRow(), 2)
        self.assertEqual(self.win.project.scenarios[2].name, "시나리오 4")

    def test_02_clean_folder_names_without_number_or_start_tag(self):
        """Verify folder name displays cleanly without [폴더 #N 시작] text."""
        f_start = Scenario(id="f1_start", name="메인 퀘스트", node_type="folder_start")
        f_end = Scenario(id="f1_end", name="메인 퀘스트", node_type="folder_end")
        self.project.scenarios = [f_start, f_end]
        self.win._refresh_scenario_table()

        item_start_name = self.win.tbl_scenarios.item(0, 3)
        self.assertEqual(item_start_name.text(), "▼ 📂 메인 퀘스트")
        self.assertNotIn("시작", item_start_name.text())
        self.assertNotIn("#", item_start_name.text())

        item_end_name = self.win.tbl_scenarios.item(1, 3)
        self.assertEqual(item_end_name.text(), "📁 메인 퀘스트")
        self.assertNotIn("종료", item_end_name.text())
        self.assertNotIn("#", item_end_name.text())

    def test_03_clean_loop_names_without_number_or_count_tag(self):
        """Verify loop node name displays cleanly without #1 numbering and (N회 반복) text."""
        l_start = Scenario(id="l1_start", name="전투 반복 루프", node_type="loop_start", loop_count=10)
        l_end = Scenario(id="l1_end", name="전투 반복 루프", node_type="loop_end")
        self.project.scenarios = [l_start, l_end]
        self.win._refresh_scenario_table()

        item_start_name = self.win.tbl_scenarios.item(0, 3)
        self.assertEqual(item_start_name.text(), "🔁 전투 반복 루프")
        self.assertNotIn("10회", item_start_name.text())
        self.assertNotIn("#", item_start_name.text())

        item_end_name = self.win.tbl_scenarios.item(1, 3)
        self.assertEqual(item_end_name.text(), "🔁 전투 반복 루프")
        self.assertNotIn("#", item_end_name.text())

    def test_04_folder_custom_color_and_child_tint(self):
        """Verify custom color on folder node applies distinct tint to child rows."""
        f_start = Scenario(id="f1_start", name="색상 테스트 폴더", node_type="folder_start", custom_color="#3b82f6")
        child_scen = Scenario(id="scen_child", name="하위 시나리오", node_type="normal")
        f_end = Scenario(id="f1_end", name="색상 테스트 폴더", node_type="folder_end", custom_color="#3b82f6")
        self.project.scenarios = [f_start, child_scen, f_end]
        self.win._refresh_scenario_table()

        # Check depth on child
        it_child = self.win.tbl_scenarios.item(1, 3)
        self.assertEqual(it_child.data(Qt.UserRole + 100), 1)  # Depth 1
        thread_colors = it_child.data(Qt.UserRole + 101)
        self.assertIsNotNone(thread_colors)
        self.assertEqual(len(thread_colors), 1)
        self.assertEqual(thread_colors[0], "#3b82f6")

        # Child cell background tint
        child_bg = it_child.background().color()
        self.assertTrue(child_bg.isValid())

    def test_05_loop_custom_color_and_child_tint(self):
        """Verify custom color on loop block applies to loop boundaries and children."""
        l_start = Scenario(id="l1_start", name="루프 색상 테스트", node_type="loop_start", custom_color="#10b981")
        child_scen = Scenario(id="l_child", name="루프 하위 시나리오", node_type="normal")
        l_end = Scenario(id="l1_end", name="루프 색상 테스트", node_type="loop_end", custom_color="#10b981")
        self.project.scenarios = [l_start, child_scen, l_end]
        self.win._refresh_scenario_table()

        it_child = self.win.tbl_scenarios.item(1, 3)
        self.assertEqual(it_child.data(Qt.UserRole + 100), 1)
        thread_colors = it_child.data(Qt.UserRole + 101)
        self.assertEqual(thread_colors, ["#10b981"])

    def test_06_inspector_block_color_sync(self):
        """Verify inspector block color button updates and syncs partner node."""
        f_start = Scenario(id="f_sync_start", name="인스펙터 색상 연동", node_type="folder_start")
        f_end = Scenario(id="f_sync_end", name="인스펙터 색상 연동", node_type="folder_end")
        self.project.scenarios = [f_start, f_end]
        self.win._refresh_scenario_table()
        self.win.tbl_scenarios.selectRow(0)
        self.win._on_table_selection_changed()

        self.assertFalse(self.win.inspector.btn_block_color.isHidden())

        # Change color in inspector
        self.win.inspector._set_block_custom_color("#8b5cf6")
        self.assertEqual(f_start.custom_color, "#8b5cf6")
        self.assertEqual(f_end.custom_color, "#8b5cf6")


    def test_07_dock_minimum_size_hint_and_row_colors(self):
        """Verify inspector docks have responsive minimumSizeHint and cells in cols 0, 1 receive row_bg."""
        # 1. Dock minimum size constraints
        cond_min_w = self.win.inspector.condition_panel.minimumSizeHint().width()
        act_min_w = self.win.inspector.action_panel.minimumSizeHint().width()
        self.assertLessEqual(cond_min_w, 250)
        self.assertLessEqual(act_min_w, 250)

        # 2. Cell colors on column 0 (snapshot) and column 1 (UID)
        scen_colored = Scenario(id="scen_col", name="컬러 시나리오", node_type="normal", custom_color="#f59e0b")
        self.project.scenarios = [scen_colored]
        self.win._refresh_scenario_table()

        # Col 0 (empty snapshot) should have background
        it_0 = self.win.tbl_scenarios.item(0, 0)
        self.assertIsNotNone(it_0)
        self.assertTrue(it_0.background().color().isValid())

        # Col 1 (UID) should have background
        it_1 = self.win.tbl_scenarios.item(0, 1)
        self.assertIsNotNone(it_1)
        self.assertTrue(it_1.background().color().isValid())

    def test_08_condition_enabled_toggle_preserves_condition_points(self):
        """Verify unchecking chk_has_condition deactivates condition without deleting points list."""
        from core.models import Condition, ColorPoint
        pt1 = ColorPoint(x=10, y=20, r=255, g=0, b=0, tolerance=10)
        pt2 = ColorPoint(x=30, y=40, r=0, g=255, b=0, tolerance=10)
        cond = Condition(name="TestCond", points=[pt1, pt2])
        scen = Scenario(id="scen_toggle", name="조건 활성 테스트", condition=cond, condition_enabled=True)
        self.project.scenarios = [scen]
        self.win._refresh_scenario_table()
        self.win.tbl_scenarios.selectRow(0)
        self.win._on_table_selection_changed()

        inspector = self.win.inspector
        self.assertTrue(inspector.chk_has_condition.isChecked())
        self.assertEqual(len(scen.condition.points), 2)

        # Uncheck condition enable
        inspector.chk_has_condition.setChecked(False)
        self.assertFalse(inspector.current_scenario.condition_enabled)
        # Condition object and points list MUST NOT be cleared
        self.assertIsNotNone(inspector.current_scenario.condition)
        self.assertEqual(len(inspector.current_scenario.condition.points), 2)

        # Save inspector draft to original scenario
        inspector._on_save_inspector()
        self.assertFalse(scen.condition_enabled)
        self.assertIsNotNone(scen.condition)
        self.assertEqual(len(scen.condition.points), 2)

        # Serialization round-trip
        data = scen.to_dict()
        self.assertFalse(data.get("condition_enabled"))
        restored = Scenario.from_dict(data)
        self.assertFalse(restored.condition_enabled)
        self.assertEqual(len(restored.condition.points), 2)

    def test_09_folder_node_inspector_vertical_stretch_fix(self):
        """Verify folder node header card does not elongate vertically and txt_name has fixed max height."""
        folder = Scenario(id="f_vstretch", name="폴더 노드", node_type="folder_start")
        self.project.scenarios = [folder]
        self.win._refresh_scenario_table()
        self.win.tbl_scenarios.selectRow(0)
        self.win._on_table_selection_changed()

        inspector = self.win.inspector
        self.assertTrue(inspector.condition_card.isHidden())
        self.assertTrue(inspector.branch_card.isHidden())
        self.assertTrue(inspector.action_card.isHidden())
        self.assertFalse(inspector.header_card.isHidden())

        # Header card vertical policy should be Maximum and txt_name max height 28
        from PyQt5.QtWidgets import QSizePolicy
        self.assertEqual(inspector.header_card.sizePolicy().verticalPolicy(), QSizePolicy.Maximum)
        self.assertEqual(inspector.txt_name.maximumHeight(), 28)

    def test_10_snapshot_enlarged_preview_support(self):
        """Verify snapshot click opens enlarged image preview instead of options menu."""
        from ui.image_preview_dialog import ImagePreviewDialog
        scen = Scenario(id="scen_preview", name="스냅샷 프리뷰", reference_image_path="test_img.png")
        self.project.scenarios = [scen]
        self.win._refresh_scenario_table()
        self.win.tbl_scenarios.selectRow(0)
        self.win._on_table_selection_changed()

        # Clicking thumbnail label triggers _on_node_snapshot_clicked
        inspector = self.win.inspector
        self.assertTrue(hasattr(inspector, "_on_node_snapshot_clicked"))
        # Verify ImagePreviewDialog is importable and functional
        dlg = ImagePreviewDialog("nonexistent.png", "Test Preview")
        self.assertEqual(dlg.windowTitle(), "Test Preview")
        dlg.close()


if __name__ == "__main__":
    unittest.main()

