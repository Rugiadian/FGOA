"""
Execution Runner Engine for FGOA.
Runs scenarios in a background QThread, handling conditions, actions, branching, and loops.
"""
import time
from typing import Optional
from PyQt5.QtCore import QThread, pyqtSignal
from core.models import Project, Scenario, Action
from core.window_manager import WindowManager
from core.evaluator import ConditionEvaluator
from core.input_controller import InputController


class WorkflowRunner(QThread):
    """Background worker thread that executes scenarios according to condition evaluation."""

    # Signals
    sig_log = pyqtSignal(str, str)  # (level, message)
    sig_scenario_started = pyqtSignal(str)  # scenario_id
    sig_scenario_completed = pyqtSignal(str, str)  # (scenario_id, result: "matched" / "mismatch" / "skipped")
    sig_loop_progress = pyqtSignal(int, int)  # (current_loop, total_loops)
    sig_finished = pyqtSignal(str)  # reason

    def __init__(self, project: Project, hwnd: int, parent=None):
        super().__init__(parent)
        self.project = project
        self.hwnd = hwnd

        self._is_running = False
        self._is_paused = False
        self._step_mode = False  # If True, runs one step then pauses

    def stop(self):
        """Signal the runner to stop immediately."""
        self._is_running = False
        self._is_paused = False

    def pause(self):
        """Pause execution."""
        self._is_paused = True

    def resume(self):
        """Resume execution."""
        self._is_paused = False

    def step_forward(self):
        """Execute one step then pause."""
        self._step_mode = True
        self._is_paused = False

    def run(self):
        self._is_running = True
        self._is_paused = False

        self.sig_log.emit("INFO", f"=== 시나리오 실행 시작 (타겟 HWND: {self.hwnd}) ===")

        target_win = WindowManager.get_window_info(self.hwnd)
        if not target_win:
            self.sig_log.emit("ERROR", "타겟 창을 찾을 수 없습니다. 실행을 중단합니다.")
            self.sig_finished.emit("타겟 창 없음")
            return

        self.sig_log.emit("INFO", f"타겟 창: '{target_win.title}' ({target_win.client_width}x{target_win.client_height})")

        total_loops = self.project.loop_count
        current_loop = 1

        while self._is_running:
            loop_str = f"{current_loop}/{total_loops}" if total_loops > 0 else f"{current_loop}/무한"
            self.sig_loop_progress.emit(current_loop, total_loops)
            self.sig_log.emit("INFO", f"--- 루프 회차 {loop_str} 시작 ---")

            # Execute scenarios starting at step 1
            current_index = 0
            scenarios = self.project.scenarios
            loop_counters = {}  # {loop_start_id: int}

            while self._is_running and current_index < len(scenarios):
                # Check pause
                while self._is_running and self._is_paused:
                    time.sleep(0.05)

                if not self._is_running:
                    break

                scen = scenarios[current_index]

                if not scen.enabled:
                    self.sig_scenario_completed.emit(scen.id, "skipped")
                    current_index += 1
                    continue

                # ----------------------------------------------------
                # Loop Node: loop_start
                # ----------------------------------------------------
                if scen.node_type == "loop_start":
                    if scen.id not in loop_counters:
                        loop_counters[scen.id] = 0
                    current_iter = loop_counters[scen.id]
                    max_iter = scen.loop_count

                    # 1. Check max iterations for count mode
                    if scen.loop_mode == "count" and current_iter >= max_iter:
                        end_idx = self.project.find_matching_loop_end(current_index)
                        self.sig_log.emit("INFO", f"🔁 [루프 #{scen.scenario_number}] '{scen.name}': 지정 횟수({max_iter}회) 완료. 루프 종료.")
                        if scen.id in loop_counters:
                            del loop_counters[scen.id]
                        current_index = (end_idx + 1) if end_idx is not None else (current_index + 1)
                        continue

                    # 2. Check screen recognition condition (until_match / while_match)
                    if scen.loop_mode in ("until_match", "while_match") and scen.condition and scen.condition.points:
                        matched, _ = ConditionEvaluator.evaluate(scen.condition, self.hwnd)
                        if scen.loop_mode == "until_match" and matched:
                            end_idx = self.project.find_matching_loop_end(current_index)
                            self.sig_log.emit("SUCCESS", f"🔁 [루프 #{scen.scenario_number}] '{scen.name}': 탈출 인식 조건 충족! 루프 종료.")
                            if scen.id in loop_counters:
                                del loop_counters[scen.id]
                            current_index = (end_idx + 1) if end_idx is not None else (current_index + 1)
                            continue
                        elif scen.loop_mode == "while_match" and not matched:
                            end_idx = self.project.find_matching_loop_end(current_index)
                            self.sig_log.emit("INFO", f"🔁 [루프 #{scen.scenario_number}] '{scen.name}': 지속 조건 불일치. 루프 종료.")
                            if scen.id in loop_counters:
                                del loop_counters[scen.id]
                            current_index = (end_idx + 1) if end_idx is not None else (current_index + 1)
                            continue

                    limit_str = f"{max_iter}회" if scen.loop_mode != "infinite" else "무한"
                    self.sig_log.emit("INFO", f"🔁 [루프 #{scen.scenario_number}] '{scen.name}': {current_iter + 1}/{limit_str} 회차 진입")
                    if scen.actions:
                        self._execute_actions(scen)
                    current_index += 1
                    continue

                # ----------------------------------------------------
                # Loop Node: loop_end
                # ----------------------------------------------------
                if scen.node_type == "loop_end":
                    start_idx = self.project.find_matching_loop_start(current_index)
                    if start_idx is not None:
                        start_scen = scenarios[start_idx]
                        loop_counters[start_scen.id] = loop_counters.get(start_scen.id, 0) + 1
                        self.sig_log.emit("INFO", f"🔁 [루프 종료 #{scen.scenario_number}] → 루프 시작 #{start_scen.scenario_number}로 복귀 (누적 {loop_counters[start_scen.id]}회)")
                        current_index = start_idx
                    else:
                        current_index += 1
                    continue

                # ----------------------------------------------------
                # Standard Scenario Evaluation
                # ----------------------------------------------------
                self.sig_scenario_started.emit(scen.id)
                self.sig_log.emit("INFO", f"[#{scen.step_number}] '{scen.name}' 조건 평가 중...")

                # Verify window is still valid
                if not WindowManager.get_window_info(self.hwnd):
                    self.sig_log.emit("ERROR", "타겟 창이 닫혔거나 유효하지 않습니다.")
                    self._is_running = False
                    break

                # Condition evaluation with optional retries
                matched = False
                attempt = 0
                max_attempts = (scen.retry_max_count + 1) if (scen.on_mismatch == "retry") else 1

                while attempt < max_attempts and self._is_running:
                    matched, point_results = ConditionEvaluator.evaluate(scen.condition, self.hwnd)
                    if matched:
                        break
                    attempt += 1
                    if attempt < max_attempts and self._is_running:
                        time.sleep(scen.retry_interval_sec)

                # Handle evaluation outcome
                if matched:
                    self.sig_scenario_completed.emit(scen.id, "matched")
                    self.sig_log.emit("SUCCESS", f"[#{scen.step_number}] '{scen.name}' 조건 일치! (판정: 성공)")

                    if scen.on_match == "execute":
                        # Execute actions
                        self._execute_actions(scen)
                        if scen.post_delay_seconds > 0:
                            time.sleep(scen.post_delay_seconds)
                        current_index += 1

                    elif scen.on_match == "break_loop":
                        # Break out of containing loop
                        end_idx = None
                        for k in range(current_index + 1, len(scenarios)):
                            if scenarios[k].node_type == "loop_end":
                                end_idx = k
                                break
                        self.sig_log.emit("INFO", f"🛑 [#{scen.step_number}] 조건 일치로 현재 루프 즉시 탈출")
                        current_index = (end_idx + 1) if end_idx is not None else len(scenarios)

                    elif scen.on_match == "jump":
                        target_scen = self._resolve_target_scenario(scen.jump_target_on_match)
                        if target_scen:
                            self.sig_log.emit("INFO", f"→ 조건 일치로 시나리오 #{target_scen.step_number} [{target_scen.name}]로 점프")
                            current_index = scenarios.index(target_scen)
                        else:
                            self.sig_log.emit("WARN", f"점프 대상 ID '{scen.jump_target_on_match}'을 찾을 수 없어 다음 단계로 진행합니다.")
                            current_index += 1

                    elif scen.on_match == "stop":
                        self.sig_log.emit("INFO", f"[#{scen.step_number}] 조건 일치로 실행 정지 지시.")
                        self._is_running = False
                        break

                else:
                    self.sig_scenario_completed.emit(scen.id, "mismatch")
                    self.sig_log.emit("WARN", f"[#{scen.step_number}] '{scen.name}' 조건 불일치.")

                    if scen.on_mismatch in ("next", "retry"):
                        current_index += 1

                    elif scen.on_mismatch == "break_loop":
                        end_idx = None
                        for k in range(current_index + 1, len(scenarios)):
                            if scenarios[k].node_type == "loop_end":
                                end_idx = k
                                break
                        self.sig_log.emit("INFO", f"🛑 [#{scen.step_number}] 조건 불일치로 현재 루프 즉시 탈출")
                        current_index = (end_idx + 1) if end_idx is not None else len(scenarios)

                    elif scen.on_mismatch == "jump":
                        target_scen = self._resolve_target_scenario(scen.jump_target_on_mismatch)
                        if target_scen:
                            self.sig_log.emit("INFO", f"→ 조건 불일치로 시나리오 #{target_scen.step_number} [{target_scen.name}]로 점프")
                            current_index = scenarios.index(target_scen)
                        else:
                            self.sig_log.emit("WARN", f"점프 대상 ID '{scen.jump_target_on_mismatch}'을 찾을 수 없어 다음 단계로 진행합니다.")
                            current_index += 1

                    elif scen.on_mismatch == "stop":
                        self.sig_log.emit("INFO", f"[#{scen.step_number}] 조건 불일치로 실행 정지 지시.")
                        self._is_running = False
                        break

                # If step mode was active, pause now
                if self._step_mode:
                    self._step_mode = False
                    self._is_paused = True
                    self.sig_log.emit("INFO", "단일 스텝 완료 (일시정지됨)")

            # Check loop completion
            if not self._is_running:
                break

            if total_loops > 0 and current_loop >= total_loops:
                self.sig_log.emit("SUCCESS", f"지정된 반복 횟수({total_loops}회)를 모두 완료했습니다.")
                break

            current_loop += 1
            if self.project.loop_delay_seconds > 0:
                time.sleep(self.project.loop_delay_seconds)

        self._is_running = False
        self.sig_finished.emit("완료")
        self.sig_log.emit("INFO", "=== 시나리오 실행 종료 ===")

    def _execute_actions(self, scenario: Scenario):
        """Sequentially execute all actions defined in the scenario."""
        for act in scenario.actions:
            if not self._is_running:
                break

            # Handle pause
            while self._is_running and self._is_paused:
                time.sleep(0.05)

            self.sig_log.emit("ACTION", f"  ▶ 액션 실행: {act.get_summary()}")

            if act.action_type == "mouse_click":
                InputController.click_at(
                    hwnd=self.hwnd,
                    rel_x=act.x,
                    rel_y=act.y,
                    button=act.mouse_button,
                    click_type=act.click_type,
                    repeat=act.repeat_count
                )
            elif act.action_type == "mouse_drag":
                InputController.drag_and_drop(
                    hwnd=self.hwnd,
                    start_x=act.x,
                    start_y=act.y,
                    end_x=act.end_x,
                    end_y=act.end_y,
                    duration_ms=act.drag_duration_ms
                )
            elif act.action_type == "key_press":
                InputController.send_key_combination(act.key, act.modifiers)
            elif act.action_type == "text_type":
                InputController.type_text(act.text)
            elif act.action_type == "delay":
                time.sleep(act.delay_seconds)
            elif act.action_type == "sound_beep":
                InputController.beep(act.beep_freq, act.beep_duration_ms)
            elif act.action_type == "log_message":
                self.sig_log.emit("USER", f"  [사용자 로그] {act.log_text}")

            # Small safety delay between actions
            time.sleep(0.05)

    def _resolve_target_scenario(self, target_identifier: str) -> Optional[Scenario]:
        """Resolves target scenario by UUID, ID, or step number string."""
        if not target_identifier:
            return None

        # Try by exact ID
        for s in self.project.scenarios:
            if s.id == target_identifier:
                return s

        # Try by scenario_number or step_number integer
        try:
            num = int(target_identifier)
            for s in self.project.scenarios:
                if getattr(s, "scenario_number", None) == num:
                    return s
            for s in self.project.scenarios:
                if s.step_number == num:
                    return s
        except ValueError:
            pass

        return None
