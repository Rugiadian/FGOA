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

        expected_headers = ["스냅샷", "고유 ID", "활성", "시나리오 이름", "인식조건 모듈", "액션시퀀스 모듈", "분기"]
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
        # Compact columns: 0 (48 for snapshot), 1 (48), 2 (38)
        self.assertEqual(header.sectionSize(0), 48)
        self.assertEqual(header.sectionSize(1), 48)
        self.assertEqual(header.sectionSize(2), 38)

        # Dynamic columns: 3 (name), 4 (cond), 5 (seq), 6 (branch)
        w3 = header.sectionSize(3)
        w4 = header.sectionSize(4)
        w5 = header.sectionSize(5)
        w6 = header.sectionSize(6)
        self.assertGreater(w3, 70)
        self.assertGreater(w4, 70)
        self.assertGreater(w5, 70)
        self.assertGreater(w6, 50)

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

    def test_scenario_node_snapshot_default_and_blank(self):
        import tempfile
        import os
        from PIL import Image

        # 1. Scenario with condition having reference image
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name
        img = Image.new("RGB", (100, 100), color=(255, 0, 0))
        img.save(tmp_path)

        try:
            cond = Condition(name="테스트조건", reference_image_path=tmp_path)
            scen_with_img = Scenario(name="조건이미지보유", condition=cond)
            self.assertEqual(scen_with_img.get_effective_reference_image(), tmp_path)

            # Test inspector snapshot loading
            self.inspector.set_scenario(scen_with_img, target_hwnd=0, project=self.main_win.project)
            self.assertEqual(self.inspector.lbl_node_snapshot.image_path, tmp_path)

            # 2. Scenario without reference image -> must be blank
            scen_blank = Scenario(name="이미지없음")
            self.assertIsNone(scen_blank.get_effective_reference_image())
            self.inspector.set_scenario(scen_blank, target_hwnd=0, project=self.main_win.project)
            self.assertIsNone(self.inspector.lbl_node_snapshot.image_path)
            self.assertEqual(self.inspector.lbl_node_snapshot.text(), "빈칸")

            # 3. Test scenario table row updating
            self.main_win.project.scenarios = [scen_with_img, scen_blank]
            self.main_win._refresh_scenario_table()

            # Row 0 has widget (snapshot thumbnail)
            self.assertIsNotNone(self.main_win.tbl_scenarios.cellWidget(0, 0))
            # Row 1 has empty item (blank)
            item_blank = self.main_win.tbl_scenarios.item(1, 0)
            self.assertIsNotNone(item_blank)
            self.assertEqual(item_blank.text(), "")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


if __name__ == "__main__":
    unittest.main()
