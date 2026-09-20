using System;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace RD_GameAuto_FGOA
{
    public class ColorPickerOverlayForm : Form
    {
        private readonly IntPtr _targetHWnd;
        private readonly CoordinatePivot _pivot;
        private readonly bool _isLineMode;

        private Point _mousePos;
        private Color _currentColor = Color.Black;
        private Point _relativePos;

        // 선(Line) 모드 선택 시 시작점과 끝점
        private Point? _lineStartPoint = null;

        public Point SelectedPoint { get; private set; }
        public Point SelectedEndPoint { get; private set; }
        public Color SelectedColor { get; private set; }

        private readonly System.Windows.Forms.Timer _timer;

        // 투명 영역에서도 모든 클릭/우클릭을 100% 감지하기 위한 저수준 마우스 훅
        private IntPtr _hookId = IntPtr.Zero;
        private readonly NativeMethods.LowLevelMouseProc _mouseHookProc;

        public ColorPickerOverlayForm(IntPtr targetHWnd, CoordinatePivot pivot, bool isLineMode = false)
        {
            _targetHWnd = targetHWnd;
            _pivot = pivot;
            _isLineMode = isLineMode;

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
            _timer.Interval = 20; // 50fps 부드러운 HUD 갱신
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

                _currentColor = WindowHelper.GetPixelColor(_targetHWnd, _relativePos.X, _relativePos.Y, _pivot);
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
            else if (e.KeyCode == Keys.Space)
            {
                HandleClickSelection();
            }
        }

        private void HandleClickSelection()
        {
            if (_isLineMode)
            {
                if (!_lineStartPoint.HasValue)
                {
                    _lineStartPoint = _relativePos;
                }
                else
                {
                    SelectedPoint = _lineStartPoint.Value;
                    SelectedEndPoint = _relativePos;
                    SelectedColor = _currentColor;

                    CleanupHook();
                    this.DialogResult = DialogResult.OK;
                    this.Close();
                }
            }
            else
            {
                SelectedPoint = _relativePos;
                SelectedColor = _currentColor;

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
            g.InterpolationMode = InterpolationMode.NearestNeighbor;

            Point mouseLocal = this.PointToClient(_mousePos);

            // 선 모드일 때 선택 중인 선 렌더링
            if (_lineStartPoint.HasValue)
            {
                Point screenStart = _pivot == CoordinatePivot.WindowRelative
                    ? WindowHelper.ClientToScreenPoint(_targetHWnd, _lineStartPoint.Value.X, _lineStartPoint.Value.Y)
                    : _lineStartPoint.Value;

                Point localStart = this.PointToClient(screenStart);

                using (Pen linePen = new Pen(Color.Cyan, 2f) { DashStyle = DashStyle.Dash })
                {
                    g.DrawLine(linePen, localStart, mouseLocal);
                }
                g.FillEllipse(Brushes.Red, localStart.X - 4, localStart.Y - 4, 8, 8);
            }

            // 돋보기 HUD 렌더링 (로컬 좌표계 전달)
            DrawMagnifierHUD(g, mouseLocal);
        }

        private void DrawMagnifierHUD(Graphics g, Point mouseLocal)
        {
            int hudSize = 130;
            int offset = 22;

            int hudX = mouseLocal.X + offset;
            int hudY = mouseLocal.Y + offset;

            if (hudX + hudSize > this.ClientSize.Width) hudX = mouseLocal.X - hudSize - offset;
            if (hudY + hudSize + 60 > this.ClientSize.Height) hudY = mouseLocal.Y - hudSize - 60 - offset;
            if (hudX < 5) hudX = 5;
            if (hudY < 5) hudY = 5;

            // 1. 커서 주변 픽셀 화면 캡처 및 9배율 확대 렌더링
            int sampleRadius = 7;
            int sampleSize = sampleRadius * 2 + 1; // 15x15 픽셀

            using (Bitmap bmp = new Bitmap(sampleSize, sampleSize))
            {
                using (Graphics bg = Graphics.FromImage(bmp))
                {
                    bg.CopyFromScreen(_mousePos.X - sampleRadius, _mousePos.Y - sampleRadius, 0, 0, new Size(sampleSize, sampleSize));
                }

                Rectangle hudRect = new Rectangle(hudX, hudY, hudSize, hudSize);
                g.FillRectangle(Brushes.Black, hudRect);
                g.DrawImage(bmp, hudRect, 0, 0, sampleSize, sampleSize, GraphicsUnit.Pixel);
                g.DrawRectangle(Pens.White, hudRect);

                // 중앙 픽셀 강조 십자선
                int cx = hudX + hudSize / 2;
                int cy = hudY + hudSize / 2;
                int cellSize = hudSize / sampleSize;

                Rectangle centerCell = new Rectangle(cx - cellSize / 2, cy - cellSize / 2, cellSize, cellSize);
                using (Pen redPen = new Pen(Color.Red, 2f))
                {
                    g.DrawRectangle(redPen, centerCell);
                }
            }

            // 2. 정보 텍스트 박스
            Rectangle infoRect = new Rectangle(hudX, hudY + hudSize + 2, hudSize, 56);
            using (SolidBrush darkBrush = new SolidBrush(Color.FromArgb(230, 20, 24, 30)))
            {
                g.FillRectangle(darkBrush, infoRect);
            }
            g.DrawRectangle(Pens.DarkGray, infoRect);

            // 현재 색상 스와치
            using (SolidBrush colorBrush = new SolidBrush(_currentColor))
            {
                g.FillRectangle(colorBrush, hudX + 4, infoRect.Y + 4, 16, 16);
                g.DrawRectangle(Pens.White, hudX + 4, infoRect.Y + 4, 16, 16);
            }

            string hexStr = $"#{_currentColor.R:X2}{_currentColor.G:X2}{_currentColor.B:X2}";
            string rgbStr = $"RGB({_currentColor.R},{_currentColor.G},{_currentColor.B})";
            string pivotStr = _pivot == CoordinatePivot.WindowRelative ? "창상대" : "화면절대";
            string coordStr = $"{pivotStr}: ({_relativePos.X}, {_relativePos.Y})";

            using (Font font = new Font("맑은 고딕", 7.5F, FontStyle.Bold))
            {
                g.DrawString(hexStr, font, Brushes.Yellow, hudX + 24, infoRect.Y + 4);
                g.DrawString(rgbStr, font, Brushes.White, hudX + 4, infoRect.Y + 22);
                g.DrawString(coordStr, font, Brushes.Cyan, hudX + 4, infoRect.Y + 38);
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
