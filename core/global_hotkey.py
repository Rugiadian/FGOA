"""
Global hotkey listener for FGOA.
Monitors system-wide keyboard events using Windows GetAsyncKeyState,
allowing hotkeys (like F6 stop) to function even when the FGOA window is not focused.
"""
import time
import ctypes
from typing import Optional
from PyQt5.QtCore import QThread, pyqtSignal


# Virtual key codes
VK_F6 = 0x75
VK_PAUSE = 0x13
VK_ESCAPE = 0x1B


class GlobalHotkeyListener(QThread):
    """
    Lightweight background worker thread that monitors global hotkeys.
    Fires signals when registered hotkeys are pressed system-wide.
    """
    sig_stop_hotkey = pyqtSignal()   # Triggered on F6 or Pause/Break press

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_running = False
        self._user32 = None
        try:
            self._user32 = ctypes.windll.user32
        except Exception:
            self._user32 = None

        self._f6_was_pressed = False
        self._pause_was_pressed = False
        import atexit
        atexit.register(self.stop_listening)

    def stop_listening(self):
        """Stops the worker thread loop."""
        self._is_running = False
        try:
            self.quit()
        except Exception:
            pass
        try:
            if self.isRunning():
                self.wait(500)
        except Exception:
            pass

    def __del__(self):
        try:
            self.stop_listening()
        except Exception:
            pass

    def run(self):
        if not self._user32:
            return

        self._is_running = True
        while self._is_running:
            try:
                # Check F6 key state
                f6_state = self._user32.GetAsyncKeyState(VK_F6)
                f6_is_down = bool(f6_state & 0x8000)

                if f6_is_down and not self._f6_was_pressed:
                    # Transition from not pressed to pressed (key down event)
                    self.sig_stop_hotkey.emit()
                self._f6_was_pressed = f6_is_down

                # Also check Pause/Break key as secondary emergency stop
                pause_state = self._user32.GetAsyncKeyState(VK_PAUSE)
                pause_is_down = bool(pause_state & 0x8000)

                if pause_is_down and not self._pause_was_pressed:
                    self.sig_stop_hotkey.emit()
                self._pause_was_pressed = pause_is_down

            except Exception:
                pass

            # Sleep 50ms (minimal CPU overhead: <0.001%)
            time.sleep(0.05)
