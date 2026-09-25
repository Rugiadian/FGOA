"""
Data models for FGOA (Windows Auto Input & Color Automation Tool).
"""
import uuid
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any


from core.path_utils import to_relative_path, to_absolute_path


@dataclass
class ColorPoint:
    """Represents a single color detection point relative to target window."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    x: int = 0
    y: int = 0
    r: int = 0
    g: int = 0
    b: int = 0
    tolerance: int = 15  # 0 ~ 255 tolerance per channel
    match_mode: str = "match"  # "match" (must match) or "not_match" (must differ)
    point_type: str = "single"  # "single" or "line"
    line_group_id: Optional[str] = None  # Group ID if generated as part of a line

    def matches(self, actual_r: int, actual_g: int, actual_b: int) -> bool:
        """Check if actual RGB matches target RGB within tolerance."""
        diff = (abs(self.r - actual_r) <= self.tolerance and
                abs(self.g - actual_g) <= self.tolerance and
                abs(self.b - actual_b) <= self.tolerance)
        return diff if self.match_mode == "match" else not diff

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ColorPoint":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Condition:
    """Execution condition containing multiple color detection points and logic."""
    id: str = field(default_factory=lambda: f"cond_{uuid.uuid4().hex[:6]}")
    condition_number: int = 1  # 고유 번호 (C1, C2...)
    name: str = "새 인식조건"
    logic_operator: str = "AND"  # "AND" (all points match) or "OR" (at least one)
    reference_image_path: Optional[str] = None
    points: List[ColorPoint] = field(default_factory=list)
    action_sequence_id: Optional[str] = None  # 자동 연결된 액션시퀀스 모듈 ID

    def get_summary(self) -> str:
        """User-friendly summary of this condition."""
        if not self.points:
            return "무조건 실행"
        return f"포인트 {len(self.points)}개 ({self.logic_operator})"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "condition_number": self.condition_number,
            "name": self.name,
            "logic_operator": self.logic_operator,
            "reference_image_path": to_relative_path(self.reference_image_path),
            "points": [p.to_dict() for p in self.points],
            "action_sequence_id": self.action_sequence_id
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Condition":
        points = [ColorPoint.from_dict(p) for p in data.get("points", [])]
        raw_ref = data.get("reference_image_path")
        return cls(
            id=data.get("id", f"cond_{uuid.uuid4().hex[:6]}"),
            condition_number=int(data.get("condition_number", 1)),
            name=data.get("name", "조건"),
            logic_operator=data.get("logic_operator", "AND"),
            reference_image_path=to_relative_path(raw_ref) if raw_ref else None,
            points=points,
            action_sequence_id=data.get("action_sequence_id")
        )


@dataclass
class Action:
    """Single input automation action (mouse, keyboard, wait)."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    action_type: str = "mouse_click"  # mouse_click, mouse_drag, key_press, text_type, delay, sound_beep, log_message
    
    # Mouse Click params (relative coords)
    x: int = 0
    y: int = 0
    mouse_button: str = "left"  # left, right, middle
    click_type: str = "single"  # single, double
    repeat_count: int = 1
    
    # Mouse Drag params
    end_x: int = 0
    end_y: int = 0
    drag_duration_ms: int = 300
    
    # Keyboard params
    key: str = "Enter"
    modifiers: List[str] = field(default_factory=list)  # ["Ctrl", "Alt", "Shift"]
    text: str = ""
    
    # Delay params
    delay_seconds: float = 0.5
    
    # Anti-ban override (None = use project default, True/False = explicit)
    anti_ban: Optional[bool] = None

    # Coordinate Anti-ban: "weak" (default, 활성화), "strong", "none" (해제)
    coord_anti_ban: str = "weak"

    # Log / Beep
    log_text: str = ""
    custom_log: str = ""  # Action execution custom log message
    beep_freq: int = 1000
    beep_duration_ms: int = 200

    def get_summary(self) -> str:
        """User-friendly one-line summary of this action."""
        if self.action_type == "mouse_click":
            btn_str = "좌클릭" if self.mouse_button == "left" else ("우클릭" if self.mouse_button == "right" else "휠클릭")
            if self.click_type == "double":
                btn_str = f"{btn_str} 더블"
            repeat_str = f" x{self.repeat_count}" if self.repeat_count > 1 else ""
            return f"{btn_str} ({self.x}, {self.y}){repeat_str}"
        elif self.action_type == "mouse_drag":
            return f"드래그 ({self.x}, {self.y}) → ({self.end_x}, {self.end_y})"
        elif self.action_type == "key_press":
            mod_str = "+".join(self.modifiers) + "+" if self.modifiers else ""
            return f"키 입력 [{mod_str}{self.key}]"
        elif self.action_type == "text_type":
            return f"텍스트 입력 \"{self.text[:15]}{'...' if len(self.text) > 15 else ''}\""
        elif self.action_type == "delay":
            return f"{self.delay_seconds:.1f}초 대기"
        elif self.action_type == "sound_beep":
            return f"비프음 ({self.beep_freq}Hz)"
        elif self.action_type == "log_message":
            return f"로그: {self.log_text[:20]}"
        return "알 수 없는 액션"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Action":
        kwargs = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        if "coord_anti_ban" not in data:
            legacy_ab = data.get("anti_ban")
            if legacy_ab is False:
                kwargs["coord_anti_ban"] = "none"
            else:
                kwargs["coord_anti_ban"] = "weak"
        return cls(**kwargs)


@dataclass
class ActionSequence:
    """A reusable modular bundle of automation actions."""
    id: str = field(default_factory=lambda: f"seq_{uuid.uuid4().hex[:6]}")
    sequence_number: int = 1      # 고유 번호 (A1, A2...)
    name: str = "새 액션 시퀀스"
    description: str = ""
    actions: List[Action] = field(default_factory=list)
    last_action_image_path: Optional[str] = None

    def get_summary(self) -> str:
        """Returns summarized text of actions in this sequence."""
        if not self.actions:
            return "(액션 없음)"
        summaries = [a.get_summary() for a in self.actions]
        if len(summaries) <= 3:
            return " → ".join(summaries)
        return f"{summaries[0]} → {summaries[1]} 외 {len(summaries) - 2}개"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "sequence_number": self.sequence_number,
            "name": self.name,
            "description": self.description,
            "actions": [a.to_dict() for a in self.actions],
            "last_action_image_path": to_relative_path(self.last_action_image_path)
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ActionSequence":
        actions = [Action.from_dict(a) for a in data.get("actions", [])]
        raw_img = data.get("last_action_image_path")
        return cls(
            id=data.get("id", f"seq_{uuid.uuid4().hex[:6]}"),
            sequence_number=int(data.get("sequence_number", 1)),
            name=data.get("name", "새 액션 시퀀스"),
            description=data.get("description", ""),
            actions=actions,
            last_action_image_path=to_relative_path(raw_img) if raw_img else None
        )


@dataclass
class Scenario:
    """A workflow step combining Condition checking and Action execution (Composite Node)."""
    id: str = field(default_factory=lambda: f"scen_{uuid.uuid4().hex[:6]}")
    step_number: int = 1          # 실행 순서 (1, 2, 3... 드래그/이동 시 재계산)
    scenario_number: int = 1      # 시나리오 고유 번호 (위치가 바뀌어도 유지되는 불변 고유 식별 번호)
    name: str = "새 시나리오"
    enabled: bool = True
    
    # Node Type & Loop Controls
    node_type: str = "normal"     # "normal", "loop_start", "loop_end"
    loop_mode: str = "count"      # "count" (지정 횟수), "until_match" (조건 일치 시 탈출), "while_match" (조건 일치 동안 반복), "infinite" (무한)
    loop_count: int = 5           # 반복 횟수 (또는 최대 안전 한도)
    loop_target_id: str = ""      # loop_end일 때 대응되는 loop_start의 ID
    
    # Modular Condition slot (references project.conditions[condition_id])
    condition_id: Optional[str] = None
    condition: Optional[Condition] = None  # Direct / legacy condition
    
    # Branching on match
    on_match: str = "execute"  # "execute" (run actions then next), "jump" (jump to target), "stop" (stop automation), "break_loop" (루프 탈출)
    jump_target_on_match: str = ""  # Scenario ID to jump to
    
    # Branching on mismatch
    on_mismatch: str = "next"  # "next" (skip actions and go to next step), "jump", "stop", "retry", "break_loop"
    jump_target_on_mismatch: str = ""  # Scenario ID to jump to
    retry_max_count: int = 3
    retry_interval_sec: float = 0.5
    retry_fail_action: str = "stop"  # "stop" (정지), "jump" (특정 시나리오로 점프), "next" (다음 단계로 진행)
    retry_fail_jump_target: str = ""  # retry_fail_action이 "jump"일 때 대상 시나리오 ID
    
    # Modular Action Sequence slot (references project.action_sequences[sequence_id])
    sequence_id: Optional[str] = None
    actions: List[Action] = field(default_factory=list)  # Standalone / fallback actions
    post_delay_seconds: float = 0.2

    # Custom log and last action image path
    custom_log: str = ""  # 액션 실행 시 출력할 사용자 지정 로그 문장
    last_action_image_path: Optional[str] = None  # 액션 좌표 지정에 마지막으로 사용한 이미지
    reference_image_path: Optional[str] = None  # 시나리오 노드 고유 레퍼런스 이미지 (None이면 인식조건 레퍼런스 이미지 자동 사용)

    def get_effective_reference_image(self, project: Optional["Project"] = None) -> Optional[str]:
        """
        Returns effective reference image path for this scenario node.
        Defaults to the linked Condition's reference image path if not explicitly set.
        Returns None if neither is specified.
        """
        if self.reference_image_path:
            return self.reference_image_path
        eff_cond = self.get_effective_condition(project)
        if eff_cond and getattr(eff_cond, "reference_image_path", None):
            return eff_cond.reference_image_path
        return None

    def is_loop_start(self) -> bool:
        return self.node_type == "loop_start"

    def is_loop_end(self) -> bool:
        return self.node_type == "loop_end"

    def is_loop_node(self) -> bool:
        return self.node_type in ("loop_start", "loop_end")

    def get_loop_summary(self) -> str:
        if self.node_type == "loop_start":
            if self.loop_mode == "count":
                return f"🔁 루프 시작: {self.loop_count}회 반복"
            elif self.loop_mode == "until_match":
                return f"🔁 루프 시작: 화면 조건 일치 시 탈출 (최대 {self.loop_count}회)"
            elif self.loop_mode == "while_match":
                return f"🔁 루프 시작: 화면 조건 일치 동안 반복"
            elif self.loop_mode == "infinite":
                return "🔁 루프 시작: 무한 반복"
            return "🔁 루프 시작"
        elif self.node_type == "loop_end":
            return "🔁 루프 종료 (시작으로 복귀)"
        return ""

    def get_effective_condition(self, project: Optional["Project"] = None) -> Optional[Condition]:
        """Returns effective condition: from linked Condition module if condition_id is set and found, else self.condition."""
        if self.condition_id and project:
            cond = project.find_condition(self.condition_id)
            if cond:
                return cond
        return self.condition

    def get_effective_actions(self, project: Optional["Project"] = None) -> List[Action]:
        """Returns effective actions: from linked ActionSequence if sequence_id is set and found, else self.actions."""
        if self.sequence_id and project:
            seq = project.find_action_sequence(self.sequence_id)
            if seq:
                return seq.actions
        return self.actions

    def get_actions_summary(self, project: Optional["Project"] = None) -> str:
        """Returns summarized text of actions in this scenario."""
        if self.sequence_id and project:
            seq = project.find_action_sequence(self.sequence_id)
            if seq:
                return f"🔗 [{seq.name}] ({len(seq.actions)}개 액션) - {seq.get_summary()}"
        actions = self.actions
        if not actions:
            return "(액션 없음)"
        summaries = [a.get_summary() for a in actions]
        if len(summaries) <= 3:
            return " → ".join(summaries)
        return f"{summaries[0]} → {summaries[1]} 외 {len(summaries) - 2}개"

    def get_condition_summary(self, project: Optional["Project"] = None) -> str:
        """Returns summarized text of condition."""
        if self.node_type == "loop_start":
            eff_cond = self.get_effective_condition(project)
            if self.loop_mode in ("until_match", "while_match") and eff_cond and eff_cond.points:
                pts = eff_cond.points
                mode_str = "일치 시 탈출" if self.loop_mode == "until_match" else "일치 동안 반복"
                return f"루프 탈출 조건: 포인트 {len(pts)}개 ({mode_str})"
            return f"횟수 제어 ({self.loop_count}회)"
        elif self.node_type == "loop_end":
            return "(루프 시작으로 복귀)"
            
        eff_cond = self.get_effective_condition(project)
        if not eff_cond or not eff_cond.points:
            return "무조건 실행"
        pts = eff_cond.points
        c_num = getattr(eff_cond, "condition_number", 1)
        return f"[C{c_num}] {eff_cond.name} ({len(pts)}개 {eff_cond.logic_operator})"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "step_number": self.step_number,
            "scenario_number": self.scenario_number,
            "name": self.name,
            "enabled": self.enabled,
            "node_type": self.node_type,
            "loop_mode": self.loop_mode,
            "loop_count": self.loop_count,
            "loop_target_id": self.loop_target_id,
            "condition_id": self.condition_id,
            "condition": self.condition.to_dict() if self.condition else None,
            "on_match": self.on_match,
            "jump_target_on_match": self.jump_target_on_match,
            "on_mismatch": self.on_mismatch,
            "jump_target_on_mismatch": self.jump_target_on_mismatch,
            "retry_max_count": self.retry_max_count,
            "retry_interval_sec": self.retry_interval_sec,
            "retry_fail_action": self.retry_fail_action,
            "retry_fail_jump_target": self.retry_fail_jump_target,
            "sequence_id": self.sequence_id,
            "actions": [a.to_dict() for a in self.actions],
            "post_delay_seconds": self.post_delay_seconds,
            "custom_log": self.custom_log,
            "last_action_image_path": to_relative_path(self.last_action_image_path),
            "reference_image_path": to_relative_path(self.reference_image_path)
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Scenario":
        cond_data = data.get("condition")
        condition = Condition.from_dict(cond_data) if cond_data else None
        actions = [Action.from_dict(a) for a in data.get("actions", [])]
        raw_img = data.get("last_action_image_path")
        return cls(
            id=data.get("id", f"scen_{uuid.uuid4().hex[:6]}"),
            step_number=data.get("step_number", 1),
            scenario_number=data.get("scenario_number", data.get("step_number", 1)),
            name=data.get("name", "시나리오"),
            enabled=data.get("enabled", True),
            node_type=data.get("node_type", "normal"),
            loop_mode=data.get("loop_mode", "count"),
            loop_count=data.get("loop_count", 5),
            loop_target_id=data.get("loop_target_id", ""),
            condition_id=data.get("condition_id"),
            condition=condition,
            on_match=data.get("on_match", "execute"),
            jump_target_on_match=data.get("jump_target_on_match", ""),
            on_mismatch=data.get("on_mismatch", "next"),
            jump_target_on_mismatch=data.get("jump_target_on_mismatch", ""),
            retry_max_count=data.get("retry_max_count", 3),
            retry_interval_sec=data.get("retry_interval_sec", 0.5),
            retry_fail_action=data.get("retry_fail_action", "stop"),
            retry_fail_jump_target=data.get("retry_fail_jump_target", ""),
            sequence_id=data.get("sequence_id"),
            actions=actions,
            post_delay_seconds=data.get("post_delay_seconds", 0.2),
            custom_log=data.get("custom_log", ""),
            last_action_image_path=to_relative_path(raw_img) if raw_img else None,
            reference_image_path=to_relative_path(data.get("reference_image_path")) if data.get("reference_image_path") else None
        )


@dataclass
class Project:
    """Root project configuration containing all scenarios and global settings."""
    version: str = "1.0.0"
    name: str = "FGOA Auto Project"
    target_window_title: str = ""
    target_client_width: int = 1600
    target_client_height: int = 900
    loop_count: int = 1  # 0 means infinite loop
    loop_delay_seconds: float = 1.0
    anti_ban_enabled: bool = False
    anti_ban_offset: int = 10
    anti_ban_min_delay: float = 0.0
    anti_ban_max_delay: float = 1.0
    anti_ban_offset_seconds: float = 1.0  # +n seconds delay offset applied globally
    anti_ban_coord_weak: int = 5          # Coordinate offset weak (약): ±5px
    anti_ban_coord_strong: int = 15       # Coordinate offset strong (강): ±15px
    conditions: List[Condition] = field(default_factory=list)
    action_sequences: List[ActionSequence] = field(default_factory=list)
    scenarios: List[Scenario] = field(default_factory=list)

    def renumber_steps(self):
        """Update step_number for all scenarios sequentially starting at 1,
        and guarantee every scenario has a strictly unique scenario_number and unique ID
        without corrupting jump targets or loop bindings."""
        if not self.scenarios:
            return

        # 1. Update sequential execution order (step_number)
        for idx, scen in enumerate(self.scenarios, start=1):
            scen.step_number = idx

        # 2. Guarantee unique ID for each scenario and remap any duplicates
        seen_ids = set()
        for scen in self.scenarios:
            if not getattr(scen, "id", None) or scen.id in seen_ids:
                old_id = getattr(scen, "id", "")
                new_id = f"scen_{uuid.uuid4().hex[:8]}"
                scen.id = new_id
                if old_id:
                    # Update any jump or loop references in project
                    for other in self.scenarios:
                        if other.jump_target_on_match == old_id:
                            other.jump_target_on_match = new_id
                        if other.jump_target_on_mismatch == old_id:
                            other.jump_target_on_mismatch = new_id
                        if other.loop_target_id == old_id:
                            other.loop_target_id = new_id
            seen_ids.add(scen.id)

        # 3. Guarantee strictly unique scenario_number
        allocated_nums = set()
        needs_num = []
        for scen in self.scenarios:
            num = getattr(scen, "scenario_number", None)
            if num is not None and isinstance(num, int) and num > 0 and num not in allocated_nums:
                allocated_nums.add(num)
            else:
                needs_num.append(scen)

        next_avail = (max(allocated_nums) + 1) if allocated_nums else 1
        for scen in needs_num:
            scen.scenario_number = next_avail
            allocated_nums.add(next_avail)
            next_avail += 1

        # 4. Normalize legacy numeric jump targets to robust UUIDs
        num_to_id = {s.scenario_number: s.id for s in self.scenarios}
        for scen in self.scenarios:
            # Check jump_target_on_match
            if scen.jump_target_on_match and scen.jump_target_on_match.isdigit():
                t_num = int(scen.jump_target_on_match)
                if t_num in num_to_id:
                    scen.jump_target_on_match = num_to_id[t_num]
            # Check jump_target_on_mismatch
            if scen.jump_target_on_mismatch and scen.jump_target_on_mismatch.isdigit():
                t_num = int(scen.jump_target_on_mismatch)
                if t_num in num_to_id:
                    scen.jump_target_on_mismatch = num_to_id[t_num]

    def get_next_scenario_number(self) -> int:
        """Generate the next unique scenario number not colliding with any existing node."""
        nums = [getattr(s, "scenario_number", 0) for s in self.scenarios if getattr(s, "scenario_number", 0) > 0]
        return (max(nums) + 1) if nums else 1

    def get_next_condition_number(self) -> int:
        """Generate next unique condition number (1, 2, 3...)."""
        nums = [getattr(c, "condition_number", 0) for c in self.conditions if getattr(c, "condition_number", 0) > 0]
        return (max(nums) + 1) if nums else 1

    def get_next_sequence_number(self) -> int:
        """Generate next unique sequence number (1, 2, 3...)."""
        nums = [getattr(s, "sequence_number", 0) for s in self.action_sequences if getattr(s, "sequence_number", 0) > 0]
        return (max(nums) + 1) if nums else 1

    def renumber_modules(self):
        """Ensure all conditions and sequences have unique positive numbers."""
        used_c = set()
        for c in self.conditions:
            if not getattr(c, "condition_number", None) or c.condition_number in used_c:
                c.condition_number = (max(used_c) + 1) if used_c else 1
            used_c.add(c.condition_number)

        used_s = set()
        for s in self.action_sequences:
            if not getattr(s, "sequence_number", None) or s.sequence_number in used_s:
                s.sequence_number = (max(used_s) + 1) if used_s else 1
            used_s.add(s.sequence_number)

    def find_condition(self, cond_id: str) -> Optional[Condition]:
        """Find registered Condition module by ID."""
        for c in self.conditions:
            if c.id == cond_id:
                return c
        return None

    def find_condition_by_number(self, num: int) -> Optional[Condition]:
        for c in self.conditions:
            if getattr(c, "condition_number", None) == num:
                return c
        return None

    def add_condition(self, cond: Condition):
        """Add a condition module if not already present."""
        if not any(c.id == cond.id for c in self.conditions):
            self.conditions.append(cond)

    def delete_condition(self, cond_id: str):
        """Delete a condition module and unlink any scenarios referencing it."""
        self.conditions = [c for c in self.conditions if c.id != cond_id]
        for scen in self.scenarios:
            if scen.condition_id == cond_id:
                scen.condition_id = None

    def find_action_sequence(self, seq_id: str) -> Optional[ActionSequence]:
        """Find registered ActionSequence by ID."""
        for seq in self.action_sequences:
            if seq.id == seq_id:
                return seq
        return None

    def find_action_sequence_by_number(self, num: int) -> Optional[ActionSequence]:
        for seq in self.action_sequences:
            if getattr(seq, "sequence_number", None) == num:
                return seq
        return None

    def add_action_sequence(self, seq: ActionSequence):
        """Add a new action sequence if not already present."""
        if not any(s.id == seq.id for s in self.action_sequences):
            self.action_sequences.append(seq)

    def delete_action_sequence(self, seq_id: str):
        """Delete an action sequence and unlink any scenarios referencing it."""
        self.action_sequences = [s for s in self.action_sequences if s.id != seq_id]
        for scen in self.scenarios:
            if scen.sequence_id == seq_id:
                scen.sequence_id = None
        for cond in self.conditions:
            if cond.action_sequence_id == seq_id:
                cond.action_sequence_id = None

    def create_composite_scenario(self, name: str = "새 시나리오", node_type: str = "normal", add_to_project: bool = True) -> Scenario:
        """
        Creates a new modular composite scenario with newly paired Condition and ActionSequence modules.
        The condition automatically links to the bundled action sequence as default.
        """
        scen_num = self.get_next_scenario_number()
        c_num = self.get_next_condition_number()
        s_num = self.get_next_sequence_number()

        seq = ActionSequence(
            id=f"seq_{uuid.uuid4().hex[:6]}",
            sequence_number=s_num,
            name=f"{name} 액션"
        )
        cond = Condition(
            id=f"cond_{uuid.uuid4().hex[:6]}",
            condition_number=c_num,
            name=f"{name} 조건",
            action_sequence_id=seq.id
        )
        self.add_condition(cond)
        self.add_action_sequence(seq)

        scen = Scenario(
            name=name,
            scenario_number=scen_num,
            node_type=node_type,
            condition_id=cond.id,
            sequence_id=seq.id,
            condition=cond,
            actions=seq.actions
        )
        if add_to_project:
            self.scenarios.append(scen)
            self.renumber_steps()
        return scen

    def compute_hierarchy_depths(self) -> List[int]:
        """Calculate nesting hierarchy depth (0, 1, 2...) for each scenario."""
        depths = []
        current_depth = 0
        for scen in self.scenarios:
            if scen.node_type == "loop_end":
                current_depth = max(0, current_depth - 1)
                depths.append(current_depth)
            elif scen.node_type == "loop_start":
                depths.append(current_depth)
                current_depth += 1
            else:
                depths.append(current_depth)
        return depths

    def find_matching_loop_end(self, start_idx: int) -> Optional[int]:
        """Find corresponding loop_end index for a loop_start at start_idx."""
        if start_idx < 0 or start_idx >= len(self.scenarios):
            return None
        depth = 0
        for i in range(start_idx, len(self.scenarios)):
            s = self.scenarios[i]
            if s.node_type == "loop_start":
                depth += 1
            elif s.node_type == "loop_end":
                depth -= 1
                if depth == 0:
                    return i
        return None

    def find_matching_loop_start(self, end_idx: int) -> Optional[int]:
        """Find corresponding loop_start index for a loop_end at end_idx."""
        if end_idx < 0 or end_idx >= len(self.scenarios):
            return None
        depth = 0
        for i in range(end_idx, -1, -1):
            s = self.scenarios[i]
            if s.node_type == "loop_end":
                depth += 1
            elif s.node_type == "loop_start":
                depth -= 1
                if depth == 0:
                    return i
        return None

    def find_scenario_by_id(self, scen_id: str) -> Optional[Scenario]:
        for s in self.scenarios:
            if s.id == scen_id:
                return s
        return None

    def find_scenario_by_number(self, num: int) -> Optional[Scenario]:
        for s in self.scenarios:
            if getattr(s, "scenario_number", None) == num:
                return s
        return None

    def find_scenario_by_step(self, step_no: int) -> Optional[Scenario]:
        for s in self.scenarios:
            if s.step_number == step_no:
                return s
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "name": self.name,
            "target_window_title": self.target_window_title,
            "target_client_width": self.target_client_width,
            "target_client_height": self.target_client_height,
            "loop_count": self.loop_count,
            "loop_delay_seconds": self.loop_delay_seconds,
            "anti_ban_enabled": self.anti_ban_enabled,
            "anti_ban_offset": self.anti_ban_offset,
            "anti_ban_min_delay": self.anti_ban_min_delay,
            "anti_ban_max_delay": self.anti_ban_max_delay,
            "anti_ban_offset_seconds": self.anti_ban_offset_seconds,
            "anti_ban_coord_weak": self.anti_ban_coord_weak,
            "anti_ban_coord_strong": self.anti_ban_coord_strong,
            "conditions": [c.to_dict() for c in self.conditions],
            "action_sequences": [s.to_dict() for s in self.action_sequences],
            "scenarios": [s.to_dict() for s in self.scenarios]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Project":
        conditions = [Condition.from_dict(c) for c in data.get("conditions", [])]
        action_sequences = [ActionSequence.from_dict(s) for s in data.get("action_sequences", [])]
        scenarios = [Scenario.from_dict(s) for s in data.get("scenarios", [])]
        offset_sec = float(data.get("anti_ban_offset_seconds", data.get("anti_ban_max_delay", 1.0)))
        proj = cls(
            version=data.get("version", "1.0.0"),
            name=data.get("name", "FGOA Auto Project"),
            target_window_title=data.get("target_window_title", ""),
            target_client_width=data.get("target_client_width", 1600),
            target_client_height=data.get("target_client_height", 900),
            loop_count=data.get("loop_count", 1),
            loop_delay_seconds=data.get("loop_delay_seconds", 1.0),
            anti_ban_enabled=data.get("anti_ban_enabled", False),
            anti_ban_offset=data.get("anti_ban_offset", 10),
            anti_ban_min_delay=data.get("anti_ban_min_delay", 0.0),
            anti_ban_max_delay=offset_sec,
            anti_ban_offset_seconds=offset_sec,
            anti_ban_coord_weak=int(data.get("anti_ban_coord_weak", 5)),
            anti_ban_coord_strong=int(data.get("anti_ban_coord_strong", 15)),
            conditions=conditions,
            action_sequences=action_sequences,
            scenarios=scenarios
        )

        # Legacy auto-migration for composite modular architecture ONLY if data lacks modular arrays
        is_legacy = ("conditions" not in data and "action_sequences" not in data)
        if is_legacy:
            for scen in proj.scenarios:
                if scen.condition and not scen.condition_id:
                    existing = proj.find_condition(scen.condition.id)
                    if not existing:
                        if not getattr(scen.condition, "condition_number", None):
                            scen.condition.condition_number = proj.get_next_condition_number()
                        if not scen.condition.name or scen.condition.name == "조건":
                            scen.condition.name = f"{scen.name} 조건"
                        proj.add_condition(scen.condition)
                        scen.condition_id = scen.condition.id
                    else:
                        scen.condition_id = existing.id

                if scen.actions and not scen.sequence_id:
                    s_num = proj.get_next_sequence_number()
                    seq = ActionSequence(
                        id=f"seq_{uuid.uuid4().hex[:6]}",
                        sequence_number=s_num,
                        name=f"{scen.name} 시퀀스",
                        actions=scen.actions
                    )
                    proj.add_action_sequence(seq)
                    scen.sequence_id = seq.id

                # Link default action sequence in condition if not set
                if scen.condition_id and scen.sequence_id:
                    cond = proj.find_condition(scen.condition_id)
                    if cond and not cond.action_sequence_id:
                        cond.action_sequence_id = scen.sequence_id

        proj.renumber_steps()
        proj.renumber_modules()
        return proj
