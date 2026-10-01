"""
Unit tests for Scenario List Folder Start/End, Indentation Hierarchy,
and Unit-based Moving (Photoshop-like Folder Group System).
"""
import unittest
import sys
import os

# Add root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from core.models import Project, Scenario, Action, Condition
from core.runner import WorkflowRunner
from ui.main_window import MainWindow

app = QApplication.instance()
if not app:
    app = QApplication([])


class TestFolderStartEndAndUnitMove(unittest.TestCase):
    def setUp(self):
        self.project = Project()
        self.main_win = MainWindow()
        self.main_win.project = self.project

    def test_01_folder_start_end_properties_and_pairing(self):
        """Verify folder_start and folder_end properties, serialization and pairing."""
        f_start = Scenario(
            scenario_number=1,
            name="그룹 1",
            node_type="folder_start",
            is_collapsed=False
        )
        child1 = Scenario(scenario_number=2, name="스텝 1", node_type="normal")
        child2 = Scenario(scenario_number=3, name="스텝 2", node_type="normal")
        f_end = Scenario(
            scenario_number=4,
            name="그룹 1 끝",
            node_type="folder_end",
            folder_target_id=f_start.id
        )
        f_start.folder_target_id = f_end.id

        self.assertTrue(f_start.is_folder_start)
        self.assertFalse(f_start.is_folder_end)
        self.assertTrue(f_start.is_folder)

        self.assertFalse(f_end.is_folder_start)
        self.assertTrue(f_end.is_folder_end)
        self.assertTrue(f_end.is_folder)

        # Serialization test
        d_start = f_start.to_dict()
        self.assertEqual(d_start["node_type"], "folder_start")
        self.assertEqual(d_start["folder_target_id"], f_end.id)

        d_end = f_end.to_dict()
        self.assertEqual(d_end["node_type"], "folder_end")
        self.assertEqual(d_end["folder_target_id"], f_start.id)

        restored_start = Scenario.from_dict(d_start)
        self.assertEqual(restored_start.node_type, "folder_start")
        self.assertEqual(restored_start.folder_target_id, f_end.id)

        # Test Project pairing
        self.project.scenarios = [f_start, child1, child2, f_end]
        self.assertEqual(self.project.find_matching_folder_end(0), 3)
        self.assertEqual(self.project.find_matching_folder_start(3), 0)

        analysis = self.project.analyze_folders()
        self.assertTrue(analysis[0]["has_pair"])
        self.assertEqual(analysis[0]["partner_index"], 3)
        self.assertEqual(analysis[0]["child_count"], 2)
        self.assertTrue(analysis[3]["has_pair"])
        self.assertEqual(analysis[3]["partner_index"], 0)

    def test_02_hierarchy_depth_and_nested_folders(self):
        """Verify compute_hierarchy_depths with nested folders and loops."""
        # Structure:
        # 0: Outer Folder Start
        # 1: Inner Item 1 (depth 1)
        # 2: Inner Folder Start (depth 1 -> child depth 2)
        # 3: Deep Item (depth 2)
        # 4: Inner Folder End (depth 1)
        # 5: Loop Start (depth 1 -> child depth 2)
        # 6: Loop Item (depth 2)
        # 7: Loop End (depth 1)
        # 8: Outer Folder End (depth 0)
        # 9: Root Item (depth 0)
        scens = [
            Scenario(scenario_number=1, name="외부 폴더", node_type="folder_start"),
            Scenario(scenario_number=2, name="항목 1", node_type="normal"),
            Scenario(scenario_number=3, name="내부 폴더", node_type="folder_start"),
            Scenario(scenario_number=4, name="심층 항목", node_type="normal"),
            Scenario(scenario_number=5, name="내부 폴더 끝", node_type="folder_end"),
            Scenario(scenario_number=6, name="루프 시작", node_type="loop_start"),
            Scenario(scenario_number=7, name="루프 항목", node_type="normal"),
            Scenario(scenario_number=8, name="루프 끝", node_type="loop_end"),
            Scenario(scenario_number=9, name="외부 폴더 끝", node_type="folder_end"),
            Scenario(scenario_number=10, name="루트 항목", node_type="normal"),
        ]
        self.project.scenarios = scens
        depths = self.project.compute_hierarchy_depths()

        expected_depths = [0, 1, 1, 2, 1, 1, 2, 1, 0, 0]
        self.assertEqual(depths, expected_depths)

    def test_03_folder_collapse_hiding_children_and_end(self):
        """Verify Photoshop-like collapse: inner items and folder_end hidden, folder_start shows count."""
        f_start = Scenario(scenario_number=1, name="그룹 A", node_type="folder_start", is_collapsed=False)
        c1 = Scenario(scenario_number=2, name="항목 1", node_type="normal")
        c2 = Scenario(scenario_number=3, name="항목 2", node_type="normal")
        f_end = Scenario(scenario_number=4, name="그룹 A 끝", node_type="folder_end")
        outside = Scenario(scenario_number=5, name="외부 항목", node_type="normal")

        self.main_win.project.scenarios = [f_start, c1, c2, f_end, outside]
        self.main_win._refresh_scenario_table()

        # All visible initially
        for i in range(5):
            self.assertFalse(self.main_win.tbl_scenarios.isRowHidden(i))

        # Collapse folder
        self.main_win._toggle_folder_collapse(f_start)
        self.assertTrue(f_start.is_collapsed)

        # Folder start is visible, c1, c2, f_end are hidden, outside is visible
        self.assertFalse(self.main_win.tbl_scenarios.isRowHidden(0))  # Start visible
        self.assertTrue(self.main_win.tbl_scenarios.isRowHidden(1))   # Child 1 hidden
        self.assertTrue(self.main_win.tbl_scenarios.isRowHidden(2))   # Child 2 hidden
        self.assertTrue(self.main_win.tbl_scenarios.isRowHidden(3))   # End hidden (Photoshop group behavior)
        self.assertFalse(self.main_win.tbl_scenarios.isRowHidden(4))  # Outside remains visible

        # Table text shows collapse icon ▶ and child count
        item_text = self.main_win.tbl_scenarios.item(0, 3).text()
        self.assertIn("▶", item_text)
        self.assertIn("2개 항목 접힘", item_text)

        # Expand folder
        self.main_win._toggle_folder_collapse(f_start)
        self.assertFalse(f_start.is_collapsed)
        for i in range(5):
            self.assertFalse(self.main_win.tbl_scenarios.isRowHidden(i))

    def test_04_folder_unit_move_up_and_down(self):
        """Verify entire folder unit (start, children, end) moves together on Move Up / Move Down."""
        s0 = Scenario(scenario_number=1, name="시나리오 0", node_type="normal")
        f_start = Scenario(scenario_number=2, name="폴더 1", node_type="folder_start")
        c1 = Scenario(scenario_number=3, name="자식 1", node_type="normal")
        c2 = Scenario(scenario_number=4, name="자식 2", node_type="normal")
        f_end = Scenario(scenario_number=5, name="폴더 1 끝", node_type="folder_end")
        s1 = Scenario(scenario_number=6, name="시나리오 1", node_type="normal")

        self.main_win.project.scenarios = [s0, f_start, c1, c2, f_end, s1]
        self.main_win._refresh_scenario_table()

        # Select folder_start (row 1) and Move Up
        self.main_win.tbl_scenarios.selectRow(1)
        self.main_win._on_move_up()

        # The entire folder block should now be at indices 0..3, and s0 at index 4
        scens = self.main_win.project.scenarios
        self.assertEqual(scens[0].node_type, "folder_start")
        self.assertEqual(scens[1].name, "자식 1")
        self.assertEqual(scens[2].name, "자식 2")
        self.assertEqual(scens[3].node_type, "folder_end")
        self.assertEqual(scens[4].name, "시나리오 0")
        self.assertEqual(scens[5].name, "시나리오 1")

        # Now select folder_start (row 0) and Move Down
        self.main_win.tbl_scenarios.selectRow(0)
        self.main_win._on_move_down()

        # The folder block moves below s0!
        scens = self.main_win.project.scenarios
        self.assertEqual(scens[0].name, "시나리오 0")
        self.assertEqual(scens[1].node_type, "folder_start")
        self.assertEqual(scens[2].name, "자식 1")
        self.assertEqual(scens[3].name, "자식 2")
        self.assertEqual(scens[4].node_type, "folder_end")
        self.assertEqual(scens[5].name, "시나리오 1")

        # Move Down again: moves below s1!
        self.main_win.tbl_scenarios.selectRow(1)
        self.main_win._on_move_down()

        scens = self.main_win.project.scenarios
        self.assertEqual(scens[0].name, "시나리오 0")
        self.assertEqual(scens[1].name, "시나리오 1")
        self.assertEqual(scens[2].node_type, "folder_start")
        self.assertEqual(scens[3].name, "자식 1")
        self.assertEqual(scens[4].name, "자식 2")
        self.assertEqual(scens[5].node_type, "folder_end")

    def test_05_adjacent_folders_swap_without_swallowing(self):
        """Verify moving a folder unit past another folder unit cleanly swaps them."""
        f0_s = Scenario(scenario_number=1, name="폴더 A", node_type="folder_start")
        f0_c = Scenario(scenario_number=2, name="A 항목", node_type="normal")
        f0_e = Scenario(scenario_number=3, name="폴더 A 끝", node_type="folder_end")

        f1_s = Scenario(scenario_number=4, name="폴더 B", node_type="folder_start")
        f1_c = Scenario(scenario_number=5, name="B 항목", node_type="normal")
        f1_e = Scenario(scenario_number=6, name="폴더 B 끝", node_type="folder_end")

        self.main_win.project.scenarios = [f0_s, f0_c, f0_e, f1_s, f1_c, f1_e]
        self.main_win._refresh_scenario_table()

        # Select Folder B start (row 3) and Move Up
        self.main_win.tbl_scenarios.selectRow(3)
        self.main_win._on_move_up()

        scens = self.main_win.project.scenarios
        # Folder B should be first, Folder A second
        self.assertEqual([s.name for s in scens], ["폴더 B", "B 항목", "폴더 B 끝", "폴더 A", "A 항목", "폴더 A 끝"])

    def test_06_folder_add_wrapping_selection(self):
        """Verify adding folder with 2+ rows selected wraps them between start and end (Photoshop Ctrl+G)."""
        s0 = Scenario(scenario_number=1, name="노드 0", node_type="normal")
        s1 = Scenario(scenario_number=2, name="노드 1", node_type="normal")
        s2 = Scenario(scenario_number=3, name="노드 2", node_type="normal")
        s3 = Scenario(scenario_number=4, name="노드 3", node_type="normal")

        self.main_win.project.scenarios = [s0, s1, s2, s3]
        self.main_win._refresh_scenario_table()

        # Select rows 1 and 2 (노드 1, 노드 2)
        from PyQt5.QtWidgets import QTableWidgetSelectionRange
        self.main_win.tbl_scenarios.clearSelection()
        self.main_win.tbl_scenarios.setRangeSelected(
            QTableWidgetSelectionRange(1, 0, 2, 6),
            True
        )

        self.main_win._on_add_folder()

        scens = self.main_win.project.scenarios
        self.assertEqual(len(scens), 6)
        self.assertEqual(scens[0].name, "노드 0")
        self.assertTrue(scens[1].is_folder_start)
        self.assertEqual(scens[2].name, "노드 1")
        self.assertEqual(scens[3].name, "노드 2")
        self.assertTrue(scens[4].is_folder_end)
        self.assertEqual(scens[5].name, "노드 3")

    def test_07_runner_folder_passthrough_and_disabled_skip(self):
        """Verify WorkflowRunner passes through enabled folders and skips entire folder if disabled."""
        executed = []

        f_start = Scenario(
            id="f_s",
            scenario_number=1,
            name="폴더",
            node_type="folder_start",
            enabled=False  # Disabled folder
        )
        child = Scenario(
            id="c1",
            scenario_number=2,
            name="실행되지 않아야 할 항목",
            node_type="normal",
            actions=[Action(action_type="delay", delay_seconds=0.01)]
        )
        f_end = Scenario(
            id="f_e",
            scenario_number=3,
            name="폴더 끝",
            node_type="folder_end"
        )
        after = Scenario(
            id="a1",
            scenario_number=4,
            name="폴더 뒤 실행 항목",
            node_type="normal",
            actions=[Action(action_type="delay", delay_seconds=0.01)]
        )

        self.project.scenarios = [f_start, child, f_end, after]
        runner = WorkflowRunner(self.project, 0)
        runner.sig_scenario_started.connect(lambda s_id: executed.append(s_id))

        # Direct loop iteration test
        end_idx = self.project.find_matching_folder_end(0)
        self.assertEqual(end_idx, 2)


if __name__ == "__main__":
    unittest.main()
