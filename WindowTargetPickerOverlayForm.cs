using System;
using System.Diagnostics;
using System.Drawing;
using System.Text;
using System.Windows.Forms;

namespace RD_GameAuto_FGOA
{
    public class WindowTargetPickerOverlayForm : Form
    {
        private Point _mousePos;
        private IntPtr _hoveredHWnd = IntPtr.Zero;
        private string _hoveredTitle = "";
        private string _hoveredProcName = "";
        private Rectangle _hoveredRect = Rectangle.Empty;

        public IntPtr SelectedHWnd { get; private set; } = IntPtr.Zero;
        public string SelectedTitle { get; private set; } = "";
        public string SelectedProcessName { get; private set; } = "";

        private readonly System.Windows.Forms.Timer _timer;

        // 투명 영역에서도 모든 클릭/우클릭을 100% 감지하기 위한 저수준 마우스 훅
        private IntPtr _hookId = IntPtr.Zero;
        private readonly NativeMethods.LowLevelMouseProc _mouseHookProc;

        public WindowTargetPickerOverlayForm()
        {
            this.FormBorderStyle = FormBorderStyle.None;
            this.WindowState = FormWindowState.Normal;
            this.StartPosition = FormStartPosition.Manual;

            Rectangle totalBounds = SystemInformation.VirtualScreen;
            this.Bounds = totalBounds;
            this.TopMost = true;
            this.ShowInTaskbar = false;
            this.DoubleBuffered = true;
            this.Cursor = Cursors.Hand;

            this.BackColor = Color.Magenta;
            this.TransparencyKey = Color.Magenta;

            // 마우스 훅 등록 (투명 영역 통과 문제 완벽 해결)
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
            _timer.Interval = 25; // 40fps 매끄러운 추적
            _timer.Tick += (s, e) =>
            {
                NativeMethods.GetCursorPos(out var pt);
                _mousePos = new Point(pt.X, pt.Y);

                IntPtr rawFound = NativeMethods.WindowFromPoint(pt);
                if (rawFound != IntPtr.Zero && rawFound != this.Handle)
                {
                    IntPtr root = WindowHelper.GetRootWindow(rawFound);
                    IntPtr target = (root != IntPtr.Zero && root != this.Handle) ? root : rawFound;

                    _hoveredHWnd = target;
                    StringBuilder sb = new StringBuilder(256);
                    NativeMethods.GetWindowText(target, sb, 256);
                    _hoveredTitle = sb.ToString().Trim();

                    try
                    {
                        NativeMethods.GetWindowThreadProcessId(target, out uint pid);
                        using (var p = Process.GetProcessById((int)pid))
                        {
                            _hoveredProcName = p.ProcessName;
                        }
                    }
                    catch
                    {
                        _hoveredProcName = "";
                    }

                    _hoveredRect = WindowHelper.GetWindowVisualBounds(target);
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
                    // 좌클릭: 창 모서리뿐 아니라 창 내부 어디를 찍든 즉시 확정 선택!
                    this.BeginInvoke(new Action(ConfirmSelection));
                    return (IntPtr)1; // 뒤의 게임 창으로 클릭이 통과되는 것 차단
                }
                else if (msg == NativeMethods.WM_LBUTTONDOWN)
                {
                    // 마우스 누름 이벤트도 뒤쪽으로 통과 차단
                    return (IntPtr)1;
                }
                else if (msg == NativeMethods.WM_RBUTTONUP)
                {
                    // 우클릭: 어디서든 즉시 취소!
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

        private void ConfirmSelection()
        {
            if (_hoveredHWnd != IntPtr.Zero)
            {
                SelectedHWnd = _hoveredHWnd;
                SelectedTitle = _hoveredTitle;
                SelectedProcessName = _hoveredProcName;

                CleanupHook();
                this.DialogResult = DialogResult.OK;
                this.Close();
            }
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

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            CleanupHook();
            base.OnFormClosing(e);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);
            Graphics g = e.Graphics;

            // 마우스 올려진 창 테두리 강조 (로컬 클라이언트 좌표 변환)
            if (_hoveredRect != Rectangle.Empty)
            {
                Point localTopLeft = this.PointToClient(_hoveredRect.Location);
                Rectangle localRect = new Rectangle(localTopLeft, _hoveredRect.Size);

                using (Pen highlightPen = new Pen(Color.Cyan, 4f))
                {
                    g.DrawRectangle(highlightPen, localRect);
                }
            }

            // 마우스 커서 옆 안내 배너 (로컬 클라이언트 좌표 기준)
            Point mouseLocal = this.PointToClient(_mousePos);
            int bx = mouseLocal.X + 20;
            int by = mouseLocal.Y + 20;
            int bw = 300;
            int bh = 58;

            if (bx + bw > this.ClientSize.Width) bx = mouseLocal.X - bw - 20;
            if (by + bh > this.ClientSize.Height) by = mouseLocal.Y - bh - 20;
            if (bx < 5) bx = 5;
            if (by < 5) by = 5;

            Rectangle banner = new Rectangle(bx, by, bw, bh);
            using (SolidBrush dark = new SolidBrush(Color.FromArgb(235, 15, 23, 42)))
            {
                g.FillRectangle(dark, banner);
            }
            g.DrawRectangle(Pens.Cyan, banner);

            using (Font titleFont = new Font("맑은 고딕", 9F, FontStyle.Bold))
            using (Font bodyFont = new Font("맑은 고딕", 8F))
            {
                g.DrawString("🎯 클릭하여 대상 게임 창 지정 (우클릭: 취소)", titleFont, Brushes.Yellow, bx + 8, by + 4);
                string procText = string.IsNullOrEmpty(_hoveredProcName) ? "프로세스: -" : $"프로세스: [{_hoveredProcName}]";
                g.DrawString(procText, bodyFont, Brushes.White, bx + 8, by + 22);
                string titleText = string.IsNullOrEmpty(_hoveredTitle) ? "(제목 없음)" : _hoveredTitle;
                if (titleText.Length > 28) titleText = titleText.Substring(0, 25) + "...";
                g.DrawString($"창 제목: {titleText}", bodyFont, Brushes.Cyan, bx + 8, by + 38);
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
