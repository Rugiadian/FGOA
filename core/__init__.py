"""
FGOA Core Package
"""
from core.models import ColorPoint, Condition, Action, Scenario, Project
from core.window_manager import WindowManager, WindowInfo
from core.screen_capture import ScreenCapture
from core.input_controller import InputController
from core.evaluator import ConditionEvaluator
from core.runner import WorkflowRunner
from core.config import get_config_filepath
from core.version import __version__

__all__ = [
    "__version__",
    "ColorPoint", "Condition", "Action", "Scenario", "Project",
    "WindowManager", "WindowInfo", "ScreenCapture", "InputController",
    "ConditionEvaluator", "WorkflowRunner", "get_config_filepath"
]

