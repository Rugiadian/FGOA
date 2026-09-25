"""
Unit tests for PopupPlayBar and ActionSequence modularization in FGOA.
"""
import sys
import unittest
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from core.models import Action, ActionSequence, Scenario, Project
from ui.popup_play_bar import PopupPlayBar
from ui.action_sequence_manager_dialog import ActionSequenceManagerDialog

app = QApplication.instance() or QApplication(sys.argv)


class TestActionSequenceAndPlayBar(unittest.TestCase):

    def setUp(self):
        self.project = Project(name="Test Sequence Project")
        self.seq1 = ActionSequence(
            id="seq_test_1",
            name="공용 전투 스킬 시퀀스",
            actions=[
                Action(action_type="mouse_click", x=100, y=200),
                Action(action_type="delay", delay_seconds=1.5),
                Action(action_type="mouse_click", x=300, y=400)
            ]
        )
        self.project.add_action_sequence(self.seq1)

        self.scen1 = Scenario(
            id="scen_1",
            name="전투 1턴",
            scenario_number=1,
            sequence_id="seq_test_1"  # Linked to seq1
        )
        self.scen2 = Scenario(
            id="scen_2",
            name="전용 클릭 시나리오",
            scenario_number=2,
            actions=[Action(action_type="mouse_click", x=500, y=600)]
        )
        self.project.scenarios = [self.scen1, self.scen2]

    def test_action_sequence_model(self):
        """Test ActionSequence serialization, deserialization, and summary."""
        self.assertEqual(len(self.seq1.actions), 3)
        summary = self.seq1.get_summary()
        self.assertIn("좌클릭 (100, 200)", summary)
        self.assertIn("1.5초 대기", summary)

        d = self.seq1.to_dict()
        recreated = ActionSequence.from_dict(d)
        self.assertEqual(recreated.id, self.seq1.id)
        self.assertEqual(recreated.name, self.seq1.name)
        self.assertEqual(len(recreated.actions), 3)

    def test_scenario_effective_actions_linked(self):
        """Test that a scenario linked to ActionSequence returns sequence actions."""
        eff_actions = self.scen1.get_effective_actions(self.project)
        self.assertEqual(len(eff_actions), 3)
        self.assertEqual(eff_actions[0].x, 100)

        # Actions summary with project should show link icon and sequence name
        summary = self.scen1.get_actions_summary(self.project)
        self.assertTrue(summary.startswith("🔗 [공용 전투 스킬 시퀀스]"))

    def test_scenario_effective_actions_unlinked(self):
        """Test that unlinked scenario returns its own standalone actions."""
        eff_actions = self.scen2.get_effective_actions(self.project)
        self.assertEqual(len(eff_actions), 1)
        self.assertEqual(eff_actions[0].x, 500)
        self.assertIn("좌클릭 (500, 600)", self.scen2.get_actions_summary(self.project))

    def test_project_sequence_management(self):
        """Test adding, finding, and deleting action sequences."""
        found = self.project.find_action_sequence("seq_test_1")
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "공용 전투 스킬 시퀀스")

        # Delete sequence and verify automatic unlinking in scenario
        self.project.delete_action_sequence("seq_test_1")
        self.assertIsNone(self.project.find_action_sequence("seq_test_1"))
        self.assertIsNone(self.scen1.sequence_id)

    def test_project_to_dict_and_from_dict_sequences(self):
        """Test project serialization preserving action_sequences."""
        data = self.project.to_dict()
        self.assertIn("action_sequences", data)
        self.assertEqual(len(data["action_sequences"]), 1)

        loaded_proj = Project.from_dict(data)
        self.assertEqual(len(loaded_proj.action_sequences), 1)
        self.assertEqual(loaded_proj.action_sequences[0].name, "공용 전투 스킬 시퀀스")
        self.assertEqual(loaded_proj.scenarios[0].sequence_id, "seq_test_1")

    def test_popup_play_bar_ui_and_signals(self):
        """Test PopupPlayBar UI components, state transitions, and signals."""
        bar = PopupPlayBar()
        bar.refresh_scenarios(self.project.scenarios)

        # Check initial state
        self.assertEqual(bar.lbl_state_badge.text(), "⚪ 대기 중")
        self.assertTrue(bar.btn_play.isEnabled())
        self.assertFalse(bar.btn_stop.isEnabled())

        # Test runner state transitions
        bar.set_runner_state("running", "전투 1턴 실행 중...")
        self.assertEqual(bar.lbl_state_badge.text(), "🟢 실행 중")
        self.assertFalse(bar.btn_play.isEnabled())
        self.assertTrue(bar.btn_stop.isEnabled())
        self.assertEqual(bar.lbl_status_detail.text(), "전투 1턴 실행 중...")

        bar.set_runner_state("paused", "일시정지됨")
        self.assertEqual(bar.lbl_state_badge.text(), "🟡 일시정지")
        self.assertTrue(bar.btn_play.isEnabled())
        self.assertEqual(bar.btn_play.text(), "▶ 선택 노드 재개")
        self.assertEqual(bar.btn_pause.text(), "▶ 전역 재개")

        # Test real-time action status formatting
        act_click = Action(action_type="mouse_click", x=250, y=350)
        bar.set_action_status(act_click, 1, 3, scenario_info="s1 [전투]")
        self.assertIn("s1 [전투] ▶ #1/3 🖱️ 클릭 (250, 350)", bar.lbl_status_detail.text())

        act_delay = Action(action_type="delay", delay_seconds=2.0)
        bar.set_action_status(act_delay, 2, 3)
        self.assertIn("#2/3 ⏱️ 2.0초 대기 진행 중...", bar.lbl_status_detail.text())

        bar.set_runner_state("stopped", "완료됨")
        self.assertEqual(bar.lbl_state_badge.text(), "⚪ 대기 중")
        self.assertEqual(bar.btn_play.text(), "▶ 시작 (F5)")
        self.assertEqual(bar.btn_pause.text(), "⏸ 일시정지")

        # Test play signal emission in paused state (emits current selected combo scenario)
        bar.set_runner_state("paused")
        play_emitted = []
        bar.sig_start_requested.connect(lambda sid: play_emitted.append(sid))
        bar.btn_play.click()
        self.assertEqual(len(play_emitted), 1)
        self.assertEqual(play_emitted[0], "scen_1")

        # Test collapse toggle
        self.assertFalse(bar.preset_section.isHidden())
        bar._toggle_collapse()
        self.assertTrue(bar.preset_section.isHidden())
        self.assertEqual(bar.btn_fold.text(), "▼")
        bar._toggle_collapse()
        self.assertFalse(bar.preset_section.isHidden())
        self.assertEqual(bar.btn_fold.text(), "▲")

        bar.close()

    def test_action_sequence_manager_dialog(self):
        """Test ActionSequenceManagerDialog initialization and table population."""
        dlg = ActionSequenceManagerDialog(self.project, current_sequence_id="seq_test_1")
        self.assertEqual(dlg.table.rowCount(), 1)
        self.assertEqual(dlg.table.item(0, 1).text(), "공용 전투 스킬 시퀀스")
        self.assertEqual(dlg.table.item(0, 2).text(), "3개")
        self.assertIn("s1", dlg.table.item(0, 4).text())
        dlg.close()


if __name__ == "__main__":
    unittest.main()
