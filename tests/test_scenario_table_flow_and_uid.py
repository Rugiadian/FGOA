"""
Tests for Scenario Table responsive layout, Toolbar FlowLayout, and 's' unique ID prefixes.
"""
import unittest
from PyQt5.QtWidgets import QApplication, QHeaderView, QWidget
from PyQt5.QtCore import QSize, QRect
from core.models import Project, Scenario, Action, Condition, ColorPoint
from ui.main_window import MainWindow, DraggableScenarioTableWidget
from ui.inspector_widget import InspectorWidget
from ui.widgets.flow_layout import FlowLayout

# Ensure QApplication exists
app = QApplication.instance()
if not app:
    app = QApplication([])


class TestScenarioTableFlowAndUID(unittest.TestCase):
    def setUp(self):
        self.main_win = MainWindow()
        self.inspector = self.main_win.inspector

    def test_scenario_table_headers_and_resize_modes(self):
        table = self.main_win.tbl_scenarios
        self.assertEqual(table.columnCount(), 7)

        expected_headers = ["순서", "고유 ID", "활성", "시나리오 이름", "인식 조건 (Eye)", "분기 (일치/불일치)", "액션"]
        headers = [table.horizontalHeaderItem(i).text() for i in range(7)]
        self.assertEqual(headers, expected_headers)

        header = table.horizontalHeader()
        for i in range(7):
            self.assertEqual(header.sectionResizeMode(i), QHeaderView.Interactive, f"Column {i} must be Interactive")

    def test_scenario_table_dynamic_proportions(self):
        table = self.main_win.tbl_scenarios
        table.resize(800, 400)
        table.adjust_column_widths()

        header = table.horizontalHeader()
        # Compact columns: 0 (34), 1 (48), 2 (38), 6 (44)
        self.assertEqual(header.sectionSize(0), 34)
        self.assertEqual(header.sectionSize(1), 48)
        self.assertEqual(header.sectionSize(2), 38)
        self.assertEqual(header.sectionSize(6), 44)

        # Dynamic columns: 3 (name), 4 (cond), 5 (branch)
        w3 = header.sectionSize(3)
        w4 = header.sectionSize(4)
        w5 = header.sectionSize(5)
        self.assertGreater(w3, 100)
        self.assertGreater(w4, 90)
        self.assertGreater(w5, 70)

    def test_scenario_uid_s_prefix_formatting(self):
        proj = Project()
        s1 = Scenario(id="scen_1", name="첫번째 시나리오", scenario_number=1, step_number=1)
        s2 = Scenario(id="scen_2", name="두번째 시나리오", scenario_number=2, step_number=2)
        proj.scenarios = [s1, s2]

        self.main_win.project = proj
        self.main_win._refresh_scenario_table()

        table = self.main_win.tbl_scenarios
        self.assertEqual(table.rowCount(), 2)

        # Col 1: UID with 's' prefix
        item_s1 = table.item(0, 1)
        self.assertEqual(item_s1.text(), "s1")
        self.assertIn("s1", item_s1.toolTip())

        item_s2 = table.item(1, 1)
        self.assertEqual(item_s2.text(), "s2")
        self.assertIn("s2", item_s2.toolTip())

    def test_inspector_scenario_number_spinbox_prefix(self):
        scen = Scenario(id="scen_test", name="테스트", scenario_number=7)
        self.inspector.set_scenario(scen, target_hwnd=0, project=self.main_win.project)

        self.assertEqual(self.inspector.spin_scen_num.prefix(), "s")
        self.assertEqual(self.inspector.spin_scen_num.value(), 7)
        self.assertIn("고유 s7", self.inspector.lbl_inspector_status.text())

    def test_inspector_jump_target_combo_prefix(self):
        proj = Project()
        s1 = Scenario(id="scen_1", name="시나리오1", scenario_number=1, step_number=1)
        s2 = Scenario(id="scen_2", name="시나리오2", scenario_number=2, step_number=2)
        proj.scenarios = [s1, s2]

        self.inspector.set_scenario(s1, target_hwnd=0, project=proj)
        combo = self.inspector.combo_jump_match
        items = [combo.itemText(i) for i in range(combo.count())]
        self.assertTrue(any("고유 s2" in it for it in items), f"Expected '고유 s2' in combo items: {items}")

    def test_toolbar_flow_layout_wrapping(self):
        from PyQt5.QtWidgets import QPushButton
        container = QWidget()
        flow = FlowLayout(container, margin=0, spacing=4)
        for i in range(12):
            flow.addWidget(QPushButton(f"Button {i}"))

        # In narrow width (200px), height must be significantly greater than in wide width (800px)
        h_narrow = flow.heightForWidth(200)
        h_wide = flow.heightForWidth(800)
        self.assertGreater(h_narrow, h_wide, "FlowLayout should wrap items into more vertical rows when narrow")


if __name__ == "__main__":
    unittest.main()
