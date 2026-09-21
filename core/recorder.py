"""
Action Sequence Operation Recorder for FGOA.
Captures real-time mouse clicks and elapsed delays on the target game window
and converts them into Action sequences.
"""
import time
from typing import List, Optional
from PyQt5.QtCore import QThread, pyqtSignal
import win32gui
import win32api
import win32con
from core.models import Action


class ActionRecorder(QThread):
    """
    Background listener that detects mouse clicks on the target window
    and records them as Actions with relative coordinates and elapsed delay times.
    """
    sig_action_recorded = pyqtSignal(Action)
    sig_recording_finished = pyqtSignal(list)  # List[Action]
    sig_status_msg = pyqtSignal(str)

    def __init__(self, target_hwnd: int = 0, parent=None):
        super().__init__(parent)
        self.target_hwnd = target_hwnd
        self._is_recording = False
        self.recorded_actions: List[Action] = []
        self._last_event_time: float = 0.0

    def set_target_hwnd(self, hwnd: int):
        self.target_hwnd = hwnd

    def stop_recording(self):
        self._is_recording = False

    def insert_delay(self, seconds: float = 1.0):
        """Manually insert an explicit delay action."""
        act = Action(action_type="delay", delay_seconds=round(seconds, 2))
        self.recorded_actions.append(act)
        self.sig_action_recorded.emit(act)
        self._last_event_time = time.time()

    def run(self):
        self._is_recording = True
        self.recorded_actions = []
        self._last_event_time = time.time()
        self.sig_status_msg.emit("조작 녹화 시작됨 (F9: 종료, 타겟 창 클릭 시 자동 기록)")

        prev_lbutton_state = False
        prev_rbutton_state = False
        click_press_time = 0.0
        click_start_pos = (0, 0)

        while self._is_recording:
            # 1. Check F9 hotkey to finish recording
            if win32api.GetAsyncKeyState(win32con.VK_F9) & 0x8000:
                self.sig_status_msg.emit("F9 입력으로 녹화 종료")
                break

            # 2. Check Left Mouse Button
            lbutton_down = bool(win32api.GetAsyncKeyState(win32con.VK_LBUTTON) & 0x8000)
            now = time.time()

            if lbutton_down and not prev_lbutton_state:
                # Left Button Pressed Down
                click_press_time = now
                click_start_pos = win32gui.GetCursorPos()

            elif not lbutton_down and prev_lbutton_state:
                # Left Button Released -> Register Click or Drag
                up_pos = win32gui.GetCursorPos()
                self._handle_mouse_release(click_start_pos, up_pos, "left", now - click_press_time)

            prev_lbutton_state = lbutton_down

            # 3. Check Right Mouse Button
            rbutton_down = bool(win32api.GetAsyncKeyState(win32con.VK_RBUTTON) & 0x8000)
            if rbutton_down and not prev_rbutton_state:
                click_press_time = now
                click_start_pos = win32gui.GetCursorPos()
            elif not rbutton_down and prev_rbutton_state:
                up_pos = win32gui.GetCursorPos()
                self._handle_mouse_release(click_start_pos, up_pos, "right", now - click_press_time)

            prev_rbutton_state = rbutton_down

            time.sleep(0.01)  # 10ms polling

        self._is_recording = False
        self.sig_recording_finished.emit(self.recorded_actions)

    def _handle_mouse_release(self, start_screen_pt, end_screen_pt, button: str, press_duration: float):
        """Converts screen mouse release to target window relative Action."""
        if not self.target_hwnd or not win32gui.IsWindow(self.target_hwnd):
            return

        # Check if click is inside target client area
        client_start = win32gui.ScreenToClient(self.target_hwnd, start_screen_pt)
        client_end = win32gui.ScreenToClient(self.target_hwnd, end_screen_pt)
        rect = win32gui.GetClientRect(self.target_hwnd)  # (left, top, right, bottom)
        c_w, c_h = rect[2], rect[3]

        if not (0 <= client_start[0] < c_w and 0 <= client_start[1] < c_h):
            # Click was outside target window
            return

        now = time.time()
        elapsed_since_last = now - self._last_event_time
        # Clamped delay between 0.1s and 10.0s
        delay = round(max(0.1, min(elapsed_since_last, 10.0)), 2)

        # Determine if click or drag
        dist = abs(client_start[0] - client_end[0]) + abs(client_start[1] - client_end[1])
        if dist > 20 and press_duration > 0.15:
            # Mouse Drag
            act = Action(
                action_type="mouse_drag",
                x=client_start[0],
                y=client_start[1],
                end_x=client_end[0],
                end_y=client_end[1],
                drag_duration_ms=int(press_duration * 1000),
                delay_seconds=delay
            )
        else:
            # Mouse Click
            act = Action(
                action_type="mouse_click",
                x=client_start[0],
                y=client_start[1],
                mouse_button=button,
                click_type="single",
                repeat_count=1,
                delay_seconds=delay
            )

        self.recorded_actions.append(act)
        self._last_event_time = now
        self.sig_action_recorded.emit(act)
