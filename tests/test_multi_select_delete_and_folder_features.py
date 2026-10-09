import unittest
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QSize
from core.models import Project, Scenario
from ui.scenario_table_widget import DraggableScenarioTableWidget
from ui.inspector_widget import InspectorWidget
from ui.main_window import MainWindow

app = QApplication.instance()
if not app:
    app = QApplication([])


class TestMultiSelectDeleteAndFolderFeatures(unittest.TestCase):
    """
    Tests for:
    1. Extended selection and multi-node batch deletion.
    2. Inspector minimum size and jump combo size policies preventing scenario panel squeezing.
    3. User-adjusted scenario name column width preservation.
    4. Blank new scenario project creation (Ctrl+N, 0 scenarios).
    5. Folder creation with clean Start/End pair (no dummy node) and distinct child background tints.
    6. Inserting and reordering nodes into empty folders with auto-expansion.
    """

    def setUp(self):
        self.project = Project(name="TestProj", scenarios=[])
        self.win = MainWindow()
        self.win.project = self.project

    def tearDown(self):
        self.win.close()

    def test_01_scenario_table_extended_selection_and_width_preservation(self):
        """Verify scenario table uses ExtendedSelection and preserves user column width for name column."""
        tbl = self.win.tbl_scenarios
        self.assertEqual(tbl.selectionMode(), DraggableScenarioTableWidget.ExtendedSelection)

        # Simulate user resizing column 3 (Scenario Name) to 450px
        tbl.horizontalHeader().resizeSection(3, 450)
        tbl._on_section_resized(3, 0, 450)
        self.assertEqual(tbl._user_column_widths.get(3), 450)

        # Trigger adjust_column_widths and verify it preserves 450
        tbl.adjust_column_widths()
        self.assertEqual(tbl.columnWidth(3), 450)

    def test_02_inspector_minimum_size_hint_and_combos(self):
        """Verify InspectorWidget has bounded minimumSizeHint preventing scenario list collapse."""
        inspector = InspectorWidget()
        hint = inspector.minimumSizeHint()
        self.assertLessEqual(hint.width(), 260)
        self.assertGreaterEqual(hint.width(), 100)
        inspector.deleteLater()

    def test_03_folder_pair_creation_and_child_tint(self):
        """Verify adding folder creates only Start and End pair without dummy nodes, and children have distinct tint."""
        # Start with empty project
        self.assertEqual(len(self.win.project.scenarios), 0)

        # Add folder block
        self.win._on_add_folder()
        self.assertEqual(len(self.win.project.scenarios), 2)
        start_node = self.win.project.scenarios[0]
        end_node = self.win.project.scenarios[1]
        self.assertEqual(start_node.node_type, "folder_start")
        self.assertEqual(end_node.node_type, "folder_end")

        # Now add a child node inside by selecting folder_start
        self.win.tbl_scenarios.selectRow(0)
        self.win._on_add_scenario()
        self.assertEqual(len(self.win.project.scenarios), 3)
        child_node = self.win.project.scenarios[1]
        self.assertEqual(child_node.node_type, "normal")

        # Folder analysis should show child info with bg tint
        folder_info = self.win.project.analyze_folders()
        self.assertIn(1, folder_info)
        child_meta = folder_info[1]
        self.assertTrue(child_meta.get("is_child"))
        self.assertIn("bg_light", child_meta)
        self.assertIn("bg_dark", child_meta)
        self.assertIsNotNone(child_meta["bg_light"])

    def test_04_drag_node_into_empty_folder(self):
        """Verify dragging a node onto an empty folder start drops it inside and uncollapses folder."""
        # Create folder pair (0: start, 1: end) and normal node (2: child)
        start = Scenario(scenario_number=1, name="폴더 1", node_type="folder_start", is_collapsed=True)
        end = Scenario(scenario_number=2, name="폴더 1 끝", node_type="folder_end", folder_target_id=start.id)
        start.folder_target_id = end.id
        normal = Scenario(scenario_number=3, name="일반노드", node_type="normal")

        self.win.project.scenarios = [start, end, normal]
        self.win.project.renumber_steps()

        # Drag node from row 2 onto row 0 (empty folder start)
        self.win._on_scenario_row_reordered(2, 0)

        # Node should now be at row 1 (between start and end)
        self.assertEqual(len(self.win.project.scenarios), 3)
        self.assertEqual(self.win.project.scenarios[0].node_type, "folder_start")
        self.assertEqual(self.win.project.scenarios[1].name, "일반노드")
        self.assertEqual(self.win.project.scenarios[2].node_type, "folder_end")
        self.assertFalse(self.win.project.scenarios[0].is_collapsed)

    def test_05_multi_node_batch_delete(self):
        """Verify multiple selected rows can be deleted in batch."""
        for i in range(5):
            self.win.project.scenarios.append(Scenario(scenario_number=i+1, name=f"Node {i+1}"))
        self.win.project.renumber_steps()
        self.win._refresh_scenario_table()
        self.assertEqual(len(self.win.project.scenarios), 5)

        # Multi-select rows 1, 2, 3 using QItemSelectionModel
        from PyQt5.QtCore import QItemSelectionModel
        self.win.tbl_scenarios.clearSelection()
        sel_model = self.win.tbl_scenarios.selectionModel()
        for r in [1, 2, 3]:
            sel_model.select(self.win.tbl_scenarios.model().index(r, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)

        # Mock QMessageBox.question to return Yes
        from PyQt5.QtWidgets import QMessageBox
        orig_question = QMessageBox.question
        QMessageBox.question = lambda *args, **kwargs: QMessageBox.Yes
        try:
            self.win._on_delete_scenario()
        finally:
            QMessageBox.question = orig_question

        # Rows 1, 2, 3 deleted -> 2 scenarios remain (Node 1 and Node 5)
        self.assertEqual(len(self.win.project.scenarios), 2)
        self.assertEqual(self.win.project.scenarios[0].name, "Node 1")
        self.assertEqual(self.win.project.scenarios[1].name, "Node 5")

    def test_06_new_scenario_project(self):
        """Verify _on_new_scenario_project resets project to 0 scenarios and clears inspector."""
        for i in range(3):
            self.win.project.scenarios.append(Scenario(scenario_number=i+1, name=f"Node {i+1}"))
        self.win.current_project_path = "some_path.json"

        from PyQt5.QtWidgets import QMessageBox
        orig_question = QMessageBox.question
        QMessageBox.question = lambda *args, **kwargs: QMessageBox.Yes
        try:
            self.win._on_new_scenario_project()
        finally:
            QMessageBox.question = orig_question

        self.assertEqual(len(self.win.project.scenarios), 0)
        self.assertIsNone(self.win.current_project_path)
        self.assertEqual(self.win.tbl_scenarios.rowCount(), 0)


if __name__ == "__main__":
    unittest.main()
