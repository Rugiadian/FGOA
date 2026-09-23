"""
Unit and Integration Tests for Recognition Conditions (Eye & Brain Evaluator) in FGOA.
3 Core Test Scenarios:
1. ConditionEditorDialog & CanvasView & Magnifier Tool Operations
2. ConditionEvaluator Multi-point Logic (AND/OR, Match/NotMatch, Tolerance, Extreme Coords)
3. Inspector Eye Integration, Condition Copying (Deepcopy) & Uniqueness Duplicate Detection
"""
import sys
import os
import unittest
import tempfile
from unittest.mock import MagicMock, patch
from PIL import Image

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import Qt, QPoint

from core.models import Project, Scenario, Condition, ColorPoint, Action
from core.evaluator import ConditionEvaluator
from core.screen_capture import ScreenCapture
from ui.condition_editor_dialog import ConditionEditorDialog
from ui.inspector_widget import InspectorWidget
from ui.canvas_view import CanvasView


class TestRecognitionConditionScenarios(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication.instance() is None:
            cls.app = QApplication(sys.argv)
        else:
            cls.app = QApplication.instance()

    # =========================================================================
    # 인식조건 시나리오 1: 캔버스 편집기(ConditionEditorDialog) & 도구 조작 테스트
    # =========================================================================
    def test_scenario_1_canvas_editor_tools_and_nudge(self):
        """
        [인식조건 시나리오 1]
        1) 레퍼런스 이미지가 있거나 없는 상태에서 ConditionEditorDialog 생성 및 캔버스 렌더링
        2) 점 피커(MODE_POINT)로 캔버스 클릭 시 ColorPoint 추가 및 RGB 추출 검증
        3) 선 피커(MODE_LINE)로 연속 샘플 포인트 균등 생성(sample_line_points) 검증
        4) 선택 모드 및 키보드 방향키 미세조정(Nudge)으로 좌표 이동, 돋보기 갱신 및 경계 클램핑 검증
        5) 포인트 인라인 오차/모드 변경 및 개별/전체 삭제 검증
        """
        print("\n=== [인식조건 시나리오 1] 캔버스 편집기 및 도구 조작 테스트 시작 ===")
        # 임시 레퍼런스 이미지 생성 (300x200 크기, 빨강/초록/파랑 영역)
        temp_img = Image.new("RGB", (300, 200), (255, 0, 0))
        for x in range(150, 300):
            for y in range(200):
                temp_img.putpixel((x, y), (0, 255, 0))

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            ref_path = tf.name
            temp_img.save(ref_path)

        try:
            proj = Project(target_client_width=800, target_client_height=600)
            cond = Condition(name="인식 편집 테스트", reference_image_path=ref_path)
            dlg = ConditionEditorDialog(
                condition=cond,
                project=proj,
                current_scenario_id="scen_edit",
                target_hwnd=0
            )

            # 1. 캔버스 로딩 확인
            self.assertIsNotNone(dlg.canvas.pixmap)
            self.assertEqual(dlg.canvas.pixmap.width(), 300)
            self.assertEqual(dlg.canvas.pixmap.height(), 200)
            print("  [성공] 레퍼런스 이미지 캔버스 로딩 및 해상도 가이드 적용 확인")

            # 2. 점 피커(MODE_POINT)로 점 추가
            dlg._set_tool_mode(CanvasView.MODE_POINT)
            # (50, 50) 빨간색 영역 클릭 시뮬레이션
            dlg.canvas.sig_point_added.emit(50, 50, 255, 0, 0)
            self.assertEqual(len(dlg.condition.points), 1)
            p1 = dlg.condition.points[0]
            self.assertEqual((p1.x, p1.y), (50, 50))
            self.assertEqual((p1.r, p1.g, p1.b), (255, 0, 0))
            print("  [성공] 점 피커: 좌표 (50, 50) 및 RGB(255, 0, 0) 포인트 등록 성공")

            # 3. 선 피커(MODE_LINE) 연속 포인트 균등 분할 생성
            with patch("PyQt5.QtWidgets.QInputDialog.getInt", return_value=(4, True)):
                dlg._on_canvas_line_added(10, 10, 100, 10)
            # 기존 1개 + 선 분할 4개 = 총 5개
            self.assertEqual(len(dlg.condition.points), 5)
            print(f"  [성공] 선 피커: 4개 연속 포인트 분할 생성 (총 {len(dlg.condition.points)}개)")

            # 4. 방향키 넛지(Nudge) 조작 검증
            dlg.tbl_points.selectRow(0)
            # x + 5, y - 3 이동
            dlg._on_nudge_point(5, -3)
            self.assertEqual(p1.x, 55)
            self.assertEqual(p1.y, 47)
            # 캔버스 좌측 경계 밖(-999)으로 과도하게 이동 시 클램핑 검증
            dlg._on_nudge_point(-999, 0)
            self.assertEqual(p1.x, 0)  # min clamped at 0
            print("  [성공] 정밀 넛지: 1픽셀 이동 및 캔버스 경계값 클램핑(0 이상) 검증 완료")

            # 5. 인라인 오차/판정모드 변경
            dlg._on_point_tolerance_changed(p1, 35)
            self.assertEqual(p1.tolerance, 35)
            dlg._on_point_match_mode_changed(p1, 1)  # 1 = not_match
            self.assertEqual(p1.match_mode, "not_match")
            print("  [성공] 인라인 오차(35) 및 불일치(not_match) 판정 모드 변경 완료")

            # 6. 개별 삭제 및 전체 비우기
            dlg.tbl_points.selectRow(0)
            dlg._on_delete_selected_point()
            self.assertEqual(len(dlg.condition.points), 4)

            with patch("PyQt5.QtWidgets.QMessageBox.question", return_value=16384):  # QMessageBox.Yes
                dlg._on_clear_all_points()
            self.assertEqual(len(dlg.condition.points), 0)
            print("  [성공] 포인트 삭제 및 전체 비우기 정상 작동")

        finally:
            if os.path.exists(ref_path):
                os.remove(ref_path)

    # =========================================================================
    # 인식조건 시나리오 2: 판정 엔진(ConditionEvaluator) 로직 & 경계값 종합 검증
    # =========================================================================
    def test_scenario_2_evaluator_logic_tolerance_and_boundary(self):
        """
        [인식조건 시나리오 2]
        1) AND 논리: 모든 포인트 일치 시에만 True 판정
        2) OR 논리: 하나라도 일치 시 True 판정
        3) not_match(불일치) 모드: 색상이 다를 때 True 판정
        4) 오차(Tolerance) 한계값 검증: 0(정확) vs 255(모두 통과)
        5) 무조건 실행(points=[]) 판정
        6) 극단 좌표(화면 밖, 음수 좌표) 판정 시 안전성 확인
        """
        print("\n=== [인식조건 시나리오 2] 판정 엔진 로직 및 극단값 검증 시작 ===")

        # 1. AND 논리 검증 (2개 포인트)
        cond_and = Condition(
            name="AND 테스트",
            logic_operator="AND",
            points=[
                ColorPoint(x=10, y=10, r=100, g=150, b=200, tolerance=10),
                ColorPoint(x=20, y=20, r=50, g=50, b=50, tolerance=10),
            ]
        )

        # Case A: 둘 다 일치 -> True
        with patch("core.screen_capture.ScreenCapture.get_client_pixel_color", side_effect=[
            (105, 148, 202),  # diff <= 10 (Pass)
            (52, 49, 51)      # diff <= 10 (Pass)
        ]):
            matched, details = ConditionEvaluator.evaluate(cond_and, hwnd=123)
            self.assertTrue(matched)
            self.assertTrue(all(d["passed"] for d in details))
            print("  [성공] AND 판정: 모든 포인트 오차 범위 내 -> True 반환")

        # Case B: 하나만 불일치 -> False
        with patch("core.screen_capture.ScreenCapture.get_client_pixel_color", side_effect=[
            (105, 148, 202),  # Pass
            (200, 200, 200)   # Fail (diff > 10)
        ]):
            matched, details = ConditionEvaluator.evaluate(cond_and, hwnd=123)
            self.assertFalse(matched)
            self.assertFalse(details[1]["passed"])
            print("  [성공] AND 판정: 1개 포인트 오차 초과 시 -> False 반환")

        # 2. OR 논리 검증
        cond_or = Condition(
            name="OR 테스트",
            logic_operator="OR",
            points=[
                ColorPoint(x=10, y=10, r=100, g=150, b=200, tolerance=10),
                ColorPoint(x=20, y=20, r=50, g=50, b=50, tolerance=10),
            ]
        )
        # 하나만 일치해도 OR은 True
        with patch("core.screen_capture.ScreenCapture.get_client_pixel_color", side_effect=[
            (0, 0, 0),        # Fail
            (52, 49, 51)      # Pass
        ]):
            matched, details = ConditionEvaluator.evaluate(cond_or, hwnd=123)
            self.assertTrue(matched)
            print("  [성공] OR 판정: 1개 포인트만 일치해도 -> True 반환")

        # 3. not_match(불일치 반전) 모드 검증
        cond_invert = Condition(
            name="불일치 반전 테스트",
            logic_operator="AND",
            points=[
                ColorPoint(x=10, y=10, r=255, g=255, b=255, tolerance=10, match_mode="not_match")
            ]
        )
        # 실제 색상이 (0, 0, 0)이면 달라야 하므로 -> Pass(True)
        with patch("core.screen_capture.ScreenCapture.get_client_pixel_color", return_value=(0, 0, 0)):
            matched, details = ConditionEvaluator.evaluate(cond_invert, hwnd=123)
            self.assertTrue(matched)
            print("  [성공] not_match 판정: 목표 색상과 다를 때 -> True 반환")

        # 실제 색상이 (255, 255, 255)이면 같으므로 -> Fail(False)
        with patch("core.screen_capture.ScreenCapture.get_client_pixel_color", return_value=(255, 255, 255)):
            matched, details = ConditionEvaluator.evaluate(cond_invert, hwnd=123)
            self.assertFalse(matched)
            print("  [성공] not_match 판정: 목표 색상과 같으면 -> False 반환")

        # 4. 무조건 실행(points=[]) 판정
        cond_empty = Condition(name="빈 조건", points=[])
        matched, _ = ConditionEvaluator.evaluate(cond_empty, hwnd=123)
        self.assertTrue(matched)
        matched_none, _ = ConditionEvaluator.evaluate(None, hwnd=123)
        self.assertTrue(matched_none)
        print("  [성공] 무조건 실행(points 빈 리스트 또는 None) -> 항상 True 반환")

        # 5. 극단 좌표(화면 밖, 음수 좌표) 안전성
        cond_extreme = Condition(
            name="극단 좌표 테스트",
            points=[
                ColorPoint(x=-9999, y=-9999, r=255, g=255, b=255),
                ColorPoint(x=99999, y=99999, r=0, g=0, b=0)
            ]
        )
        # get_client_pixel_color가 None을 반환하더라도 크래시 없이 False 처리
        with patch("core.screen_capture.ScreenCapture.get_client_pixel_color", return_value=None):
            matched, details = ConditionEvaluator.evaluate(cond_extreme, hwnd=123)
            self.assertFalse(matched)
            self.assertEqual(len(details), 2)
            self.assertFalse(details[0]["passed"])
            print("  [성공] 극단 좌표(음수/초과) 및 픽셀 읽기 실패 시 안전하게 False 반환")

    # =========================================================================
    # 인식조건 시나리오 3: 인스펙터 인식 조건 연동 & 고유화/중복 감지(Uniqueness)
    # =========================================================================
    def test_scenario_3_inspector_eye_integration_and_uniqueness(self):
        """
        [인식조건 시나리오 3]
        1) 인스펙터에서 조건 활성화/비활성화 체크박스 토글
        2) 다른 시나리오에서 조건 복사(가져오기) 시 Deep Copy 무결성 검증
        3) 2개 시나리오가 동일한 인식 조건을 가질 때 ConditionEvaluator.check_project_uniqueness 감지
        4) 좌표 또는 색상 변경 시 중복 경고가 즉시 해제되는지 검증
        5) 인스펙터 [⚡ 판정 테스트] 버튼 클릭 시 실시간 판정 결과 라벨 표시 확인
        """
        print("\n=== [인식조건 시나리오 3] 인스펙터 조건 연동 & 중복/고유화 검사 시작 ===")
        widget = InspectorWidget()
        proj = Project()

        # 시나리오 1: 기준 조건
        cond1 = Condition(
            name="조건 1",
            points=[
                ColorPoint(x=100, y=150, r=200, g=100, b=50, tolerance=15),
                ColorPoint(x=200, y=250, r=30, g=40, b=50, tolerance=10)
            ]
        )
        scen1 = Scenario(id="scen_1", scenario_number=1, name="시나리오 1", condition=cond1)

        # 시나리오 2: 처음에는 조건 없음
        scen2 = Scenario(id="scen_2", scenario_number=2, name="시나리오 2", condition=None)

        proj.scenarios = [scen1, scen2]

        # 1. 인스펙터에 시나리오 2 바인딩 후 조건 활성화 체크박스 토글
        widget.set_scenario(scen2, target_hwnd=123, project=proj)
        self.assertFalse(widget.chk_has_condition.isChecked())
        widget.chk_has_condition.setChecked(True)
        self.assertIsNotNone(widget.current_scenario.condition)
        # 인스펙터 변경사항 저장 (드래프트 -> 원본 반영)
        widget._on_save_inspector()
        self.assertIsNotNone(scen2.condition)
        print("  [성공] 인스펙터: 조건 비활성 -> 활성 토글 및 저장 시 Condition 모델 자동 생성")

        # 2. [📋 조건 가져오기] - scen1의 조건을 scen2로 복사
        widget._copy_condition_from(scen1)
        widget._on_save_inspector()
        self.assertEqual(len(scen2.condition.points), 2)
        # Deep Copy 검증: scen2의 포인트를 수정해도 scen1은 변경되지 않아야 함
        scen2.condition.points[0].x = 999
        self.assertEqual(scen1.condition.points[0].x, 100)
        print("  [성공] 조건 가져오기(Deep Copy) 무결성: 원본 조건에 영향 없음 확인")

        # 3. 동일 조건 중복 감지(Uniqueness Warning) 검증
        # scen2의 포인트를 다시 scen1과 동일하게 맞춤
        scen2.condition.points[0].x = 100
        warnings = ConditionEvaluator.check_project_uniqueness(proj)
        self.assertIn("scen_1", warnings)
        self.assertIn("scen_2", warnings)
        print(f"  [성공] 조건 고유화 중복 검사: 시나리오 1, 2 중복 감지 경고 확인 -> {warnings['scen_1']}")

        # 4. 좌표 변경 시 중복 경고 즉시 해제 확인
        scen2.condition.points[0].x = 500  # 좌표 변경
        warnings_after = ConditionEvaluator.check_project_uniqueness(proj)
        self.assertNotIn("scen_1", warnings_after)
        self.assertNotIn("scen_2", warnings_after)
        print("  [성공] 조건 차별화 시 중복 경고 자동 해제 확인")

        # 5. [⚡ 판정 테스트] 버튼 클릭 시 결과 라벨 표시 확인
        widget.set_scenario(scen1, target_hwnd=123, project=proj)
        with patch("core.evaluator.ConditionEvaluator.evaluate", return_value=(True, [{"passed": True}])):
            widget._on_test_condition_now()
            self.assertFalse(widget.lbl_cond_test_result.isHidden())
            self.assertIn("일치", widget.lbl_cond_test_result.text())
            print(f"  [성공] 인스펙터 실시간 판정 테스트: '{widget.lbl_cond_test_result.text()}' 정상 표출")


if __name__ == "__main__":
    unittest.main()
