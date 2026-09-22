"""
Integration and regression tests for new features:
1. Scenario Loop Nodes & Condition Break
2. Action Sequence Recorder
3. Reference Coordinate Picker
4. Reference Gallery & Usage Detection
5. Scenario List Hierarchy Formatting
"""
import unittest
import time
from unittest.mock import MagicMock, patch
from core.models import Project, Scenario, Condition, ColorPoint, Action
from core.runner import WorkflowRunner
from core.recorder import ActionRecorder
from ui.reference_gallery_dialog import ReferenceGalleryDialog


class TestNewFeatures(unittest.TestCase):

    def test_loop_node_count_execution(self):
        """Test loop node executes the specified count of iterations then completes."""
        proj = Project(name="Loop Count Test", loop_count=1)
        s_start = Scenario(id="l_start", scenario_number=1, name="루프시작", node_type="loop_start", loop_mode="count", loop_count=2)
        s_work = Scenario(id="l_work", scenario_number=2, name="작업", node_type="normal", actions=[Action(action_type="delay", delay_seconds=0.01)])
        s_end = Scenario(id="l_end", scenario_number=3, name="루프끝", node_type="loop_end", loop_target_id="l_start")
        s_after = Scenario(id="l_after", scenario_number=4, name="루프이후", node_type="normal")
        proj.scenarios = [s_start, s_work, s_end, s_after]

        runner = WorkflowRunner(project=proj, hwnd=12345)
        # Mock window manager so it doesn't fail on hwnd
        with patch("core.runner.WindowManager.get_window_info") as mock_win:
            mock_win.return_value = MagicMock(title="TestWin", client_width=800, client_height=600)
            runner.run()

        # Should finish cleanly
        self.assertFalse(runner._is_running)

    def test_loop_node_until_match_break(self):
        """Test until_match loop exits when condition matches."""
        proj = Project(name="Loop Break Test", loop_count=1)
        cond = Condition(points=[ColorPoint(x=10, y=10, r=255, g=0, b=0)])
        s_start = Scenario(
            id="l_start", scenario_number=1, name="루프시작",
            node_type="loop_start", loop_mode="until_match", loop_count=10,
            condition=cond
        )
        s_work = Scenario(id="l_work", scenario_number=2, name="작업", node_type="normal")
        s_end = Scenario(id="l_end", scenario_number=3, name="루프끝", node_type="loop_end", loop_target_id="l_start")
        proj.scenarios = [s_start, s_work, s_end]

        runner = WorkflowRunner(project=proj, hwnd=12345)
        with patch("core.runner.WindowManager.get_window_info") as mock_win, \
             patch("core.runner.ConditionEvaluator.evaluate") as mock_eval:
            mock_win.return_value = MagicMock(title="TestWin", client_width=800, client_height=600)
            # Condition matches on first evaluation
            mock_eval.return_value = (True, {s_start.condition.points[0].id: True})
            runner.run()

        self.assertFalse(runner._is_running)

    def test_action_recorder_delay_insert(self):
        """Test ActionRecorder manual delay insertion and action models."""
        recorder = ActionRecorder(target_hwnd=0)
        recorder.insert_delay(1.5)
        self.assertEqual(len(recorder.recorded_actions), 1)
        self.assertEqual(recorder.recorded_actions[0].action_type, "delay")
        self.assertEqual(recorder.recorded_actions[0].delay_seconds, 1.5)

    def test_reference_gallery_usage_detection(self):
        """Test that ReferenceGallery correctly detects usages across Eye and Hand."""
        proj = Project(name="Gallery Detect Test")
        ref_image = "C:/refs/test_card.png"
        s1 = Scenario(
            id="s1", scenario_number=1, name="카드 선택",
            condition=Condition(reference_image_path=ref_image, points=[ColorPoint(x=50, y=50)]),
            actions=[Action(action_type="mouse_click", x=200, y=300)]
        )
        proj.scenarios = [s1]

        usages = ReferenceGalleryDialog.compute_image_usages(ref_image, proj)
        self.assertEqual(len(usages), 2)  # 1 Eye condition + 1 Hand action
        types = [u["type"] for u in usages]
        self.assertIn("👁️ Eye 색상 조건", types)
        self.assertIn("✋ Hand 액션", types)

    def test_nested_loop_hierarchy_depths(self):
        """Test nested loops compute correct hierarchy depths."""
        proj = Project(name="Nested Loop Test")
        s1 = Scenario(id="s1", name="루프1 시작", node_type="loop_start")
        s2 = Scenario(id="s2", name="루프2 시작", node_type="loop_start")
        s3 = Scenario(id="s3", name="내부작업")
        s4 = Scenario(id="s4", name="루프2 종료", node_type="loop_end")
        s5 = Scenario(id="s5", name="루프1 종료", node_type="loop_end")
        proj.scenarios = [s1, s2, s3, s4, s5]

        depths = proj.compute_hierarchy_depths()
        self.assertEqual(depths, [0, 1, 2, 1, 0])

    def test_single_action_dialog_get_action(self):
        """Test SingleActionDialog has get_action method returning the action."""
        from PyQt5.QtWidgets import QApplication
        import sys
        app = QApplication.instance() or QApplication(sys.argv)
        from ui.action_editor_dialog import SingleActionDialog
        act = Action(action_type="mouse_click", x=123, y=456)
        dlg = SingleActionDialog(action=act)
        res = dlg.get_action()
        self.assertEqual(res.x, 123)
        self.assertEqual(res.y, 456)

    def test_inspector_full_sequence_test(self):
        """Test InspectorWidget full action sequence test execution."""
        from PyQt5.QtWidgets import QApplication
        import sys
        app = QApplication.instance() or QApplication(sys.argv)
        from ui.inspector_widget import InspectorWidget
        proj = Project(name="Sequence Test")
        scen = Scenario(
            id="s1", name="시퀀스",
            actions=[
                Action(action_type="mouse_click", x=10, y=20),
                Action(action_type="delay", delay_seconds=0.01),
                Action(action_type="key_press", key="Enter")
            ]
        )
        proj.scenarios = [scen]
        insp = InspectorWidget()
        insp.set_scenario(scen, 12345, proj)

        with patch("core.input_controller.InputController.execute_action") as mock_exec:
            insp._on_test_all_actions_now()
            self.assertEqual(mock_exec.call_count, 3)

    def test_action_recorder_wait_time_between_clicks(self):
        """Test ActionRecorder automatically records delay actions between clicks."""
        recorder = ActionRecorder(target_hwnd=123)
        recorder._last_event_time = 100.0

        with patch("win32gui.IsWindow", return_value=True), \
             patch("win32gui.ScreenToClient", side_effect=lambda hwnd, pt: pt), \
             patch("win32gui.GetClientRect", return_value=(0, 0, 1920, 1080)):

            # First click at t=100.5
            with patch("time.time", return_value=100.5):
                recorder._handle_mouse_release((100, 100), (100, 100), "left", 0.05)

            self.assertEqual(len(recorder.recorded_actions), 1)
            self.assertEqual(recorder.recorded_actions[0].action_type, "mouse_click")
            self.assertEqual(recorder.recorded_actions[0].x, 100)

            # Second click at t=102.3 (1.8s wait time)
            with patch("time.time", return_value=102.3):
                recorder._handle_mouse_release((200, 250), (200, 250), "left", 0.05)

            # Expect: [click, delay(1.8s), click]
            self.assertEqual(len(recorder.recorded_actions), 3)
            self.assertEqual(recorder.recorded_actions[1].action_type, "delay")
            self.assertAlmostEqual(recorder.recorded_actions[1].delay_seconds, 1.8, places=1)
            self.assertEqual(recorder.recorded_actions[2].action_type, "mouse_click")
            self.assertEqual(recorder.recorded_actions[2].x, 200)
            self.assertEqual(recorder.recorded_actions[2].y, 250)

    def test_anti_ban_coordinate_offset_and_variable_delay(self):
        """Test anti-ban random coordinate offset (+-10px) and variable delay (0.15~1.0s)."""
        from core.input_controller import InputController
        act = Action(action_type="mouse_click", x=500, y=300)

        with patch("core.input_controller.InputController.click_at") as mock_click, \
             patch("time.sleep") as mock_sleep:

            InputController.execute_action(act, hwnd=123, apply_anti_ban=True, offset_range=10, min_delay=0.15, max_delay=1.0)

            self.assertTrue(mock_click.called)
            called_x = mock_click.call_args[1]["rel_x"]
            called_y = mock_click.call_args[1]["rel_y"]

            # Offset must be within +-10 pixels
            self.assertTrue(490 <= called_x <= 510)
            self.assertTrue(290 <= called_y <= 310)

            # Variable sleep must be called with value in 0.15~1.0s
            self.assertTrue(mock_sleep.called)
            slept_time = mock_sleep.call_args[0][0]
            self.assertTrue(0.15 <= slept_time <= 1.0)

    def test_project_anti_ban_serialization(self):
        """Test Project to_dict and from_dict preserve anti_ban settings."""
        proj = Project(anti_ban_enabled=True, anti_ban_offset=10, anti_ban_min_delay=0.15, anti_ban_max_delay=1.0)
        data = proj.to_dict()
        self.assertTrue(data["anti_ban_enabled"])
        self.assertEqual(data["anti_ban_offset"], 10)
        self.assertEqual(data["anti_ban_min_delay"], 0.15)
        self.assertEqual(data["anti_ban_max_delay"], 1.0)

        loaded = Project.from_dict(data)
        self.assertTrue(loaded.anti_ban_enabled)
        self.assertEqual(loaded.anti_ban_offset, 10)
        self.assertEqual(loaded.anti_ban_min_delay, 0.15)
        self.assertEqual(loaded.anti_ban_max_delay, 1.0)

    def test_coordinate_picker_dialog_actions_table_and_view(self):
        """Test CoordinatePickerDialog right frame action sequence list and view features."""
        from PyQt5.QtWidgets import QApplication
        import sys
        app = QApplication.instance() or QApplication(sys.argv)
        from ui.coordinate_picker_dialog import CoordinatePickerDialog

        acts = [
            Action(action_type="mouse_click", x=100, y=200),
            Action(action_type="delay", delay_seconds=0.5),
            Action(action_type="mouse_drag", x=300, y=400, end_x=500, end_y=600)
        ]
        dlg = CoordinatePickerDialog(target_hwnd=0, actions=acts, selected_action_index=0)

        # 1. Action Sequence table in right frame
        self.assertEqual(dlg.tbl_actions.rowCount(), 3)
        self.assertEqual(len(dlg.get_actions()), 3)

        # 2. View adjustment controls (Fit to view, 1:1)
        dlg.canvas.set_target_resolution(1600, 900)
        dlg.canvas.fit_to_view()
        self.assertTrue(dlg.canvas.zoom > 0)
        dlg.canvas.zoom_100()
        self.assertEqual(dlg.canvas.zoom, 1.0)

        # 3. Nudge
        dlg.canvas.nudge_selected_action(1, -1)
        coords = dlg.get_coordinates()
        self.assertEqual(coords[0], 101)
        self.assertEqual(coords[1], 199)

    def test_action_sequence_log_anti_ban_time(self):
        """Test that runner logs specified original time and anti-ban time."""
        from core.runner import WorkflowRunner
        proj = Project(anti_ban_enabled=True, anti_ban_min_delay=0.2, anti_ban_max_delay=0.5)
        scen = Scenario(id="scen_log", actions=[Action(action_type="delay", delay_seconds=1.0)])
        proj.scenarios = [scen]

        runner = WorkflowRunner(proj, hwnd=0)
        runner._is_running = True
        logs = []
        runner.sig_log.connect(lambda level, msg: logs.append(msg))

        with patch("core.input_controller.InputController.execute_action"):
            runner._execute_actions(scen)

        self.assertTrue(any("액션 실행:" in m and "(원본1.00초) 대기" in m for m in logs))

    def test_coordinate_picker_image_recording_without_target_app(self):
        """Test recording actions directly on reference image without target app."""
        from PyQt5.QtWidgets import QApplication
        import sys
        app = QApplication.instance() or QApplication(sys.argv)
        from ui.coordinate_picker_dialog import CoordinatePickerDialog
        dlg = CoordinatePickerDialog(target_hwnd=0, actions=[])

        # Start image recording
        dlg._toggle_image_recording()
        self.assertTrue(dlg.is_recording_mode)

        # 1st click at (150, 250)
        with patch("time.time", return_value=10.0):
            dlg._on_canvas_clicked_for_recording(150, 250)

        self.assertEqual(len(dlg.actions), 1)
        self.assertEqual(dlg.actions[0].action_type, "mouse_click")
        self.assertEqual(dlg.actions[0].x, 150)
        self.assertEqual(dlg.actions[0].y, 250)

        # 2nd click at (400, 500) after 1.5s
        with patch("time.time", return_value=11.5):
            dlg._on_canvas_clicked_for_recording(400, 500)

        # Expect: [click, delay(1.5s), click]
        self.assertEqual(len(dlg.actions), 3)
        self.assertEqual(dlg.actions[1].action_type, "delay")
        self.assertAlmostEqual(dlg.actions[1].delay_seconds, 1.5, places=1)
        self.assertEqual(dlg.actions[2].action_type, "mouse_click")
        self.assertEqual(dlg.actions[2].x, 400)
        self.assertEqual(dlg.actions[2].y, 500)

        # Stop recording
        dlg._toggle_image_recording()
        self.assertFalse(dlg.is_recording_mode)

    def test_coordinate_picker_virtual_cursor_and_no_popup(self):
        """Test virtual cursor simulation and verify no popup dialog is shown."""
        from PyQt5.QtWidgets import QApplication
        import sys
        app = QApplication.instance() or QApplication(sys.argv)
        from ui.coordinate_picker_dialog import CoordinatePickerDialog
        acts = [
            Action(action_type="mouse_click", x=200, y=300),
            Action(action_type="delay", delay_seconds=0.01)
        ]
        dlg = CoordinatePickerDialog(target_hwnd=0, actions=acts)

        # Test single action: check virtual cursor and NO QMessageBox
        with patch("PyQt5.QtWidgets.QMessageBox.information") as mock_msg:
            dlg._on_test_single_action()
            mock_msg.assert_not_called()
            self.assertIn("선택 액션 테스트 완료", dlg.lbl_guide.text())

        # Test full sequence: check virtual cursor and NO QMessageBox
        with patch("PyQt5.QtWidgets.QMessageBox.information") as mock_msg:
            dlg._toggle_full_sequence_test()
            mock_msg.assert_not_called()
            self.assertIn("전체 액션 시퀀스", dlg.lbl_guide.text())

    def test_drag_recording_on_image(self):
        """Test recording mouse drag action directly on canvas."""
        from PyQt5.QtWidgets import QApplication
        import sys
        app = QApplication.instance() or QApplication(sys.argv)
        from ui.coordinate_picker_dialog import CoordinatePickerDialog
        dlg = CoordinatePickerDialog(target_hwnd=0, actions=[])

        dlg._toggle_image_recording()
        self.assertTrue(dlg.is_recording_mode)

        # 1. Simulate mouse drag: start (100, 150), end (350, 400), dist ~320px > 15px
        with patch("time.time", return_value=20.0):
            dlg._on_canvas_action_recorded(
                start_x=100, start_y=150,
                end_x=350, end_y=400,
                dist=320.0, duration=0.4
            )

        self.assertEqual(len(dlg.actions), 1)
        drag_act = dlg.actions[0]
        self.assertEqual(drag_act.action_type, "mouse_drag")
        self.assertEqual(drag_act.x, 100)
        self.assertEqual(drag_act.y, 150)
        self.assertEqual(drag_act.end_x, 350)
        self.assertEqual(drag_act.end_y, 400)
        self.assertEqual(drag_act.drag_duration_ms, 400)

        # 2. Simulate subsequent click after 2.0s pause: start (500, 600)
        with patch("time.time", return_value=22.0):
            dlg._on_canvas_action_recorded(
                start_x=500, start_y=600,
                end_x=500, end_y=600,
                dist=0.0, duration=0.0
            )

        self.assertEqual(len(dlg.actions), 3)
        self.assertEqual(dlg.actions[1].action_type, "delay")
        self.assertAlmostEqual(dlg.actions[1].delay_seconds, 2.0, places=1)
        self.assertEqual(dlg.actions[2].action_type, "mouse_click")
        self.assertEqual(dlg.actions[2].x, 500)
        self.assertEqual(dlg.actions[2].y, 600)

        dlg._toggle_image_recording()
        self.assertFalse(dlg.is_recording_mode)

    def test_dummy_canvas_creation_and_auto_loading(self):
        """Test dummy canvas generator and auto-loading when target_hwnd is 0."""
        from PyQt5.QtWidgets import QApplication
        import sys
        app = QApplication.instance() or QApplication(sys.argv)
        from core.dummy_canvas import create_dummy_canvas_qimage, create_dummy_canvas_pil
        from ui.coordinate_picker_dialog import CoordinatePickerDialog
        from ui.condition_editor_dialog import ConditionEditorDialog
        from core.models import Project, Condition

        # Check generator
        qimg = create_dummy_canvas_qimage(1600, 900)
        self.assertEqual(qimg.width(), 1600)
        self.assertEqual(qimg.height(), 900)

        pil_img = create_dummy_canvas_pil(1600, 900)
        self.assertEqual(pil_img.size, (1600, 900))

        # Check CoordinatePickerDialog loads dummy canvas when target_hwnd=0
        coord_dlg = CoordinatePickerDialog(target_hwnd=0, actions=[Action(action_type="mouse_click", x=200, y=200)])
        self.assertIsNotNone(coord_dlg.canvas.pixmap)
        self.assertFalse(coord_dlg.canvas.pixmap.isNull())
        self.assertEqual(coord_dlg.canvas.pixmap.width(), 1600)
        self.assertEqual(coord_dlg.canvas.pixmap.height(), 900)

        # Check ConditionEditorDialog loads dummy canvas when target_hwnd=0
        cond_dlg = ConditionEditorDialog(
            condition=Condition(name="더미 테스트 조건"),
            project=Project(),
            current_scenario_id="scen_dummy",
            target_hwnd=0
        )
        self.assertIsNotNone(cond_dlg.canvas.pixmap)
        self.assertFalse(cond_dlg.canvas.pixmap.isNull())
        self.assertEqual(cond_dlg.canvas.pixmap.width(), 1600)
        self.assertEqual(cond_dlg.canvas.pixmap.height(), 900)

    def test_delay_log_format_improved(self):
        """Test exact log format '[ACTION] ... 액션 실행: 0.3초 (원본0.29초) 대기'."""
        proj = Project(anti_ban_enabled=False)
        scen = Scenario(id="scen_fmt", actions=[Action(action_type="delay", delay_seconds=0.29)])
        proj.scenarios = [scen]

        runner = WorkflowRunner(proj, hwnd=0)
        runner._is_running = True
        logs = []
        runner.sig_log.connect(lambda level, msg: logs.append((level, msg)))

        with patch("core.input_controller.InputController.execute_action"):
            runner._execute_actions(scen)

        # Expected format: 액션 실행: 0.3초 (원본0.29초) 대기
        self.assertTrue(any(level == "ACTION" and "액션 실행: 0.3초 (원본0.29초) 대기" in msg for level, msg in logs))


if __name__ == "__main__":
    unittest.main()


