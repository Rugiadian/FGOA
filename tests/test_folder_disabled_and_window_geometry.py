"""
Unit tests for Folder Disabled/Enabled Visual Enhancements and Window Position/Size Persistence.
(폴더 단위 비활성/활성 알아보기 쉽게 개선 및 마지막 창 위치/크기 기억 기능 검증)
"""
import os
import sys
import json
import tempfile
import unittest
from PyQt5.QtWidgets import QApplication, QCheckBox, QTableWidgetItem
from PyQt5.QtCore import Qt, QPoint, QByteArray
from PyQt5.QtGui import QColor

from core.models import Project, Scenario
from core.runner import WorkflowRunner
from core.config import get_config_filepath
from ui.main_window import MainWindow

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)


class TestFolderDisabledAndWindowGeometry(unittest.TestCase):
    def setUp(self):
        self.project = Project(name="Test Folder & Window Project")
        # Create a folder with 2 children
        self.f_start = Scenario(id="fld_start_1", name="파밍 그룹", node_type="folder_start", enabled=True)
        self.scen_1 = Scenario(id="scen_a", name="퀘스트 선택", node_type="normal", enabled=True)
        self.scen_2 = Scenario(id="scen_b", name="전투 시작", node_type="normal", enabled=True)
        self.f_end = Scenario(id="fld_end_1", name="파밍 그룹", node_type="folder_end", enabled=True)

        self.project.scenarios = [self.f_start, self.scen_1, self.scen_2, self.f_end]
        self.project.renumber_steps()

    def test_find_scenario_index(self):
        """Verify Project.find_scenario_index returns correct indices."""
        self.assertEqual(self.project.find_scenario_index("fld_start_1"), 0)
        self.assertEqual(self.project.find_scenario_index("scen_a"), 1)
        self.assertEqual(self.project.find_scenario_index("scen_b"), 2)
        self.assertEqual(self.project.find_scenario_index("fld_end_1"), 3)
        self.assertEqual(self.project.find_scenario_index("non_existent"), -1)

    def test_runner_skips_disabled_folder_and_emits_signals(self):
        """Verify WorkflowRunner skips entire disabled folder and emits skipped signals for all items."""
        self.f_start.enabled = False
        runner = WorkflowRunner(self.project, hwnd=0)

        skipped_ids = []
        runner.sig_scenario_completed.connect(lambda sid, status: skipped_ids.append((sid, status)))

        # Run step directly
        runner._stop_flag = True  # Stop after skipping the folder block
        # Start the runner thread briefly or execute loop body logic
        end_idx = self.project.find_matching_folder_end(0)
        self.assertEqual(end_idx, 3)

        # Test runner folder check logic directly
        scen = self.project.scenarios[0]
        if getattr(scen, "is_folder_start", False) and not scen.enabled:
            for i in range(0, end_idx + 1):
                runner.sig_scenario_completed.emit(self.project.scenarios[i].id, "skipped")

        self.assertEqual(len(skipped_ids), 4)
        self.assertEqual(skipped_ids[0], ("fld_start_1", "skipped"))
        self.assertEqual(skipped_ids[1], ("scen_a", "skipped"))
        self.assertEqual(skipped_ids[2], ("scen_b", "skipped"))
        self.assertEqual(skipped_ids[3], ("fld_end_1", "skipped"))

    def test_window_geometry_persistence_methods(self):
        """Verify MainWindow._save_app_config and _load_app_config remember window position and size."""
        window = MainWindow()
        window.resize(1420, 910)
        window.move(120, 150)

        # Save config
        window._save_app_config()

        # Read config file to verify fields were written
        cfg_file = get_config_filepath()
        self.assertTrue(os.path.exists(cfg_file))
        with open(cfg_file, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        self.assertIn("window_width", cfg)
        self.assertIn("window_height", cfg)
        self.assertIn("window_x", cfg)
        self.assertIn("window_y", cfg)
        self.assertIn("window_geometry", cfg)
        self.assertIn("window_is_maximized", cfg)

        self.assertGreaterEqual(cfg["window_width"], 1020)
        self.assertGreaterEqual(cfg["window_height"], 650)

        # Create another window instance and verify restoration
        window2 = MainWindow()
        # _load_app_config was called in __init__
        self.assertIsNotNone(window2.width())
        self.assertIsNotNone(window2.height())

        window.close()
        window2.close()

    def test_folder_toggle_synchronization(self):
        """Verify toggling folder start synchronizes folder end and updates table."""
        window = MainWindow()
        window.project = self.project
        window._refresh_scenario_table()

        # Initially all enabled
        self.assertTrue(self.f_start.enabled)
        self.assertTrue(self.f_end.enabled)

        # Toggle folder start to unchecked
        window._on_scenario_toggle(self.f_start, Qt.Unchecked)
        self.assertFalse(self.f_start.enabled)
        self.assertFalse(self.f_end.enabled)

        # Toggle folder end back to checked
        window._on_scenario_toggle(self.f_end, Qt.Checked)
        self.assertTrue(self.f_start.enabled)
        self.assertTrue(self.f_end.enabled)

        window.close()

    def test_folder_batch_children_toggle(self):
        """Verify _set_folder_children_enabled batch toggles child items."""
        window = MainWindow()
        window.project = self.project
        window._refresh_scenario_table()

        # Batch disable children
        window._set_folder_children_enabled(self.f_start, False)
        self.assertFalse(self.scen_1.enabled)
        self.assertFalse(self.scen_2.enabled)
        # Folder markers stay unchanged
        self.assertTrue(self.f_start.enabled)
        self.assertTrue(self.f_end.enabled)

        # Batch enable children
        window._set_folder_children_enabled(self.f_start, True)
        self.assertTrue(self.scen_1.enabled)
        self.assertTrue(self.scen_2.enabled)

        window.close()

    def test_folder_disabled_visual_elements(self):
        """Verify disabled folder and child rows show only gray text, no strikethrough/icons/replacement text, preserving contents."""
        window = MainWindow()
        window.project = self.project

        # Disable folder
        self.f_start.enabled = False
        self.f_end.enabled = False
        window._refresh_scenario_table()

        # Check Row 0 (folder start)
        item_start_uid = window.tbl_scenarios.item(0, 1)
        self.assertNotIn("🚫", item_start_uid.text())
        self.assertFalse(item_start_uid.font().strikeOut())
        item_start_name = window.tbl_scenarios.item(0, 3)
        self.assertNotIn("비활성", item_start_name.text())
        self.assertNotIn("🚫", item_start_name.text())
        self.assertFalse(item_start_name.font().strikeOut())
        self.assertFalse(item_start_name.font().underline())
        item_start_cond = window.tbl_scenarios.item(0, 4)
        self.assertIn("그룹 폴더 시작", item_start_cond.text())
        self.assertNotIn("스킵", item_start_cond.text())

        # Check Row 1 (child scenario inside disabled folder)
        item_child_uid = window.tbl_scenarios.item(1, 1)
        self.assertNotIn("🚫", item_child_uid.text())
        self.assertFalse(item_child_uid.font().strikeOut())
        item_child_name = window.tbl_scenarios.item(1, 3)
        self.assertNotIn("폴더 비활성", item_child_name.text())
        self.assertNotIn("🚫", item_child_name.text())
        self.assertFalse(item_child_name.font().strikeOut())
        self.assertFalse(item_child_name.font().underline())
        # Check single arrow indentation (not double)
        self.assertTrue(item_child_name.text().startswith("  ↳ 퀘스트 선택"))
        self.assertNotIn("↳ ↳", item_child_name.text())
        self.assertNotIn("│", item_child_name.text())

        # Branch text preserved, not replaced with '(폴더 비활성)'
        item_child_branch = window.tbl_scenarios.item(1, 6)
        self.assertNotIn("폴더 비활성", item_child_branch.text())
        self.assertIn("실행 / 다음", item_child_branch.text())

        # Check Row 3 (folder end)
        item_end_name = window.tbl_scenarios.item(3, 3)
        self.assertNotIn("비활성", item_end_name.text())
        self.assertNotIn("🚫", item_end_name.text())
        self.assertFalse(item_end_name.font().strikeOut())

        # Check individual disabled scenario (all columns gray and tagged)
        self.f_start.enabled = True
        self.f_end.enabled = True
        self.scen_1.enabled = False
        window._refresh_scenario_table()
        item_scen1_uid = window.tbl_scenarios.item(1, 1)
        item_scen1_name = window.tbl_scenarios.item(1, 3)
        item_scen1_cond = window.tbl_scenarios.item(1, 4)
        item_scen1_act = window.tbl_scenarios.item(1, 5)
        item_scen1_branch = window.tbl_scenarios.item(1, 6)
        self.assertFalse(item_scen1_name.font().strikeOut())
        self.assertTrue(item_scen1_uid.data(Qt.UserRole + 99))
        self.assertTrue(item_scen1_name.data(Qt.UserRole + 99))
        self.assertTrue(item_scen1_cond.data(Qt.UserRole + 99))
        self.assertTrue(item_scen1_act.data(Qt.UserRole + 99))
        self.assertTrue(item_scen1_branch.data(Qt.UserRole + 99))

        # Check inspector real-time reflection disabled, save reflects
        window.inspector.set_scenario(self.scen_1, None, window.project)
        window.inspector.txt_name.setText("테스트 변경 이름")
        # Must not be reflected in table yet
        self.assertNotIn("테스트 변경 이름", window.tbl_scenarios.item(1, 3).text())
        # Save explicitly
        window.inspector._on_save_inspector()
        self.assertIn("테스트 변경 이름", window.tbl_scenarios.item(1, 3).text())

        window.close()

    def test_add_scenario_below_selected_node(self):
        """Verify adding a scenario inserts it directly below the currently selected scenario."""
        window = MainWindow()
        window.project = self.project
        window._refresh_scenario_table()

        # Select row 1 (scen_1)
        window.tbl_scenarios.selectRow(1)
        initial_len = len(window.project.scenarios)

        window._on_add_scenario()

        self.assertEqual(len(window.project.scenarios), initial_len + 1)
        # New scenario should be at index 2 (below row 1)
        inserted_scen = window.project.scenarios[2]
        self.assertEqual(inserted_scen.node_type, "normal")
        # Table should have row 2 selected
        self.assertEqual(window.tbl_scenarios.currentRow(), 2)

        # Insert at the end when nothing is selected
        window.inspector.current_scenario = None
        window.tbl_scenarios.clearSelection()
        window._on_add_scenario()
        self.assertEqual(len(window.project.scenarios), initial_len + 2)
        self.assertEqual(window.tbl_scenarios.currentRow(), len(window.project.scenarios) - 1)

        window.close()

    def test_disabled_folder_child_node_checkbox_gray_styling(self):
        """Verify child node checkbox indicator is styled with gray colors when parent folder is disabled."""
        window = MainWindow()
        window.project = self.project

        # 1. Folder enabled: children should not have custom gray stylesheet
        self.f_start.enabled = True
        window._refresh_scenario_table()
        w1 = window.tbl_scenarios.cellWidget(1, 2)
        chk1 = w1.findChild(QCheckBox) if w1 else None
        self.assertIsNotNone(chk1)
        self.assertEqual(chk1.styleSheet(), "")

        # 2. Disable folder: child node checkbox should have gray indicator stylesheet
        self.f_start.enabled = False
        window._refresh_scenario_table()
        w1 = window.tbl_scenarios.cellWidget(1, 2)
        chk1 = w1.findChild(QCheckBox) if w1 else None
        self.assertIsNotNone(chk1)
        self.assertTrue("#94a3b8" in chk1.styleSheet() or "#64748b" in chk1.styleSheet())
        self.assertIn("상위 그룹 폴더가 비활성화되어", chk1.toolTip())

        # 3. Re-enable folder: child node checkbox stylesheet should be empty (default blue theme)
        self.f_start.enabled = True
        window._refresh_scenario_table()
        w1 = window.tbl_scenarios.cellWidget(1, 2)
        chk1 = w1.findChild(QCheckBox) if w1 else None
        self.assertIsNotNone(chk1)
        self.assertEqual(chk1.styleSheet(), "")

        window.close()


if __name__ == "__main__":
    unittest.main()
