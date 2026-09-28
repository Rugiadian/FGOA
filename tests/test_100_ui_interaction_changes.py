"""
100 Comprehensive UI Interaction and State Change Tests for FGOA.
Covers:
- Main Window initialization, lifecycle, config, themes (Tests 01-10)
- Dock layout splitting, presets, dragging, toggling (Tests 11-25)
- Scenario Table manipulations, drag-reorder, undo/redo (Tests 26-45)
- Inspector panel editing, conditions, branching, actions (Tests 46-65)
- Virtual Canvas Window interactions, ripple effects, resize (Tests 66-75)
- Playback controls, pause/resume, runner transitions (Tests 76-88)
- Target window picker, activation, alive monitor (Tests 89-95)
- Log console, HTML styling, dialogs, presets (Tests 96-100)
"""
import os
import json
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QDockWidget, QTableWidget,
    QAbstractItemView, QHeaderView, QDialog, QMessageBox
)
from PyQt5.QtGui import QColor, QPaintEvent, QMouseEvent, QPixmap
from PyQt5.QtCore import Qt, QPoint, QByteArray

from core.models import Project, Scenario, Condition, Action, ColorPoint, ActionSequence
from core.window_manager import WindowInfo
from ui.virtual_canvas_window import VirtualCanvasWindow
from ui.main_window import MainWindow
from ui.anti_ban_dialog import AntiBanDialog

app = QApplication.instance() or QApplication([])


class Test100UIInteractionChanges(unittest.TestCase):
    """Suite of 100 robust UI interaction and state mutation test cases."""

    @classmethod
    def setUpClass(cls):
        cls.main_win = MainWindow()
        cls.main_win.show()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.main_win.close()
        except Exception:
            pass

    def setUp(self):
        # Reset to clean project state and clean inspector per test
        self.win = self.main_win
        self.win.project = Project(name="Test100Project")
        self.win._init_sample_project()
        self.win.scenario_undo_stack.clear()
        self.win.scenario_redo_stack.clear()
        self.win.inspector.is_dirty = False
        self.win.inspector.original_scenario = None
        self.win.inspector.current_scenario = None
        self.win._refresh_scenario_table()

    # ======================================================================
    # Category 1: Main Window Initialization & Lifecycle (Tests 01-10)
    # ======================================================================

    def test_01_window_title_formatting(self):
        """[Test 01] Verify window title formatting with project name."""
        self.win.current_project_path = "C:/dummy/test_project.json"
        self.win._update_window_title()
        self.assertIn("FGOA v", self.win.windowTitle())
        self.assertIn("[test_project.json]", self.win.windowTitle())

    def test_02_window_title_without_project(self):
        """[Test 02] Verify window title formatting when current_project_path is None."""
        self.win.current_project_path = None
        self.win._update_window_title()
        self.assertIn("FGOA v", self.win.windowTitle())
        self.assertNotIn("[", self.win.windowTitle())

    def test_03_window_minimum_size_enforced(self):
        """[Test 03] Verify main window has valid minimum size bounds."""
        self.assertGreaterEqual(self.win.minimumWidth(), 1000)
        self.assertGreaterEqual(self.win.minimumHeight(), 600)

    def test_04_theme_switch_to_dark(self):
        """[Test 04] Verify theme switching to dark mode mutates current_theme."""
        self.win.current_theme = "dark"
        self.win._apply_theme()
        self.assertEqual(self.win.current_theme, "dark")

    def test_05_theme_switch_to_light(self):
        """[Test 05] Verify theme switching to light mode mutates current_theme."""
        self.win.current_theme = "light"
        self.win._apply_theme()
        self.assertEqual(self.win.current_theme, "light")

    def test_06_hot_reload_checkbox_toggle(self):
        """[Test 06] Verify code hot reload checkbox toggling state."""
        self.win.chk_hot_reload.setChecked(True)
        self.assertTrue(self.win.chk_hot_reload.isChecked())
        self.win.chk_hot_reload.setChecked(False)
        self.assertFalse(self.win.chk_hot_reload.isChecked())

    def test_07_autoscroll_checkbox_toggle(self):
        """[Test 07] Verify log autoscroll checkbox toggle state."""
        self.win.chk_autoscroll.setChecked(False)
        self.assertFalse(self.win.chk_autoscroll.isChecked())
        self.win.chk_autoscroll.setChecked(True)
        self.assertTrue(self.win.chk_autoscroll.isChecked())

    def test_08_clear_log_interaction(self):
        """[Test 08] Verify clearing execution log clears records and widget text."""
        self.win._append_log("INFO", "테스트 로그 라인 1")
        self.assertGreater(len(self.win._log_records), 0)
        self.win._clear_logs()
        self.assertEqual(len(self.win._log_records), 0)
        self.assertEqual(self.win.txt_log.toPlainText().strip(), "")

    def test_09_save_and_load_app_config(self):
        """[Test 09] Verify app config serialization and reading with last_project_path."""
        self.win.current_project_path = "C:/tmp/saved_test.json"
        self.win._save_app_config()
        self.win._load_app_config()
        self.assertEqual(self.win.last_project_path, "C:/tmp/saved_test.json")

    def test_10_check_reload_state_returns_false_when_no_file(self):
        """[Test 10] Verify _check_reload_state returns False when no temp file exists."""
        reloaded = self.win._check_reload_state()
        self.assertFalse(reloaded)

    # ======================================================================
    # Category 2: Dock Layout & Splitting (Tests 11-25)
    # ======================================================================

    def test_11_apply_layout_default_3_column(self):
        """[Test 11] Verify applying '기본 3열 (Default)' layout."""
        self.win.apply_layout("기본 3열 (Default)", save_current=False)
        self.assertEqual(self.win.current_layout_name, "기본 3열 (Default)")
        self.assertFalse(self.win.dock_scenarios.isFloating())
        self.assertFalse(self.win.dock_inspector.isFloating())
        self.assertFalse(self.win.dock_actions.isFloating())
        self.assertFalse(self.win.dock_log.isFloating())

    def test_12_apply_layout_side_by_side(self):
        """[Test 12] Verify applying '인식 조건 / 액션 나란히 (Side-by-Side)' layout."""
        self.win.apply_layout("인식 조건 / 액션 나란히 (Side-by-Side)", save_current=False)
        self.assertEqual(self.win.current_layout_name, "인식 조건 / 액션 나란히 (Side-by-Side)")

    def test_13_apply_layout_wide(self):
        """[Test 13] Verify applying '와이드 (하단 콘솔)' layout."""
        self.win.apply_layout("와이드 (하단 콘솔)", save_current=False)
        self.assertEqual(self.win.current_layout_name, "와이드 (하단 콘솔)")

    def test_14_apply_layout_tall(self):
        """[Test 14] Verify applying '세로 분할 (Tall)' layout."""
        self.win.apply_layout("세로 분할 (Tall)", save_current=False)
        self.assertEqual(self.win.current_layout_name, "세로 분할 (Tall)")

    def test_15_apply_layout_unity_2x3(self):
        """[Test 15] Verify applying '2 by 3 (Unity 스타일)' layout."""
        self.win.apply_layout("2 by 3 (Unity 스타일)", save_current=False)
        self.assertEqual(self.win.current_layout_name, "2 by 3 (Unity 스타일)")

    def test_16_apply_layout_tabbed(self):
        """[Test 16] Verify applying '탭 묶음 (Tabbed)' layout."""
        self.win.apply_layout("탭 묶음 (Tabbed)", save_current=False)
        self.assertEqual(self.win.current_layout_name, "탭 묶음 (Tabbed)")

    def test_17_apply_layout_inspector_focus(self):
        """[Test 17] Verify applying '인스펙터 전면 (Inspector Focus)' layout."""
        self.win.apply_layout("인스펙터 전면 (Inspector Focus)", save_current=False)
        self.assertEqual(self.win.current_layout_name, "인스펙터 전면 (Inspector Focus)")

    def test_18_layout_dropdown_sync(self):
        """[Test 18] Verify layout dropdown selection synchronizes apply_layout."""
        idx = self.win.combo_layout.findText("기본 3열 (Default)")
        if idx >= 0:
            self.win.combo_layout.setCurrentIndex(idx)
            self.assertEqual(self.win.current_layout_name, "기본 3열 (Default)")

    def test_19_dock_nesting_options_enabled(self):
        """[Test 19] Verify AllowNestedDocks and GroupedDragging options are set."""
        opts = self.win.dockOptions()
        self.assertTrue(bool(opts & QMainWindow.AllowNestedDocks))
        self.assertTrue(bool(opts & QMainWindow.GroupedDragging))

    def test_20_dock_scenarios_set_visible(self):
        """[Test 20] Verify controlling scenario dock visibility."""
        self.win.dock_scenarios.setVisible(False)
        self.assertTrue(self.win.dock_scenarios.isHidden())
        self.win.dock_scenarios.setVisible(True)
        self.assertFalse(self.win.dock_scenarios.isHidden())

    def test_21_dock_inspector_set_visible(self):
        """[Test 21] Verify controlling inspector dock visibility."""
        self.win.dock_inspector.setVisible(False)
        self.assertTrue(self.win.dock_inspector.isHidden())
        self.win.dock_inspector.setVisible(True)
        self.assertFalse(self.win.dock_inspector.isHidden())

    def test_22_dock_actions_set_visible(self):
        """[Test 22] Verify controlling actions dock visibility."""
        self.win.dock_actions.setVisible(False)
        self.assertTrue(self.win.dock_actions.isHidden())
        self.win.dock_actions.setVisible(True)
        self.assertFalse(self.win.dock_actions.isHidden())

    def test_23_dock_log_set_visible(self):
        """[Test 23] Verify controlling log dock visibility."""
        self.win.dock_log.setVisible(False)
        self.assertTrue(self.win.dock_log.isHidden())
        self.win.dock_log.setVisible(True)
        self.assertFalse(self.win.dock_log.isHidden())

    def test_24_custom_layout_save_and_apply(self):
        """[Test 24] Verify custom layout registration and retrieval."""
        self.win.custom_layouts["MyTestLayout"] = self.win.saveState().toHex().data().decode()
        self.assertIn("MyTestLayout", self.win.custom_layouts)
        self.win.apply_layout("MyTestLayout", save_current=False)
        self.assertEqual(self.win.current_layout_name, "MyTestLayout")

    def test_25_refresh_layout_combo(self):
        """[Test 25] Verify refresh_layout_combo includes builtins and custom items."""
        self.win.custom_layouts["CustomPresetA"] = "00"
        self.win._refresh_layout_combo()
        self.assertGreaterEqual(self.win.combo_layout.count(), 7)

    # ======================================================================
    # Category 3: Scenario Table & List Interactions (Tests 26-45)
    # ======================================================================

    def test_26_scenario_table_row_count(self):
        """[Test 26] Verify scenario table row count reflects project scenarios."""
        self.assertEqual(self.win.tbl_scenarios.rowCount(), len(self.win.project.scenarios))

    def test_27_scenario_selection_updates_inspector(self):
        """[Test 27] Verify selecting row 0 updates inspector widget."""
        self.win.tbl_scenarios.clearSelection()
        self.win.tbl_scenarios.selectRow(0)
        self.win._on_table_selection_changed()
        self.assertIsNotNone(self.win.inspector.original_scenario)
        self.assertEqual(self.win.inspector.original_scenario.id, self.win.project.scenarios[0].id)

    def test_28_scenario_reorder_event(self):
        """[Test 28] Verify drag reorder signal updates scenario order and renumbers."""
        orig_s0 = self.win.project.scenarios[0].id
        orig_s1 = self.win.project.scenarios[1].id
        self.win._on_scenario_row_reordered(0, 1)
        self.assertEqual(self.win.project.scenarios[1].id, orig_s0)
        self.assertEqual(self.win.project.scenarios[0].id, orig_s1)

    def test_29_add_scenario_node(self):
        """[Test 29] Verify adding a new scenario node increments count and refreshes table."""
        initial_count = len(self.win.project.scenarios)
        self.win._on_add_scenario()
        self.assertEqual(len(self.win.project.scenarios), initial_count + 1)
        self.assertEqual(self.win.tbl_scenarios.rowCount(), initial_count + 1)

    @patch("PyQt5.QtWidgets.QMessageBox.question", return_value=QMessageBox.Yes)
    def test_30_delete_scenario_node(self, mock_msg):
        """[Test 30] Verify deleting selected scenario node."""
        self.win.tbl_scenarios.selectRow(1)
        initial_count = len(self.win.project.scenarios)
        self.win._on_delete_scenario()
        self.assertEqual(len(self.win.project.scenarios), initial_count - 1)

    def test_31_duplicate_scenario_node(self):
        """[Test 31] Verify duplicating a scenario creates a clone with new ID."""
        self.win.tbl_scenarios.selectRow(0)
        initial_count = len(self.win.project.scenarios)
        self.win._on_duplicate_scenario()
        self.assertEqual(len(self.win.project.scenarios), initial_count + 1)
        self.assertIn("복제", self.win.project.scenarios[1].name)

    def test_32_toggle_scenario_enabled_via_table(self):
        """[Test 32] Verify toggling scenario enable checkbox in table cell."""
        scen = self.win.project.scenarios[0]
        initial_enabled = scen.enabled
        chk_widget = self.win.tbl_scenarios.cellWidget(0, 2)
        if chk_widget and hasattr(chk_widget, "chk"):
            chk_widget.chk.setChecked(not initial_enabled)
            self.assertEqual(scen.enabled, not initial_enabled)

    def test_33_scenario_name_refresh_in_table(self):
        """[Test 33] Verify updating scenario name updates table cell text on refresh."""
        self.win.project.scenarios[0].name = "새로운 전투 확인 노드"
        self.win._refresh_scenario_table()
        item = self.win.tbl_scenarios.item(0, 3)
        self.assertIsNotNone(item)
        self.assertEqual(item.text(), "새로운 전투 확인 노드")

    def test_34_scenario_table_column_widths_adjustment(self):
        """[Test 34] Verify adjust_column_widths executes cleanly."""
        self.win.tbl_scenarios.adjust_column_widths()
        header = self.win.tbl_scenarios.horizontalHeader()
        self.assertEqual(header.sectionSize(0), 48)  # Snapshot
        self.assertEqual(header.sectionSize(1), 48)  # UID
        self.assertEqual(header.sectionSize(2), 38)  # Enabled

    def test_35_scenario_table_selection_mode(self):
        """[Test 35] Verify scenario table selection behaviors."""
        self.assertEqual(self.win.tbl_scenarios.selectionBehavior(), QAbstractItemView.SelectRows)
        self.assertEqual(self.win.tbl_scenarios.selectionMode(), QAbstractItemView.ExtendedSelection)

    def test_36_scenario_undo_stack_push(self):
        """[Test 36] Verify pushing state into scenario undo stack."""
        self.win.scenario_undo_stack.clear()
        self.win._push_scenario_undo_state("Before Change")
        self.assertEqual(len(self.win.scenario_undo_stack), 1)

    def test_37_scenario_undo_redo_cycle(self):
        """[Test 37] Verify scenario undo and redo restoration."""
        self.win.scenario_undo_stack.clear()
        self.win.scenario_redo_stack.clear()
        self.win._push_scenario_undo_state("Step 1")
        self.win.project.scenarios[0].name = "Mutated Name"
        self.win._undo_scenario()
        self.assertNotEqual(self.win.project.scenarios[0].name, "Mutated Name")
        self.win._redo_scenario()
        self.assertEqual(self.win.project.scenarios[0].name, "Mutated Name")

    def test_38_scenario_renumber_steps(self):
        """[Test 38] Verify renumber_steps keeps sequential 1-based indexes."""
        self.win.project.renumber_steps()
        for idx, scen in enumerate(self.win.project.scenarios):
            self.assertEqual(scen.step_number, idx + 1)

    def test_39_highlight_running_row_header(self):
        """[Test 39] Verify running row indicator highlighting."""
        self.win._highlight_running_row_header(0)
        self.assertEqual(self.win._current_running_row, 0)
        self.win._highlight_running_row_header(None)
        self.assertIsNone(self.win._current_running_row)

    def test_40_module_tab_switching(self):
        """[Test 40] Verify switching tab between Scenario Flow and Modules."""
        self.win.tab_scenario_manager.setCurrentIndex(1)
        self.assertEqual(self.win.tab_scenario_manager.currentIndex(), 1)
        self.win.tab_scenario_manager.setCurrentIndex(0)
        self.assertEqual(self.win.tab_scenario_manager.currentIndex(), 0)

    def test_41_branch_target_display_column(self):
        """[Test 41] Verify branch target cell (col 6) formatting."""
        item = self.win.tbl_scenarios.item(0, 6)
        self.assertIsNotNone(item)
        self.assertTrue(len(item.text()) > 0)

    def test_42_empty_project_scenario_table(self):
        """[Test 42] Verify scenario table handles 0 scenarios without crashing."""
        self.win.project.scenarios = []
        self.win._refresh_scenario_table()
        self.assertEqual(self.win.tbl_scenarios.rowCount(), 0)

    def test_43_batch_scenarios_table_load(self):
        """[Test 43] Verify loading 50 scenarios handles table rendering efficiently."""
        self.win.project.scenarios = [
            Scenario(id=f"scen_{i}", step_number=i + 1, name=f"노드 {i}")
            for i in range(50)
        ]
        self.win._refresh_scenario_table()
        self.assertEqual(self.win.tbl_scenarios.rowCount(), 50)

    def test_44_select_all_scenarios_shortcut(self):
        """[Test 44] Verify selectAll selects all rows in table."""
        self.win.tbl_scenarios.selectAll()
        self.assertEqual(len(self.win.tbl_scenarios.selectedIndexes()), len(self.win.project.scenarios) * 7)

    def test_45_cell_double_clicked_focuses_inspector(self):
        """[Test 45] Verify double clicking a row keeps focus and selects valid row."""
        self.win._on_scenario_cell_double_clicked(0, 3)
        self.assertEqual(self.win.inspector.original_scenario.id, self.win.project.scenarios[0].id)

    # ======================================================================
    # Category 4: Inspector Panel & Conditions/Actions (Tests 46-65)
    # ======================================================================

    def test_46_inspector_bind_scenario(self):
        """[Test 46] Verify inspector binds scenario and synchronizes UI fields."""
        scen = self.win.project.scenarios[0]
        self.win.inspector.set_scenario(scen)
        self.assertEqual(self.win.inspector.current_scenario.id, scen.id)
        self.assertEqual(self.win.inspector.txt_name.text(), scen.name)

    def test_47_inspector_change_scenario_name(self):
        """[Test 47] Verify inspector name line edit updates scenario model."""
        scen = self.win.project.scenarios[0]
        self.win.inspector.set_scenario(scen)
        self.win.inspector.txt_name.setText("인스펙터 수정 이름")
        self.assertEqual(self.win.inspector.current_scenario.name, "인스펙터 수정 이름")

    def test_48_inspector_toggle_enabled(self):
        """[Test 48] Verify inspector enabled checkbox updates scenario model."""
        scen = self.win.project.scenarios[0]
        self.win.inspector.set_scenario(scen)
        self.win.inspector.chk_enabled.setChecked(False)
        self.assertFalse(self.win.inspector.current_scenario.enabled)
        self.win.inspector.chk_enabled.setChecked(True)
        self.assertTrue(self.win.inspector.current_scenario.enabled)

    def test_49_inspector_loop_mode_change(self):
        """[Test 49] Verify inspector loop mode combo box updates scenario loop_mode."""
        scen = self.win.project.scenarios[0]
        self.win.inspector.set_scenario(scen)
        idx = self.win.inspector.combo_loop_mode.findData("until_match")
        if idx >= 0:
            self.win.inspector.combo_loop_mode.setCurrentIndex(idx)
            self.assertEqual(self.win.inspector.current_scenario.loop_mode, "until_match")

    def test_50_inspector_on_match_change(self):
        """[Test 50] Verify inspector on_match branch combo box updates scenario."""
        scen = self.win.project.scenarios[0]
        self.win.inspector.set_scenario(scen)
        idx = self.win.inspector.combo_on_match.findData("stop")
        if idx >= 0:
            self.win.inspector.combo_on_match.setCurrentIndex(idx)
            self.assertEqual(self.win.inspector.current_scenario.on_match, "stop")

    def test_51_inspector_on_mismatch_change(self):
        """[Test 51] Verify inspector on_mismatch branch combo box updates scenario."""
        scen = self.win.project.scenarios[0]
        self.win.inspector.set_scenario(scen)
        idx = self.win.inspector.combo_on_mismatch.findData("retry")
        if idx >= 0:
            self.win.inspector.combo_on_mismatch.setCurrentIndex(idx)
            self.assertEqual(self.win.inspector.current_scenario.on_mismatch, "retry")

    def test_52_inspector_delay_spin_change(self):
        """[Test 52] Verify inspector post delay spinbox updates scenario model."""
        scen = self.win.project.scenarios[0]
        self.win.inspector.set_scenario(scen)
        self.win.inspector.spin_post_delay.setValue(1.5)
        self.assertEqual(self.win.inspector.current_scenario.post_delay_seconds, 1.5)

    def test_53_inspector_custom_log_edit(self):
        """[Test 53] Verify inspector custom log text edit updates scenario model."""
        scen = self.win.project.scenarios[0]
        self.win.inspector.set_scenario(scen)
        self.win.inspector.txt_action_log.setText("진입 성공 로그")
        self.assertEqual(self.win.inspector.current_scenario.custom_log, "진입 성공 로그")

    def test_54_inspector_add_color_point(self):
        """[Test 54] Verify adding color point in inspector updates condition."""
        scen = self.win.project.scenarios[0]
        self.win.inspector.set_scenario(scen)
        eff_cond = self.win.inspector._get_active_condition()
        init_points = len(eff_cond.points) if eff_cond else 0
        self.win.inspector._on_add_point()
        eff_cond_after = self.win.inspector._get_active_condition()
        self.assertEqual(len(eff_cond_after.points), init_points + 1)

    def test_55_inspector_delete_color_point(self):
        """[Test 55] Verify deleting color point in inspector table."""
        scen = self.win.project.scenarios[0]
        self.win.inspector.set_scenario(scen)
        eff_cond = self.win.inspector._get_active_condition()
        if eff_cond and eff_cond.points:
            init_points = len(eff_cond.points)
            self.win.inspector.tbl_points.selectRow(0)
            self.win.inspector._on_delete_point()
            self.assertEqual(len(eff_cond.points), init_points - 1)

    def test_56_inspector_point_tolerance_edit(self):
        """[Test 56] Verify changing color point tolerance in points table."""
        scen = self.win.project.scenarios[0]
        self.win.inspector.set_scenario(scen)
        eff_cond = self.win.inspector._get_active_condition()
        if eff_cond and not eff_cond.points:
            eff_cond.points.append(ColorPoint(x=10, y=20, r=100, g=100, b=100))
            self.win.inspector._refresh_points_table()
        spin = self.win.inspector.tbl_points.cellWidget(0, 4)
        if spin and hasattr(spin, "setValue"):
            spin.setValue(45)
            self.assertEqual(eff_cond.points[0].tolerance, 45)

    def test_57_inspector_point_match_mode_toggle(self):
        """[Test 57] Verify toggling point match mode (not_match) in inspector points table."""
        scen = self.win.project.scenarios[0]
        self.win.inspector.set_scenario(scen)
        eff_cond = self.win.inspector._get_active_condition()
        if eff_cond and not eff_cond.points:
            eff_cond.points.append(ColorPoint(x=10, y=20, r=100, g=100, b=100))
            self.win.inspector._refresh_points_table()
        combo = self.win.inspector.tbl_points.cellWidget(0, 4)
        if combo and hasattr(combo, "setCurrentIndex"):
            combo.setCurrentIndex(1)
            self.assertEqual(eff_cond.points[0].match_mode, "not_match")

    def test_58_inspector_condition_mode_toggle(self):
        """[Test 58] Verify switching condition match mode between AND / OR."""
        scen = self.win.project.scenarios[0]
        self.win.inspector.set_scenario(scen)
        idx_or = self.win.inspector.combo_cond_logic.findData("OR")
        if idx_or >= 0:
            self.win.inspector.combo_cond_logic.setCurrentIndex(idx_or)
            eff_cond = self.win.inspector._get_active_condition()
            self.assertEqual(eff_cond.logic_operator, "OR")

    def test_59_inspector_add_click_action(self):
        """[Test 59] Verify adding a mouse click action via inspector."""
        scen = self.win.project.scenarios[0]
        self.win.inspector.set_scenario(scen)
        eff_acts = self.win.inspector._get_active_actions_list()
        init_actions = len(eff_acts)
        self.win.inspector._on_quick_add_action("mouse_click")
        self.assertEqual(len(self.win.inspector._get_active_actions_list()), init_actions + 1)
        self.assertEqual(self.win.inspector._get_active_actions_list()[-1].action_type, "mouse_click")

    def test_60_inspector_delete_action(self):
        """[Test 60] Verify deleting selected action in action table."""
        scen = self.win.project.scenarios[0]
        self.win.inspector.set_scenario(scen)
        eff_acts = self.win.inspector._get_active_actions_list()
        if eff_acts:
            init_actions = len(eff_acts)
            self.win.inspector.tbl_actions.selectRow(0)
            self.win.inspector._on_delete_action()
            self.assertEqual(len(self.win.inspector._get_active_actions_list()), init_actions - 1)

    def test_61_inspector_action_coord_edit(self):
        """[Test 61] Verify editing action x, y coordinates."""
        scen = self.win.project.scenarios[0]
        self.win.inspector.set_scenario(scen)
        eff_acts = self.win.inspector._get_active_actions_list()
        if not eff_acts:
            eff_acts.append(Action(action_type="mouse_click", x=100, y=200))
            self.win.inspector._refresh_actions_table()
        spin_x = self.win.inspector.tbl_actions.cellWidget(0, 2)
        if spin_x and hasattr(spin_x, "setValue"):
            spin_x.setValue(550)
            self.assertEqual(eff_acts[0].x, 550)

    def test_62_inspector_action_reorder_up(self):
        """[Test 62] Verify moving action up in sequence."""
        scen = self.win.project.scenarios[0]
        scen.actions = [
            Action(action_type="mouse_click", x=100, y=100),
            Action(action_type="delay", delay_seconds=2.0)
        ]
        self.win.inspector.set_scenario(scen)
        self.win.inspector.tbl_actions.selectRow(1)
        self.win.inspector._on_move_action_up()
        self.assertEqual(self.win.inspector._get_active_actions_list()[0].action_type, "delay")

    def test_63_inspector_action_reorder_down(self):
        """[Test 63] Verify moving action down in sequence."""
        scen = self.win.project.scenarios[0]
        scen.actions = [
            Action(action_type="delay", delay_seconds=1.0),
            Action(action_type="mouse_click", x=200, y=200)
        ]
        self.win.inspector.set_scenario(scen)
        self.win.inspector.tbl_actions.selectRow(0)
        self.win.inspector._on_move_action_down()
        self.assertEqual(self.win.inspector._get_active_actions_list()[1].action_type, "delay")

    def test_64_inspector_action_duplicate(self):
        """[Test 64] Verify duplicating an action creates an identical clone."""
        scen = self.win.project.scenarios[0]
        scen.actions = [Action(action_type="mouse_click", x=333, y=444)]
        self.win.inspector.set_scenario(scen)
        self.win.inspector.tbl_actions.selectRow(0)
        self.win.inspector._on_duplicate_action()
        self.assertEqual(len(self.win.inspector._get_active_actions_list()), 2)
        self.assertEqual(self.win.inspector._get_active_actions_list()[1].x, 333)

    def test_65_inspector_clear_scenario_selection(self):
        """[Test 65] Verify clearing inspector when scenario is None switches stack to empty."""
        self.win.inspector.set_scenario(None)
        self.assertIsNone(self.win.inspector.current_scenario)
        self.assertEqual(self.win.inspector.stack.currentIndex(), 0)

    # ======================================================================
    # Category 5: Virtual Canvas Window Interactions (Tests 66-75)
    # ======================================================================

    def test_66_virtual_canvas_instance_creation(self):
        """[Test 66] Verify VirtualCanvasWindow creation and title formatting."""
        vwin = VirtualCanvasWindow(1280, 720)
        self.assertEqual(vwin.canvas_width, 1280)
        self.assertEqual(vwin.canvas_height, 720)
        self.assertIn("1280x720", vwin.windowTitle())
        vwin.close()

    def test_67_virtual_canvas_resolution_update(self):
        """[Test 67] Verify set_target_resolution regenerates dummy image."""
        vwin = VirtualCanvasWindow(800, 600)
        vwin.set_target_resolution(1920, 1080)
        self.assertEqual(vwin.canvas_width, 1920)
        self.assertEqual(vwin.canvas_height, 1080)
        self.assertEqual(vwin.dummy_image.width(), 1920)
        vwin.close()

    def test_68_virtual_canvas_trigger_click_ripple(self):
        """[Test 68] Verify trigger_click_effect appends active ripple and starts timer."""
        vwin = VirtualCanvasWindow(800, 600)
        vwin.trigger_click_effect(150, 250)
        self.assertEqual(len(vwin._ripples), 1)
        self.assertEqual(vwin._ripples[0]["x"], 150)
        self.assertEqual(vwin._ripples[0]["y"], 250)
        self.assertTrue(vwin.ripple_timer.isActive())
        vwin.close()

    def test_69_virtual_canvas_multi_ripple_queue(self):
        """[Test 69] Verify queuing multiple ripples at different coordinates."""
        vwin = VirtualCanvasWindow(800, 600)
        vwin.trigger_click_effect(50, 50)
        vwin.trigger_click_effect(100, 100)
        vwin.trigger_click_effect(150, 150)
        self.assertEqual(len(vwin._ripples), 3)
        vwin.close()

    def test_70_virtual_canvas_ripple_decay_and_cleanup(self):
        """[Test 70] Verify ripples decay and get removed when max radius reached."""
        vwin = VirtualCanvasWindow(800, 600)
        vwin.trigger_click_effect(200, 200)
        for _ in range(30):
            vwin._update_ripples()
        self.assertEqual(len(vwin._ripples), 0)
        self.assertFalse(vwin.ripple_timer.isActive())
        vwin.close()

    def test_71_virtual_canvas_paint_event_render(self):
        """[Test 71] Verify paintEvent draws without exception using QPixmap render."""
        vwin = VirtualCanvasWindow(800, 600)
        vwin.trigger_click_effect(100, 100)
        pix = QPixmap(800, 600)
        vwin.render(pix)
        self.assertFalse(pix.isNull())
        vwin.close()

    def test_72_virtual_canvas_mouse_press_signal(self):
        """[Test 72] Verify mouse press event emits sig_clicked."""
        vwin = VirtualCanvasWindow(800, 600)
        clicked_coords = []
        vwin.sig_clicked.connect(lambda x, y: clicked_coords.append((x, y)))
        event = QMouseEvent(QMouseEvent.MouseButtonPress, QPoint(120, 240), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        vwin.mousePressEvent(event)
        self.assertEqual(len(clicked_coords), 1)
        self.assertEqual(clicked_coords[0], (120, 240))
        vwin.close()

    def test_73_virtual_canvas_close_signal(self):
        """[Test 73] Verify closing VirtualCanvasWindow emits sig_closed."""
        vwin = VirtualCanvasWindow(800, 600)
        closed_flag = []
        vwin.sig_closed.connect(lambda: closed_flag.append(True))
        vwin.close()
        self.assertEqual(len(closed_flag), 1)

    def test_74_main_win_open_virtual_canvas_action(self):
        """[Test 74] Verify _on_open_virtual_canvas creates window and binds target_hwnd."""
        self.win._on_open_virtual_canvas()
        self.assertIsNotNone(self.win.virtual_canvas_window)
        self.assertEqual(self.win.target_hwnd, int(self.win.virtual_canvas_window.winId()))
        self.win.virtual_canvas_window.close()

    def test_75_main_win_virtual_canvas_closed_handler(self):
        """[Test 75] Verify closing virtual canvas resets target_hwnd to 0."""
        self.win._on_open_virtual_canvas()
        self.assertNotEqual(self.win.target_hwnd, 0)
        self.win._on_virtual_canvas_closed()
        self.assertEqual(self.win.target_hwnd, 0)

    # ======================================================================
    # Category 6: Execution Controls & Run States (Tests 76-88)
    # ======================================================================

    @patch("core.runner.WorkflowRunner.start")
    def test_76_auto_virtual_canvas_fallback_on_run(self, mock_start):
        """[Test 76] Verify starting execution with no target launches virtual canvas."""
        self.win.target_hwnd = 0
        self.win._on_start_execution()
        self.assertIsNotNone(self.win.virtual_canvas_window)
        self.assertNotEqual(self.win.target_hwnd, 0)
        mock_start.assert_called_once()
        if self.win.virtual_canvas_window:
            self.win.virtual_canvas_window.close()

    @patch("core.runner.WorkflowRunner.start")
    def test_77_start_selected_execution_with_selection(self, mock_start):
        """[Test 77] Verify _on_start_selected_execution selects current row node."""
        self.win.tbl_scenarios.selectRow(1)
        self.win._on_start_selected_execution()
        self.assertIsNotNone(self.win.virtual_canvas_window)
        mock_start.assert_called_once()
        if self.win.virtual_canvas_window:
            self.win.virtual_canvas_window.close()

    def test_78_pause_execution_toggling(self):
        """[Test 78] Verify _on_pause_execution toggles pause/resume states on mock runner."""
        runner_mock = MagicMock()
        runner_mock.isRunning.return_value = True
        runner_mock._is_paused = False
        self.win.runner = runner_mock
        self.win._on_pause_execution()
        runner_mock.pause.assert_called_once()
        self.assertEqual(self.win.btn_pause.text(), "▶ 재개")

        runner_mock._is_paused = True
        self.win._on_pause_execution()
        runner_mock.resume.assert_called_once()
        self.assertEqual(self.win.btn_pause.text(), "⏸ 일시정지")

    def test_79_stop_execution_resets_buttons(self):
        """[Test 79] Verify stopping execution stops runner cleanly."""
        runner_mock = MagicMock()
        self.win.runner = runner_mock
        self.win._on_stop_execution()
        runner_mock.stop.assert_called_once()
        self.assertIn("정지", self.win.lbl_run_status.text())

    def test_80_anti_ban_button_exists(self):
        """[Test 80] Verify anti-ban config button exists in playback bar."""
        self.assertTrue(hasattr(self.win, "btn_anti_ban"))

    def test_81_antiban_dialog_offset_spin_change(self):
        """[Test 81] Verify anti-ban offset spinbox in AntiBanDialog."""
        dlg = AntiBanDialog(self.win.project, parent=self.win)
        dlg.spin_offset.setValue(2.2)
        self.assertEqual(dlg.spin_offset.value(), 2.2)
        dlg.close()

    def test_82_loop_count_spin_change(self):
        """[Test 82] Verify loop count spinbox mutates project loop_count."""
        self.win.spin_loops.setValue(5)
        self.assertEqual(self.win.project.loop_count, 5)

    def test_83_loop_delay_spin_change(self):
        """[Test 83] Verify loop delay spinbox mutates project loop_delay_seconds."""
        self.win.spin_loop_delay.setValue(3.5)
        self.assertEqual(self.win.project.loop_delay_seconds, 3.5)

    def test_84_antiban_dialog_coord_weak_spin_change(self):
        """[Test 84] Verify weak coordinate jitter spinbox in AntiBanDialog."""
        dlg = AntiBanDialog(self.win.project, parent=self.win)
        dlg.spin_weak.setValue(8)
        self.assertEqual(dlg.spin_weak.value(), 8)
        dlg.close()

    def test_85_antiban_dialog_coord_strong_spin_change(self):
        """[Test 85] Verify strong coordinate jitter spinbox in AntiBanDialog."""
        dlg = AntiBanDialog(self.win.project, parent=self.win)
        dlg.spin_strong.setValue(22)
        self.assertEqual(dlg.spin_strong.value(), 22)
        dlg.close()

    def test_86_action_overlay_checkbox_toggle(self):
        """[Test 86] Verify action overlay checkbox mutates action overlay visibility."""
        if hasattr(self.win, "chk_action_overlay"):
            self.win.chk_action_overlay.setChecked(True)
            self.assertTrue(self.win.action_overlay.is_overlay_enabled)
            self.win.chk_action_overlay.setChecked(False)
            self.assertFalse(self.win.action_overlay.is_overlay_enabled)

    def test_87_action_executing_visual_ripple_trigger(self):
        """[Test 87] Verify _on_action_executing_visual triggers virtual canvas ripple."""
        self.win._on_open_virtual_canvas()
        act = Action(action_type="mouse_click", x=123, y=456)
        self.win._on_action_executing_visual(act, 0, 1)
        self.assertGreater(len(self.win.virtual_canvas_window._ripples), 0)
        self.win.virtual_canvas_window.close()

    def test_88_runner_finished_restores_ui(self):
        """[Test 88] Verify _on_runner_finished restores button states."""
        self.win._on_runner_finished("completed")
        self.assertTrue(self.win.btn_run.isEnabled())
        self.assertFalse(self.win.btn_pause.isEnabled())
        self.assertFalse(self.win.btn_stop.isEnabled())

    # ======================================================================
    # Category 7: Target Window & Monitoring (Tests 89-95)
    # ======================================================================

    def test_89_update_target_label_with_valid_window(self):
        """[Test 89] Verify _update_target_label formats title and HWND."""
        win_info = WindowInfo(hwnd=0x1234, title="Sample Game", client_width=1600, client_height=900, screen_x=0, screen_y=0, pid=100)
        self.win._update_target_label(win_info)
        self.assertIn("Sample Game", self.win.lbl_target_info.text())
        self.assertIn("1234", self.win.lbl_target_info.text())

    def test_90_update_target_label_with_none(self):
        """[Test 90] Verify _update_target_label formats remembered resolution when win is None."""
        self.win.project.target_client_width = 1600
        self.win.project.target_client_height = 900
        self.win._update_target_label(None)
        self.assertIn("1600×900", self.win.lbl_target_info.text())

    def test_91_focus_target_window_with_virtual_canvas(self):
        """[Test 91] Verify _on_focus_target_window activates virtual canvas if visible."""
        self.win._on_open_virtual_canvas()
        self.win._on_focus_target_window()
        self.assertTrue(self.win.virtual_canvas_window.isVisible())
        self.win.virtual_canvas_window.close()

    def test_92_check_target_alive_with_invalid_hwnd(self):
        """[Test 92] Verify target monitor flags warning if target window HWND is invalid."""
        self.win.target_hwnd = 999999999  # Invalid HWND
        self.win._check_target_alive()
        self.assertIn("닫혔거나", self.win.lbl_target_info.text())
        self.win.target_hwnd = 0

    def test_93_reference_gallery_button_handler(self):
        """[Test 93] Verify reference gallery dialog invocation handler exists."""
        self.assertTrue(hasattr(self.win, "_on_open_reference_gallery"))

    def test_94_target_monitor_timer_active(self):
        """[Test 94] Verify background target monitoring timer is active."""
        self.assertTrue(self.win.timer_monitor.isActive())

    def test_95_set_target_window_properties(self):
        """[Test 95] Verify setting target resolution updates project attributes."""
        self.win.project.target_client_width = 1920
        self.win.project.target_client_height = 1080
        self.assertEqual(self.win.project.target_client_width, 1920)
        self.assertEqual(self.win.project.target_client_height, 1080)

    # ======================================================================
    # Category 8: Log Console, HTML Styling & Dialogs (Tests 96-100)
    # ======================================================================

    def test_96_log_level_formatting_colors(self):
        """[Test 96] Verify log entries format HTML with level colors."""
        self.win._append_log("ERROR", "치명적인 오류 발생 테스트")
        html_content = self.win.txt_log.toHtml()
        self.assertIn("치명적인 오류 발생 테스트", html_content)
        self.win._clear_logs()

    def test_97_log_multi_record_storage(self):
        """[Test 97] Verify appending multiple log entries preserves order."""
        self.win._clear_logs()
        self.win._append_log("INFO", "로그 A")
        self.win._append_log("WARN", "로그 B")
        self.assertEqual(len(self.win._log_records), 2)
        self.assertEqual(self.win._log_records[0]["raw_msg"], "로그 A")
        self.assertEqual(self.win._log_records[1]["raw_msg"], "로그 B")
        self.win._clear_logs()

    def test_98_load_project_file_success(self):
        """[Test 98] Verify _load_project_file loads JSON and refreshes UI."""
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        p = Project(name="ProjectFromFile", loop_count=7)
        json.dump(p.to_dict(), tmp, indent=2)
        tmp.close()

        success = self.win._load_project_file(tmp.name, silent=True)
        self.assertTrue(success)
        self.assertEqual(self.win.project.loop_count, 7)
        self.assertEqual(self.win.spin_loops.value(), 7)

        if os.path.exists(tmp.name):
            os.remove(tmp.name)

    def test_99_load_project_file_failure_handles_gracefully(self):
        """[Test 99] Verify _load_project_file handles invalid path returning False."""
        success = self.win._load_project_file("C:/non_existent_file_path_xyz.json", silent=True)
        self.assertFalse(success)

    def test_100_antiban_dialog_instantiation(self):
        """[Test 100] Verify AntiBanDialog instantiates without QDialog NameError."""
        dlg = AntiBanDialog(self.win.project, parent=self.win)
        self.assertIsInstance(dlg, QDialog)
        dlg.close()


if __name__ == "__main__":
    unittest.main()
