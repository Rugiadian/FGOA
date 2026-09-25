"""
Screen capture and pixel color reading module for FGOA.
Provides high-speed pixel sampling via Win32 GDI and client area snapshotting via mss/GDI.
"""
import ctypes
from typing import Optional, Tuple
from PIL import Image
import mss
import win32gui
import win32ui
import win32con
from core.window_manager import WindowManager


class ScreenCapture:
    """Provides methods for reading screen/window colors and capturing images."""

    _sct = None

    @classmethod
    def get_sct(cls):
        if cls._sct is None:
            cls._sct = mss.mss()
        return cls._sct

    @staticmethod
    def get_pixel_color_gdi(screen_x: int, screen_y: int) -> Optional[Tuple[int, int, int]]:
        """
        Fastest method to sample a single pixel using Windows GDI GetPixel.
        Returns (R, G, B) tuple.
        """
        hdc = win32gui.GetDC(0)
        if not hdc:
            return None
        try:
            colorref = ctypes.windll.gdi32.GetPixel(hdc, screen_x, screen_y)
            # COLORREF is 0x00BBGGRR
            r = colorref & 0xFF
            g = (colorref >> 8) & 0xFF
            b = (colorref >> 16) & 0xFF
            return (r, g, b)
        finally:
            win32gui.ReleaseDC(0, hdc)

    @classmethod
    def get_client_pixel_color(cls, hwnd: int, rel_x: int, rel_y: int) -> Optional[Tuple[int, int, int]]:
        """
        Get RGB color at relative coordinates (rel_x, rel_y) inside target window.
        Automatically converts to screen coordinates.
        """
        screen_pt = WindowManager.client_to_screen(hwnd, rel_x, rel_y)
        if not screen_pt:
            return None
        return cls.get_pixel_color_gdi(screen_pt[0], screen_pt[1])

    @classmethod
    def capture_client_area(cls, hwnd: int, prefer_display: bool = True) -> Optional[Image.Image]:
        """
        Capture the client area of target window as a PIL Image.
        Prioritizes high-speed display capture (mss) so that captured pixel colors
        match live screen detection (GDI GetPixel) with 0 color discrepancy (< 5 tolerance).
        Falls back to PrintWindow if display capture is unavailable or window is obscured.
        """
        if not win32gui.IsWindow(hwnd):
            return None

        win_info = WindowManager.get_window_info(hwnd)
        if not win_info or win_info.client_width <= 0 or win_info.client_height <= 0:
            return None

        # 1. Primary: Direct display capture via mss (ensures 100% pixel color parity with GDI GetPixel)
        is_min = getattr(win_info, "is_minimized", False) if win_info else False
        if prefer_display and not is_min:
            try:
                sct = cls.get_sct()
                monitor = {
                    "top": win_info.screen_y,
                    "left": win_info.screen_x,
                    "width": win_info.client_width,
                    "height": win_info.client_height
                }
                sct_img = sct.grab(monitor)
                return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            except Exception:
                pass

        # 2. Secondary / Fallback: PrintWindow (for partially obscured or background windows)
        try:
            hwnd_dc = win32gui.GetWindowDC(hwnd)
            mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
            save_dc = mfc_dc.CreateCompatibleDC()
            
            save_bitmap = win32ui.CreateBitmap()
            save_bitmap.CreateCompatibleBitmap(mfc_dc, win_info.client_width, win_info.client_height)
            save_dc.SelectObject(save_bitmap)
            
            # PW_CLIENTONLY = 1 or PW_RENDERFULLCONTENT = 2
            result = ctypes.windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 2)
            if result != 0:
                bmpinfo = save_bitmap.GetInfo()
                bmpstr = save_bitmap.GetBitmapBits(True)
                img = Image.frombuffer(
                    'RGB',
                    (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
                    bmpstr, 'raw', 'BGRX', 0, 1
                )
                win32gui.DeleteObject(save_bitmap.GetHandle())
                save_dc.DeleteDC()
                mfc_dc.DeleteDC()
                win32gui.ReleaseDC(hwnd, hwnd_dc)
                return img
            
            win32gui.DeleteObject(save_bitmap.GetHandle())
            save_dc.DeleteDC()
            mfc_dc.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwnd_dc)
        except Exception:
            pass

        # 3. Final Fallback: Attempt mss regardless
        try:
            sct = cls.get_sct()
            monitor = {
                "top": win_info.screen_y,
                "left": win_info.screen_x,
                "width": win_info.client_width,
                "height": win_info.client_height
            }
            sct_img = sct.grab(monitor)
            return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        except Exception:
            return None

    @staticmethod
    def get_image_pixel(image: Image.Image, x: int, y: int) -> Optional[Tuple[int, int, int]]:
        """Safely sample pixel from a PIL Image."""
        if x < 0 or y < 0 or x >= image.width or y >= image.height:
            return None
        rgb_img = image.convert("RGB")
        return rgb_img.getpixel((x, y))
