"""
Tests for Scenario Presets and Unity-Style Dynamic Layout:
1. Scenario Preset Manager (Save, List, Instantiate with ID remapping, Delete)
2. SavePresetDialog and PresetManagerDialog
3. MainWindow Preset Integration (Save selected, load, replace, append, insert after)
4. Unity-Style QDockWidget Layout Presets (Default, Wide, Tall, Tabbed, Inspector Focus)
5. Custom Layout Save & Restore (saveState / restoreState)
"""
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import Qt, QByteArray
from core.models import Project, Scenario, Condition, Action, ColorPoint
from core.preset_manager import PresetManager
from ui.preset_dialog import SavePresetDialog, PresetManagerDialog
from ui.main_window import MainWindow

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)


class TestPresetsAndLayouts(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.patcher = patch("core.preset_manager.PRESETS_DIR", self.tmp_dir)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_01_preset_manager_save_and_instantiate_with_remapping(self):
        """Verify saving scenarios as preset and instantiating them with new unique IDs and remapped jumps."""
        s1 = Scenario(id="scen_orig_1", name="시나리오 1", actions=[Action(action_type="delay", delay_seconds=1.0)])
        s2 = Scenario(
            id="scen_orig_2",
            name="시나리오 2",
            on_match="jump",
            jump_target_on_match="scen_orig_1",
            actions=[Action(action_type="mouse_click", x=100, y=200)]
        )

        # Save preset
        saved_path = PresetManager.save_preset("전투 루프 프리셋", [s1, s2], "전투 진입 및 점프 설명")
        self.assertTrue(os.path.exists(saved_path))

        # List presets
        presets = PresetManager.list_presets()
        self.assertTrue(any(p["name"] == "전투 루프 프리셋" for p in presets))

        # Instantiate scenarios from preset
        preset_data = PresetManager.load_preset_file(saved_path)
        instances = PresetManager.instantiate_preset_scenarios(preset_data)

        self.assertEqual(len(instances), 2)
        # Verify IDs are newly generated
        self.assertNotEqual(instances[0].id, "scen_orig_1")
        self.assertNotEqual(instances[1].id, "scen_orig_2")
        # Verify jump target was automatically remapped to new ID of instance 0
        self.assertEqual(instances[1].jump_target_on_match, instances[0].id)

    def test_02_preset_manager_seed_builtins(self):
        """Verify built-in starter presets are automatically seeded when library is accessed."""
        presets = PresetManager.list_presets()
        preset_names = [p["name"] for p in presets]

        self.assertTrue(any("[기본] 전투 사이클" in name for name in preset_names))
        self.assertTrue(any("[기본] 단순 반복 클릭" in name for name in preset_names))
        self.assertTrue(any("[기본] 5회 카운트 루프" in name for name in preset_names))

    def test_03_main_window_preset_import_modes(self):
        """Verify MainWindow applying presets in 'append', 'after_selected', and 'replace' modes."""
        win = MainWindow()
        win.project.scenarios = [
            Scenario(id="base_1", step_number=1, name="기존 1"),
            Scenario(id="base_2", step_number=2, name="기존 2"),
        ]
        win.project.renumber_steps()

        new_scens = [
            Scenario(id="new_1", name="신규 A"),
            Scenario(id="new_2", name="신규 B"),
        ]

        # 1. Mode: 'after_selected' (select row 0, so inserts between 1 and 2)
        win.tbl_scenarios.selectRow(0)
        win._apply_imported_scenarios(new_scens, mode="after_selected")

        self.assertEqual(len(win.project.scenarios), 4)
        self.assertEqual(win.project.scenarios[0].name, "기존 1")
        self.assertEqual(win.project.scenarios[1].name, "신규 A")
        self.assertEqual(win.project.scenarios[2].name, "신규 B")
        self.assertEqual(win.project.scenarios[3].name, "기존 2")
        # Verify step numbers were sequentially updated
        self.assertEqual([s.step_number for s in win.project.scenarios], [1, 2, 3, 4])

        # 2. Mode: 'replace'
        replace_scens = [Scenario(id="rep_1", name="단독 시나리오")]
        win._apply_imported_scenarios(replace_scens, mode="replace")
        self.assertEqual(len(win.project.scenarios), 1)
        self.assertEqual(win.project.scenarios[0].name, "단독 시나리오")
        self.assertEqual(win.project.scenarios[0].step_number, 1)

        win.close()

    def test_04_unity_dock_layout_presets_switching(self):
        """Verify Unity-style dock layout presets (Default, Wide, Tall, Tabbed, Inspector Focus) switch cleanly."""
        win = MainWindow()
        win.show()

        # Docks should exist and have object names
        self.assertIsNotNone(win.dock_scenarios)
        self.assertIsNotNone(win.dock_inspector)
        self.assertIsNotNone(win.dock_log)
        self.assertEqual(win.dock_scenarios.objectName(), "DockScenarios")
        self.assertEqual(win.dock_inspector.objectName(), "DockInspector")
        self.assertEqual(win.dock_log.objectName(), "DockLog")

        # Test each layout mode
        layouts = [
            "기본 3열 (Default)",
            "와이드 (하단 콘솔)",
            "세로 분할 (Tall)",
            "2 by 3 (Unity 스타일)",
            "탭 묶음 (Tabbed)",
            "인스펙터 전면 (Inspector Focus)"
        ]

        for layout in layouts:
            win.apply_layout(layout)
            self.assertEqual(win.current_layout_name, layout)
            # Ensure all docks remain visible
            self.assertFalse(win.dock_scenarios.isHidden())
            self.assertFalse(win.dock_inspector.isHidden())
            self.assertFalse(win.dock_log.isHidden())

        win.close()

    def test_05_custom_layout_save_and_restore(self):
        """Verify custom layout saving and restoring via Qt saveState/restoreState."""
        win = MainWindow()
        win.show()

        # Arrange in Wide layout
        win.apply_layout("와이드 (하단 콘솔)")
        custom_state_hex = win.saveState().toHex().data().decode()

        win.custom_layouts["내 커스텀 레이아웃"] = custom_state_hex
        win._refresh_layout_combo()

        # Change to another layout
        win.apply_layout("기본 3열 (Default)")
        self.assertEqual(win.current_layout_name, "기본 3열 (Default)")

        # Restore custom layout
        win.apply_layout("내 커스텀 레이아웃")
        self.assertFalse(win.dock_scenarios.isHidden())
        self.assertFalse(win.dock_inspector.isHidden())
        self.assertFalse(win.dock_log.isHidden())

        win.close()

    def test_06_user_log_color_and_styling(self):
        """Verify user log color is distinct (fuchsia/pink) and formatted with bold [사용자 로그] tag."""
        from ui.theme import get_theme_colors
        light_pal = get_theme_colors("light")
        dark_pal = get_theme_colors("dark")

        # Verify distinct fuchsia/pink colors
        self.assertEqual(light_pal["log_user"], "#c026d3")
        self.assertEqual(dark_pal["log_user"], "#f472b6")

        # Verify no collision with existing log levels
        standard_light_levels = ["log_info", "log_action", "log_success", "log_warn", "log_error"]
        for lvl in standard_light_levels:
            self.assertNotEqual(light_pal["log_user"], light_pal[lvl])
            self.assertNotEqual(dark_pal["log_user"], dark_pal[lvl])

        # Test log output HTML in MainWindow
        win = MainWindow()
        win.current_theme = "light"
        win.txt_log.clear()
        win._append_log("USER", "사용자 정의 매크로 문장 출력 테스트")

        log_html = win.txt_log.toHtml()
        self.assertIn("#c026d3", log_html)
        self.assertIn("사용자 로그", log_html)
        self.assertIn("사용자 정의 매크로 문장 출력 테스트", log_html)
        win.close()

    def test_07_preset_duplicate_id_prevention_and_jump_integrity(self):
        """Verify preset importation generates non-colliding scenario numbers (no #1, #2, #3 duplication)
        and preserves internal jump target references."""
        proj = Project()
        # Initial 3 scenarios with #1, #2, #3
        proj.scenarios = [
            Scenario(id="base_1", scenario_number=1, step_number=1, name="기초 시나리오 1"),
            Scenario(id="base_2", scenario_number=2, step_number=2, name="기초 시나리오 2"),
            Scenario(id="base_3", scenario_number=3, step_number=3, name="기초 시나리오 3"),
        ]
        proj.renumber_steps()

        # Load battle cycle preset (which internally has old IDs and old #1, #2, #3)
        presets = PresetManager.list_presets()
        battle_preset = next(p for p in presets if p["id"] == "preset_battle_cycle")

        # Instantiate preset scenarios
        imported_scens = PresetManager.instantiate_preset_scenarios(battle_preset)
        self.assertEqual(len(imported_scens), 3)

        # Append to project and renumber
        proj.scenarios.extend(imported_scens)
        proj.renumber_steps()

        # Verify all scenario numbers are strictly unique
        scen_numbers = [s.scenario_number for s in proj.scenarios]
        self.assertEqual(len(scen_numbers), len(set(scen_numbers)), f"Duplicate scenario numbers found: {scen_numbers}")
        # The first 3 remain 1, 2, 3 and the imported 3 become 4, 5, 6
        self.assertEqual(scen_numbers, [1, 2, 3, 4, 5, 6])

        # Verify all IDs are strictly unique
        ids = [s.id for s in proj.scenarios]
        self.assertEqual(len(ids), len(set(ids)), f"Duplicate IDs found: {ids}")

        # Verify jump target integrity:
        # In battle cycle preset, scen 3 jumps to scen 1 on match.
        # Now scen 5 (index 5) must jump to scen 3 (index 3)'s new ID!
        jump_source = proj.scenarios[5]
        jump_target_id = jump_source.jump_target_on_match
        self.assertTrue(bool(jump_target_id))
        self.assertEqual(jump_target_id, proj.scenarios[3].id, "Jump target must point to the instantiated preset scenario #4's new ID")

        # Verify get_next_scenario_number returns 7
        self.assertEqual(proj.get_next_scenario_number(), 7)

    def test_08_inspector_50px_reference_thumbnail(self):
        """Verify inspector displays 50px wide reference image thumbnails for condition and action images."""
        from PyQt5.QtGui import QImage, QPainter, QColor
        from ui.inspector_widget import InspectorWidget

        # Create dummy image file (100x60)
        img_path = os.path.join(self.tmp_dir, "test_ref_image.png")
        img = QImage(100, 60, QImage.Format_RGB32)
        img.fill(QColor(220, 50, 50))
        img.save(img_path)

        inspector = InspectorWidget()
        proj = Project()

        # 1. Scenario without images: both thumbnails should be hidden
        s1 = Scenario(id="s1", name="이미지 없음", condition=Condition(name="조건"))
        inspector.set_scenario(s1, 0, proj)
        self.assertTrue(inspector.lbl_thumb_cond.isHidden())
        self.assertTrue(inspector.lbl_thumb_act.isHidden())

        # 2. Scenario with condition reference image: condition thumbnail shown at condition tab top
        s2 = Scenario(
            id="s2",
            name="인식 조건 이미지 있음",
            condition=Condition(name="조건", reference_image_path=img_path)
        )
        inspector.set_scenario(s2, 0, proj)
        self.assertFalse(inspector.lbl_thumb_cond.isHidden())
        self.assertTrue(inspector.lbl_thumb_act.isHidden())
        self.assertEqual(inspector.lbl_thumb_cond.width(), 50)
        self.assertIsNotNone(inspector.lbl_thumb_cond.pixmap())
        self.assertEqual(inspector.lbl_thumb_cond.pixmap().width(), 50)

        # 3. Scenario with action reference image: action thumbnail shown at action tab top
        s3 = Scenario(
            id="s3",
            name="액션 이미지 있음",
            last_action_image_path=img_path
        )
        inspector.set_scenario(s3, 0, proj)
        self.assertTrue(inspector.lbl_thumb_cond.isHidden())
        self.assertFalse(inspector.lbl_thumb_act.isHidden())
        self.assertEqual(inspector.lbl_thumb_act.width(), 50)
        self.assertIsNotNone(inspector.lbl_thumb_act.pixmap())
        self.assertEqual(inspector.lbl_thumb_act.pixmap().width(), 50)

        inspector.close()

    def test_09_inspector_draft_save_cancel_and_undo_redo(self):
        """Verify inspector edits do not mutate original until Save is clicked,
        and support Cancel, Undo (Ctrl+Z), and Redo (Ctrl+Y)."""
        from ui.inspector_widget import InspectorWidget

        inspector = InspectorWidget()
        proj = Project()
        orig_scen = Scenario(id="scen_orig", scenario_number=1, name="초기 시나리오 이름", enabled=True)
        proj.scenarios = [orig_scen]

        inspector.set_scenario(orig_scen, 0, proj)
        self.assertFalse(inspector.is_dirty)
        self.assertFalse(inspector.btn_save_inspector.isEnabled())
        self.assertFalse(inspector.btn_cancel_inspector.isEnabled())

        # 1. Edit name in inspector
        inspector.txt_name.setText("수정된 임시 시나리오 이름")
        self.assertTrue(inspector.is_dirty)
        self.assertTrue(inspector.btn_save_inspector.isEnabled())
        self.assertTrue(inspector.btn_cancel_inspector.isEnabled())
        # Original scenario should remain UNCHANGED before Save
        self.assertEqual(orig_scen.name, "초기 시나리오 이름")

        # 2. Undo edit
        self.assertTrue(inspector.btn_undo_inspector.isEnabled())
        inspector._on_undo_inspector()
        self.assertEqual(inspector.txt_name.text(), "초기 시나리오 이름")

        # 3. Redo edit
        self.assertTrue(inspector.btn_redo_inspector.isEnabled())
        inspector._on_redo_inspector()
        self.assertEqual(inspector.txt_name.text(), "수정된 임시 시나리오 이름")

        # 4. Save edit
        saved_scenarios = []
        inspector.sig_scenario_saved.connect(lambda s: saved_scenarios.append(s))
        inspector._on_save_inspector()

        self.assertFalse(inspector.is_dirty)
        self.assertEqual(len(saved_scenarios), 1)
        # Original scenario now updated!
        self.assertEqual(orig_scen.name, "수정된 임시 시나리오 이름")

        # 5. Edit again and Cancel
        inspector.txt_name.setText("다시 바꾼 이름")
        self.assertTrue(inspector.is_dirty)
        inspector._on_cancel_inspector()
        self.assertFalse(inspector.is_dirty)
        self.assertEqual(inspector.txt_name.text(), "수정된 임시 시나리오 이름")
        self.assertEqual(orig_scen.name, "수정된 임시 시나리오 이름")

        inspector.close()

    def test_10_scenario_list_undo_redo(self):
        """Verify MainWindow scenario list modifications support Undo (Ctrl+Z) and Redo (Ctrl+Y)."""
        win = MainWindow()
        win.project.scenarios = [
            Scenario(id="s1", scenario_number=1, step_number=1, name="시나리오 1"),
            Scenario(id="s2", scenario_number=2, step_number=2, name="시나리오 2"),
        ]
        win.project.renumber_steps()
        win._refresh_scenario_table()

        initial_count = len(win.project.scenarios)
        self.assertEqual(initial_count, 2)
        self.assertFalse(win.btn_undo_scenario.isEnabled())

        # 1. Add scenario -> Undo -> Redo
        win._on_add_scenario()
        self.assertEqual(len(win.project.scenarios), 3)
        self.assertTrue(win.btn_undo_scenario.isEnabled())

        # Undo addition
        win._undo_scenario()
        self.assertEqual(len(win.project.scenarios), 2)
        self.assertEqual([s.scenario_number for s in win.project.scenarios], [1, 2])
        self.assertTrue(win.btn_redo_scenario.isEnabled())

        # Redo addition
        win._redo_scenario()
        self.assertEqual(len(win.project.scenarios), 3)

        # 2. Delete scenario -> Undo
        win.tbl_scenarios.selectRow(2)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            win._on_delete_scenario()
        self.assertEqual(len(win.project.scenarios), 2)

        # Undo deletion
        win._undo_scenario()
        self.assertEqual(len(win.project.scenarios), 3)

        # 3. Move scenario up -> Undo
        win.tbl_scenarios.selectRow(1)
        win._on_move_up()
        self.assertEqual(win.project.scenarios[0].id, "s2")
        win._undo_scenario()
        self.assertEqual(win.project.scenarios[0].id, "s1")

        win.close()


if __name__ == "__main__":
    unittest.main()
