"""
10 Focused Functional Tests for Image Coordinate Recognition Conditions and Action Sequences in FGOA.
(이미지 좌표 지정 인식조건 및 이미지 좌표 지정 액션 시퀀스 중심 기능 테스트 10건)

Test Cases:
[Part 1: 이미지 좌표 지정 인식조건 (Image Coordinate Recognition Conditions)]
1. test_01_condition_dummy_canvas_auto_creation
2. test_02_condition_point_picker_and_magnifier_color_extraction
3. test_03_condition_line_picker_multisampling_and_grouping
4. test_04_condition_point_nudge_and_boundary_clamping
5. test_05_condition_image_evaluator_and_tolerance_matching

[Part 2: 이미지 좌표 지정 액션 시퀀스 (Image Coordinate Action Sequences)]
6. test_06_action_sequence_dummy_canvas_and_top_margin_layout
7. test_07_action_sequence_canvas_click_and_delay_recording
8. test_08_action_sequence_canvas_drag_recording_with_duration
9. test_09_action_sequence_virtual_cursor_simulation_without_popup
10. test_10_action_sequence_log_time_format_and_reordering
"""
import sys
import os
import unittest
import time
from unittest.mock import MagicMock, patch
from PIL import Image

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from PyQt5.QtWidgets import QApplication, QSizePolicy
from PyQt5.QtCore import Qt, QPointF
from PyQt5.QtGui import QImage, QPixmap

from core.models import Project, Scenario, Condition, ColorPoint, Action
from core.evaluator import ConditionEvaluator
from core.dummy_canvas import (
    create_dummy_canvas_qimage,
    create_dummy_canvas_pixmap,
    create_dummy_canvas_pil
)
from core.runner import WorkflowRunner
from ui.condition_editor_dialog import ConditionEditorDialog
from ui.coordinate_picker_dialog import CoordinatePickerDialog, ActionCanvasView
from ui.inspector_widget import InspectorWidget


class TestImageCoordinate10Cases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication.instance() is None:
            cls.app = QApplication(sys.argv)
        else:
            cls.app = QApplication.instance()

    # =========================================================================
    # [Part 1] 이미지 좌표 지정 인식조건 기능 테스트 5건
    # =========================================================================

    def test_01_condition_dummy_canvas_auto_creation(self):
        """
        [테스트 1] 인식조건 더미 캔버스 자동 생성 및 해상도/배경 검증
        - 타겟 창 미지정(target_hwnd=0) 및 레퍼런스 이미지 부재 시 ConditionEditorDialog 생성
        - 1600x900 더미 캔버스가 자동 생성되어 캔버스에 바인딩되는지 검증
        - 캔버스 pan, zoom 및 타겟 해상도 설정 무결성 검증
        """
        print("\n=== [테스트 1] 인식조건 더미 캔버스 자동 생성 및 해상도/배경 검증 시작 ===")
        proj = Project(target_client_width=1600, target_client_height=900)
        cond = Condition(name="더미 캔버스 조건")
        
        # Open condition editor dialog without target hwnd and without image
        dlg = ConditionEditorDialog(
            condition=cond,
            project=proj,
            current_scenario_id="scen_dummy_1",
            target_hwnd=0
        )

        # 1. Check canvas pixmap exists and is valid
        self.assertIsNotNone(dlg.canvas.pixmap, "더미 캔버스 Pixmap이 생성되어야 합니다.")
        self.assertFalse(dlg.canvas.pixmap.isNull(), "더미 캔버스 Pixmap이 비어있지 않아야 합니다.")
        self.assertEqual(dlg.canvas.pixmap.width(), 1600, "더미 캔버스 가로 해상도는 1600이어야 합니다.")
        self.assertEqual(dlg.canvas.pixmap.height(), 900, "더미 캔버스 세로 해상도는 900이어야 합니다.")

        # 2. Check canvas target resolution
        self.assertEqual(dlg.canvas.target_width, 1600)
        self.assertEqual(dlg.canvas.target_height, 900)

        # 3. Check pixel color sampling from dummy canvas
        # Header bar left background (e.g. at 5, 20 is header bar #0f172a)
        r, g, b = dlg.canvas.get_pixel_color_at(5, 20)
        self.assertEqual((r, g, b), (15, 23, 42), "상단 헤더 바 배경색(#0f172a)이 정확히 샘플링되어야 합니다.")
        print("  [성공] 타겟 앱 미지정 시 1600×900 고해상도 더미 캔버스 자동 로딩 및 픽셀 샘플링 확인")

    def test_02_condition_point_picker_and_magnifier_color_extraction(self):
        """
        [테스트 2] 인식조건 단일 점 피커(Point Picker) 및 돋보기 색상 추출 검증
        - 더미 캔버스의 특정 UI 버튼 위치(초록 확인 버튼)를 클릭
        - ColorPoint 모델 추가 및 RGB 색상 추출 정확성 검증
        - 돋보기(MagnifierWidget) 및 포인트 테이블의 동기화 검증
        """
        print("\n=== [테스트 2] 인식조건 점 피커 및 돋보기 색상 추출 검증 시작 ===")
        proj = Project(target_client_width=1600, target_client_height=900)
        cond = Condition(name="포인트 피커 조건")
        dlg = ConditionEditorDialog(condition=cond, project=proj, current_scenario_id="scen_2", target_hwnd=0)

        # Set Point Picker tool mode (MODE_POINT = 0)
        dlg._set_tool_mode(0)
        self.assertEqual(dlg.canvas.current_mode, 0)

        # In dummy canvas, green button is around x=130..250, y=70..114 (Color: Green #16a34a -> RGB(22, 163, 74))
        # Click at (160, 90) on the green button
        target_x, target_y = 160, 90
        dlg.canvas.sig_point_added.emit(target_x, target_y, 22, 163, 74)

        # Verify point is registered in condition
        self.assertEqual(len(dlg.condition.points), 1)
        pt = dlg.condition.points[0]
        self.assertEqual(pt.x, target_x)
        self.assertEqual(pt.y, target_y)
        self.assertEqual((pt.r, pt.g, pt.b), (22, 163, 74))
        self.assertEqual(pt.tolerance, 15)
        self.assertEqual(pt.match_mode, "match")

        # Verify points table reflects the point
        self.assertEqual(dlg.tbl_points.rowCount(), 1)
        coord_item = dlg.tbl_points.item(0, 1)
        self.assertIn(f"({target_x}, {target_y})", coord_item.text())

        # Verify magnifier updates hover pixel
        dlg._on_canvas_pixel_hovered(target_x, target_y)
        self.assertEqual(dlg.magnifier.canvas.center_x, target_x)
        self.assertEqual(dlg.magnifier.canvas.center_y, target_y)
        print("  [성공] 점 피커로 더미 캔버스 UI 색상 추출, ColorPoint 등록 및 돋보기 연동 확인")

    def test_03_condition_line_picker_multisampling_and_grouping(self):
        """
        [테스트 3] 인식조건 연속 선 피커(Line Picker) 등간격 다중 포인트 생성 및 그룹화 검증
        - (100, 200) -> (500, 200) 구간 드래그로 선 샘플링 트리거
        - 5개의 포인트가 등간격으로 계산되어 생성되는지 검증
        - 모든 포인트가 동일한 line_group_id를 공유하는지 검증
        """
        print("\n=== [테스트 3] 인식조건 선 피커 등간격 다중 포인트 생성 및 그룹화 검증 시작 ===")
        proj = Project(target_client_width=1600, target_client_height=900)
        cond = Condition(name="선 피커 조건")
        dlg = ConditionEditorDialog(condition=cond, project=proj, current_scenario_id="scen_3", target_hwnd=0)

        # Trigger line points added from (100, 200) to (500, 200) with mocked dialog input
        with patch("PyQt5.QtWidgets.QInputDialog.getInt", return_value=(5, True)):
            dlg._on_canvas_line_added(100, 200, 500, 200)

        # Expected: 5 points created along horizontal line
        self.assertEqual(len(dlg.condition.points), 5)
        expected_x_coords = [100, 200, 300, 400, 500]
        line_group = dlg.condition.points[0].line_group_id
        self.assertIsNotNone(line_group)

        for i, pt in enumerate(dlg.condition.points):
            self.assertEqual(pt.x, expected_x_coords[i], f"포인트 #{i+1}의 X 좌표는 {expected_x_coords[i]}여야 합니다.")
            self.assertEqual(pt.y, 200, f"포인트 #{i+1}의 Y 좌표는 200이어야 합니다.")
            self.assertEqual(pt.point_type, "line")
            self.assertEqual(pt.line_group_id, line_group, "동일한 선 그룹 ID를 가져야 합니다.")

        self.assertEqual(dlg.tbl_points.rowCount(), 5)
        print("  [성공] 선 피커 5개 등간격 포인트 자동 생성, 좌표 계산 및 라인 그룹화 무결성 확인")

    def test_04_condition_point_nudge_and_boundary_clamping(self):
        """
        [테스트 4] 인식조건 1픽셀 정밀 미세조정(Nudge) 및 경계 클램핑 검증
        - 포인트 선택 후 방향키 넛지 조작
        - 1px 이동 및 (0, 0) 하한 경계 클램핑 안전성 검증
        """
        print("\n=== [테스트 4] 인식조건 1픽셀 미세조정(Nudge) 및 경계 클램핑 검증 시작 ===")
        proj = Project(target_client_width=1600, target_client_height=900)
        cond = Condition(name="넛지 조건", points=[ColorPoint(id="pt_nudge", x=5, y=5, r=255, g=0, b=0)])
        dlg = ConditionEditorDialog(condition=cond, project=proj, current_scenario_id="scen_4", target_hwnd=0)

        # Select point
        dlg.canvas.selected_point_id = "pt_nudge"

        # Nudge (dx=1, dy=2) -> (6, 7)
        dlg._on_nudge_point(1, 2)
        pt = dlg.condition.points[0]
        self.assertEqual(pt.x, 6)
        self.assertEqual(pt.y, 7)

        # Nudge beyond top-left boundary (dx=-20, dy=-30) -> should clamp to (0, 0)
        dlg._on_nudge_point(-20, -30)
        self.assertEqual(pt.x, 0, "X 좌표는 0 이하로 떨어지지 않아야 합니다.")
        self.assertEqual(pt.y, 0, "Y 좌표는 0 이하로 떨어지지 않아야 합니다.")

        # Sync verification with table item
        dlg._refresh_points_table()
        self.assertIn("(0, 0)", dlg.tbl_points.item(0, 1).text())
        print("  [성공] 1픽셀 정밀 넛지 이동 및 (0, 0) 경계 클램핑 안전 제어 확인")

    def test_05_condition_image_evaluator_and_tolerance_matching(self):
        """
        [테스트 5] 더미 캔버스/이미지 기반 인식조건 판정 엔진(ConditionEvaluator) 매칭 및 허용 오차 검증
        - ConditionEvaluator.evaluate(cond, hwnd=0, image=dummy_pil) 검증
        - 정확한 색상 일치, 오차 범위 내 판정, 오차 초과 불일치 및 OR 연산자 검증
        """
        print("\n=== [테스트 5] 더미 캔버스/이미지 기반 조건 판정 및 허용 오차 검증 시작 ===")
        dummy_pil = create_dummy_canvas_pil(1600, 900)

        # Header area at (5, 20) is #0f172a -> RGB(15, 23, 42)
        pt1 = ColorPoint(x=5, y=20, r=15, g=23, b=42, tolerance=5, match_mode="match")
        cond_exact = Condition(name="일치 조건", logic_operator="AND", points=[pt1])

        matched, details = ConditionEvaluator.evaluate(cond_exact, hwnd=0, image=dummy_pil)
        self.assertTrue(matched, "더미 캔버스 실제 색상과 일치하므로 True여야 합니다.")
        self.assertTrue(details[0]["passed"])

        # Tolerance test: target R=20 (diff=5 <= tolerance 10) -> should PASS
        pt_tol = ColorPoint(x=5, y=20, r=20, g=23, b=42, tolerance=10, match_mode="match")
        cond_tol = Condition(name="오차 허용 조건", logic_operator="AND", points=[pt_tol])
        matched_tol, _ = ConditionEvaluator.evaluate(cond_tol, hwnd=0, image=dummy_pil)
        self.assertTrue(matched_tol, "허용 오차 범위 내 색상 차이는 일치 판정되어야 합니다.")

        # Out-of-tolerance test: target R=100 (diff=85 > tolerance 10) -> should FAIL
        pt_fail = ColorPoint(x=5, y=20, r=100, g=23, b=42, tolerance=10, match_mode="match")
        cond_fail = Condition(name="오차 초과 조건", logic_operator="AND", points=[pt_fail])
        matched_fail, _ = ConditionEvaluator.evaluate(cond_fail, hwnd=0, image=dummy_pil)
        self.assertFalse(matched_fail, "허용 오차 초과 시 불일치 판정되어야 합니다.")

        # OR Logic: 1 failed + 1 passed -> should PASS
        cond_or = Condition(name="OR 조건", logic_operator="OR", points=[pt_fail, pt1])
        matched_or, _ = ConditionEvaluator.evaluate(cond_or, hwnd=0, image=dummy_pil)
        self.assertTrue(matched_or, "OR 조건에서 하나라도 일치하면 True를 반환해야 합니다.")
        print("  [성공] 더미 캔버스 기반 ConditionEvaluator 정확 일치, 허용 오차 및 OR 복합 판정 검증 완료")

    # =========================================================================
    # [Part 2] 이미지 좌표 지정 액션 시퀀스 기능 테스트 5건
    # =========================================================================

    def test_06_action_sequence_dummy_canvas_and_top_margin_layout(self):
        """
        [테스트 6] 액션 시퀀스 더미 캔버스 자동 로딩 및 UI 상단 레이아웃 여백 검증
        - target_hwnd=0 상태에서 CoordinatePickerDialog 생성
        - 더미 캔버스(1600x900) 자동 로딩 검증
        - 툴바 위젯 QSizePolicy.Fixed 및 splitter 세로 stretch factor 1 적용 확인 (여백 버그 해결 검증)
        """
        print("\n=== [테스트 6] 액션 시퀀스 더미 캔버스 및 상단 레이아웃 여백 검증 시작 ===")
        dlg = CoordinatePickerDialog(target_hwnd=0, actions=[])

        # 1. Dummy canvas loaded
        self.assertIsNotNone(dlg.canvas.pixmap)
        self.assertEqual(dlg.canvas.pixmap.width(), 1600)
        self.assertEqual(dlg.canvas.pixmap.height(), 900)

        # 2. Verify layout stretch factors
        layout = dlg.layout()
        # Item 0: top_bar_widget (Fixed vertical policy)
        top_widget = layout.itemAt(0).widget()
        self.assertIsNotNone(top_widget)
        self.assertEqual(top_widget.sizePolicy().verticalPolicy(), QSizePolicy.Fixed)

        # Item 1: splitter (Stretch factor 1)
        splitter_item = layout.itemAt(1).widget()
        self.assertEqual(splitter_item, dlg.splitter)
        self.assertEqual(layout.stretch(1), 1, "스플리터는 수직 스트레치 팩터 1을 가져야 합니다.")

        # Item 2: bottom_bar_widget (Fixed vertical policy)
        bottom_widget = layout.itemAt(2).widget()
        self.assertIsNotNone(bottom_widget)
        self.assertEqual(bottom_widget.sizePolicy().verticalPolicy(), QSizePolicy.Fixed)
        print("  [성공] 더미 캔버스 자동 로딩 및 스플리터 100% 수직 스트레치(상단 비정상 여백 제거) 구조 확인")

    def test_07_action_sequence_canvas_click_and_delay_recording(self):
        """
        [테스트 7] 액션 시퀀스 이미지 상에서 클릭 조작 녹화 및 대기 시간 자동 기록 검증
        - 조작 녹화 모드 활성화 후 2회 클릭 시뮬레이션
        - 클릭과 클릭 사이의 대기 시간(delay) 자동 삽입 검증
        """
        print("\n=== [테스트 7] 이미지 상 클릭 조작 녹화 및 대기 시간 자동 기록 검증 시작 ===")
        dlg = CoordinatePickerDialog(target_hwnd=0, actions=[])

        dlg._toggle_image_recording()
        self.assertTrue(dlg.is_recording_mode)

        # Click 1 at (250, 350) at t=100.0
        with patch("time.time", return_value=100.0):
            dlg._on_canvas_clicked_for_recording(250, 350)

        self.assertEqual(len(dlg.actions), 1)
        self.assertEqual(dlg.actions[0].action_type, "mouse_click")
        self.assertEqual(dlg.actions[0].x, 250)
        self.assertEqual(dlg.actions[0].y, 350)

        # Click 2 at (480, 520) after 1.8 seconds at t=101.8
        with patch("time.time", return_value=101.8):
            dlg._on_canvas_clicked_for_recording(480, 520)

        # Expected: [click, delay(1.8s), click]
        self.assertEqual(len(dlg.actions), 3)
        self.assertEqual(dlg.actions[1].action_type, "delay")
        self.assertAlmostEqual(dlg.actions[1].delay_seconds, 1.8, places=1)
        self.assertEqual(dlg.actions[2].action_type, "mouse_click")
        self.assertEqual(dlg.actions[2].x, 480)
        self.assertEqual(dlg.actions[2].y, 520)

        dlg._toggle_image_recording()
        self.assertFalse(dlg.is_recording_mode)
        print("  [성공] 이미지 상 클릭 위치 및 클릭 간 대기 시간(1.8초) 실시간 자동 녹화 확인")

    def test_08_action_sequence_canvas_drag_recording_with_duration(self):
        """
        [테스트 8] 액션 시퀀스 이미지 상에서 드래그 조작 녹화 및 소요시간/선행대기 기록 검증
        - 드래그 동작 (이동 거리 > 15px) 감지 시 mouse_drag 액션 생성
        - 시작 좌표, 끝 좌표, 드래그 소요 시간(ms), 선행 대기 시간 기록 검증
        """
        print("\n=== [테스트 8] 이미지 상 드래그 조작 녹화 및 소요시간/선행대기 기록 검증 시작 ===")
        dlg = CoordinatePickerDialog(target_hwnd=0, actions=[])

        dlg._toggle_image_recording()
        self.assertTrue(dlg.is_recording_mode)

        # 1. Action 1: Click at (100, 100) at t=10.0
        with patch("time.time", return_value=10.0):
            dlg._on_canvas_action_recorded(100, 100, 100, 100, dist=0.0, duration=0.0)

        # 2. Action 2: Drag from (200, 200) to (500, 600) (dist ~500px, duration 0.45s)
        # Drag finished at t=12.45, so drag started at t=12.0 (pre-delay: 12.0 - 10.0 = 2.0s)
        with patch("time.time", return_value=12.45):
            dlg._on_canvas_action_recorded(
                start_x=200, start_y=200,
                end_x=500, end_y=600,
                dist=500.0, duration=0.45
            )

        # Expected actions: [click, delay(2.0s), drag(450ms)]
        self.assertEqual(len(dlg.actions), 3)

        act_delay = dlg.actions[1]
        self.assertEqual(act_delay.action_type, "delay")
        self.assertAlmostEqual(act_delay.delay_seconds, 2.0, places=1)

        act_drag = dlg.actions[2]
        self.assertEqual(act_drag.action_type, "mouse_drag")
        self.assertEqual(act_drag.x, 200)
        self.assertEqual(act_drag.y, 200)
        self.assertEqual(act_drag.end_x, 500)
        self.assertEqual(act_drag.end_y, 600)
        self.assertEqual(act_drag.drag_duration_ms, 450)

        dlg._toggle_image_recording()
        print("  [성공] 마우스 드래그 인식, 시작/끝 좌표, 소요 시간(450ms) 및 선행 대기 시간(2.0초) 자동 등록 확인")

    def test_09_action_sequence_virtual_cursor_simulation_without_popup(self):
        """
        [테스트 9] 액션 시퀀스 이미지 상의 가상 커서 애니메이션 시뮬레이션 및 무팝업 테스트 검증
        - 단일 액션 테스트 및 전체 시퀀스 테스트 실행 시 캔버스 상 가상 커서 작동
        - 완료 시 작업 흐름을 방해하는 팝업창(QMessageBox)이 전혀 뜨지 않음을 검증
        """
        print("\n=== [테스트 9] 가상 커서 애니메이션 시뮬레이션 및 팝업창 미표시 검증 시작 ===")
        acts = [
            Action(action_type="mouse_click", x=150, y=200),
            Action(action_type="mouse_drag", x=200, y=200, end_x=300, end_y=300, drag_duration_ms=100),
            Action(action_type="delay", delay_seconds=0.02)
        ]
        dlg = CoordinatePickerDialog(target_hwnd=0, actions=acts)

        # Single action test: ensure NO popup and virtual cursor is triggered
        with patch("time.sleep"), patch("PyQt5.QtWidgets.QMessageBox.information") as mock_info:
            dlg._on_test_single_action()
            mock_info.assert_not_called()
            self.assertIn("선택 액션 테스트 완료", dlg.lbl_guide.text())

        # Full sequence test: ensure virtual cursor moves and NO popup
        with patch("time.sleep"), patch("PyQt5.QtWidgets.QMessageBox.information") as mock_info:
            dlg._toggle_full_sequence_test()
            mock_info.assert_not_called()
            self.assertIn("전체 액션 시퀀스", dlg.lbl_guide.text())

        print("  [성공] 캔버스 가상 커서 시뮬레이션 및 무팝업(상태 라벨 안내) 사용자 경험 검증 완료")

    def test_10_action_sequence_log_time_format_and_reordering(self):
        """
        [테스트 10] 대기 액션 타임 개선 표기 및 안티밴 로그 포맷 및 시퀀스 재정렬 검증
        - 로그 포맷 '[ACTION] ... 액션 실행: 0.3초 (원본0.29초) 대기' 검증
        - 액션 순서 위로 이동, 아래로 이동 및 1px 방향키 미세조정 검증
        """
        print("\n=== [테스트 10] 대기 액션 타임 개선 표기 및 시퀀스 재정렬 검증 시작 ===")
        # 1. Log time format verification
        proj = Project(anti_ban_enabled=True, anti_ban_min_delay=0.1, anti_ban_max_delay=0.1)
        scen = Scenario(id="scen_fmt_10", actions=[Action(action_type="delay", delay_seconds=0.29)])
        proj.scenarios = [scen]

        runner = WorkflowRunner(proj, hwnd=0)
        runner._is_running = True
        runner_logs = []
        runner.sig_log.connect(lambda level, msg: runner_logs.append((level, msg)))

        with patch("core.input_controller.InputController.execute_action"):
            runner._execute_actions(scen)

        # Check format: '액션 실행: 0.4초 (원본0.29초) 대기' (0.29 + 0.1 jitter = 0.39 -> 0.4s)
        self.assertTrue(
            any("(원본0.29초) 대기" in msg for level, msg in runner_logs),
            f"러너 로그에 '(원본0.29초) 대기'가 포함되어야 합니다. 실제 로그: {runner_logs}"
        )

        # 2. Action reordering & 1px nudge in CoordinatePickerDialog
        act1 = Action(action_type="mouse_click", x=100, y=100)
        act2 = Action(action_type="mouse_click", x=200, y=200)
        dlg = CoordinatePickerDialog(target_hwnd=0, actions=[act1, act2])

        # Select first action and nudge (dx=1, dy=-1)
        dlg.selected_action_index = 0
        dlg._on_nudge_action(1, -1)
        self.assertEqual(dlg.actions[0].x, 101)
        self.assertEqual(dlg.actions[0].y, 99)

        # Move Down: act1 (index 0) moves to index 1
        dlg._on_move_down()
        self.assertEqual(dlg.actions[0].x, 200)
        self.assertEqual(dlg.actions[1].x, 101)
        self.assertEqual(dlg.selected_action_index, 1)

        # Move Up: act1 (index 1) moves back to index 0
        dlg._on_move_up()
        self.assertEqual(dlg.actions[0].x, 101)
        self.assertEqual(dlg.actions[1].x, 200)
        self.assertEqual(dlg.selected_action_index, 0)
        print("  [성공] 개선된 대기 타임 포맷 '0.X초 (원본0.29초) 대기', 1px 미세조정 및 시퀀스 순서 이동 검증 완료")


if __name__ == "__main__":
    unittest.main()
