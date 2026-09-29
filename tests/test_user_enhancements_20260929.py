"""
Unit tests for user enhancements on 2026-09-29:
1. Action sequence clear button and new sequence button in InspectorWidget
2. Real-time loop progress count display in bottom scenario toolbar in MainWindow
3. QCursor and QDialog import availability in ui.inspector_widget
"""
import unittest
from unittest.mock import MagicMock, patch
from PyQt5.QtWidgets import QApplication, QMessageBox, QInputDialog
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import QDialog

from core.models import Scenario, Project, Action, ActionSequence
from ui.inspector_widget import InspectorWidget
from ui.main_window import MainWindow

app = QApplication.instance()
if not app:
    app = QApplication([])


class TestEnhancements20260929(unittest.TestCase):

    def setUp(self):
        self.project = Project()
        self.scen = Scenario(scenario_number=1, name="테스트 노드", actions=[
            Action(action_type="mouse_click", x=100, y=200),
            Action(action_type="delay", delay_seconds=1.0)
        ])
        self.project.scenarios.append(self.scen)

    def test_01_imports_in_inspector_widget(self):
        import ui.inspector_widget as iw
        self.assertTrue(hasattr(iw, "QCursor"))
        self.assertTrue(hasattr(iw, "QDialog"))

    def test_02_inspector_action_sequence_buttons_exist(self):
        inspector = InspectorWidget()
        inspector.set_scenario(self.scen, project=self.project)

        self.assertTrue(hasattr(inspector, "btn_new_seq"))
        self.assertTrue(hasattr(inspector, "btn_clear_seq"))
        self.assertTrue(hasattr(inspector, "btn_clear_act"))
        self.assertEqual(inspector.btn_new_seq.text(), "✨ 새로 만들기")
        self.assertEqual(inspector.btn_clear_seq.text(), "🧹 클리어")
        self.assertEqual(inspector.btn_clear_act.text(), "🧹 전체 클리어")

    @patch.object(QInputDialog, "getText", return_value=("전투 액션 묶음", True))
    def test_03_create_new_sequence(self, mock_input):
        inspector = InspectorWidget()
        inspector.set_scenario(self.scen, project=self.project)

        inspector._on_new_sequence()

        self.assertIsNotNone(inspector.current_scenario.sequence_id)
        created_seq = self.project.find_action_sequence(inspector.current_scenario.sequence_id)
        self.assertIsNotNone(created_seq)
        self.assertEqual(created_seq.name, "전투 액션 묶음")
        self.assertEqual(len(created_seq.actions), 0)

    @patch.object(QMessageBox, "question", return_value=QMessageBox.Yes)
    def test_04_clear_instant_actions(self, mock_msgbox):
        inspector = InspectorWidget()
        inspector.set_scenario(self.scen, project=self.project)

        self.assertEqual(len(inspector._get_active_actions_list()), 2)
        inspector._on_clear_actions()
        self.assertEqual(len(inspector._get_active_actions_list()), 0)

    @patch.object(QMessageBox, "question", return_value=QMessageBox.Yes)
    def test_05_clear_linked_sequence_actions(self, mock_msgbox):
        seq = ActionSequence(
            name="공용 시퀀스",
            actions=[Action(action_type="mouse_click", x=50, y=50)]
        )
        self.project.add_action_sequence(seq)
        self.scen.sequence_id = seq.id

        inspector = InspectorWidget()
        inspector.set_scenario(self.scen, project=self.project)

        self.assertEqual(len(inspector._get_active_actions_list()), 1)
        inspector._on_clear_actions()
        self.assertEqual(len(inspector._get_active_actions_list()), 0)
        self.assertEqual(len(seq.actions), 0)

    def test_06_main_window_loop_progress_display(self):
        window = MainWindow()
        self.assertTrue(hasattr(window, "lbl_loop_progress"))
        self.assertEqual(window.lbl_loop_progress.text(), "(대기)")

        # In-progress with finite loops (e.g. loop 2 of 5)
        window._on_loop_progress(2, 5)
        self.assertIn("2 / 5회 진행 중", window.lbl_loop_progress.text())

        # In-progress with infinite loops (loop count = 0)
        window._on_loop_progress(3, 0)
        self.assertIn("3회 진행 중", window.lbl_loop_progress.text())

        # Runner finished
        window._on_runner_finished("정상 종료")
        self.assertIn("총 3회 완료", window.lbl_loop_progress.text())

        # Runner stopped
        window._current_run_loop = 4
        window._on_stop_execution()
        self.assertIn("4회차 정지", window.lbl_loop_progress.text())


if __name__ == "__main__":
    unittest.main()
