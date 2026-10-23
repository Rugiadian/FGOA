"""
Playback & Execution Controller Mixin for MainWindow.
Handles scenario execution (start all / start selected / step / pause / resume / stop),
WorkflowRunner lifecycle and signal handlers, visual action overlays, and popup playbar sync.
"""
from typing import Optional, List
from PyQt5.QtWidgets import QMessageBox
from core.runner import WorkflowRunner
from core.window_manager import WindowManager


class MainWindowPlaybackMixin:
    """Mixin providing scenario playback and execution control to MainWindow."""

    # ==========================================
    # Execution Engine Control
    # ==========================================
    def _on_start_all_execution(self):
        """첫 번째 시나리오 노드부터 전체를 순차적으로 실행"""
        self._on_start_execution(start_scenario_id=None)

    def _on_start_selected_execution(self):
        """현재 목록에서 선택된 시나리오 노드부터 실행"""
        selected_indexes = self.tbl_scenarios.selectedIndexes()
        selected_scen_id = None
        if selected_indexes:
            row = selected_indexes[0].row()
            if 0 <= row < len(self.project.scenarios):
                selected_scen_id = self.project.scenarios[row].id
        self._on_start_execution(start_scenario_id=selected_scen_id)

    def _set_paused_state(self, scenario_id: Optional[str]):
        """Records paused scenario ID and visually marks it in header and scenario list."""
        self._paused_scenario_id = scenario_id
        if hasattr(self, "project") and self.project and scenario_id:
            p_idx = next((i for i, s in enumerate(self.project.scenarios) if s.id == scenario_id), None)
            if p_idx is not None:
                self._highlight_running_row_header(p_idx)
                if hasattr(self, "tbl_scenarios") and self.tbl_scenarios:
                    it = self.tbl_scenarios.item(p_idx, 0)
                    if it:
                        self.tbl_scenarios.scrollToItem(it)
        if hasattr(self, "_refresh_scenario_table"):
            self._refresh_scenario_table()

    def _clear_paused_state(self):
        """Clears paused scenario ID and removes paused visual markers."""
        self._paused_scenario_id = None
        if hasattr(self, "_refresh_scenario_table"):
            self._refresh_scenario_table()

    def _on_start_execution(self, start_scenario_id: Optional[str] = None):
        if not getattr(self, "target_hwnd", 0) or not WindowManager.get_window_info(self.target_hwnd):
            # Target window not selected or closed: Auto-launch virtual canvas window
            if hasattr(self, "_on_open_virtual_canvas"):
                self._on_open_virtual_canvas()
            self._append_log("INFO", "🚀 타깃 앱이 설정되어 있지 않아 가상 캔버스를 띄우고 실행을 시작합니다.")

        if hasattr(self, "runner") and self.runner and self.runner.isRunning():
            if self.runner._is_paused:
                target_id = start_scenario_id or getattr(self, "_paused_scenario_id", None)
                if target_id:
                    self.runner.set_next_scenario_id(target_id)
                self.runner.resume()
                self._clear_paused_state()
                self.lbl_run_status.setText("실행 중...")
                self.btn_pause.setText("⏸ 일시정지 (Shift+F6)")
                if hasattr(self, "popup_play_bar") and self.popup_play_bar:
                    self.popup_play_bar.set_runner_state("running", "재개되어 실행 중...")
                return
            else:
                self.runner.stop()
                self.runner.wait(100)

        # If starting execution with a paused scenario remembered and no specific start_scenario_id
        if start_scenario_id is None and getattr(self, "_paused_scenario_id", None):
            start_scenario_id = self._paused_scenario_id
        self._clear_paused_state()

        bg_en = bool(getattr(self, "chk_background_mode", None) and self.chk_background_mode.isChecked())
        self.runner = WorkflowRunner(
            self.project,
            self.target_hwnd,
            start_scenario_id=start_scenario_id,
            anti_burn_overlay=getattr(self, "anti_burn_overlay", None),
            parent=self,
            robust_trace_enabled=getattr(self, "chk_robust_trace", None) and self.chk_robust_trace.isChecked(),
            background_mode=bg_en
        )
        self.runner.sig_log.connect(self._append_log)
        self.runner.sig_scenario_started.connect(self._on_scenario_started)
        self.runner.sig_scenario_completed.connect(self._on_scenario_completed)
        self.runner.sig_action_executing.connect(self._on_action_executing_visual)
        self.runner.sig_action_finished.connect(self._on_action_finished_visual)
        self.runner.sig_action_sequence_started.connect(self._on_action_sequence_started_visual)
        self.runner.sig_action_sequence_finished.connect(self._on_action_sequence_finished_visual)
        self.runner.sig_loop_progress.connect(self._on_loop_progress)
        self.runner.sig_loop_completed.connect(self._on_loop_completed)
        self.runner.sig_step_completed.connect(self._on_step_completed)
        self.runner.sig_finished.connect(self._on_runner_finished)

        self._current_run_loop = 0
        self._last_loop_duration = 0.0
        if hasattr(self, "lbl_loop_progress"):
            self.lbl_loop_progress.setText("(준비 중...)")
            self.lbl_loop_progress.setStyleSheet("font-weight: bold; color: #16a34a; font-size: 8.5pt;")

        self.btn_run.setEnabled(False)
        if hasattr(self, "btn_run_selected"):
            self.btn_run_selected.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_stop.setEnabled(True)
        self.lbl_run_status.setText("실행 중 (F5/F6)")
        self.lbl_run_status.setStyleSheet("color: #16a34a; font-weight: bold;")
        if hasattr(self, "popup_play_bar") and self.popup_play_bar:
            self.popup_play_bar.set_runner_state("running", "시나리오 실행 중...")

        if hasattr(self, "chk_floating_stop") and self.chk_floating_stop.isChecked():
            if hasattr(self, "floating_stop") and self.floating_stop:
                self.floating_stop.show()
                self.floating_stop.raise_()

        self.runner.start()

    def _on_pause_execution(self):
        if hasattr(self, "runner") and self.runner and self.runner.isRunning():
            if self.runner._is_paused:
                # Resuming execution from paused node
                target_id = getattr(self, "_paused_scenario_id", None) or getattr(self.runner, "current_scenario_id", None)
                if target_id:
                    self.runner.set_next_scenario_id(target_id)
                self.runner.resume()
                self._clear_paused_state()
                self.btn_pause.setText("⏸ 일시정지 (Shift+F6)")
                self.lbl_run_status.setText("실행 중...")
                self.lbl_run_status.setStyleSheet("color: #16a34a; font-weight: bold;")
                if hasattr(self, "popup_play_bar") and self.popup_play_bar:
                    self.popup_play_bar.set_runner_state("running", "재개되어 실행 중...")
                if hasattr(self, "floating_stop") and self.floating_stop:
                    self.floating_stop.set_paused_state(False)
            else:
                # Pausing execution and recording paused node
                self.runner.pause()
                paused_id = getattr(self.runner, "current_scenario_id", None) or getattr(self, "_last_running_scenario_id", None)
                self._set_paused_state(paused_id)
                self.btn_pause.setText("▶ 재개 (Shift+F6)")
                self.lbl_run_status.setText("일시정지됨")
                self.lbl_run_status.setStyleSheet("color: #ea580c; font-weight: bold;")
                if hasattr(self, "popup_play_bar") and self.popup_play_bar:
                    self.popup_play_bar.set_runner_state("paused", "일시정지됨")
                if hasattr(self, "floating_stop") and self.floating_stop:
                    self.floating_stop.set_paused_state(True)

    def _on_stop_execution(self):
        if hasattr(self, "runner") and self.runner:
            self.runner.stop()
            self.runner.wait(500)
        self._clear_paused_state()
        self._last_running_scenario_id = None
        self.btn_run.setEnabled(True)
        if hasattr(self, "btn_run_selected"):
            self.btn_run_selected.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.btn_pause.setText("⏸ 일시정지 (Shift+F6)")
        self.lbl_run_status.setText("정지됨")
        self.lbl_run_status.setStyleSheet("color: #dc2626; font-weight: bold;")
        self._highlight_running_row_header(None)
        if hasattr(self, "floating_stop") and self.floating_stop:
            self.floating_stop.hide()
        if hasattr(self, "popup_play_bar") and self.popup_play_bar:
            self.popup_play_bar.set_runner_state("stopped", "정지됨")
        if hasattr(self, "action_overlay") and self.action_overlay:
            self.action_overlay.clear_action()
        if hasattr(self, "lbl_loop_progress"):
            dur_str = f" | 최근 루프: {WorkflowRunner._format_duration(self._last_loop_duration)}" if self._last_loop_duration > 0 else ""
            if self._current_run_loop > 0:
                self.lbl_loop_progress.setText(f"({self._current_run_loop}회차 정지{dur_str})")
                self.lbl_loop_progress.setStyleSheet("font-weight: bold; color: #dc2626; font-size: 8.5pt;")
            else:
                self.lbl_loop_progress.setText("(대기)")
                self.lbl_loop_progress.setStyleSheet("font-weight: bold; color: #64748b; font-size: 8.5pt;")
        if hasattr(self, "status_bar") and self.status_bar:
            self.status_bar.showMessage("시나리오 실행이 즉시 정지되었습니다.", 3000)

    def _on_step_execution(self):
        if not getattr(self, "target_hwnd", 0):
            QMessageBox.warning(self, "타겟 창 필요", "타겟 창을 먼저 선택해주세요.")
            return

        # Find selected scenario node (start from selected node, not from beginning)
        selected_indexes = self.tbl_scenarios.selectedIndexes()
        selected_scen_id = None
        if selected_indexes:
            row = selected_indexes[0].row()
            if 0 <= row < len(self.project.scenarios):
                selected_scen_id = self.project.scenarios[row].id

        if not hasattr(self, "runner") or not self.runner or not self.runner.isRunning():
            self._on_start_execution(start_scenario_id=selected_scen_id)
            if hasattr(self, "runner") and self.runner:
                self.runner.step_forward()
                self.lbl_run_status.setText("단일 스텝 (F7)")
                self.lbl_run_status.setStyleSheet("color: #0284c7; font-weight: bold;")
        else:
            if selected_scen_id:
                self.runner.set_next_scenario_id(selected_scen_id)
            self.runner.step_forward()
            self.lbl_run_status.setText("단일 스텝 (F7)")
            self.lbl_run_status.setStyleSheet("color: #0284c7; font-weight: bold;")
        if hasattr(self, "popup_play_bar") and self.popup_play_bar:
            self.popup_play_bar.set_runner_state("stepping", "단일 스텝 실행 중...")

    def _on_step_completed(self, next_index: int):
        """단일 스텝 실행 완료 시 다음 노드로 포인터(헤더 번호) 이동 및 하이라이트 갱신"""
        if 0 <= next_index < len(self.project.scenarios):
            self.tbl_scenarios.blockSignals(True)
            self.tbl_scenarios.setCurrentCell(next_index, 0)
            self.tbl_scenarios.clearSelection()
            self.tbl_scenarios.blockSignals(False)
            it = self.tbl_scenarios.item(next_index, 0)
            if it:
                self.tbl_scenarios.scrollToItem(it)
            self._highlight_running_row_header(next_index)
            next_scen = self.project.scenarios[next_index]
            if hasattr(self, "popup_play_bar") and self.popup_play_bar:
                self.popup_play_bar.set_runner_state("paused", f"대기: s{next_scen.scenario_number} [{next_scen.name}]")
        else:
            self._highlight_running_row_header(None)

    def _highlight_running_row_header(self, row: Optional[int]):
        """시나리오 목록 표의 행 넘버링(세로 헤더) 셀 컬러로 현재 진행 중인 노드 강조 표기"""
        self._current_running_row = row
        idx = row if row is not None else -1
        if hasattr(self.tbl_scenarios, "set_highlight_row"):
            self.tbl_scenarios.set_highlight_row(idx)

    def _on_action_sequence_started_visual(self, actions: list, scenario_name: str):
        """전체 액션 시퀀스의 모든 포인트들을 오버레이 화면상에 동시 시각화"""
        is_bg = getattr(self, "chk_background_mode", None) and self.chk_background_mode.isChecked()
        if is_bg:
            return  # 백그라운드 모드 시 사용자의 채팅/작업 포커스 방해를 원천 차단하기 위해 오버레이 팝업 억제
        if hasattr(self, "action_overlay") and self.action_overlay and hasattr(self, "chk_action_overlay") and self.chk_action_overlay.isChecked():
            self.action_overlay.set_target_hwnd(self.target_hwnd)
            self.action_overlay.show_sequence(actions, 1, scenario_name)

    def _on_action_sequence_finished_visual(self):
        """액션 시퀀스 완료 시 오버레이 화면 서서히 정리"""
        if hasattr(self, "action_overlay") and self.action_overlay:
            self.action_overlay.hide_action_delayed(500)

    def _on_action_executing_visual(self, action, index, total):
        # 1. Action overlay for click/drag coordinates on target screen (completely click-through)
        is_bg = getattr(self, "chk_background_mode", None) and self.chk_background_mode.isChecked()
        if not is_bg and hasattr(self, "action_overlay") and self.action_overlay and hasattr(self, "chk_action_overlay") and self.chk_action_overlay.isChecked():
            self.action_overlay.set_target_hwnd(self.target_hwnd)
            self.action_overlay.set_current_action_index(index, action)

        # 2. Real-time sequence action progress output on play bar
        if hasattr(self, "popup_play_bar") and self.popup_play_bar:
            self.popup_play_bar.set_action_status(action, index, total)

        # 3. Virtual canvas target visual click effect
        if hasattr(self, "virtual_canvas_window") and self.virtual_canvas_window and self.virtual_canvas_window.isVisible():
            if hasattr(action, "action_type") and action.action_type in ("mouse_click", "mouse_drag"):
                cx = getattr(action, "x", getattr(action, "start_x", 0))
                cy = getattr(action, "y", getattr(action, "start_y", 0))
                self.virtual_canvas_window.trigger_click_effect(cx, cy)

    def _on_action_finished_visual(self, action):
        pass

    def _on_toggle_action_overlay(self, checked: bool):
        if hasattr(self, "action_overlay") and self.action_overlay:
            self.action_overlay.is_overlay_enabled = checked
            if not checked:
                self.action_overlay.clear_action()
        if hasattr(self, "_save_app_config"):
            self._save_app_config()

    def _on_toggle_floating_stop(self, checked: bool):
        if hasattr(self, "floating_stop") and self.floating_stop:
            if hasattr(self, "runner") and self.runner and self.runner.isRunning() and checked:
                self.floating_stop.show()
                self.floating_stop.raise_()
            elif not checked:
                self.floating_stop.hide()
        if hasattr(self, "_save_app_config"):
            self._save_app_config()

    def _on_toggle_background_mode(self, checked: bool):
        if hasattr(self, "runner") and self.runner and self.runner.isRunning():
            self.runner.set_background_mode(checked)
        if checked and hasattr(self, "action_overlay") and self.action_overlay:
            self.action_overlay.clear_action()
        status_text = "활성화 (마우스 독립 조작 가능, 비활성 PostMessage/PrintWindow)" if checked else "비활성화 (물리 마우스 조작 모드)"
        self._append_log("INFO", f"👻 백그라운드 제어 모드 {status_text}")
        if hasattr(self, "_save_app_config"):
            self._save_app_config()

    def _on_scenario_started(self, scenario_id: str):
        self._last_running_scenario_id = scenario_id
        for row, s in enumerate(self.project.scenarios):
            if s.id == scenario_id:
                # 행 선택(드래그 모양)을 유발하지 않고 스크롤 이동 및 헤더 녹색 하이라이트만 적용
                self.tbl_scenarios.blockSignals(True)
                self.tbl_scenarios.setCurrentCell(row, 0)
                self.tbl_scenarios.clearSelection()
                self.tbl_scenarios.blockSignals(False)
                it = self.tbl_scenarios.item(row, 0)
                if it:
                    self.tbl_scenarios.scrollToItem(it)
                self._highlight_running_row_header(row)
                if hasattr(self, "popup_play_bar") and self.popup_play_bar:
                    self.popup_play_bar.set_runner_state("running", f"s{s.scenario_number} [{s.name}] 실행 중...")
                if hasattr(self, "floating_stop") and self.floating_stop:
                    self.floating_stop.set_status(f"s{s.scenario_number} [{s.name}]")
                break

    def _on_scenario_completed(self, scenario_id: str, result: str):
        pass

    def _on_runner_finished(self, reason: str):
        self._clear_paused_state()
        self._last_running_scenario_id = None
        self.btn_run.setEnabled(True)
        if hasattr(self, "btn_run_selected"):
            self.btn_run_selected.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.btn_pause.setText("⏸ 일시정지 (Shift+F6)")
        self.lbl_run_status.setText(f"완료 ({reason})")
        self.lbl_run_status.setStyleSheet("font-weight: bold;")
        self._highlight_running_row_header(None)
        if hasattr(self, "floating_stop") and self.floating_stop:
            self.floating_stop.hide()
        if hasattr(self, "popup_play_bar") and self.popup_play_bar:
            self.popup_play_bar.set_runner_state("stopped", f"완료 ({reason})")
        if hasattr(self, "action_overlay") and self.action_overlay:
            self.action_overlay.clear_action()
        if hasattr(self, "lbl_loop_progress"):
            dur_str = f" | 최근 루프: {WorkflowRunner._format_duration(self._last_loop_duration)}" if self._last_loop_duration > 0 else ""
            if self._current_run_loop > 0:
                self.lbl_loop_progress.setText(f"(총 {self._current_run_loop}회 완료{dur_str})")
                self.lbl_loop_progress.setStyleSheet("font-weight: bold; color: #2563eb; font-size: 8.5pt;")
            else:
                self.lbl_loop_progress.setText("(대기)")
                self.lbl_loop_progress.setStyleSheet("font-weight: bold; color: #64748b; font-size: 8.5pt;")

    def _on_loop_completed(self, completed_loop: int, total_loops: int, duration: float):
        self._last_loop_duration = duration
        dur_str = WorkflowRunner._format_duration(duration)
        if hasattr(self, "lbl_loop_progress"):
            if total_loops > 0:
                self.lbl_loop_progress.setText(f"({completed_loop} / {total_loops}회 완료 | 소요: {dur_str})")
            else:
                self.lbl_loop_progress.setText(f"({completed_loop}회 완료 | 소요: {dur_str})")
            self.lbl_loop_progress.setStyleSheet("font-weight: bold; color: #16a34a; font-size: 8.5pt;")

    def _on_loop_progress(self, current_loop: int, total_loops: int):
        self._current_run_loop = current_loop
        dur_str = f" | 이전 루프: {WorkflowRunner._format_duration(self._last_loop_duration)}" if self._last_loop_duration > 0 else ""
        if hasattr(self, "lbl_loop_progress"):
            if total_loops > 0:
                self.lbl_loop_progress.setText(f"({current_loop} / {total_loops}회 진행 중{dur_str})")
            else:
                self.lbl_loop_progress.setText(f"({current_loop}회 진행 중{dur_str})")
            self.lbl_loop_progress.setStyleSheet("font-weight: bold; color: #16a34a; font-size: 8.5pt;")

    # ==========================================
    # Popup Play Bar Controls & Signal Handlers
    # ==========================================
    def _on_playbar_closed(self):
        if hasattr(self, "btn_popup_playbar") and self.btn_popup_playbar:
            self.btn_popup_playbar.setChecked(False)

    def _toggle_popup_playbar(self):
        if not hasattr(self, "popup_play_bar") or not self.popup_play_bar:
            return
        if self.popup_play_bar.isVisible():
            self.popup_play_bar.hide()
            if hasattr(self, "btn_popup_playbar"):
                self.btn_popup_playbar.setChecked(False)
        else:
            self.popup_play_bar.refresh_scenarios(self.project.scenarios)
            self.popup_play_bar.position_relative_to_target(self.target_hwnd, self.geometry())
            self.popup_play_bar.show()
            self.popup_play_bar.raise_()
            if hasattr(self, "btn_popup_playbar"):
                self.btn_popup_playbar.setChecked(True)

    def _on_playbar_start(self, scenario_id: Optional[str] = None):
        if scenario_id:
            for row, s in enumerate(self.project.scenarios):
                if s.id == scenario_id:
                    self.tbl_scenarios.selectRow(row)
                    break
            self._on_start_execution(start_scenario_id=scenario_id)
        else:
            self._on_start_execution()

    def _on_playbar_step(self, scenario_id: Optional[str] = None):
        if scenario_id:
            for row, s in enumerate(self.project.scenarios):
                if s.id == scenario_id:
                    self.tbl_scenarios.selectRow(row)
                    break
        self._on_step_execution()

    def _on_playbar_select_scenario(self, scenario_id: str):
        for row, s in enumerate(self.project.scenarios):
            if s.id == scenario_id:
                self.tbl_scenarios.selectRow(row)
                break
