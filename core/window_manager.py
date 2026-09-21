"""
Window Manager module for FGOA.
Handles window enumeration, target window tracking, client rect calculation,
and relative to screen coordinate conversions using Win32 API.
"""
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from typing import List, Optional, Tuple
import win32gui
import win32process
import win32con

def _attach_input_desktop():
    try:
        user32 = ctypes.windll.user32
        h_input = user32.OpenInputDesktop(0, False, 0x01FF)
        if h_input:
            user32.SetThreadDesktop(h_input)
    except Exception:
        pass

_attach_input_desktop()


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    client_width: int
    client_height: int
    screen_x: int
    screen_y: int
    pid: int = 0
    process_name: str = ""

    def __str__(self) -> str:
        return f"{self.title} (HWND: {self.hwnd}, 크기: {self.client_width}x{self.client_height})"


class WindowManager:
    """Manages Windows windows, client coordinate mapping and window selection."""

    @staticmethod
    def ensure_input_desktop():
        _attach_input_desktop()

    @staticmethod
    def get_all_visible_windows() -> List[WindowInfo]:
        """Enumerate all visible, non-empty top-level windows from interactive desktop."""
        windows: List[WindowInfo] = []

        def enum_callback(hwnd):
            if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
                return True

            title = win32gui.GetWindowText(hwnd).strip()
            if not title:
                return True

            # Skip common utility/tool windows
            if title in ("Program Manager", "Settings", "Microsoft Text Input Application"):
                return True

            try:
                rect = win32gui.GetClientRect(hwnd)
                width = rect[2] - rect[0]
                height = rect[3] - rect[1]

                if width < 50 or height < 50:
                    return True

                screen_origin = win32gui.ClientToScreen(hwnd, (0, 0))
                _, pid = win32process.GetWindowThreadProcessId(hwnd)

                windows.append(WindowInfo(
                    hwnd=hwnd,
                    title=title,
                    client_width=width,
                    client_height=height,
                    screen_x=screen_origin[0],
                    screen_y=screen_origin[1],
                    pid=pid
                ))
            except Exception:
                pass
            return True

        enumerated = False
        try:
            user32 = ctypes.windll.user32
            h_input = user32.OpenInputDesktop(0, False, 0x01FF)
            if h_input:
                WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
                user32.EnumDesktopWindows(h_input, WNDENUMPROC(lambda hwnd, lp: enum_callback(hwnd)), 0)
                user32.CloseDesktop(h_input)
                enumerated = True
        except Exception:
            pass

        if not enumerated or not windows:
            try:
                win32gui.EnumWindows(lambda hwnd, extra: enum_callback(hwnd), None)
            except Exception:
                pass

        # Sort by title
        windows.sort(key=lambda w: w.title.lower())
        return windows

    @staticmethod
    def find_window_by_title(title_query: str) -> Optional[WindowInfo]:
        """Find the first visible window containing the query title string."""
        for w in WindowManager.get_all_visible_windows():
            if title_query.lower() in w.title.lower():
                return w
        return None

    @staticmethod
    def get_window_info(hwnd: int) -> Optional[WindowInfo]:
        """Get live WindowInfo for a specific HWND."""
        if not win32gui.IsWindow(hwnd):
            return None
        
        try:
            title = win32gui.GetWindowText(hwnd)
            rect = win32gui.GetClientRect(hwnd)
            width = rect[2] - rect[0]
            height = rect[3] - rect[1]
            origin = win32gui.ClientToScreen(hwnd, (0, 0))
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            return WindowInfo(
                hwnd=hwnd,
                title=title,
                client_width=width,
                client_height=height,
                screen_x=origin[0],
                screen_y=origin[1],
                pid=pid
            )
        except Exception:
            return None

    @staticmethod
    def client_to_screen(hwnd: int, rel_x: int, rel_y: int) -> Optional[Tuple[int, int]]:
        """
        Converts relative client coordinate (rel_x, rel_y) inside target window
        to absolute screen coordinates (screen_x, screen_y).
        Returns None if window is invalid or closed.
        """
        if not win32gui.IsWindow(hwnd):
            return None
        try:
            origin_x, origin_y = win32gui.ClientToScreen(hwnd, (0, 0))
            return (origin_x + rel_x, origin_y + rel_y)
        except Exception:
            return None

    @staticmethod
    def screen_to_client(hwnd: int, screen_x: int, screen_y: int) -> Optional[Tuple[int, int]]:
        """
        Converts absolute screen coordinates to relative client coordinate.
        """
        if not win32gui.IsWindow(hwnd):
            return None
        try:
            origin_x, origin_y = win32gui.ClientToScreen(hwnd, (0, 0))
            return (screen_x - origin_x, screen_y - origin_y)
        except Exception:
            return None

    @staticmethod
    def bring_to_foreground(hwnd: int) -> bool:
        """Activate and bring target window to front."""
        if not win32gui.IsWindow(hwnd):
            return False
        try:
            # If minimized, restore it
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
            return True
        except Exception:
            # Sometimes SetForegroundWindow fails if another window has focus,
            # attach thread input to force foreground
            try:
                cur_thread = win32process.GetCurrentThreadId()
                fore_hwnd = win32gui.GetForegroundWindow()
                fore_thread, _ = win32process.GetWindowThreadProcessId(fore_hwnd)
                ctypes.windll.user32.AttachThreadInput(cur_thread, fore_thread, True)
                win32gui.SetForegroundWindow(hwnd)
                ctypes.windll.user32.AttachThreadInput(cur_thread, fore_thread, False)
                return True
            except Exception:
                return False

    @staticmethod
    def get_window_from_point(x: int, y: int) -> Optional[int]:
        """Find top-level window HWND under a specific screen coordinate (x, y)."""
        pt = wintypes.POINT(x, y)
        hwnd = ctypes.windll.user32.WindowFromPoint(pt)
        if not hwnd:
            return None
        # Traverse up to top-level parent
        root = win32gui.GetAncestor(hwnd, win32con.GA_ROOT)
        return root if root else hwnd
