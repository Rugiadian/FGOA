"""
Execution Runner Engine for FGOA.
Runs scenarios in a background QThread, handling conditions, actions, branching, and loops.
"""
import time
import random
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
    sig_action_executing = pyqtSignal(object, int, int)  # (action, action_index, total_actions)
    sig_action_finished = pyqtSignal(object)  # action
    sig_loop_progress = pyqtSignal(int, int)  # (current_loop, total_loops)
    sig_step_completed = pyqtSignal(int)  # next_scenario_index
    sig_finished = pyqtSignal(str)  # reason

    def __init__(self, project: Project, hwnd: int, start_scenario_id: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.project = project
        self.hwnd = hwnd
        self.start_scenario_id = start_scenario_id
        self._next_scenario_id: Optional[str] = None

        self._is_running = False
        self._is_paused = False
        self._step_mode = False  # If True, runs one step then pauses

    def set_next_scenario_id(self, scenario_id: Optional[str]):
        """Sets the scenario ID to jump to next (used when stepping from user-selected node)."""
        self._next_scenario_id = scenario_id

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
            self._is_running = False
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

            # Execute scenarios starting at step 1 or selected node
            scenarios = self.project.scenarios
            current_index = 0
            if self.start_scenario_id:
                found_idx = next((i for i, s in enumerate(scenarios) if s.id == self.start_scenario_id), None)
                if found_idx is not None:
                    current_index = found_idx
                    self.sig_log.emit("INFO", f"▶ 선택된 노드 [#{scenarios[found_idx].step_number}] '{scenarios[found_idx].name}'부터 실행을 시작합니다.")
                self.start_scenario_id = None

            loop_counters = {}  # {loop_start_id: int}

            while self._is_running and current_index < len(scenarios):
                # Check pause
                while self._is_running and self._is_paused:
                    time.sleep(0.05)

                if not self._is_running:
                    break

                # If user selected a different scenario while paused / stepping
                if self._next_scenario_id:
                    target = self._resolve_target_scenario(self._next_scenario_id)
                    if target and target in scenarios:
                        current_index = scenarios.index(target)
                        self.sig_log.emit("INFO", f"▶ 선택된 노드 [#{target.step_number}] '{target.name}'(으)로 이동하여 진행합니다.")
                    self._next_scenario_id = None

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
                        self.sig_log.emit("INFO", f"🔁 [루프 s{scen.scenario_number}] '{scen.name}': 지정 횟수({max_iter}회) 완료. 루프 종료.")
                        if scen.id in loop_counters:
                            del loop_counters[scen.id]
                        current_index = (end_idx + 1) if end_idx is not None else (current_index + 1)
                        continue

                    # 2. Check screen recognition condition (until_match / while_match)
                    eff_cond = scen.get_effective_condition(self.project) if hasattr(scen, "get_effective_condition") else scen.condition
                    if scen.loop_mode in ("until_match", "while_match") and eff_cond and eff_cond.points:
                        matched, _ = ConditionEvaluator.evaluate(eff_cond, self.hwnd)
                        if scen.loop_mode == "until_match" and matched:
                            end_idx = self.project.find_matching_loop_end(current_index)
                            self.sig_log.emit("SUCCESS", f"🔁 [루프 s{scen.scenario_number}] '{scen.name}': 탈출 인식 조건 충족! 루프 종료.")
                            if scen.id in loop_counters:
                                del loop_counters[scen.id]
                            current_index = (end_idx + 1) if end_idx is not None else (current_index + 1)
                            continue
                        elif scen.loop_mode == "while_match" and not matched:
                            end_idx = self.project.find_matching_loop_end(current_index)
                            self.sig_log.emit("INFO", f"🔁 [루프 s{scen.scenario_number}] '{scen.name}': 지속 조건 불일치. 루프 종료.")
                            if scen.id in loop_counters:
                                del loop_counters[scen.id]
                            current_index = (end_idx + 1) if end_idx is not None else (current_index + 1)
                            continue

                    limit_str = f"{max_iter}회" if scen.loop_mode != "infinite" else "무한"
                    self.sig_log.emit("INFO", f"🔁 [루프 s{scen.scenario_number}] '{scen.name}': {current_iter + 1}/{limit_str} 회차 진입")
                    eff_actions = scen.get_effective_actions(self.project) if hasattr(scen, "get_effective_actions") else scen.actions
                    if eff_actions:
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
                        self.sig_log.emit("INFO", f"🔁 [루프 종료 s{scen.scenario_number}] → 루프 시작 s{start_scen.scenario_number}로 복귀 (누적 {loop_counters[start_scen.id]}회)")
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
                eff_cond = scen.get_effective_condition(self.project) if hasattr(scen, "get_effective_condition") else scen.condition

                while attempt < max_attempts and self._is_running:
                    matched, point_results = ConditionEvaluator.evaluate(eff_cond, self.hwnd)
                    if matched:
                        break
                    attempt += 1
                    if attempt < max_attempts and self._is_running:
                        self.sig_log.emit("INFO", f"⏳ [#{scen.step_number}] '{scen.name}' 조건 불일치 - 재시도 대기 ({attempt}/{scen.retry_max_count}회, {scen.retry_interval_sec:.1f}초 후 재검사)...")
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
                            self.sig_log.emit("INFO", f"→ 조건 일치로 시나리오 s{target_scen.scenario_number} (실행 #{target_scen.step_number}) [{target_scen.name}]로 점프")
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
                    if scen.on_mismatch == "retry":
                        fail_action = getattr(scen, "retry_fail_action", "stop")
                        self.sig_log.emit("WARN", f"[#{scen.step_number}] '{scen.name}' 조건 재시도({scen.retry_max_count}회) 모두 소진! (실패 처리: {fail_action})")
                        if fail_action == "stop":
                            self.sig_log.emit("ERROR", f"[#{scen.step_number}] 조건 재시도 실패로 오토 실행을 정지합니다.")
                            self._is_running = False
                            break
                        elif fail_action == "jump":
                            target_id = getattr(scen, "retry_fail_jump_target", "") or scen.jump_target_on_mismatch
                            target_scen = self._resolve_target_scenario(target_id)
                            if target_scen and target_scen in scenarios:
                                self.sig_log.emit("INFO", f"→ [#{scen.step_number}] 재시도 소진으로 시나리오 s{target_scen.scenario_number} (실행 #{target_scen.step_number}) [{target_scen.name}]로 점프합니다.")
                                current_index = scenarios.index(target_scen)
                            else:
                                self.sig_log.emit("WARN", f"재시도 실패 점프 대상 ID '{target_id}'를 찾을 수 없어 오토 실행을 정지합니다.")
                                self._is_running = False
                                break
                        else:  # "next"
                            self.sig_log.emit("INFO", f"[#{scen.step_number}] 조건 재시도 소진으로 다음 시나리오로 진행합니다.")
                            current_index += 1

                    elif scen.on_mismatch == "next":
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
                            self.sig_log.emit("INFO", f"→ 조건 불일치로 시나리오 s{target_scen.scenario_number} (실행 #{target_scen.step_number}) [{target_scen.name}]로 점프")
                            current_index = scenarios.index(target_scen)
                        else:
                            self.sig_log.emit("WARN", f"점프 대상 ID '{scen.jump_target_on_mismatch}'을 찾을 수 없어 다음 단계로 진행합니다.")
                            current_index += 1

                    elif scen.on_mismatch == "stop":
                        self.sig_log.emit("INFO", f"[#{scen.step_number}] 조건 불일치로 실행 정지 지시.")
                        self._is_running = False
                        break

                # If step mode was active, pause now and notify UI of next scenario pointer
                if self._step_mode:
                    self._step_mode = False
                    self._is_paused = True
                    self.sig_log.emit("INFO", "단일 스텝 완료 (일시정지됨)")
                    self.sig_step_completed.emit(current_index)

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
        actions = scenario.get_effective_actions(self.project) if hasattr(scenario, "get_effective_actions") else scenario.actions
        use_anti_ban = getattr(self.project, "anti_ban_enabled", False)
        offset_range = getattr(self.project, "anti_ban_offset", 10)
        offset_sec = float(getattr(self.project, "anti_ban_offset_seconds", getattr(self.project, "anti_ban_max_delay", 1.0)))
        scen_log = getattr(scenario, "custom_log", "")
        if scen_log:
            self.sig_log.emit("USER", f"  [액션 로그] {scen_log}")

        for act_idx, act in enumerate(actions):
            if not self._is_running:
                break

            # Handle pause
            while self._is_running and self._is_paused:
                time.sleep(0.05)

            # Signal action visualizer overlay that this action is about to execute
            self.sig_action_executing.emit(act, act_idx + 1, len(actions))

            # Scenario-wide batch anti-ban: strictly positive +n seconds delay offset
            should_anti_ban = use_anti_ban
            jitter = round(random.uniform(0.0, offset_sec), 3) if (should_anti_ban and offset_sec > 0) else 0.0

            # Per-action coordinate anti-ban: "weak", "strong", "none" (with global strength values)
            coord_mode = getattr(act, "coord_anti_ban", "weak")
            if coord_mode == "none" or act.action_type not in ("mouse_click", "mouse_drag"):
                act_offset_range = 0
                coord_str = ""
            elif coord_mode == "strong":
                act_offset_range = getattr(self.project, "anti_ban_coord_strong", 15)
                coord_str = f" [좌표 강 ±{act_offset_range}px]"
            else:  # "weak" (default)
                act_offset_range = getattr(self.project, "anti_ban_coord_weak", 5)
                coord_str = f" [좌표 약 ±{act_offset_range}px]"

            orig_t = act.delay_seconds if act.action_type == "delay" else getattr(act, "delay_seconds", 0.0)
            if act.action_type == "delay":
                sleep_total = round(orig_t + jitter, 2) if should_anti_ban else orig_t
                if should_anti_ban and jitter > 0:
                    log_msg = f"액션 실행: {sleep_total:.1f}초 (원본{orig_t:.2f}초) 대기"
                elif round(orig_t, 1) != round(orig_t, 2):
                    log_msg = f"액션 실행: {orig_t:.1f}초 (원본{orig_t:.2f}초) 대기"
                else:
                    log_msg = f"액션 실행: {sleep_total:.1f}초 대기"
            else:
                time_str = f" (안티밴 +{jitter:.2f}초)" if (should_anti_ban and jitter > 0) else ""
                log_msg = f"액션 실행: {act.get_summary()}{coord_str}{time_str}"

            self.sig_log.emit("ACTION", f"  ▶ {log_msg}")

            if act.action_type == "log_message":
                self.sig_log.emit("USER", f"  [사용자 로그] {act.log_text}")
            elif getattr(act, "custom_log", ""):
                self.sig_log.emit("USER", f"  [사용자 로그] {act.custom_log}")

            # Brief visual display delay (80ms) so overlay dotted indicator is visible before action
            if act.action_type in ("mouse_click", "mouse_drag"):
                time.sleep(0.08)

            InputController.execute_action(
                action=act,
                hwnd=self.hwnd,
                apply_anti_ban=use_anti_ban,
                offset_range=act_offset_range,
                min_delay=0.0,
                max_delay=offset_sec,
                precomputed_jitter=jitter
            )

            self.sig_action_finished.emit(act)

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
