"""
Robust Trace Logger Module for FGOA.
Captures ultra-fast, low-overhead screenshots synchronized with execution logs,
organizing snapshots into per-loop subdirectories, stamping visible numbering,
and providing bulk cleanup.
Supports cross-computer relative paths and portable folder mapping.
"""
import os
import time
import shutil
import datetime
from typing import Optional, Dict, Any
from PIL import Image, ImageDraw
from core.screen_capture import ScreenCapture
from core.path_utils import get_trace_dir, to_trace_relative_path, to_trace_absolute_path, get_project_root

DEFAULT_TRACE_DIR = get_trace_dir()


class TraceLogger:
    """Manages high-speed screenshot trace capture, per-loop directory storage, and cleanup."""

    def __init__(self, trace_base_dir: Optional[str] = None, min_interval_sec: float = 1.0):
        if trace_base_dir:
            self.trace_base_dir = to_trace_absolute_path(trace_base_dir)
        else:
            self.trace_base_dir = get_trace_dir()
        os.makedirs(self.trace_base_dir, exist_ok=True)

        self.min_interval_sec = min_interval_sec
        self.last_capture_time: float = 0.0
        self.current_loop_dir: Optional[str] = None
        self.current_loop_index: int = 1
        self.shot_counter: int = 0

    def start_loop(self, loop_index: int) -> str:
        """Creates and sets the directory for the current overall scenario loop."""
        self.current_loop_index = loop_index
        now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        folder_name = f"loop_{loop_index:03d}_{now_str}"
        self.current_loop_dir = os.path.join(self.trace_base_dir, folder_name)
        os.makedirs(self.current_loop_dir, exist_ok=True)
        self.shot_counter = 0
        return self.current_loop_dir

    def capture_screenshot_if_eligible(self, hwnd: int, as_relative: bool = True) -> Optional[str]:
        """
        Captures a low-resolution snapshot if at least min_interval_sec (1.0s) has passed.
        Fastest performance: small downscaled JPEG with quality=40 for minimal CPU/disk footprint.
        Stamps visual numbering (#0001 HH:MM:SS) on top-left of image for 1:1 cross-checking with logs.
        Returns 'path|NUM:0001' or None if skipped (within 1s) or failed.
        """
        if not hwnd:
            return None

        now = time.time()
        # Strictly enforce: do not capture if interval is 1 second or less
        if (now - self.last_capture_time) < self.min_interval_sec:
            return None

        # Ensure loop folder exists (fallback if start_loop was not explicitly called)
        if not self.current_loop_dir or not os.path.isdir(self.current_loop_dir):
            self.start_loop(self.current_loop_index)

        try:
            # Capture target window client area
            img = ScreenCapture.capture_client_area(hwnd)
            if img is None:
                return None

            # Ultra-fast downscale: max width 640px using NEAREST (sub-millisecond)
            w, h = img.size
            if w > 640:
                target_h = max(1, int(h * (640 / w)))
                resample = getattr(Image, "Resampling", Image).NEAREST
                img = img.resize((640, target_h), resample=resample)

            self.shot_counter += 1
            shot_num = self.shot_counter
            now_dt = datetime.datetime.now()
            ts = now_dt.strftime("%H%M%S")
            time_display = now_dt.strftime("%H:%M:%S")

            # Stamp visual numbering badge on top-left of image
            try:
                draw = ImageDraw.Draw(img)
                stamp_text = f"#{shot_num:04d} ({time_display})"
                bbox = draw.textbbox((0, 0), stamp_text)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]
                # High-contrast background box
                draw.rectangle([(6, 6), (6 + tw + 8, 6 + th + 6)], fill=(0, 0, 0))
                draw.text((10, 8), stamp_text, fill=(255, 230, 0))
            except Exception:
                pass

            filename = f"shot_{shot_num:04d}_{ts}.jpg"
            file_path = os.path.join(self.current_loop_dir, filename)

            # Fast low-quality JPEG save (quality=40)
            img.save(file_path, format="JPEG", quality=40)
            self.last_capture_time = now

            target_path = to_trace_relative_path(file_path) if as_relative else file_path
            return f"{target_path}|NUM:{shot_num:04d}"
        except Exception:
            return None

    @classmethod
    def clean_all_trace_logs(cls, trace_base_dir: Optional[str] = None) -> Dict[str, Any]:
        """
        Deletes all loop directories and screenshot files in trace_base_dir.
        Returns summary info: {'deleted_dirs': int, 'deleted_files': int, 'freed_bytes': int}.
        """
        target_dir = os.path.abspath(trace_base_dir or get_trace_dir())
        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)
            return {"deleted_dirs": 0, "deleted_files": 0, "freed_bytes": 0}

        deleted_dirs = 0
        deleted_files = 0
        freed_bytes = 0

        for root, dirs, files in os.walk(target_dir, topdown=False):
            for f in files:
                fp = os.path.join(root, f)
                try:
                    freed_bytes += os.path.getsize(fp)
                    os.remove(fp)
                    deleted_files += 1
                except Exception:
                    pass
            for d in dirs:
                dp = os.path.join(root, d)
                try:
                    os.rmdir(dp)
                    deleted_dirs += 1
                except Exception:
                    pass

        # Re-ensure base dir exists
        os.makedirs(target_dir, exist_ok=True)

        return {
            "deleted_dirs": deleted_dirs,
            "deleted_files": deleted_files,
            "freed_bytes": freed_bytes
        }
