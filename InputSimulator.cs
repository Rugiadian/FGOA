using System;
using System.Drawing;
using System.Threading;
using System.Windows.Forms;

namespace RD_GameAuto_FGOA
{
    public static class InputSimulator
    {
        public static void Click(IntPtr hWnd, int x, int y, CoordinatePivot pivot, ActionType actionType)
        {
            Point screenPt = ResolveScreenPoint(hWnd, x, y, pivot);

            // 마우스 커서 이동
            NativeMethods.SetCursorPos(screenPt.X, screenPt.Y);
            Thread.Sleep(20);

            switch (actionType)
            {
                case ActionType.LeftClick:
                    NativeMethods.mouse_event(NativeMethods.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, UIntPtr.Zero);
                    Thread.Sleep(30);
                    NativeMethods.mouse_event(NativeMethods.MOUSEEVENTF_LEFTUP, 0, 0, 0, UIntPtr.Zero);
                    break;

                case ActionType.DoubleClick:
                    NativeMethods.mouse_event(NativeMethods.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, UIntPtr.Zero);
                    Thread.Sleep(30);
                    NativeMethods.mouse_event(NativeMethods.MOUSEEVENTF_LEFTUP, 0, 0, 0, UIntPtr.Zero);
                    Thread.Sleep(60);
                    NativeMethods.mouse_event(NativeMethods.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, UIntPtr.Zero);
                    Thread.Sleep(30);
                    NativeMethods.mouse_event(NativeMethods.MOUSEEVENTF_LEFTUP, 0, 0, 0, UIntPtr.Zero);
                    break;

                case ActionType.RightClick:
                    NativeMethods.mouse_event(NativeMethods.MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, UIntPtr.Zero);
                    Thread.Sleep(30);
                    NativeMethods.mouse_event(NativeMethods.MOUSEEVENTF_RIGHTUP, 0, 0, 0, UIntPtr.Zero);
                    break;
            }
        }

        public static void Drag(IntPtr hWnd, int startX, int startY, int endX, int endY, int durationMs, CoordinatePivot pivot, CancellationToken ct)
        {
            Point startPt = ResolveScreenPoint(hWnd, startX, startY, pivot);
            Point endPt = ResolveScreenPoint(hWnd, endX, endY, pivot);

            // 시작 위치로 이동
            NativeMethods.SetCursorPos(startPt.X, startPt.Y);
            Thread.Sleep(30);

            // 마우스 누름
            NativeMethods.mouse_event(NativeMethods.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, UIntPtr.Zero);
            Thread.Sleep(30);

            // 부드러운 드래그 보간 이동
            durationMs = Math.Max(50, durationMs);
            int steps = Math.Max(10, durationMs / 15);
            int stepDelay = durationMs / steps;

            for (int i = 1; i <= steps; i++)
            {
                if (ct.IsCancellationRequested) break;

                float t = (float)i / steps;
                // 부드러운 가감속(EaseInOut) 곡선 적용
                float smoothT = t * t * (3 - 2 * t);

                int curX = (int)Math.Round(startPt.X + (endPt.X - startPt.X) * smoothT);
                int curY = (int)Math.Round(startPt.Y + (endPt.Y - startPt.Y) * smoothT);

                NativeMethods.SetCursorPos(curX, curY);
                Thread.Sleep(stepDelay);
            }

            // 끝 위치 확인 및 마우스 뗌
            NativeMethods.SetCursorPos(endPt.X, endPt.Y);
            Thread.Sleep(30);
            NativeMethods.mouse_event(NativeMethods.MOUSEEVENTF_LEFTUP, 0, 0, 0, UIntPtr.Zero);
            Thread.Sleep(20);
        }

        public static void KeyPress(Keys key)
        {
            if (key == Keys.None) return;

            byte vk = (byte)key;
            NativeMethods.keybd_event(vk, 0, NativeMethods.KEYEVENTF_KEYDOWN, UIntPtr.Zero);
            Thread.Sleep(40);
            NativeMethods.keybd_event(vk, 0, NativeMethods.KEYEVENTF_KEYUP, UIntPtr.Zero);
        }

        public static void TypeText(string text, CancellationToken ct)
        {
            if (string.IsNullOrEmpty(text)) return;

            foreach (char c in text)
            {
                if (ct.IsCancellationRequested) break;
                SendKeys.SendWait(c.ToString());
                Thread.Sleep(30);
            }
        }

        public static Point ResolveScreenPoint(IntPtr hWnd, int x, int y, CoordinatePivot pivot)
        {
            if (pivot == CoordinatePivot.WindowRelative && hWnd != IntPtr.Zero)
            {
                return WindowHelper.ClientToScreenPoint(hWnd, x, y);
            }
            return new Point(x, y);
        }
    }
}
