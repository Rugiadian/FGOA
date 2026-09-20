using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Text;

namespace RD_GameAuto_FGOA
{
    public class WindowInfo
    {
        public IntPtr HWnd { get; set; }
        public string Title { get; set; }
        public string ProcessName { get; set; }

        public override string ToString()
        {
            if (string.IsNullOrEmpty(ProcessName))
                return Title;
            return $"[{ProcessName}] {Title}";
        }
    }

    public static class WindowHelper
    {
        public static List<WindowInfo> GetOpenWindows()
        {
            var list = new List<WindowInfo>();

            NativeMethods.EnumWindows((hWnd, lParam) =>
            {
                if (!NativeMethods.IsWindowVisible(hWnd)) return true;

                int length = NativeMethods.GetWindowTextLength(hWnd);
                if (length == 0) return true;

                var sb = new StringBuilder(length + 1);
                NativeMethods.GetWindowText(hWnd, sb, sb.Capacity);
                string title = sb.ToString().Trim();

                if (string.IsNullOrEmpty(title)) return true;

                // 의미 없는 시스템 창 필터링
                if (title == "Program Manager" || title == "Windows Shell Experience Host") return true;

                string procName = "";
                try
                {
                    NativeMethods.GetWindowThreadProcessId(hWnd, out uint pid);
                    using (var proc = Process.GetProcessById((int)pid))
                    {
                        procName = proc.ProcessName;
                    }
                }
                catch { }

                list.Add(new WindowInfo { HWnd = hWnd, Title = title, ProcessName = procName });
                return true;
            }, IntPtr.Zero);

            return list;
        }

        public static Point ClientToScreenPoint(IntPtr hWnd, int clientX, int clientY)
        {
            if (hWnd == IntPtr.Zero)
            {
                return new Point(clientX, clientY);
            }

            var pt = new NativeMethods.POINT(clientX, clientY);
            NativeMethods.ClientToScreen(hWnd, ref pt);
            return pt.ToPoint();
        }

        public static Point ScreenToClientPoint(IntPtr hWnd, int screenX, int screenY)
        {
            if (hWnd == IntPtr.Zero)
            {
                return new Point(screenX, screenY);
            }

            var pt = new NativeMethods.POINT(screenX, screenY);
            NativeMethods.ScreenToClient(hWnd, ref pt);
            return pt.ToPoint();
        }

        public static Size GetClientSize(IntPtr hWnd)
        {
            if (hWnd == IntPtr.Zero)
            {
                return System.Windows.Forms.Screen.PrimaryScreen.Bounds.Size;
            }

            if (NativeMethods.GetClientRect(hWnd, out var rect))
            {
                return new Size(rect.Width, rect.Height);
            }
            return Size.Empty;
        }

        public static IntPtr GetRootWindow(IntPtr hWnd)
        {
            if (hWnd == IntPtr.Zero) return IntPtr.Zero;
            IntPtr root = NativeMethods.GetAncestor(hWnd, NativeMethods.GA_ROOT);
            return (root != IntPtr.Zero && NativeMethods.IsWindowVisible(root)) ? root : hWnd;
        }

        public static Rectangle GetWindowVisualBounds(IntPtr hWnd)
        {
            if (hWnd == IntPtr.Zero) return Rectangle.Empty;

            try
            {
                if (NativeMethods.DwmGetWindowAttribute(hWnd, NativeMethods.DWMWA_EXTENDED_FRAME_BOUNDS, out var dRect, Marshal.SizeOf<NativeMethods.RECT>()) == 0)
                {
                    return new Rectangle(dRect.Left, dRect.Top, dRect.Width, dRect.Height);
                }
            }
            catch { }

            if (NativeMethods.GetWindowRect(hWnd, out var gRect))
            {
                return new Rectangle(gRect.Left, gRect.Top, gRect.Width, gRect.Height);
            }

            return Rectangle.Empty;
        }

        public static Color GetPixelColor(IntPtr hWnd, int x, int y, CoordinatePivot pivot)
        {
            Point screenPt;
            if (pivot == CoordinatePivot.WindowRelative && hWnd != IntPtr.Zero)
            {
                screenPt = ClientToScreenPoint(hWnd, x, y);
            }
            else
            {
                screenPt = new Point(x, y);
            }

            IntPtr hdc = NativeMethods.GetDC(IntPtr.Zero);
            if (hdc == IntPtr.Zero) return Color.Black;

            try
            {
                uint pixel = NativeMethods.GetPixel(hdc, screenPt.X, screenPt.Y);
                if (pixel == 0xFFFFFFFF) return Color.Black;

                int r = (int)(pixel & 0x000000FF);
                int g = (int)((pixel & 0x0000FF00) >> 8);
                int b = (int)((pixel & 0x00FF0000) >> 16);
                return Color.FromArgb(r, g, b);
            }
            finally
            {
                NativeMethods.ReleaseDC(IntPtr.Zero, hdc);
            }
        }

        public static bool IsColorMatch(Color actual, Color target, int tolerance)
        {
            int diffR = Math.Abs(actual.R - target.R);
            int diffG = Math.Abs(actual.G - target.G);
            int diffB = Math.Abs(actual.B - target.B);

            return (diffR <= tolerance) && (diffG <= tolerance) && (diffB <= tolerance);
        }

        // 선(Line) 형태의 복수 포인트 샘플링 색상 판별 (시작점 ~ 끝점 구간 N개 균등 추출)
        public static bool IsLineColorMatch(IntPtr hWnd, int x1, int y1, int x2, int y2, int sampleCount, Color target, int tolerance, CoordinatePivot pivot)
        {
            sampleCount = Math.Max(2, sampleCount);
            int matchCount = 0;

            for (int i = 0; i < sampleCount; i++)
            {
                float t = (float)i / (sampleCount - 1);
                int curX = (int)Math.Round(x1 + (x2 - x1) * t);
                int curY = (int)Math.Round(y1 + (y2 - y1) * t);

                Color c = GetPixelColor(hWnd, curX, curY, pivot);
                if (IsColorMatch(c, target, tolerance))
                {
                    matchCount++;
                }
            }

            // 샘플 포인트의 80% 이상 일치 시 참으로 판정
            return ((float)matchCount / sampleCount) >= 0.8f;
        }

        public static void ActivateWindow(IntPtr hWnd)
        {
            if (hWnd != IntPtr.Zero && NativeMethods.GetForegroundWindow() != hWnd)
            {
                NativeMethods.SetForegroundWindow(hWnd);
            }
        }
    }
}
