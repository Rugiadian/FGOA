"""
Unit tests for Composite Scenario Nodes, Modular Condition/ActionSequence,
Relative Path Resolution, and Decoupled Image Import.
"""

import os
import sys
import unittest
import tempfile
import shutil
from PIL import Image

from PyQt5.QtWidgets import QApplication

from core.models import Project, Scenario, Condition, ActionSequence, Action
from core.path_utils import (
    get_project_root,
    get_references_dir,
    to_relative_path,
    to_absolute_path,
)
from ui.coordinate_picker_dialog import CoordinatePickerDialog
from ui.modules_manager_widget import ModulesManagerWidget

# Ensure single QApplication instance
app = QApplication.instance() or QApplication(sys.argv)


class TestCompositeScenarioModules(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.dummy_img_path = os.path.join(self.tmp_dir, "test_ref_img.png")
        img = Image.new("RGB", (100, 50), color="blue")
        img.save(self.dummy_img_path)

        # Also create a dummy file inside repo references/ for relative path tests
        self.repo_refs_dir = get_references_dir()
        self.repo_test_img = os.path.join(self.repo_refs_dir, "_temp_unit_test_img.png")
        img.save(self.repo_test_img)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        if os.path.exists(self.repo_test_img):
            try:
                os.remove(self.repo_test_img)
            except Exception:
                pass

    def test_01_path_utils_relative_and_absolute(self):
        """Test conversion between relative and absolute paths for GitHub portability."""
        # Relative conversion
        rel_path = to_relative_path(self.repo_test_img)
        self.assertEqual(rel_path.replace("\\", "/"), "references/_temp_unit_test_img.png")

        # Absolute conversion from relative
        abs_resolved = to_absolute_path(rel_path)
        self.assertTrue(os.path.samefile(abs_resolved, self.repo_test_img))

        # Recovery across different computers (foreign absolute path with same filename)
        foreign_path = r"D:\old_computer_path\references\_temp_unit_test_img.png"
        recovered = to_absolute_path(foreign_path)
        self.assertTrue(os.path.exists(recovered))
        self.assertTrue(os.path.samefile(recovered, self.repo_test_img))

    def test_02_create_composite_scenario(self):
        """Verify Project.create_composite_scenario creates paired modules and binds them."""
        project = Project(name="Composite Test")
        scen = project.create_composite_scenario(name="배틀 시작", node_type="action")

        self.assertEqual(len(project.scenarios), 1)
        self.assertEqual(len(project.conditions), 1)
        self.assertEqual(len(project.action_sequences), 1)

        cond = project.conditions[0]
        seq = project.action_sequences[0]

        # Condition module has number and links to paired ActionSequence
        self.assertEqual(cond.condition_number, 1)
        self.assertEqual(cond.action_sequence_id, seq.id)

        # ActionSequence module has number
        self.assertEqual(seq.sequence_number, 1)

        # Scenario node references both modules
        self.assertEqual(scen.condition_id, cond.id)
        self.assertEqual(scen.sequence_id, seq.id)

        # Effective condition & actions
        self.assertEqual(scen.get_effective_condition(project).id, cond.id)
        self.assertEqual(len(scen.get_effective_actions(project)), 0)

    def test_03_modular_swapping_in_scenario_node(self):
        """Verify scenario nodes can swap condition and action sequence modules freely."""
        project = Project(name="Modular Swap Test")
        scen1 = project.create_composite_scenario(name="노드 1")
        scen2 = project.create_composite_scenario(name="노드 2")

        cond1 = project.conditions[0]
        cond2 = project.conditions[1]
        seq1 = project.action_sequences[0]
        seq2 = project.action_sequences[1]

        # Swap: Scen1 reuses cond2 and seq2
        scen1.condition_id = cond2.id
        scen1.sequence_id = seq2.id

        self.assertEqual(scen1.get_effective_condition(project).id, cond2.id)
        self.assertEqual(scen1.get_effective_condition(project).condition_number, 2)

        # Update action in seq2, verify scen1 reflects it
        seq2.actions.append(Action(action_type="mouse_click", x=123, y=456))
        eff_actions = scen1.get_effective_actions(project)
        self.assertEqual(len(eff_actions), 1)
        self.assertEqual(eff_actions[0].x, 123)

    def test_04_serialization_preserves_relative_paths_and_modules(self):
        """Verify Project to_dict and from_dict preserve module IDs and convert to relative paths."""
        project = Project(name="Serialization Test")
        scen = project.create_composite_scenario(name="시리얼 테스트")
        cond = scen.get_effective_condition(project)
        seq = project.find_action_sequence(scen.sequence_id)

        cond.reference_image_path = self.repo_test_img
        seq.last_action_image_path = self.repo_test_img

        data = project.to_dict()
        # Paths in dict should be relative
        self.assertEqual(data["conditions"][0]["reference_image_path"].replace("\\", "/"), "references/_temp_unit_test_img.png")
        self.assertEqual(data["action_sequences"][0]["last_action_image_path"].replace("\\", "/"), "references/_temp_unit_test_img.png")

        # Reconstruct project
        loaded = Project.from_dict(data)
        self.assertEqual(len(loaded.conditions), 1)
        self.assertEqual(len(loaded.action_sequences), 1)
        self.assertEqual(loaded.scenarios[0].condition_id, loaded.conditions[0].id)
        self.assertEqual(loaded.scenarios[0].sequence_id, loaded.action_sequences[0].id)
        self.assertEqual(loaded.conditions[0].action_sequence_id, loaded.action_sequences[0].id)

    def test_05_coordinate_picker_decoupled_and_import_button(self):
        """Verify CoordinatePickerDialog decouples condition image and button explicitly imports it."""
        CoordinatePickerDialog.set_last_used_image_path(None)

        project = Project(name="Picker Decouple Test")
        scen = project.create_composite_scenario(name="좌표 피커 테스트")
        cond = scen.get_effective_condition(project)
        cond.reference_image_path = self.repo_test_img

        # 1. Dialog initialized: condition image is NOT loaded automatically
        dlg = CoordinatePickerDialog(scenario=scen, project=project, target_hwnd=0)
        self.assertIsNone(dlg.current_image_path)

        # 2. Click explicit button to import linked condition's reference image
        dlg._on_import_linked_condition_image()
        self.assertTrue(os.path.samefile(dlg.current_image_path, self.repo_test_img))
        self.assertIsNotNone(dlg.canvas.pixmap)
        self.assertEqual(dlg.canvas.pixmap.width(), 100)
        self.assertEqual(dlg.canvas.pixmap.height(), 50)
        dlg.close()

    def test_06_modules_manager_widget(self):
        """Verify ModulesManagerWidget lists condition and action sequence modules."""
        project = Project(name="Modules Manager Test")
        project.create_composite_scenario(name="모듈 관리 테스트 1")
        project.create_composite_scenario(name="모듈 관리 테스트 2")

        widget = ModulesManagerWidget(project=project)
        widget.refresh()

        self.assertEqual(widget.table_conditions.rowCount(), 2)
        self.assertEqual(widget.table_sequences.rowCount(), 2)

        # Check table headers and content
        item_c1 = widget.table_conditions.item(0, 0)
        self.assertEqual(item_c1.text(), "C1")
        item_a1 = widget.table_sequences.item(0, 0)
        self.assertEqual(item_a1.text(), "A1")

        from unittest.mock import patch

        # Test adding a condition with mock input
        with patch("ui.modules_manager_widget.QInputDialog.getText", return_value=("인식조건 3", True)):
            widget._on_add_condition()
        self.assertEqual(len(project.conditions), 3)
        self.assertEqual(widget.table_conditions.rowCount(), 3)
        self.assertEqual(project.conditions[-1].condition_number, 3)

        # Test adding an action sequence with mock input
        with patch("ui.modules_manager_widget.QInputDialog.getText", return_value=("액션 시퀀스 3", True)):
            widget._on_add_sequence()
        self.assertEqual(len(project.action_sequences), 3)
        self.assertEqual(widget.table_sequences.rowCount(), 3)
        self.assertEqual(project.action_sequences[-1].sequence_number, 3)


if __name__ == "__main__":
    unittest.main()
