"""
Scenario Preset Manager for FGOA.
Allows saving selected scenarios as reusable presets, managing preset libraries,
and importing/instantiating presets into any scenario sequence with clean ID remapping.
"""
import os
import json
import uuid
import datetime
from typing import List, Dict, Any, Optional
from core.models import Scenario, Project

PRESETS_DIR = os.path.expanduser("~/.fgoa_presets")


class PresetManager:
    """
    Handles saving, listing, loading, importing, and deleting scenario presets.
    """

    @classmethod
    def get_presets_directory(cls) -> str:
        os.makedirs(PRESETS_DIR, exist_ok=True)
        return PRESETS_DIR

    @classmethod
    def list_presets(cls) -> List[Dict[str, Any]]:
        """
        Returns list of available presets with metadata.
        Seeds built-in default presets if directory is empty.
        """
        presets_dir = cls.get_presets_directory()
        files = [f for f in os.listdir(presets_dir) if f.endswith(".json")]
        
        if not files:
            cls.seed_default_presets()
            files = [f for f in os.listdir(presets_dir) if f.endswith(".json")]

        presets = []
        for fname in files:
            fpath = os.path.join(presets_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    data["filepath"] = fpath
                    data["filename"] = fname
                    if "scenarios" in data and "scenario_count" not in data:
                        data["scenario_count"] = len(data["scenarios"])
                    presets.append(data)
            except Exception:
                continue

        # Sort: builtin first, then by name
        presets.sort(key=lambda p: (not p.get("is_builtin", False), p.get("name", "")))
        return presets

    @classmethod
    def save_preset(
        cls,
        name: str,
        scenarios: List[Scenario],
        description: str = "",
        filepath: Optional[str] = None
    ) -> str:
        """
        Saves given scenarios as a new preset.
        """
        if not scenarios:
            raise ValueError("프리셋으로 저장할 시나리오가 없습니다.")
        if not name or not name.strip():
            raise ValueError("프리셋 이름을 입력해주세요.")

        clean_name = name.strip()
        presets_dir = cls.get_presets_directory()

        if not filepath:
            safe_fname = "".join(c for c in clean_name if c.isalnum() or c in (' ', '_', '-')).rstrip()
            if not safe_fname:
                safe_fname = f"preset_{uuid.uuid4().hex[:6]}"
            fname = f"{safe_fname}.json"
            filepath = os.path.join(presets_dir, fname)
            # Collision handling
            counter = 1
            while os.path.exists(filepath):
                filepath = os.path.join(presets_dir, f"{safe_fname}_{counter}.json")
                counter += 1

        preset_id = f"preset_{uuid.uuid4().hex[:8]}"
        created_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        preset_data = {
            "id": preset_id,
            "name": clean_name,
            "description": description.strip(),
            "created_at": created_at,
            "is_builtin": False,
            "scenario_count": len(scenarios),
            "scenarios": [s.to_dict() for s in scenarios]
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(preset_data, f, indent=2, ensure_ascii=False)

        return filepath

    @classmethod
    def load_preset_file(cls, filepath: str) -> Dict[str, Any]:
        """Loads and returns raw preset dictionary from file."""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"프리셋 파일을 찾을 수 없습니다: {filepath}")
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    @classmethod
    def instantiate_preset_scenarios(
        cls,
        preset_data: Dict[str, Any],
        selected_indices: Optional[List[int]] = None
    ) -> List[Scenario]:
        """
        Converts preset scenario dicts into Scenario instances with new unique IDs
        and intelligently remaps internal jump / loop targets.
        """
        raw_scenarios = preset_data.get("scenarios", [])
        if not raw_scenarios:
            return []

        # Filter if selected_indices specified
        if selected_indices is not None:
            indices_set = set(selected_indices)
            raw_scenarios = [s for i, s in enumerate(raw_scenarios) if i in indices_set]

        # 1. Map old IDs (and numeric scenario numbers) to new UUIDs
        id_map: Dict[str, str] = {}
        for s_dict in raw_scenarios:
            old_id = s_dict.get("id")
            new_uuid = f"scen_{uuid.uuid4().hex[:8]}"
            if old_id:
                id_map[old_id] = new_uuid
            old_num = s_dict.get("scenario_number")
            if old_num is not None:
                id_map[str(old_num)] = new_uuid

        # 2. Instantiate and remap targets
        instances: List[Scenario] = []
        for s_dict in raw_scenarios:
            copied = json.loads(json.dumps(s_dict))  # Deep copy dict
            old_id = copied.get("id")
            copied["id"] = id_map.get(old_id, f"scen_{uuid.uuid4().hex[:8]}")
            # Reset scenario_number to None so the project renumbers it with fresh non-colliding IDs
            copied["scenario_number"] = None

            # Remap jump targets and loop parent
            if copied.get("jump_target_on_match") in id_map:
                copied["jump_target_on_match"] = id_map[copied["jump_target_on_match"]]
            if copied.get("jump_target_on_mismatch") in id_map:
                copied["jump_target_on_mismatch"] = id_map[copied["jump_target_on_mismatch"]]
            if copied.get("loop_target_id") in id_map:
                copied["loop_target_id"] = id_map[copied["loop_target_id"]]

            scen_obj = Scenario.from_dict(copied)
            instances.append(scen_obj)

        return instances

    @classmethod
    def delete_preset(cls, filepath: str) -> bool:
        """Deletes preset file from disk."""
        if os.path.exists(filepath):
            os.remove(filepath)
            return True
        return False

    @classmethod
    def seed_default_presets(cls):
        """Creates standard built-in starter presets if they don't already exist."""
        presets_dir = cls.get_presets_directory()

        default_presets = [
            {
                "id": "preset_battle_cycle",
                "name": "[기본] 전투 사이클 템플릿",
                "description": "전투 화면 인식 → 스킬 발동 → 클리어 후 복귀 기본 사이클",
                "created_at": "2026-09-22 00:00:00",
                "is_builtin": True,
                "scenarios": [
                    {
                        "id": "scen_b1",
                        "step_number": 1,
                        "scenario_number": 1,
                        "name": "전투 진입 확인",
                        "enabled": True,
                        "node_type": "normal",
                        "condition": {
                            "name": "전투 화면 인식",
                            "logic_operator": "AND",
                            "points": [
                                {"x": 100, "y": 100, "r": 220, "g": 20, "b": 60, "tolerance": 20, "match_mode": "match"}
                            ]
                        },
                        "on_match": "execute",
                        "on_mismatch": "retry",
                        "retry_max_count": 5,
                        "actions": [
                            {"action_type": "mouse_click", "x": 450, "y": 550, "mouse_button": "left"},
                            {"action_type": "delay", "delay_seconds": 1.5}
                        ]
                    },
                    {
                        "id": "scen_b2",
                        "step_number": 2,
                        "scenario_number": 2,
                        "name": "스킬 1 발동",
                        "enabled": True,
                        "node_type": "normal",
                        "condition": None,
                        "on_match": "execute",
                        "actions": [
                            {"action_type": "mouse_click", "x": 120, "y": 620, "mouse_button": "left"},
                            {"action_type": "delay", "delay_seconds": 2.0}
                        ]
                    },
                    {
                        "id": "scen_b3",
                        "step_number": 3,
                        "scenario_number": 3,
                        "name": "결과 대기 및 루프 복귀",
                        "enabled": True,
                        "node_type": "normal",
                        "condition": {
                            "name": "클리어 화면",
                            "logic_operator": "AND",
                            "points": [
                                {"x": 640, "y": 360, "r": 255, "g": 215, "b": 0, "tolerance": 25, "match_mode": "match"}
                            ]
                        },
                        "on_match": "jump",
                        "jump_target_on_match": "scen_b1",
                        "on_mismatch": "next",
                        "actions": [
                            {"action_type": "mouse_click", "x": 640, "y": 680, "mouse_button": "left"},
                            {"action_type": "delay", "delay_seconds": 3.0}
                        ]
                    }
                ]
            },
            {
                "id": "preset_click_delay",
                "name": "[기본] 단순 반복 클릭 및 딜레이",
                "description": "지정 좌표 순차 클릭 및 안전 대기 기본 템플릿",
                "created_at": "2026-09-22 00:00:00",
                "is_builtin": True,
                "scenarios": [
                    {
                        "id": "scen_cd1",
                        "step_number": 1,
                        "scenario_number": 1,
                        "name": "1차 확인 클릭",
                        "enabled": True,
                        "node_type": "normal",
                        "condition": None,
                        "on_match": "execute",
                        "actions": [
                            {"action_type": "mouse_click", "x": 500, "y": 500, "mouse_button": "left"},
                            {"action_type": "delay", "delay_seconds": 1.0}
                        ]
                    },
                    {
                        "id": "scen_cd2",
                        "step_number": 2,
                        "scenario_number": 2,
                        "name": "2차 진행 클릭",
                        "enabled": True,
                        "node_type": "normal",
                        "condition": None,
                        "on_match": "execute",
                        "actions": [
                            {"action_type": "mouse_click", "x": 800, "y": 600, "mouse_button": "left"},
                            {"action_type": "delay", "delay_seconds": 1.5}
                        ]
                    }
                ]
            },
            {
                "id": "preset_loop_block",
                "name": "[기본] 5회 카운트 루프 블록",
                "description": "루프 시작 노드(5회)와 종료 노드로 감싸진 안전 루프 템플릿",
                "created_at": "2026-09-22 00:00:00",
                "is_builtin": True,
                "scenarios": [
                    {
                        "id": "scen_lp_start",
                        "step_number": 1,
                        "scenario_number": 1,
                        "name": "루프 시작 (5회)",
                        "enabled": True,
                        "node_type": "loop_start",
                        "loop_mode": "count",
                        "loop_count": 5,
                        "condition": None,
                        "actions": []
                    },
                    {
                        "id": "scen_lp_work",
                        "step_number": 2,
                        "scenario_number": 2,
                        "name": "루프 내 작업",
                        "enabled": True,
                        "node_type": "normal",
                        "condition": None,
                        "actions": [
                            {"action_type": "mouse_click", "x": 600, "y": 450, "mouse_button": "left"},
                            {"action_type": "delay", "delay_seconds": 1.0}
                        ]
                    },
                    {
                        "id": "scen_lp_end",
                        "step_number": 3,
                        "scenario_number": 3,
                        "name": "루프 종료",
                        "enabled": True,
                        "node_type": "loop_end",
                        "loop_target_id": "scen_lp_start",
                        "condition": None,
                        "actions": []
                    }
                ]
            }
        ]

        for p in default_presets:
            p["scenario_count"] = len(p["scenarios"])
            safe_fname = p["id"] + ".json"
            fpath = os.path.join(presets_dir, safe_fname)
            if not os.path.exists(fpath):
                try:
                    with open(fpath, "w", encoding="utf-8") as f:
                        json.dump(p, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass
