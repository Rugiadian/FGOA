import unittest
from PyQt5.QtWidgets import QApplication, QHeaderView, QComboBox, QDoubleSpinBox, QLineEdit, QPushButton
from core.models import Scenario, Action
from ui.inspector_widget import InspectorWidget
from ui.action_editor_dialog import SingleActionDialog

# Ensure QApplication exists
app = QApplication.instance()
if not app:
    app = QApplication([])

class TestInspectorActionTable(unittest.TestCase):
    def setUp(self):
        self.inspector = InspectorWidget()

    def test_table_headers_and_resize_mode(self):
        table = self.inspector.tbl_actions
        self.assertEqual(table.columnCount(), 6)
        
        headers = [table.horizontalHeaderItem(i).text() for i in range(6)]
        expected_headers = ["#", "액션 유형", "좌표 / 키 / 텍스트", "오프셋", "대기", "로그"]
        self.assertEqual(headers, expected_headers)
        
        self.assertTrue(table.wordWrap(), "Table should have wordWrap enabled")
        
        hdr = table.horizontalHeader()
        for i in range(6):
            self.assertEqual(hdr.sectionResizeMode(i), QHeaderView.Interactive, f"Column {i} must be Interactive")

    def test_refresh_actions_table_content_and_inline_widgets(self):
        scen = Scenario(name="테스트 시나리오")
        
        # 1. Left click (weak)
        act1 = Action(
            action_type="mouse_click",
            x=100, y=200,
            mouse_button="left",
            click_type="single",
            coord_anti_ban="weak",
            delay_seconds=0.5,
            custom_log="첫번째 클릭"
        )
        # 2. Right double click (strong)
        act2 = Action(
            action_type="mouse_click",
            x=300, y=400,
            mouse_button="right",
            click_type="double",
            coord_anti_ban="strong",
            delay_seconds=0.0
        )
        # 3. Mouse drag (none)
        act3 = Action(
            action_type="mouse_drag",
            x=10, y=20,
            end_x=100, end_y=200,
            drag_duration_ms=450,
            coord_anti_ban="none",
            delay_seconds=1.2,
            custom_log="드래그 이동"
        )
        # 4. Key combo
        act4 = Action(
            action_type="key_press",
            key="c",
            modifiers=["ctrl"],
            delay_seconds=0.1
        )
        # 5. Log message
        act5 = Action(
            action_type="log_message",
            log_text="시스템 상태 정상",
            delay_seconds=0.0
        )

        scen.actions = [act1, act2, act3, act4, act5]
        self.inspector.set_scenario(scen)
        
        table = self.inspector.tbl_actions
        self.assertEqual(table.rowCount(), 5)
        
        # Row 0: act1 (a1)
        self.assertEqual(table.item(0, 0).text(), "a1")
        self.assertEqual(table.item(0, 1).text(), "🖱️ 좌클릭")
        self.assertEqual(table.item(0, 2).text(), "(100, 200)")
        self.assertEqual(table.item(0, 3).text(), "약")
        self.assertEqual(table.item(0, 4).text(), "0.5s")
        self.assertEqual(table.item(0, 5).text(), "첫번째 클릭")

        # Row 1: act2 (a2)
        self.assertEqual(table.item(1, 0).text(), "a2")
        self.assertEqual(table.item(1, 1).text(), "🖱️ 더블우클릭")
        self.assertEqual(table.item(1, 2).text(), "(300, 400)")
        self.assertEqual(table.item(1, 3).text(), "강")
        self.assertEqual(table.item(1, 4).text(), "-")
        self.assertEqual(table.item(1, 5).text(), "-")

        # Row 2: act3 (a3)
        self.assertEqual(table.item(2, 0).text(), "a3")
        self.assertEqual(table.item(2, 1).text(), "↔️ 드래그(450ms)")
        self.assertEqual(table.item(2, 2).text(), "(10, 20) ➔ (100, 200)")
        self.assertEqual(table.item(2, 3).text(), "해제")
        self.assertEqual(table.item(2, 4).text(), "1.2s")
        self.assertEqual(table.item(2, 5).text(), "드래그 이동")

        # Row 3: act4 (a4) - Key press non-mouse action has item "-"
        self.assertEqual(table.item(3, 0).text(), "a4")
        self.assertEqual(table.item(3, 1).text(), "⌨️ 키 조합")
        self.assertEqual(table.item(3, 2).text(), "[ctrl+c]")
        self.assertEqual(table.item(3, 3).text(), "-")
        self.assertEqual(table.item(3, 4).text(), "0.1s")
        self.assertEqual(table.item(3, 5).text(), "-")

        # Row 4: act5 (a5)
        self.assertEqual(table.item(4, 0).text(), "a5")
        self.assertEqual(table.item(4, 1).text(), "📋 로그")
        self.assertEqual(table.item(4, 2).text(), "시스템 상태 정상")
        self.assertEqual(table.item(4, 3).text(), "-")
        self.assertEqual(table.item(4, 4).text(), "-")
        self.assertEqual(table.item(4, 5).text(), "시스템 상태 정상")

    def test_inline_editing_updates_scenario(self):
        scen = Scenario(name="인라인 수정 테스트")
        act = Action(action_type="mouse_click", x=50, y=50, coord_anti_ban="weak", delay_seconds=0.5, custom_log="")
        scen.actions = [act]
        self.inspector.set_scenario(scen)
        
        table = self.inspector.tbl_actions
        cur_act = self.inspector.current_scenario.actions[0]
        delegate = self.inspector.action_column_delegate

        # 1. Modify offset inline via delegate editor
        editor_offset = delegate.createEditor(table, None, table.model().index(0, 3))
        self.assertIsInstance(editor_offset, QComboBox)
        delegate.setEditorData(editor_offset, table.model().index(0, 3))
        editor_offset.setCurrentIndex(editor_offset.findData("strong"))
        delegate.setModelData(editor_offset, table.model(), table.model().index(0, 3))
        self.assertEqual(cur_act.coord_anti_ban, "strong")
        self.assertEqual(table.item(0, 3).text(), "강")

        # 2. Modify delay inline via delegate editor (verify NoButtons)
        from PyQt5.QtWidgets import QAbstractSpinBox
        editor_delay = delegate.createEditor(table, None, table.model().index(0, 4))
        self.assertIsInstance(editor_delay, QDoubleSpinBox)
        self.assertEqual(editor_delay.buttonSymbols(), QAbstractSpinBox.NoButtons)
        editor_delay.setValue(1.8)
        delegate.setModelData(editor_delay, table.model(), table.model().index(0, 4))
        self.assertAlmostEqual(cur_act.delay_seconds, 1.8)
        self.assertEqual(table.item(0, 4).text(), "1.8s")

        # 3. Modify log inline via delegate editor
        editor_log = delegate.createEditor(table, None, table.model().index(0, 5))
        self.assertIsInstance(editor_log, QLineEdit)
        editor_log.setText("인라인 수정된 로그")
        delegate.setModelData(editor_log, table.model(), table.model().index(0, 5))
        self.assertEqual(cur_act.custom_log, "인라인 수정된 로그")
        self.assertEqual(table.item(0, 5).text(), "인라인 수정된 로그")

    def test_drag_and_drop_reorder(self):
        scen = Scenario(name="드래그 순서 테스트")
        act1 = Action(action_type="mouse_click", x=10, y=10, custom_log="1번")
        act2 = Action(action_type="key_press", key="Enter", custom_log="2번")
        act3 = Action(action_type="delay", delay_seconds=2.0, custom_log="3번")
        scen.actions = [act1, act2, act3]
        self.inspector.set_scenario(scen)

        # Move index 2 (act3) to index 0
        self.inspector._on_action_row_reordered(2, 0)
        self.assertEqual(len(self.inspector.current_scenario.actions), 3)
        self.assertEqual(self.inspector.current_scenario.actions[0].custom_log, "3번")
        self.assertEqual(self.inspector.current_scenario.actions[1].custom_log, "1번")
        self.assertEqual(self.inspector.current_scenario.actions[2].custom_log, "2번")

        # Ensure table rows and cells are completely preserved without disappearance
        self.assertEqual(self.inspector.tbl_actions.rowCount(), 3)
        self.assertEqual(self.inspector.tbl_actions.item(0, 0).text(), "a1")
        self.assertEqual(self.inspector.tbl_actions.item(1, 0).text(), "a2")
        self.assertEqual(self.inspector.tbl_actions.item(2, 0).text(), "a3")
        self.assertEqual(self.inspector.tbl_actions.item(0, 5).text(), "3번")
        self.assertEqual(self.inspector.tbl_actions.item(1, 5).text(), "1번")
        self.assertEqual(self.inspector.tbl_actions.item(2, 5).text(), "2번")

    def test_single_action_dialog_features(self):
        act = Action(action_type="mouse_click", x=100, y=200, delay_seconds=0.5, custom_log="")
        dlg = SingleActionDialog(action=act)
        
        # 1. Verify action type buttons exist and can be clicked
        self.assertIn("key_press", dlg.type_buttons)
        dlg.type_buttons["key_press"].click()
        self.assertEqual(dlg.action.action_type, "key_press")

        # 2. Verify large delay adjustment buttons (+0.5, +1.0, -0.5, -1.0)
        dlg.spin_delay.setValue(1.0)
        dlg._adjust_delay(0.5)
        self.assertAlmostEqual(dlg.spin_delay.value(), 1.5)
        dlg._adjust_delay(1.0)
        self.assertAlmostEqual(dlg.spin_delay.value(), 2.5)
        dlg._adjust_delay(-0.5)
        self.assertAlmostEqual(dlg.spin_delay.value(), 2.0)
        dlg._adjust_delay(-1.0)
        self.assertAlmostEqual(dlg.spin_delay.value(), 1.0)

        # 3. Verify custom log always directly editable and auto-off when empty
        self.assertTrue(dlg.txt_custom_log.isEnabled())
        dlg.txt_custom_log.setText("  직접 입력한 로그  ")
        dlg._on_ok()
        self.assertEqual(dlg.action.custom_log, "직접 입력한 로그")

        # When empty, automatically off ("")
        dlg.txt_custom_log.setText("")
        dlg._on_ok()
        self.assertEqual(dlg.action.custom_log, "")

    def test_scenario_drag_and_drop_reorder(self):
        from ui.main_window import MainWindow
        win = MainWindow()
        s1 = Scenario(name="시나리오1")
        s2 = Scenario(name="시나리오2")
        s3 = Scenario(name="시나리오3")
        win.project.scenarios = [s1, s2, s3]
        win._refresh_scenario_table()

        # Reorder s3 to top
        win._on_scenario_row_reordered(2, 0)
        self.assertEqual(win.project.scenarios[0].name, "시나리오3")
        self.assertEqual(win.project.scenarios[1].name, "시나리오1")
        self.assertEqual(win.project.scenarios[2].name, "시나리오2")

if __name__ == "__main__":
    unittest.main()
