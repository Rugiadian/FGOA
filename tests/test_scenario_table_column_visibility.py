"""
Tests for Scenario Table Column Visibility (View/Hide Condition, Action Sequence, Branch columns).
"""
import unittest
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from ui.main_window import MainWindow
from ui.scenario_table_widget import (
    DraggableScenarioTableWidget,
    COL_CONDITION, COL_ACTION, COL_BRANCH, COL_NAME,
    TOGGLEABLE_COLUMNS
)

app = QApplication.instance()
if not app:
    app = QApplication([])


class TestScenarioTableColumnVisibility(unittest.TestCase):
    def setUp(self):
        self.main_win = MainWindow()
        self.table = self.main_win.tbl_scenarios
        self.table.show_all_columns()

    def tearDown(self):
        self.table.show_all_columns()
        self.main_win._save_app_config()
        self.main_win.close()

    def test_default_visibility(self):
        """Verify that condition, action sequence, and branch columns are visible by default."""
        for col_idx, _ in TOGGLEABLE_COLUMNS:
            self.assertTrue(self.table.is_column_visible(col_idx))
            self.assertFalse(self.table.isColumnHidden(col_idx))

    def test_toggle_column_visibility_and_signal(self):
        """Verify hiding and showing columns emits the correct signal and updates column state."""
        received_signals = []
        self.table.sig_column_visibility_changed.connect(
            lambda col, vis: received_signals.append((col, vis))
        )

        # Hide Condition column (4)
        self.table.set_column_visible(COL_CONDITION, False)
        self.assertFalse(self.table.is_column_visible(COL_CONDITION))
        self.assertTrue(self.table.isColumnHidden(COL_CONDITION))
        self.assertEqual(received_signals[-1], (COL_CONDITION, False))

        # Show Condition column (4)
        self.table.set_column_visible(COL_CONDITION, True)
        self.assertTrue(self.table.is_column_visible(COL_CONDITION))
        self.assertFalse(self.table.isColumnHidden(COL_CONDITION))
        self.assertEqual(received_signals[-1], (COL_CONDITION, True))

    def test_hide_all_toggleable_columns_adjusts_width(self):
        """Verify that when condition, action, and branch are hidden, scenario name expands to fill available width."""
        self.table.resize(800, 400)
        self.table.adjust_column_widths()

        # Hide columns 4, 5, 6
        self.table.set_column_visible(COL_CONDITION, False)
        self.table.set_column_visible(COL_ACTION, False)
        self.table.set_column_visible(COL_BRANCH, False)

        header = self.table.horizontalHeader()
        w_name = header.sectionSize(COL_NAME)

        # Scenario name should take all remaining width (viewport.width() - fixed columns)
        expected_rem = self.table.viewport().width() - (48 + 48 + 38)
        self.assertEqual(w_name, expected_rem)
        self.assertGreater(w_name, 400)

        # Restore all columns
        self.table.show_all_columns()
        for col_idx, _ in TOGGLEABLE_COLUMNS:
            self.assertTrue(self.table.is_column_visible(col_idx))

    def test_column_visibility_menu_creation_and_actions(self):
        """Verify column visibility menu actions toggle table columns correctly."""
        menu = self.table.create_column_visibility_menu()
        actions = menu.actions()

        # Should have 3 toggleable actions + separator + show all action
        toggle_actions = [a for a in actions if a.isCheckable()]
        self.assertEqual(len(toggle_actions), 3)

        # Uncheck first toggle action (Condition)
        act_cond = toggle_actions[0]
        self.assertEqual(act_cond.data(), COL_CONDITION)
        self.assertTrue(act_cond.isChecked())

        act_cond.setChecked(False)
        self.assertFalse(self.table.is_column_visible(COL_CONDITION))

        act_cond.setChecked(True)
        self.assertTrue(self.table.is_column_visible(COL_CONDITION))

    def test_state_export_and_import(self):
        """Verify column visibility dictionary export and import."""
        self.table.set_column_visible(COL_CONDITION, False)
        self.table.set_column_visible(COL_ACTION, True)
        self.table.set_column_visible(COL_BRANCH, False)

        state = self.table.get_column_visibility_state()
        self.assertFalse(state[str(COL_CONDITION)])
        self.assertTrue(state[str(COL_ACTION)])
        self.assertFalse(state[str(COL_BRANCH)])

        # Test restoring from friendly name state
        new_state = {
            "condition": True,
            "action": False,
            "branch": True,
        }
        self.table.set_column_visibility_state(new_state)
        self.assertTrue(self.table.is_column_visible(COL_CONDITION))
        self.assertFalse(self.table.is_column_visible(COL_ACTION))
        self.assertTrue(self.table.is_column_visible(COL_BRANCH))

    def test_toolbar_button_and_apply_ui_config(self):
        """Verify toolbar button exists with menu and _apply_ui_config restores column settings."""
        self.assertTrue(hasattr(self.main_win, "btn_col_visibility"))
        self.assertIsNotNone(self.main_win.btn_col_visibility.menu())

        # Test applying from config dict
        cfg = {
            "scenario_columns_visible": {
                "condition": False,
                "action": False,
                "branch": False,
            }
        }
        self.main_win._apply_ui_config(cfg)
        self.assertFalse(self.table.is_column_visible(COL_CONDITION))
        self.assertFalse(self.table.is_column_visible(COL_ACTION))
        self.assertFalse(self.table.is_column_visible(COL_BRANCH))


if __name__ == "__main__":
    unittest.main()
