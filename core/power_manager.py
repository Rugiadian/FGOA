"""
Power and Screen Saver Manager Module for FGOA.
Prevents Windows screen saver and display sleep while scenarios are actively executing,
without simulating mouse/keyboard input (prevents control hijacking).
Restores normal screen saver and sleep state when execution is stopped or paused.
"""
import ctypes
from ctypes import wintypes
from typing import Optional


# Win32 Execution State Flags for SetThreadExecutionState
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002
ES_USER_PRESENT = 0x00000004
ES_AWAYMODE_REQUIRED = 0x00000040
ES_CONTINUOUS = 0x80000000

# Win32 SysCommand Message Constants
WM_SYSCOMMAND = 0x0112
SC_SCREENSAVE = 0xF140
SC_MONITORPOWER = 0xF170
SPI_GETSCREENSAVERRUNNING = 0x0072
WM_CLOSE = 0x0010


class PowerManager:
    """
    Manages display idle timers and screen saver prevention at the OS level.
    Uses Win32 SetThreadExecutionState without generating synthetic mouse/keyboard events,
    ensuring background automation and user inputs are never hijacked.
    """
    _is_preventing: bool = False

    @classmethod
    def prevent_screensaver(cls) -> bool:
        """
        Informs Windows that the display and system must stay awake.
        Prevents screen saver activation and monitor power down.
        """
        try:
            # 1. Dismiss any already active screen saver window cleanly
            cls.dismiss_active_screensaver()

            # 2. Set continuous display and system required state
            flags = ES_CONTINUOUS | ES_DISPLAY_REQUIRED | ES_SYSTEM_REQUIRED
            prev = ctypes.windll.kernel32.SetThreadExecutionState(flags)
            cls._is_preventing = True
            return bool(prev != 0)
        except Exception:
            return False

    @classmethod
    def allow_screensaver(cls) -> bool:
        """
        Restores normal Windows power management.
        Allows screen saver and display sleep to activate according to user preferences.
        """
        try:
            prev = ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
            cls._is_preventing = False
            return bool(prev != 0)
        except Exception:
            return False

    @classmethod
    def is_preventing(cls) -> bool:
        """Returns True if screen saver prevention is currently active."""
        return cls._is_preventing

    @classmethod
    def dismiss_active_screensaver(cls) -> bool:
        """
        If a screen saver window is already actively running, safely closes it
        via WM_CLOSE message without simulating any mouse/keyboard input.
        """
        try:
            is_running = ctypes.c_bool(False)
            if ctypes.windll.user32.SystemParametersInfoW(SPI_GETSCREENSAVERRUNNING, 0, ctypes.byref(is_running), 0):
                if is_running.value:
                    hwnd_ss = ctypes.windll.user32.FindWindowW("WindowsScreenSaverClass", None)
                    if hwnd_ss:
                        ctypes.windll.user32.PostMessageW(hwnd_ss, WM_CLOSE, 0, 0)
                        return True
        except Exception:
            pass
        return False

    @classmethod
    def should_block_syscommand(cls, message: int, wparam: int) -> bool:
        """
        Helper for QWidget.nativeEvent to filter out SC_SCREENSAVE and SC_MONITORPOWER
        system commands if execution is actively in progress.
        """
        if not cls._is_preventing:
            return False
        if message == WM_SYSCOMMAND:
            cmd = wparam & 0xFFF0
            if cmd in (SC_SCREENSAVE, SC_MONITORPOWER):
                return True
        return False
