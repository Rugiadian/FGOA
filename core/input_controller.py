"""
Input Controller module for FGOA.
Simulates mouse clicks, drags, keyboard shortcuts, and text entry using Win32 API SendInput.
"""
import time
import ctypes
from ctypes import wintypes
from typing import List, Tuple, Optional
import win32api
import win32con
from core.window_manager import WindowManager


# Win32 Constants
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_ABSOLUTE = 0x8000

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

VK_MAP = {
    "Enter": win32con.VK_RETURN,
    "Return": win32con.VK_RETURN,
    "Space": win32con.VK_SPACE,
    "Esc": win32con.VK_ESCAPE,
    "Escape": win32con.VK_ESCAPE,
    "Tab": win32con.VK_TAB,
    "Back": win32con.VK_BACK,
    "Backspace": win32con.VK_BACK,
    "Delete": win32con.VK_DELETE,
    "Up": win32con.VK_UP,
    "Down": win32con.VK_DOWN,
    "Left": win32con.VK_LEFT,
    "Right": win32con.VK_RIGHT,
    "Shift": win32con.VK_SHIFT,
    "Ctrl": win32con.VK_CONTROL,
    "Control": win32con.VK_CONTROL,
    "Alt": win32con.VK_MENU,
    "F1": win32con.VK_F1, "F2": win32con.VK_F2, "F3": win32con.VK_F3, "F4": win32con.VK_F4,
    "F5": win32con.VK_F5, "F6": win32con.VK_F6, "F7": win32con.VK_F7, "F8": win32con.VK_F8,
    "F9": win32con.VK_F9, "F10": win32con.VK_F10, "F11": win32con.VK_F11, "F12": win32con.VK_F12,
}


class InputController:
    """Provides high precision mouse and keyboard simulation."""

    @staticmethod
    def set_cursor_pos(screen_x: int, screen_y: int):
        ctypes.windll.user32.SetCursorPos(screen_x, screen_y)

    @classmethod
    def click_at(cls, hwnd: int, rel_x: int, rel_y: int, button: str = "left", click_type: str = "single", repeat: int = 1):
        """
        Clicks at relative client coordinates inside target window.
        """
        screen_pt = WindowManager.client_to_screen(hwnd, rel_x, rel_y)
        if not screen_pt:
            return False

        sx, sy = screen_pt
        cls.set_cursor_pos(sx, sy)
        time.sleep(0.03)

        down_flag, up_flag = {
            "left": (win32con.MOUSEEVENTF_LEFTDOWN, win32con.MOUSEEVENTF_LEFTUP),
            "right": (win32con.MOUSEEVENTF_RIGHTDOWN, win32con.MOUSEEVENTF_RIGHTUP),
            "middle": (win32con.MOUSEEVENTF_MIDDLEDOWN, win32con.MOUSEEVENTF_MIDDLEUP)
        }.get(button, (win32con.MOUSEEVENTF_LEFTDOWN, win32con.MOUSEEVENTF_LEFTUP))

        clicks = 2 if click_type == "double" else 1

        for _ in range(repeat):
            for _ in range(clicks):
                win32api.mouse_event(down_flag, 0, 0, 0, 0)
                time.sleep(0.04)
                win32api.mouse_event(up_flag, 0, 0, 0, 0)
                if clicks > 1:
                    time.sleep(0.08)
            time.sleep(0.05)
        return True

    @classmethod
    def drag_and_drop(cls, hwnd: int, start_x: int, start_y: int, end_x: int, end_y: int, duration_ms: int = 300):
        """Smooth drag from start relative coordinate to end relative coordinate."""
        start_pt = WindowManager.client_to_screen(hwnd, start_x, start_y)
        end_pt = WindowManager.client_to_screen(hwnd, end_x, end_y)
        if not start_pt or not end_pt:
            return False

        sx1, sy1 = start_pt
        sx2, sy2 = end_pt

        cls.set_cursor_pos(sx1, sy1)
        time.sleep(0.05)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.05)

        # Interpolate points
        steps = max(10, int(duration_ms / 15))
        for step in range(1, steps + 1):
            cur_x = int(sx1 + (sx2 - sx1) * (step / steps))
            cur_y = int(sy1 + (sy2 - sy1) * (step / steps))
            cls.set_cursor_pos(cur_x, cur_y)
            time.sleep(duration_ms / (steps * 1000.0))

        time.sleep(0.05)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        return True

    @classmethod
    def send_key_combination(cls, key_name: str, modifiers: Optional[List[str]] = None):
        """Sends a key press with optional modifier keys (Ctrl, Alt, Shift)."""
        modifiers = modifiers or []
        mod_vks = []
        for mod in modifiers:
            if mod in ("Ctrl", "Control"):
                mod_vks.append(win32con.VK_CONTROL)
            elif mod == "Alt":
                mod_vks.append(win32con.VK_MENU)
            elif mod == "Shift":
                mod_vks.append(win32con.VK_SHIFT)

        # Resolve primary key vk
        key_name_clean = key_name.strip()
        vk = VK_MAP.get(key_name_clean)
        if vk is None:
            if len(key_name_clean) == 1:
                vk = win32api.VkKeyScan(key_name_clean) & 0xFF
            else:
                vk = win32con.VK_RETURN

        # Press modifiers
        for mvk in mod_vks:
            win32api.keybd_event(mvk, 0, 0, 0)
            time.sleep(0.02)

        # Press primary key
        win32api.keybd_event(vk, 0, 0, 0)
        time.sleep(0.04)
        win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)

        # Release modifiers in reverse
        for mvk in reversed(mod_vks):
            time.sleep(0.02)
            win32api.keybd_event(mvk, 0, win32con.KEYEVENTF_KEYUP, 0)

    @classmethod
    def type_text(cls, text: str, delay_per_char: float = 0.02):
        """Types string of text into current focus."""
        for ch in text:
            # Send char as unicode
            win32api.keybd_event(0, ord(ch), KEYEVENTF_UNICODE, 0)
            win32api.keybd_event(0, ord(ch), KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0)
            if delay_per_char > 0:
                time.sleep(delay_per_char)

    @staticmethod
    def beep(freq: int = 1000, duration_ms: int = 200):
        try:
            import winsound
            winsound.Beep(freq, duration_ms)
        except Exception:
            pass
