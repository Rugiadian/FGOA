"""
Data models for FGOA (Windows Auto Input & Color Automation Tool).
"""
import uuid
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any


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
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = "조건 1"
    logic_operator: str = "AND"  # "AND" (all points match) or "OR" (at least one)
    reference_image_path: Optional[str] = None
    points: List[ColorPoint] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "logic_operator": self.logic_operator,
            "reference_image_path": self.reference_image_path,
            "points": [p.to_dict() for p in self.points]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Condition":
        points = [ColorPoint.from_dict(p) for p in data.get("points", [])]
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            name=data.get("name", "조건"),
            logic_operator=data.get("logic_operator", "AND"),
            reference_image_path=data.get("reference_image_path"),
            points=points
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
    
    # Log / Beep
    log_text: str = ""
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
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Scenario:
    """A workflow step combining Condition checking and Action execution."""
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
    
    # Condition
    condition: Optional[Condition] = None  # None means unconditional execution
    
    # Branching on match
    on_match: str = "execute"  # "execute" (run actions then next), "jump" (jump to target), "stop" (stop automation), "break_loop" (루프 탈출)
    jump_target_on_match: str = ""  # Scenario ID to jump to
    
    # Branching on mismatch
    on_mismatch: str = "next"  # "next" (skip actions and go to next step), "jump", "stop", "retry", "break_loop"
    jump_target_on_mismatch: str = ""  # Scenario ID to jump to
    retry_max_count: int = 3
    retry_interval_sec: float = 0.5
    
    # Actions to execute when condition is met (or unconditional)
    actions: List[Action] = field(default_factory=list)
    post_delay_seconds: float = 0.2

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

    def get_actions_summary(self) -> str:
        """Returns summarized text of actions in this scenario."""
        if not self.actions:
            return "(액션 없음)"
        summaries = [a.get_summary() for a in self.actions]
        if len(summaries) <= 3:
            return " → ".join(summaries)
        return f"{summaries[0]} → {summaries[1]} 외 {len(summaries) - 2}개"

    def get_condition_summary(self) -> str:
        """Returns summarized text of condition."""
        if self.node_type == "loop_start":
            if self.loop_mode in ("until_match", "while_match") and self.condition and self.condition.points:
                pts = self.condition.points
                mode_str = "일치 시 탈출" if self.loop_mode == "until_match" else "일치 동안 반복"
                return f"루프 탈출 조건: 포인트 {len(pts)}개 ({mode_str})"
            return f"횟수 제어 ({self.loop_count}회)"
        elif self.node_type == "loop_end":
            return "(루프 시작으로 복귀)"
            
        if not self.condition or not self.condition.points:
            return "무조건 실행"
        pts = self.condition.points
        return f"포인트 {len(pts)}개 ({self.condition.logic_operator})"

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
            "condition": self.condition.to_dict() if self.condition else None,
            "on_match": self.on_match,
            "jump_target_on_match": self.jump_target_on_match,
            "on_mismatch": self.on_mismatch,
            "jump_target_on_mismatch": self.jump_target_on_mismatch,
            "retry_max_count": self.retry_max_count,
            "retry_interval_sec": self.retry_interval_sec,
            "actions": [a.to_dict() for a in self.actions],
            "post_delay_seconds": self.post_delay_seconds
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Scenario":
        cond_data = data.get("condition")
        condition = Condition.from_dict(cond_data) if cond_data else None
        actions = [Action.from_dict(a) for a in data.get("actions", [])]
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
            condition=condition,
            on_match=data.get("on_match", "execute"),
            jump_target_on_match=data.get("jump_target_on_match", ""),
            on_mismatch=data.get("on_mismatch", "next"),
            jump_target_on_mismatch=data.get("jump_target_on_mismatch", ""),
            retry_max_count=data.get("retry_max_count", 3),
            retry_interval_sec=data.get("retry_interval_sec", 0.5),
            actions=actions,
            post_delay_seconds=data.get("post_delay_seconds", 0.2)
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
    scenarios: List[Scenario] = field(default_factory=list)

    def renumber_steps(self):
        """Update step_number for all scenarios sequentially starting at 1."""
        for idx, scen in enumerate(self.scenarios, start=1):
            scen.step_number = idx
            if not hasattr(scen, "scenario_number") or scen.scenario_number is None or scen.scenario_number <= 0:
                scen.scenario_number = idx

    def get_next_scenario_number(self) -> int:
        """Generate the next unique scenario number."""
        nums = [getattr(s, "scenario_number", 0) for s in self.scenarios if getattr(s, "scenario_number", 0) > 0]
        return max(nums, default=0) + 1

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
            "scenarios": [s.to_dict() for s in self.scenarios]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Project":
        scenarios = [Scenario.from_dict(s) for s in data.get("scenarios", [])]
        proj = cls(
            version=data.get("version", "1.0.0"),
            name=data.get("name", "FGOA Auto Project"),
            target_window_title=data.get("target_window_title", ""),
            target_client_width=data.get("target_client_width", 1600),
            target_client_height=data.get("target_client_height", 900),
            loop_count=data.get("loop_count", 1),
            loop_delay_seconds=data.get("loop_delay_seconds", 1.0),
            scenarios=scenarios
        )
        proj.renumber_steps()
        return proj
