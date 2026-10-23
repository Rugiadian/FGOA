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
    def capture_client_area_background(cls, hwnd: int) -> Optional[Image.Image]:
        """
        Captures the client area of target window even when covered by other windows or in background.
        Uses PrintWindow with PW_CLIENTONLY | PW_RENDERFULLCONTENT (3) and falls back to BitBlt on the target window's DC.
        """
        if not hwnd or not win32gui.IsWindow(hwnd):
            return None

        win_info = WindowManager.get_window_info(hwnd)
        if not win_info or win_info.client_width <= 0 or win_info.client_height <= 0:
            return None

        w = win_info.client_width
        h = win_info.client_height

        # 1. Try PrintWindow on client area DC
        try:
            hwnd_dc = win32gui.GetDC(hwnd)
            if hwnd_dc:
                mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
                save_dc = mfc_dc.CreateCompatibleDC()
                save_bitmap = win32ui.CreateBitmap()
                save_bitmap.CreateCompatibleBitmap(mfc_dc, w, h)
                save_dc.SelectObject(save_bitmap)

                printed = False
                for flag in (3, 2, 1, 0):
                    res = ctypes.windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), flag)
                    if res != 0:
                        printed = True
                        break

                if not printed:
                    # Fallback to direct BitBlt from client DC
                    save_dc.BitBlt((0, 0), (w, h), mfc_dc, (0, 0), win32con.SRCCOPY)

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
        except Exception:
            pass

        # 2. Fallback to general capture_client_area with prefer_display=False
        return cls.capture_client_area(hwnd, prefer_display=False)

    @classmethod
    def get_client_pixel_color(
        cls, hwnd: int, rel_x: int, rel_y: int, background: bool = False
    ) -> Optional[Tuple[int, int, int]]:
        """
        Get RGB color at relative coordinates (rel_x, rel_y) inside target window.
        When background=True, samples directly from the target window's DC / background snapshot
        without requiring screen visibility.
        When background=False, automatically converts to screen coordinates and reads via GDI GetPixel(0).
        """
        if not hwnd or not win32gui.IsWindow(hwnd):
            return None

        if background:
            # 1. First try direct GetPixel on window DC
            hdc = win32gui.GetDC(hwnd)
            if hdc:
                try:
                    colorref = ctypes.windll.gdi32.GetPixel(hdc, int(rel_x), int(rel_y))
                    if colorref != -1 and colorref != 0xFFFFFFFF:
                        r = colorref & 0xFF
                        g = (colorref >> 8) & 0xFF
                        b = (colorref >> 16) & 0xFF
                        return (r, g, b)
                finally:
                    win32gui.ReleaseDC(hwnd, hdc)

            # 2. If direct GetPixel failed or returned invalid, sample via background capture
            bg_img = cls.capture_client_area_background(hwnd)
            if bg_img:
                return cls.get_image_pixel(bg_img, int(rel_x), int(rel_y))

        # Standard foreground display capture via screen coordinates
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
