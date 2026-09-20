using System;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace RD_GameAuto_FGOA
{
    public class CoordinatePickerOverlayForm : Form
    {
        private readonly IntPtr _targetHWnd;
        private readonly CoordinatePivot _pivot;
        private readonly bool _isDragMode;

        private Point _mousePos;
        private Point _relativePos;
        private Point? _dragStart = null;

        public Point SelectedPoint { get; private set; }
        public Point SelectedEndPoint { get; private set; }

        private readonly System.Windows.Forms.Timer _timer;

        // 투명 영역에서도 모든 클릭/우클릭을 100% 감지하기 위한 저수준 마우스 훅
        private IntPtr _hookId = IntPtr.Zero;
        private readonly NativeMethods.LowLevelMouseProc _mouseHookProc;

        public CoordinatePickerOverlayForm(IntPtr targetHWnd, CoordinatePivot pivot, bool isDragMode = false)
        {
            _targetHWnd = targetHWnd;
            _pivot = pivot;
            _isDragMode = isDragMode;

            this.FormBorderStyle = FormBorderStyle.None;
            this.WindowState = FormWindowState.Normal;
            this.StartPosition = FormStartPosition.Manual;

            Rectangle totalBounds = SystemInformation.VirtualScreen;
            this.Bounds = totalBounds;
            this.TopMost = true;
            this.ShowInTaskbar = false;
            this.DoubleBuffered = true;
            this.Cursor = Cursors.Cross;

            this.BackColor = Color.Magenta;
            this.TransparencyKey = Color.Magenta;

            _mouseHookProc = MouseHookCallback;
            using (var curProcess = Process.GetCurrentProcess())
            using (var curModule = curProcess.MainModule)
            {
                _hookId = NativeMethods.SetWindowsHookEx(
                    NativeMethods.WH_MOUSE_LL,
                    _mouseHookProc,
                    NativeMethods.GetModuleHandle(curModule.ModuleName),
                    0);
            }

            _timer = new System.Windows.Forms.Timer();
            _timer.Interval = 20;
            _timer.Tick += (s, e) =>
            {
                NativeMethods.GetCursorPos(out var pt);
                _mousePos = new Point(pt.X, pt.Y);

                if (_pivot == CoordinatePivot.WindowRelative && _targetHWnd != IntPtr.Zero)
                {
                    _relativePos = WindowHelper.ScreenToClientPoint(_targetHWnd, _mousePos.X, _mousePos.Y);
                }
                else
                {
                    _relativePos = _mousePos;
                }

                this.Invalidate();
            };
            _timer.Start();
        }

        private IntPtr MouseHookCallback(int nCode, IntPtr wParam, IntPtr lParam)
        {
            if (nCode >= 0)
            {
                int msg = (int)wParam;
                if (msg == NativeMethods.WM_LBUTTONUP)
                {
                    this.BeginInvoke(new Action(HandleClickSelection));
                    return (IntPtr)1;
                }
                else if (msg == NativeMethods.WM_LBUTTONDOWN)
                {
                    return (IntPtr)1;
                }
                else if (msg == NativeMethods.WM_RBUTTONUP)
                {
                    this.BeginInvoke(new Action(CancelSelection));
                    return (IntPtr)1;
                }
                else if (msg == NativeMethods.WM_RBUTTONDOWN)
                {
                    return (IntPtr)1;
                }
            }

            return NativeMethods.CallNextHookEx(_hookId, nCode, wParam, lParam);
        }

        private void CancelSelection()
        {
            CleanupHook();
            this.DialogResult = DialogResult.Cancel;
            this.Close();
        }

        private void CleanupHook()
        {
            _timer?.Stop();
            if (_hookId != IntPtr.Zero)
            {
                NativeMethods.UnhookWindowsHookEx(_hookId);
                _hookId = IntPtr.Zero;
            }
        }

        protected override void OnKeyDown(KeyEventArgs e)
        {
            base.OnKeyDown(e);
            if (e.KeyCode == Keys.Escape)
            {
                CancelSelection();
            }
        }

        private void HandleClickSelection()
        {
            if (_isDragMode)
            {
                if (!_dragStart.HasValue)
                {
                    _dragStart = _relativePos;
                }
                else
                {
                    SelectedPoint = _dragStart.Value;
                    SelectedEndPoint = _relativePos;

                    CleanupHook();
                    this.DialogResult = DialogResult.OK;
                    this.Close();
                }
            }
            else
            {
                SelectedPoint = _relativePos;
                CleanupHook();
                this.DialogResult = DialogResult.OK;
                this.Close();
            }
        }

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            CleanupHook();
            base.OnFormClosing(e);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);
            Graphics g = e.Graphics;
            g.SmoothingMode = SmoothingMode.HighQuality;

            Point mouseLocal = this.PointToClient(_mousePos);

            // 드래그 모드 진행 중 화살표/선 그리기
            if (_dragStart.HasValue)
            {
                Point screenStart = _pivot == CoordinatePivot.WindowRelative
                    ? WindowHelper.ClientToScreenPoint(_targetHWnd, _dragStart.Value.X, _dragStart.Value.Y)
                    : _dragStart.Value;

                Point localStart = this.PointToClient(screenStart);

                using (Pen dragPen = new Pen(Color.Lime, 3f) { EndCap = LineCap.ArrowAnchor })
                {
                    g.DrawLine(dragPen, localStart, mouseLocal);
                }
                g.FillEllipse(Brushes.Red, localStart.X - 5, localStart.Y - 5, 10, 10);
            }

            // 마우스 커서 주변 십자선 (로컬 좌표 기준)
            using (Pen crossPen = new Pen(Color.FromArgb(220, 13, 110, 253), 1.5f))
            {
                g.DrawLine(crossPen, mouseLocal.X - 25, mouseLocal.Y, mouseLocal.X + 25, mouseLocal.Y);
                g.DrawLine(crossPen, mouseLocal.X, mouseLocal.Y - 25, mouseLocal.X, mouseLocal.Y + 25);
            }

            // HUD 박스 (로컬 좌표 기준)
            int hudW = 160;
            int hudH = 46;
            int hx = mouseLocal.X + 15;
            int hy = mouseLocal.Y + 15;

            if (hx + hudW > this.ClientSize.Width) hx = mouseLocal.X - hudW - 15;
            if (hy + hudH > this.ClientSize.Height) hy = mouseLocal.Y - hudH - 15;
            if (hx < 5) hx = 5;
            if (hy < 5) hy = 5;

            Rectangle box = new Rectangle(hx, hy, hudW, hudH);
            using (SolidBrush dark = new SolidBrush(Color.FromArgb(230, 20, 24, 30)))
            {
                g.FillRectangle(dark, box);
            }
            g.DrawRectangle(Pens.DodgerBlue, box);

            string pivotStr = _pivot == CoordinatePivot.WindowRelative ? "창 상대좌표" : "화면 절대좌표";
            string title = _isDragMode ? (_dragStart.HasValue ? "📍 드래그 [끝점] 클릭" : "📍 드래그 [시작점] 클릭") : "🎯 조작 좌표 클릭";

            using (Font fontBold = new Font("맑은 고딕", 8F, FontStyle.Bold))
            using (Font font = new Font("맑은 고딕", 8F))
            {
                g.DrawString(title, fontBold, Brushes.Yellow, hx + 6, hy + 4);
                g.DrawString($"{pivotStr}: ({_relativePos.X}, {_relativePos.Y})", font, Brushes.White, hx + 6, hy + 24);
            }
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                CleanupHook();
                _timer?.Dispose();
            }
            base.Dispose(disposing);
        }
    }
}
