"""
Condition Evaluator and Uniqueness Checker for FGOA.
Handles real-time pixel matching, continuous line sampling, and condition uniqueness validation.
"""
from typing import List, Tuple, Optional, Dict, Any
from PIL import Image
from core.models import Condition, ColorPoint, Scenario, Project
from core.screen_capture import ScreenCapture


class ConditionEvaluator:
    """Evaluates color conditions and checks for duplicates/uniqueness."""

    @staticmethod
    def sample_line_points(start_x: int, start_y: int, end_x: int, end_y: int,
                           count: int = 5,
                           image: Optional[Image.Image] = None,
                           hwnd: Optional[int] = None) -> List[ColorPoint]:
        """
        Generates N evenly spaced ColorPoints along a line from (start_x, start_y) to (end_x, end_y).
        Samples RGB values from image or live window if provided.
        """
        points: List[ColorPoint] = []
        if count < 2:
            count = 2

        import uuid
        line_group = f"line_{uuid.uuid4().hex[:6]}"

        for i in range(count):
            t = i / (count - 1)
            px = int(round(start_x + (end_x - start_x) * t))
            py = int(round(start_y + (end_y - start_y) * t))

            r, g, b = 255, 255, 255
            if image is not None:
                color = ScreenCapture.get_image_pixel(image, px, py)
                if color:
                    r, g, b = color[:3]
            elif hwnd is not None:
                color = ScreenCapture.get_client_pixel_color(hwnd, px, py)
                if color:
                    r, g, b = color

            pt = ColorPoint(
                x=px,
                y=py,
                r=r,
                g=g,
                b=b,
                tolerance=15,
                match_mode="match",
                point_type="line",
                line_group_id=line_group
            )
            points.append(pt)

        return points

    @staticmethod
    def evaluate(condition: Optional[Condition], hwnd: int) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Evaluates condition against live target window HWND.
        Returns:
            (is_matched, point_results_list)
        """
        if condition is None or not condition.points:
            # Unconditional
            return (True, [])

        point_results = []
        matches_count = 0
        total_points = len(condition.points)

        for pt in condition.points:
            actual_color = ScreenCapture.get_client_pixel_color(hwnd, pt.x, pt.y)
            if actual_color is None:
                passed = False
                actual_rgb = (0, 0, 0)
            else:
                actual_rgb = actual_color
                passed = pt.matches(actual_color[0], actual_color[1], actual_color[2])

            if passed:
                matches_count += 1

            point_results.append({
                "point_id": pt.id,
                "x": pt.x,
                "y": pt.y,
                "target_rgb": (pt.r, pt.g, pt.b),
                "actual_rgb": actual_rgb,
                "tolerance": pt.tolerance,
                "match_mode": pt.match_mode,
                "passed": passed
            })

        if condition.logic_operator == "OR":
            matched = matches_count > 0
        else:  # AND
            matched = matches_count == total_points

        return (matched, point_results)

    @staticmethod
    def are_conditions_duplicate(cond1: Condition, cond2: Condition, coord_thresh: int = 2, color_thresh: int = 5) -> bool:
        """
        Checks whether two conditions have effectively identical detection points
        (same coordinates within coord_thresh and RGB within color_thresh).
        """
        if len(cond1.points) != len(cond2.points):
            return False
        if len(cond1.points) == 0:
            return False

        # Sort points by (x, y) for deterministic comparison
        pts1 = sorted(cond1.points, key=lambda p: (p.x, p.y))
        pts2 = sorted(cond2.points, key=lambda p: (p.x, p.y))

        for p1, p2 in zip(pts1, pts2):
            if abs(p1.x - p2.x) > coord_thresh or abs(p1.y - p2.y) > coord_thresh:
                return False
            if (abs(p1.r - p2.r) > color_thresh or
                abs(p1.g - p2.g) > color_thresh or
                abs(p1.b - p2.b) > color_thresh):
                return False
            if p1.match_mode != p2.match_mode:
                return False

        return True

    @classmethod
    def check_project_uniqueness(cls, project: Project) -> Dict[str, List[str]]:
        """
        Analyzes all scenarios in the project.
        Returns a dict mapping scenario_id -> list of warning messages regarding duplicates.
        """
        warnings_map: Dict[str, List[str]] = {}
        scenarios_with_cond = [s for s in project.scenarios if s.condition and s.condition.points]

        for i in range(len(scenarios_with_cond)):
            s1 = scenarios_with_cond[i]
            for j in range(i + 1, len(scenarios_with_cond)):
                s2 = scenarios_with_cond[j]
                if cls.are_conditions_duplicate(s1.condition, s2.condition):
                    msg1 = f"⚠️ 시나리오 #{s2.step_number} [{s2.name}]와 조건이 동일합니다."
                    msg2 = f"⚠️ 시나리오 #{s1.step_number} [{s1.name}]와 조건이 동일합니다."
                    
                    if s1.condition.reference_image_path != s2.condition.reference_image_path:
                        msg1 += " (서로 다른 레퍼런스 이미지이지만 결과 프리셋 내용 일치)"
                        msg2 += " (서로 다른 레퍼런스 이미지이지만 결과 프리셋 내용 일치)"

                    warnings_map.setdefault(s1.id, []).append(msg1)
                    warnings_map.setdefault(s2.id, []).append(msg2)

        return warnings_map
