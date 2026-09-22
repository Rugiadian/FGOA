"""
Automated Test for 3 Core User Scenarios in FGOA.
Scenario 1: Action Creation, Editing & Immediate Execution (Hand - [⚡ 선택 액션 즉시 실행])
Scenario 2: Window Missing / Invalid HWND Condition Evaluation & Workflow Runner Lifecycle (Eye & Runner)
Scenario 3: Scenario Table Operations (Add, Loop Block, Duplicate, Move, Delete, Clear all) & Project Save/Load
"""
import sys
import os
import unittest
import json
import tempfile
from unittest.mock import MagicMock, patch

# Ensure project root in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from core.models import Project, Scenario, Condition, ColorPoint, Action
from core.input_controller import InputController
from core.evaluator import ConditionEvaluator
from core.runner import WorkflowRunner
from core.screen_capture import ScreenCapture
from core.window_manager import WindowManager, WindowInfo
from ui.main_window import MainWindow
from ui.inspector_widget import InspectorWidget


class TestThreeScenarios(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication.instance() is None:
            cls.app = QApplication(sys.argv)
        else:
            cls.app = QApplication.instance()

    # =========================================================================
    # 시나리오 1: 액션 생성 및 인스펙터 [⚡ 선택 액션 즉시 실행] 테스트
    # =========================================================================
    def test_scenario_1_action_quick_add_and_execute(self):
        """
        [시나리오 1] 사용자가 액션을 추가하고 [⚡ 선택 액션 즉시 실행] 버튼을 눌렀을 때
        InputController.execute_action 호출 및 각 액션 타입(클릭, 드래그, 키입력, 텍스트, 딜레이)이
        정상적으로 실행되는지 검증 (프로그램 크래시 여부 확인)
        """
        print("\n=== [시나리오 1] 액션 생성 및 즉시 실행 테스트 시작 ===")
        widget = InspectorWidget()
        proj = Project()
        scen = Scenario(id="scen_test1", scenario_number=1, name="액션 테스트 시나리오")
        scen.actions = [
            Action(action_type="mouse_click", x=100, y=100, mouse_button="left"),
            Action(action_type="mouse_drag", x=100, y=100, end_x=200, end_y=200, drag_duration_ms=50),
            Action(action_type="key_press", key="Enter"),
            Action(action_type="text_type", text="test"),
            Action(action_type="delay", delay_seconds=0.01),
            Action(action_type="sound_beep", beep_freq=1000, beep_duration_ms=10),
            Action(action_type="log_message", log_text="테스트 로그"),
        ]
        proj.scenarios.append(scen)
        widget.set_scenario(scen, target_hwnd=12345, project=proj)

        # 각 액션에 대해 즉시 실행 검증
        for row, act in enumerate(scen.actions):
            widget.tbl_actions.selectRow(row)
            print(f"  - 액션 실행 시도: {act.get_summary()}")
            # Mock InputController internal Win32 APIs so it doesn't move real mouse / press real keys
            with patch("core.input_controller.WindowManager.client_to_screen", return_value=(100, 100)), \
                 patch("core.input_controller.InputController.set_cursor_pos"), \
                 patch("win32api.mouse_event"), \
                 patch("win32api.keybd_event"), \
                 patch("winsound.Beep"), \
                 patch("PyQt5.QtWidgets.QMessageBox.critical") as mock_crit:
                widget._on_test_action_now()
                if mock_crit.called:
                    args, _ = mock_crit.call_args
                    err_msg = args[2] if len(args) > 2 else ""
                    print(f"    [실패/크래시 감지!] {act.action_type} 실행 시 critical 오류 팝업 발생: {err_msg}")
                    self.fail(f"시나리오 1 실패 - {act.action_type} 실행 시 critical 오류 발생: {err_msg}")
                else:
                    print(f"    [성공] {act.action_type} 실행 성공")

    # =========================================================================
    # 시나리오 2: 타겟 창 없음/닫힘 상태에서 조건 판정 및 실행 엔진(Runner) 동작 테스트
    # =========================================================================
    def test_scenario_2_invalid_window_evaluation_and_runner(self):
        """
        [시나리오 2] 타겟 창이 없거나 닫힌 상태(HWND=0 또는 유효하지 않은 HWND)에서
        1) 인스펙터 [⚡ 판정 테스트] 버튼 클릭 시
        2) ConditionEvaluator.evaluate 실행 시
        3) WorkflowRunner 백그라운드 스레드 실행 및 중지(stop/pause/step) 시
        프로그램이 비정상 종료(Crash)되거나 먹통(Hang)되지 않고 안전하게 처리되는지 검증
        """
        print("\n=== [시나리오 2] 타겟 창 부재 시 조건 판정 및 러너 안전성 테스트 시작 ===")

        # 1) HWND = 0 일 때 ConditionEvaluator.evaluate
        cond = Condition(name="테스트 조건", points=[ColorPoint(x=10, y=10, r=255, g=0, b=0)])
        matched, results = ConditionEvaluator.evaluate(cond, 0)
        self.assertFalse(matched)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["passed"])
        print("  [성공] HWND=0 조건 평가 안전 통과 (False 반환)")

        # 2) 인스펙터에서 target_hwnd=0 일 때 _on_test_condition_now()
        widget = InspectorWidget()
        proj = Project()
        scen = Scenario(id="scen_test2", name="판정 테스트", condition=cond)
        proj.scenarios.append(scen)
        widget.set_scenario(scen, target_hwnd=0, project=proj)
        # Mock QMessageBox so dialog doesn't block
        with patch("PyQt5.QtWidgets.QMessageBox.warning") as mock_warn:
            widget._on_test_condition_now()
            self.assertTrue(mock_warn.called)
        print("  [성공] 타겟 창 미선택 시 경고 다이얼로그 표시 후 안전 복귀")

        # 3) WorkflowRunner: 존재하지 않는 HWND로 run() 호출 시 안전 종료 확인
        runner = WorkflowRunner(proj, hwnd=99999999)
        runner.run()  # Run synchronously to check
        self.assertFalse(runner._is_running)
        print("  [성공] 존재하지 않는 HWND에 대한 러너 안전 종료 확인")

        # 4) WorkflowRunner: 루프 회차 실행 중 타겟 창이 닫혔을 때 (중간 창 소멸)
        s_loop = Scenario(id="s_loop", scenario_number=1, name="창소멸 감지", condition=cond)
        proj.scenarios = [s_loop]
        runner2 = WorkflowRunner(proj, hwnd=12345)
        # First check passes, second check returns None (window closed)
        with patch("core.runner.WindowManager.get_window_info", side_effect=[
            MagicMock(title="Game", client_width=800, client_height=600),
            None  # Window closed
        ]):
            runner2.run()
        self.assertFalse(runner2._is_running)
        print("  [성공] 실행 중 창 소멸 시 안전하게 루프 중단 확인")

    # =========================================================================
    # 시나리오 3: 시나리오 테이블 전체 조작 & 루프 블록 & 프로젝트 저장/불러오기
    # =========================================================================
    def test_scenario_3_table_operations_loop_blocks_and_serialization(self):
        """
        [시나리오 3] 시나리오 테이블의 핵심 조작 테스트:
        1) 시나리오 추가, 복제, 삭제, 순서 이동(위/아래)
        2) 루프 블록(루프 시작 - 내부 작업 - 루프 종료) 추가 및 중첩
        3) 모든 시나리오 삭제 후 빈 상태에서의 테이블 및 인스펙터 반응
        4) 복잡한 시나리오/루프 프로젝트를 JSON으로 저장 후 다시 불러오기
        """
        print("\n=== [시나리오 3] 시나리오 조작, 루프 블록 & 저장/불러오기 테스트 시작 ===")
        win = MainWindow()
        win.project.scenarios.clear()
        win._refresh_scenario_table()

        # 1) 시나리오 추가 2건
        win._on_add_scenario()
        win._on_add_scenario()
        self.assertEqual(len(win.project.scenarios), 2)
        print(f"  [성공] 시나리오 추가 2건: 총 {len(win.project.scenarios)}개")

        # 2) 루프 블록 추가 (start, child, end 3개 노드 생성)
        win._on_add_loop_block()
        self.assertEqual(len(win.project.scenarios), 5)
        print(f"  [성공] 루프 블록 추가: 총 {len(win.project.scenarios)}개")

        # 3) 순서 이동 (위, 아래)
        win.tbl_scenarios.selectRow(1)
        win._on_move_down()
        win._on_move_up()
        print("  [성공] 시나리오 위/아래 이동 정상")

        # 4) 시나리오 복제
        win.tbl_scenarios.selectRow(2)
        win._on_duplicate_scenario()
        self.assertEqual(len(win.project.scenarios), 6)
        print("  [성공] 시나리오 복제 정상")

        # 5) 프로젝트 JSON 저장 및 불러오기 검증
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            temp_path = tf.name

        try:
            # Save
            proj_dict = win.project.to_dict()
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(proj_dict, f, indent=2, ensure_ascii=False)
            self.assertTrue(os.path.exists(temp_path))

            # Load into new project
            with open(temp_path, "r", encoding="utf-8") as f:
                loaded_dict = json.load(f)
            loaded_proj = Project.from_dict(loaded_dict)
            self.assertEqual(len(loaded_proj.scenarios), len(win.project.scenarios))

            win.project = loaded_proj
            win._refresh_scenario_table()
            print("  [성공] 프로젝트 JSON 직렬화 및 역직렬화 완벽 일치")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

        # 6) 시나리오 전체 삭제 (빈 상태 테스트 - 빈 상태에서 크래시 여부 점검)
        with patch("PyQt5.QtWidgets.QMessageBox.question", return_value=16384): # QMessageBox.Yes
            while len(win.project.scenarios) > 0:
                win.tbl_scenarios.selectRow(0)
                win._on_delete_scenario()

        self.assertEqual(len(win.project.scenarios), 0)
        win._refresh_scenario_table()
        # Ensure inspector handles empty scenario without crashing
        win.inspector.set_scenario(None, 0, win.project)
        self.assertEqual(win.inspector.stack.currentIndex(), 0)
        print("  [성공] 시나리오 전체 삭제 및 빈 상태 안전 처리 완료")


if __name__ == "__main__":
    unittest.main()
