using System;
using System.Collections.Generic;
using System.Drawing;
using System.Linq;
using System.Windows.Forms;
using FormsTimer = System.Windows.Forms.Timer;

namespace RD_GameAuto_FGOA
{
    public partial class MainForm : Form
    {
        private MacroProfile _profile;
        private readonly MacroEngine _engine;
        private GlobalKeyboardHook _globalHook;
        private IntPtr _currentTargetHWnd = IntPtr.Zero;
        private ScenarioPreset _selectedPreset = null;
        private readonly FormsTimer _realtimeMonitorTimer;

        // UI 컨트롤 선언 - 상단 바
        private ComboBox cmbWindows;
        private Button btnRefreshWindows;
        private Button btnPickWindow;
        private Button btnAlwaysOnTop;
        private Button btnDisableHotkeys;
        private ComboBox cmbDefaultPivot;
        private NumericUpDown numCheckInterval;
        private Button btnSaveLayout;
        private ToolTip toolTip;
        private Label lblWindowStatus;
        private bool _hotkeysDisabled = false;
        private bool _isUpdatingWindowsList = false;

        // UI 레이아웃 분할 컨테이너
        private SafeSplitContainer splitMain;
        private SafeSplitContainer splitDetail;
        private TableLayoutPanel bottomLayout;

        // 좌측: 시나리오 프리셋 목록
        private ListView lvPresets;
        private Button btnAddPreset;
        private Button btnClonePreset;
        private Button btnDeletePreset;
        private Button btnMoveUpPreset;
        private Button btnMoveDownPreset;
        private Button btnExportConfig;
        private Button btnImportConfig;

        // 우측 상단: [Eye & Brain] 조건 및 분기 판단
        private NumericUpDown numScenarioNumber;
        private TextBox txtPresetName;
        private ComboBox cmbConditionMode;
        private NumericUpDown numCooldown;
        private ComboBox cmbOnMatchBranch;
        private NumericUpDown numOnMatchJump;
        private ComboBox cmbOnMismatchBranch;
        private NumericUpDown numOnMismatchJump;

        private ListView lvColorConditions;
        private Button btnPickPointColor;
        private Button btnPickLineColor;
        private Button btnEditCondition;
        private Button btnDeleteCondition;
        private Button btnTestCondition;

        // 우측 하단: [Hand] 액션 시퀀스
        private ListView lvActions;
        private Button btnAddClickAction;
        private Button btnAddDragAction;
        private Button btnAddCustomAction;
        private Button btnEditAction;
        private Button btnDeleteAction;
        private Button btnMoveUpAction;
        private Button btnMoveDownAction;
        private Button btnTestAction;

        // 하단 대시보드
        private Label lblEngineStatus;
        private Button btnStartEngine;
        private Button btnStopEngine;
        private RichTextBox rtbLog;

        public MainForm()
        {
            toolTip = new ToolTip();
            InitializeComponentLayout();

            _engine = new MacroEngine();
            _engine.StatusChanged += Engine_StatusChanged;
            _engine.LogMessage += Engine_LogMessage;
            _engine.ActiveScenarioChanged += Engine_ActiveScenarioChanged;
            _engine.PointEvaluated += Engine_PointEvaluated;

            _realtimeMonitorTimer = new FormsTimer();
            _realtimeMonitorTimer.Interval = 150; // 0.15초마다 실시간 색상 및 상태 갱신
            _realtimeMonitorTimer.Tick += RealtimeMonitorTimer_Tick;

            InitGlobalHook();
        }

        private void InitGlobalHook()
        {
            try
            {
                _globalHook = new GlobalKeyboardHook();
                _globalHook.KeyDown += (key) =>
                {
                    if (_hotkeysDisabled) return;

                    if (key == Keys.Escape)
                    {
                        // 어느 창에 있든 ESC 누르면 즉시 긴급 정지
                        this.BeginInvoke(new Action(() =>
                        {
                            if (_engine.IsRunning)
                            {
                                _engine.Stop();
                                AppendLog("🚨 [ESC] 긴급 정지 핫키가 감지되어 오토를 즉시 중단했습니다!", Color.Red);
                            }
                        }));
                    }
                    else if (key == Keys.F6)
                    {
                        this.BeginInvoke(new Action(StartMacro));
                    }
                    else if (key == Keys.F7)
                    {
                        this.BeginInvoke(new Action(StopMacro));
                    }
                };
            }
            catch { }
        }

        protected override void OnLoad(EventArgs e)
        {
            base.OnLoad(e);

            _profile = ConfigManager.LoadDefault();
            ApplyProfileToUI();
            ApplyLayoutSettings();
            RefreshOpenWindows();
            _realtimeMonitorTimer.Start();

            AppendLog("💡 FGOA 지능형 화면 감지 자동화 툴이 준비되었습니다. 대상 창을 지정해 주세요.", Color.FromArgb(13, 110, 253));
        }

        protected override void OnShown(EventArgs e)
        {
            base.OnShown(e);
            RestoreSplitterDistances();

            if (lvPresets.Items.Count > 0)
            {
                try
                {
                    lvPresets.Items[0].Selected = true;
                    lvPresets.Items[0].Focused = true;
                }
                catch { }
            }
        }

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            _realtimeMonitorTimer.Stop();
            _engine.Stop();
            _globalHook?.Dispose();

            // 종료 시 현재 창 크기 및 화면 분할 비율 자동 저장
            SaveCurrentLayout();

            base.OnFormClosing(e);
        }

        // ==========================================
        // UI 빌드 및 레이아웃 구성
        // ==========================================
        private void InitializeComponentLayout()
        {
            this.Text = "⚡ FGOA 지능형 화면 감지 자동화 툴 v2.0";
            this.Size = new Size(1166, 973);
            this.MinimumSize = new Size(1000, 720);
            this.StartPosition = FormStartPosition.CenterScreen;
            this.Font = new Font("맑은 고딕", 9F, FontStyle.Regular);
            this.BackColor = Color.FromArgb(246, 248, 250);
            this.ForeColor = Color.FromArgb(33, 37, 41);

            // 메인 3단 분할 레이아웃
            TableLayoutPanel rootLayout = new TableLayoutPanel
            {
                Dock = DockStyle.Fill,
                RowCount = 3,
                ColumnCount = 1,
                Padding = new Padding(10)
            };
            rootLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 70));  // 상단: 윈도우 선택 바
            rootLayout.RowStyles.Add(new RowStyle(SizeType.Percent, 100)); // 중앙: 시나리오 & 상세 편집
            rootLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 180)); // 하단: 대시보드 및 로그

            rootLayout.Controls.Add(CreateTopWindowBar(), 0, 0);
            rootLayout.Controls.Add(CreateCenterPanel(), 0, 1);
            rootLayout.Controls.Add(CreateBottomDashboard(), 0, 2);

            this.Controls.Add(rootLayout);
        }

        private Control CreateTopWindowBar()
        {
            Panel panel = new Panel
            {
                Dock = DockStyle.Fill,
                BackColor = Color.White,
                Padding = new Padding(8)
            };

            Label lblTitle = new Label
            {
                Text = "🎯 대상 게임 창:",
                ForeColor = Color.FromArgb(13, 110, 253),
                Font = new Font("맑은 고딕", 9.5F, FontStyle.Bold),
                Location = new Point(10, 12),
                AutoSize = true
            };

            cmbWindows = new ComboBox
            {
                DropDownStyle = ComboBoxStyle.DropDownList,
                Location = new Point(125, 9),
                Width = 260,
                Font = new Font("맑은 고딕", 9F),
                BackColor = Color.White,
                ForeColor = Color.FromArgb(33, 37, 41)
            };
            cmbWindows.SelectedIndexChanged += CmbWindows_SelectedIndexChanged;

            btnRefreshWindows = new Button
            {
                Text = "🔄 새로고침",
                Location = new Point(390, 8),
                Size = new Size(76, 28),
                BackColor = Color.FromArgb(235, 238, 242),
                ForeColor = Color.FromArgb(33, 37, 41),
                FlatStyle = FlatStyle.Flat
            };
            btnRefreshWindows.FlatAppearance.BorderColor = Color.FromArgb(206, 212, 218);
            btnRefreshWindows.Click += (s, e) => RefreshOpenWindows();

            btnPickWindow = new Button
            {
                Text = "🎯 화면 클릭으로 게임 창 지정",
                Location = new Point(404, 8),
                Size = new Size(170, 28),
                BackColor = Color.FromArgb(13, 110, 253),
                ForeColor = Color.White,
                Font = new Font("맑은 고딕", 9F, FontStyle.Bold),
                FlatStyle = FlatStyle.Flat
            };
            btnPickWindow.FlatAppearance.BorderSize = 0;
            btnPickWindow.Click += BtnPickWindow_Click;

            Label lblPivot = new Label
            {
                Text = "좌표 피봇:",
                ForeColor = Color.FromArgb(73, 80, 87),
                Location = new Point(582, 12),
                AutoSize = true
            };

            cmbDefaultPivot = new ComboBox
            {
                DropDownStyle = ComboBoxStyle.DropDownList,
                Location = new Point(646, 9),
                Width = 120,
                BackColor = Color.White,
                ForeColor = Color.FromArgb(33, 37, 41)
            };
            cmbDefaultPivot.Items.AddRange(new object[] { "창 상대좌표 (0,0)", "화면 절대좌표 (0,0)" });
            cmbDefaultPivot.SelectedIndex = 0;
            cmbDefaultPivot.SelectedIndexChanged += (s, e) =>
            {
                if (_profile != null)
                {
                    _profile.DefaultPivot = (CoordinatePivot)cmbDefaultPivot.SelectedIndex;
                }
            };

            Label lblInterval = new Label
            {
                Text = "주기:",
                ForeColor = Color.FromArgb(73, 80, 87),
                Location = new Point(772, 12),
                AutoSize = true
            };

            numCheckInterval = new NumericUpDown
            {
                Minimum = 20,
                Maximum = 5000,
                Value = 100,
                Increment = 20,
                Location = new Point(810, 9),
                Width = 55,
                BackColor = Color.White,
                ForeColor = Color.FromArgb(33, 37, 41)
            };
            numCheckInterval.ValueChanged += (s, e) =>
            {
                if (_profile != null) _profile.CheckIntervalMs = (int)numCheckInterval.Value;
            };

            // 우측 상단 1: 화면 비율 저장 버튼
            btnSaveLayout = new Button
            {
                Text = "💾 비율 저장",
                Size = new Size(95, 28),
                BackColor = Color.FromArgb(240, 244, 248),
                ForeColor = Color.FromArgb(13, 110, 253),
                Font = new Font("맑은 고딕", 9F, FontStyle.Bold),
                FlatStyle = FlatStyle.Flat,
                Cursor = Cursors.Hand
            };
            btnSaveLayout.FlatAppearance.BorderColor = Color.FromArgb(13, 110, 253);
            btnSaveLayout.FlatAppearance.BorderSize = 1;
            toolTip.SetToolTip(btnSaveLayout, "현재 창 크기 및 가운데 창 분할 비율을 저장합니다.\n프로그램 시작 시 이 화면 비율로 자동 복원됩니다.");
            btnSaveLayout.Click += BtnSaveLayout_Click;

            // 우측 상단 2: 모든 단축키 비활성화 토글 버튼
            btnDisableHotkeys = new Button
            {
                Text = "⌨️ 단축키 [활성]",
                Size = new Size(130, 28),
                BackColor = Color.FromArgb(235, 238, 242),
                ForeColor = Color.FromArgb(33, 37, 41),
                Font = new Font("맑은 고딕", 8.5F, FontStyle.Bold),
                FlatStyle = FlatStyle.Flat,
                Cursor = Cursors.Hand
            };
            btnDisableHotkeys.FlatAppearance.BorderColor = Color.FromArgb(206, 212, 218);
            toolTip.SetToolTip(btnDisableHotkeys, "단축키(ESC 긴급정지, F6 시작, F7 정지) 사용 중입니다.\n클릭 시 모든 단축키를 비활성화합니다.");
            btnDisableHotkeys.Click += BtnDisableHotkeys_Click;

            // 우측 상단 3: 항상 위 토글 버튼 (맨 오른쪽 구석)
            btnAlwaysOnTop = new Button
            {
                Text = "📌 항상 위 [ON]",
                Size = new Size(100, 28),
                BackColor = Color.FromArgb(25, 135, 84),
                ForeColor = Color.White,
                Font = new Font("맑은 고딕", 8.5F, FontStyle.Bold),
                FlatStyle = FlatStyle.Flat,
                Cursor = Cursors.Hand
            };
            btnAlwaysOnTop.FlatAppearance.BorderSize = 0;
            btnAlwaysOnTop.Click += BtnAlwaysOnTop_Click;

            Action layoutRightButtons = () =>
            {
                int rightMargin = 10;
                btnAlwaysOnTop.Location = new Point(panel.Width - btnAlwaysOnTop.Width - rightMargin, 8);
                btnDisableHotkeys.Location = new Point(btnAlwaysOnTop.Left - btnDisableHotkeys.Width - 6, 8);
                btnSaveLayout.Location = new Point(btnDisableHotkeys.Left - btnSaveLayout.Width - 6, 8);
            };

            layoutRightButtons();
            panel.Resize += (s, e) => layoutRightButtons();

            lblWindowStatus = new Label
            {
                Text = "⚠️ 대상 창이 선택되지 않았습니다. [화면 클릭으로 게임 창 지정]을 눌러 창을 클릭하세요.",
                ForeColor = Color.FromArgb(217, 119, 6),
                Location = new Point(125, 40),
                AutoSize = true,
                Font = new Font("맑은 고딕", 8.5F)
            };

            panel.Controls.AddRange(new Control[] {
                lblTitle, cmbWindows, btnRefreshWindows, btnPickWindow,
                lblPivot, cmbDefaultPivot, lblInterval, numCheckInterval,
                btnSaveLayout, btnDisableHotkeys, btnAlwaysOnTop, lblWindowStatus
            });

            return panel;
        }

        private Control CreateCenterPanel()
        {
            splitMain = new SafeSplitContainer
            {
                Dock = DockStyle.Fill,
                Orientation = Orientation.Vertical,
                FixedPanel = FixedPanel.Panel1,
                SplitterWidth = 6,
                BackColor = Color.FromArgb(222, 226, 230)
            };

            splitMain.SplitterMoved += (s, e) =>
            {
                if (bottomLayout != null && bottomLayout.ColumnStyles.Count > 0)
                {
                    bottomLayout.ColumnStyles[0].Width = splitMain.SplitterDistance;
                    btnStartEngine.Width = Math.Max(200, splitMain.SplitterDistance - 20);
                    btnStopEngine.Width = Math.Max(200, splitMain.SplitterDistance - 20);
                }
            };

            splitMain.Panel1.Controls.Add(CreatePresetListPanel());
            splitMain.Panel2.Controls.Add(CreatePresetDetailPanel());

            return splitMain;
        }

        private Control CreatePresetListPanel()
        {
            Panel panel = new Panel
            {
                Dock = DockStyle.Fill,
                BackColor = Color.White,
                Padding = new Padding(6)
            };

            Label lblPresetHeader = new Label
            {
                Text = "📑 자동화 시나리오 목록 (체크된 항목 실행)",
                Font = new Font("맑은 고딕", 9.5F, FontStyle.Bold),
                ForeColor = Color.FromArgb(13, 110, 253),
                Dock = DockStyle.Top,
                Height = 26
            };

            lvPresets = new ListView
            {
                Dock = DockStyle.Fill,
                View = View.Details,
                CheckBoxes = true,
                FullRowSelect = true,
                GridLines = true,
                BackColor = Color.White,
                ForeColor = Color.FromArgb(33, 37, 41),
                Font = new Font("맑은 고딕", 9F)
            };
            lvPresets.Columns.Add("No", 45);
            lvPresets.Columns.Add("시나리오 이름", 160);
            lvPresets.Columns.Add("조건 분기 요약", 120);
            lvPresets.Columns.Add("동작수", 55);

            lvPresets.ItemChecked += LvPresets_ItemChecked;
            lvPresets.SelectedIndexChanged += LvPresets_SelectedIndexChanged;

            // 하단 버튼 툴바
            FlowLayoutPanel btnBar = new FlowLayoutPanel
            {
                Dock = DockStyle.Bottom,
                Height = 68,
                Padding = new Padding(2),
                BackColor = Color.FromArgb(248, 249, 250)
            };

            btnAddPreset = new Button { Text = "➕ 시나리오 추가", Size = new Size(110, 28), BackColor = Color.FromArgb(25, 135, 84), ForeColor = Color.White, FlatStyle = FlatStyle.Flat };
            btnAddPreset.FlatAppearance.BorderSize = 0;
            btnAddPreset.Click += BtnAddPreset_Click;

            btnClonePreset = new Button { Text = "📋 복제", Size = new Size(58, 28), BackColor = Color.FromArgb(13, 110, 253), ForeColor = Color.White, FlatStyle = FlatStyle.Flat };
            btnClonePreset.FlatAppearance.BorderSize = 0;
            btnClonePreset.Click += BtnClonePreset_Click;

            btnDeletePreset = new Button { Text = "🗑️ 삭제", Size = new Size(58, 28), BackColor = Color.FromArgb(220, 53, 69), ForeColor = Color.White, FlatStyle = FlatStyle.Flat };
            btnDeletePreset.FlatAppearance.BorderSize = 0;
            btnDeletePreset.Click += BtnDeletePreset_Click;

            btnMoveUpPreset = new Button { Text = "▲ 위로", Size = new Size(62, 28), BackColor = Color.FromArgb(235, 238, 242), ForeColor = Color.FromArgb(33, 37, 41), FlatStyle = FlatStyle.Flat };
            btnMoveUpPreset.FlatAppearance.BorderColor = Color.FromArgb(206, 212, 218);
            btnMoveUpPreset.Click += BtnMoveUpPreset_Click;

            btnMoveDownPreset = new Button { Text = "▼ 아래", Size = new Size(62, 28), BackColor = Color.FromArgb(235, 238, 242), ForeColor = Color.FromArgb(33, 37, 41), FlatStyle = FlatStyle.Flat };
            btnMoveDownPreset.FlatAppearance.BorderColor = Color.FromArgb(206, 212, 218);
            btnMoveDownPreset.Click += BtnMoveDownPreset_Click;

            btnExportConfig = new Button { Text = "💾 설정 내보내기", Size = new Size(110, 26), BackColor = Color.FromArgb(235, 238, 242), ForeColor = Color.FromArgb(33, 37, 41), FlatStyle = FlatStyle.Flat };
            btnExportConfig.FlatAppearance.BorderColor = Color.FromArgb(206, 212, 218);
            btnExportConfig.Click += BtnExportConfig_Click;

            btnImportConfig = new Button { Text = "📂 설정 가져오기", Size = new Size(110, 26), BackColor = Color.FromArgb(235, 238, 242), ForeColor = Color.FromArgb(33, 37, 41), FlatStyle = FlatStyle.Flat };
            btnImportConfig.FlatAppearance.BorderColor = Color.FromArgb(206, 212, 218);
            btnImportConfig.Click += BtnImportConfig_Click;

            btnBar.Controls.AddRange(new Control[] {
                btnAddPreset, btnClonePreset, btnDeletePreset, btnMoveUpPreset, btnMoveDownPreset,
                btnExportConfig, btnImportConfig
            });

            panel.Controls.Add(lvPresets);
            panel.Controls.Add(lblPresetHeader);
            panel.Controls.Add(btnBar);

            return panel;
        }

        private Control CreatePresetDetailPanel()
        {
            splitDetail = new SafeSplitContainer
            {
                Dock = DockStyle.Fill,
                Orientation = Orientation.Horizontal,
                FixedPanel = FixedPanel.Panel1,
                SplitterWidth = 6,
                BackColor = Color.FromArgb(222, 226, 230)
            };

            splitDetail.Panel1.Controls.Add(CreateConditionEditorPanel());
            splitDetail.Panel2.Controls.Add(CreateActionEditorPanel());

            return splitDetail;
        }

        private Control CreateConditionEditorPanel()
        {
            Panel panel = new Panel
            {
                Dock = DockStyle.Fill,
                BackColor = Color.White,
                Padding = new Padding(8)
            };

            // 상단 2줄 설정 바: 시나리오 번호, 이름, 일치 규칙, 분기 판단
            Panel topBar = new Panel { Dock = DockStyle.Top, Height = 74, BackColor = Color.FromArgb(246, 248, 250), Padding = new Padding(4) };

            Label lblNo = new Label { Text = "No:", Location = new Point(6, 8), AutoSize = true, ForeColor = Color.FromArgb(13, 110, 253), Font = new Font("맑은 고딕", 9F, FontStyle.Bold) };
            numScenarioNumber = new NumericUpDown { Location = new Point(36, 6), Width = 45, Minimum = 1, Maximum = 9999, Value = 1 };
            numScenarioNumber.ValueChanged += (s, e) =>
            {
                if (_selectedPreset != null)
                {
                    _selectedPreset.ScenarioNumber = (int)numScenarioNumber.Value;
                    UpdatePresetListItems();
                }
            };

            Label lblName = new Label { Text = "시나리오명:", Location = new Point(88, 8), AutoSize = true, ForeColor = Color.FromArgb(73, 80, 87) };
            txtPresetName = new TextBox { Location = new Point(160, 6), Width = 170, BackColor = Color.White, ForeColor = Color.FromArgb(33, 37, 41) };
            txtPresetName.TextChanged += (s, e) =>
            {
                if (_selectedPreset != null)
                {
                    _selectedPreset.Name = txtPresetName.Text;
                    UpdatePresetListItems();
                }
            };

            Label lblCond = new Label { Text = "일치 규칙:", Location = new Point(340, 8), AutoSize = true, ForeColor = Color.FromArgb(73, 80, 87) };
            cmbConditionMode = new ComboBox
            {
                DropDownStyle = ComboBoxStyle.DropDownList,
                Location = new Point(405, 6),
                Width = 150,
                BackColor = Color.White
            };
            cmbConditionMode.Items.AddRange(new object[] { "모든 포인트 일치 (AND)", "하나라도 일치 (OR)" });
            cmbConditionMode.SelectedIndexChanged += (s, e) =>
            {
                if (_selectedPreset != null) _selectedPreset.MatchMode = (ConditionMatchMode)cmbConditionMode.SelectedIndex;
            };

            Label lblCool = new Label { Text = "쿨다운:", Location = new Point(565, 8), AutoSize = true, ForeColor = Color.FromArgb(73, 80, 87) };
            numCooldown = new NumericUpDown { Location = new Point(615, 6), Width = 65, Minimum = 0, Maximum = 60000, Value = 500, Increment = 100 };
            numCooldown.ValueChanged += (s, e) =>
            {
                if (_selectedPreset != null) _selectedPreset.CooldownMs = (int)numCooldown.Value;
            };
            Label lblCoolMs = new Label { Text = "ms", Location = new Point(682, 8), AutoSize = true, ForeColor = Color.FromArgb(73, 80, 87) };

            // 2행: 조건 일치 시 분기 vs 조건 불일치 시 분기
            Label lblMatch = new Label { Text = "만약 [조건 일치] ➔", Location = new Point(6, 40), AutoSize = true, ForeColor = Color.FromArgb(25, 135, 84), Font = new Font("맑은 고딕", 9F, FontStyle.Bold) };
            cmbOnMatchBranch = new ComboBox { DropDownStyle = ComboBoxStyle.DropDownList, Location = new Point(135, 37), Width = 145 };
            cmbOnMatchBranch.Items.AddRange(new object[] { "액션 시퀀스 실행", "다른 시나리오로 점프", "매크로 즉시 정지", "1초 대기" });
            cmbOnMatchBranch.SelectedIndexChanged += (s, e) =>
            {
                if (_selectedPreset != null)
                {
                    _selectedPreset.OnMatchBranch = IndexToBranchAction(cmbOnMatchBranch.SelectedIndex);
                    numOnMatchJump.Visible = (_selectedPreset.OnMatchBranch == BranchAction.JumpToScenario);
                    UpdatePresetListItems();
                }
            };

            numOnMatchJump = new NumericUpDown { Location = new Point(285, 37), Width = 45, Minimum = 1, Maximum = 9999, Value = 1, Visible = false };
            numOnMatchJump.ValueChanged += (s, e) =>
            {
                if (_selectedPreset != null)
                {
                    _selectedPreset.OnMatchJumpNumber = (int)numOnMatchJump.Value;
                    UpdatePresetListItems();
                }
            };

            Label lblMismatch = new Label { Text = "만약 [조건 불일치] ➔", Location = new Point(340, 40), AutoSize = true, ForeColor = Color.FromArgb(220, 53, 69), Font = new Font("맑은 고딕", 9F, FontStyle.Bold) };
            cmbOnMismatchBranch = new ComboBox { DropDownStyle = ComboBoxStyle.DropDownList, Location = new Point(480, 37), Width = 150 };
            cmbOnMismatchBranch.Items.AddRange(new object[] { "아무 동작 안함(다음)", "다른 시나리오로 점프", "매크로 즉시 정지", "액션 시퀀스 실행" });
            cmbOnMismatchBranch.SelectedIndexChanged += (s, e) =>
            {
                if (_selectedPreset != null)
                {
                    _selectedPreset.OnMismatchBranch = IndexToMismatchBranchAction(cmbOnMismatchBranch.SelectedIndex);
                    numOnMismatchJump.Visible = (_selectedPreset.OnMismatchBranch == BranchAction.JumpToScenario);
                    UpdatePresetListItems();
                }
            };

            numOnMismatchJump = new NumericUpDown { Location = new Point(635, 37), Width = 45, Minimum = 1, Maximum = 9999, Value = 5, Visible = false };
            numOnMismatchJump.ValueChanged += (s, e) =>
            {
                if (_selectedPreset != null)
                {
                    _selectedPreset.OnMismatchJumpNumber = (int)numOnMismatchJump.Value;
                    UpdatePresetListItems();
                }
            };

            topBar.Controls.AddRange(new Control[] {
                lblNo, numScenarioNumber, lblName, txtPresetName, lblCond, cmbConditionMode, lblCool, numCooldown, lblCoolMs,
                lblMatch, cmbOnMatchBranch, numOnMatchJump, lblMismatch, cmbOnMismatchBranch, numOnMismatchJump
            });

            // 화면 감지 컬러 포인트 리스트뷰
            lvColorConditions = new ListView
            {
                Dock = DockStyle.Fill,
                View = View.Details,
                FullRowSelect = true,
                GridLines = true,
                BackColor = Color.White,
                ForeColor = Color.FromArgb(33, 37, 41),
                Font = new Font("맑은 고딕", 9F)
            };
            lvColorConditions.Columns.Add("감지 포인트 이름", 140);
            lvColorConditions.Columns.Add("형태", 55);
            lvColorConditions.Columns.Add("피봇", 75);
            lvColorConditions.Columns.Add("좌표 (X, Y)", 110);
            lvColorConditions.Columns.Add("목표 색상", 85);
            lvColorConditions.Columns.Add("허용오차", 65);
            lvColorConditions.Columns.Add("현재 감지 색상", 105);
            lvColorConditions.Columns.Add("일치 판정", 80);

            // 하단 툴바
            FlowLayoutPanel pointBar = new FlowLayoutPanel
            {
                Dock = DockStyle.Bottom,
                Height = 36,
                Padding = new Padding(2),
                BackColor = Color.FromArgb(248, 249, 250)
            };

            btnPickPointColor = new Button
            {
                Text = "🎨 [돋보기 컬러피커] 점 등록",
                Size = new Size(185, 28),
                BackColor = Color.FromArgb(13, 110, 253),
                ForeColor = Color.White,
                Font = new Font("맑은 고딕", 9F, FontStyle.Bold),
                FlatStyle = FlatStyle.Flat
            };
            btnPickPointColor.FlatAppearance.BorderSize = 0;
            btnPickPointColor.Click += (s, e) => PickColorCondition(false);

            btnPickLineColor = new Button
            {
                Text = "📏 [선(Line) 샘플링] 선 등록",
                Size = new Size(185, 28),
                BackColor = Color.FromArgb(111, 66, 193),
                ForeColor = Color.White,
                Font = new Font("맑은 고딕", 9F, FontStyle.Bold),
                FlatStyle = FlatStyle.Flat
            };
            btnPickLineColor.FlatAppearance.BorderSize = 0;
            btnPickLineColor.Click += (s, e) => PickColorCondition(true);

            btnEditCondition = new Button
            {
                Text = "✏️ 직접 수정",
                Size = new Size(90, 28),
                BackColor = Color.FromArgb(235, 238, 242),
                ForeColor = Color.FromArgb(33, 37, 41),
                FlatStyle = FlatStyle.Flat
            };
            btnEditCondition.FlatAppearance.BorderColor = Color.FromArgb(206, 212, 218);
            btnEditCondition.Click += BtnEditCondition_Click;

            btnDeleteCondition = new Button
            {
                Text = "🗑️ 삭제",
                Size = new Size(70, 28),
                BackColor = Color.FromArgb(220, 53, 69),
                ForeColor = Color.White,
                FlatStyle = FlatStyle.Flat
            };
            btnDeleteCondition.FlatAppearance.BorderSize = 0;
            btnDeleteCondition.Click += BtnDeleteCondition_Click;

            btnTestCondition = new Button
            {
                Text = "🔍 현재 조건 즉시 테스트",
                Size = new Size(165, 28),
                BackColor = Color.FromArgb(25, 135, 84),
                ForeColor = Color.White,
                FlatStyle = FlatStyle.Flat
            };
            btnTestCondition.FlatAppearance.BorderSize = 0;
            btnTestCondition.Click += BtnTestCondition_Click;

            pointBar.Controls.AddRange(new Control[] {
                btnPickPointColor, btnPickLineColor, btnEditCondition, btnDeleteCondition, btnTestCondition
            });

            panel.Controls.Add(lvColorConditions);
            panel.Controls.Add(topBar);
            panel.Controls.Add(pointBar);

            return panel;
        }

        private Control CreateActionEditorPanel()
        {
            Panel panel = new Panel
            {
                Dock = DockStyle.Fill,
                BackColor = Color.White,
                Padding = new Padding(8)
            };

            Label lblHeader = new Label
            {
                Text = "🎬 [자동 조작 순서] 조건 만족 시 실행할 조작 단계 (Action Sequence)",
                Font = new Font("맑은 고딕", 9.5F, FontStyle.Bold),
                ForeColor = Color.FromArgb(25, 135, 84),
                Dock = DockStyle.Top,
                Height = 24
            };

            lvActions = new ListView
            {
                Dock = DockStyle.Fill,
                View = View.Details,
                FullRowSelect = true,
                GridLines = true,
                BackColor = Color.White,
                ForeColor = Color.FromArgb(33, 37, 41),
                Font = new Font("맑은 고딕", 9F)
            };
            lvActions.Columns.Add("순서", 45);
            lvActions.Columns.Add("조작 방식", 100);
            lvActions.Columns.Add("피봇", 75);
            lvActions.Columns.Add("좌표 (X, Y) / 구간", 130);
            lvActions.Columns.Add("대기 시간", 80);
            lvActions.Columns.Add("키 / 점프 / 조작 설명", 220);

            FlowLayoutPanel actionBar = new FlowLayoutPanel
            {
                Dock = DockStyle.Bottom,
                Height = 36,
                Padding = new Padding(2),
                BackColor = Color.FromArgb(248, 249, 250)
            };

            btnAddClickAction = new Button
            {
                Text = "🎯 [화면 클릭]으로 조작 등록",
                Size = new Size(185, 28),
                BackColor = Color.FromArgb(25, 135, 84),
                ForeColor = Color.White,
                Font = new Font("맑은 고딕", 9F, FontStyle.Bold),
                FlatStyle = FlatStyle.Flat
            };
            btnAddClickAction.FlatAppearance.BorderSize = 0;
            btnAddClickAction.Click += (s, e) => AddPickerAction(false);

            btnAddDragAction = new Button
            {
                Text = "↔️ [화면 드래그]로 조작 등록",
                Size = new Size(185, 28),
                BackColor = Color.FromArgb(111, 66, 193),
                ForeColor = Color.White,
                Font = new Font("맑은 고딕", 9F, FontStyle.Bold),
                FlatStyle = FlatStyle.Flat
            };
            btnAddDragAction.FlatAppearance.BorderSize = 0;
            btnAddDragAction.Click += (s, e) => AddPickerAction(true);

            btnAddCustomAction = new Button
            {
                Text = "➕ 조작 직접 추가",
                Size = new Size(120, 28),
                BackColor = Color.FromArgb(235, 238, 242),
                ForeColor = Color.FromArgb(33, 37, 41),
                FlatStyle = FlatStyle.Flat
            };
            btnAddCustomAction.FlatAppearance.BorderColor = Color.FromArgb(206, 212, 218);
            btnAddCustomAction.Click += BtnAddCustomAction_Click;

            btnEditAction = new Button
            {
                Text = "✏️ 수정",
                Size = new Size(65, 28),
                BackColor = Color.FromArgb(235, 238, 242),
                ForeColor = Color.FromArgb(33, 37, 41),
                FlatStyle = FlatStyle.Flat
            };
            btnEditAction.FlatAppearance.BorderColor = Color.FromArgb(206, 212, 218);
            btnEditAction.Click += BtnEditAction_Click;

            btnDeleteAction = new Button
            {
                Text = "🗑️ 삭제",
                Size = new Size(65, 28),
                BackColor = Color.FromArgb(220, 53, 69),
                ForeColor = Color.White,
                FlatStyle = FlatStyle.Flat
            };
            btnDeleteAction.FlatAppearance.BorderSize = 0;
            btnDeleteAction.Click += BtnDeleteAction_Click;

            btnMoveUpAction = new Button
            {
                Text = "▲",
                Size = new Size(40, 28),
                BackColor = Color.FromArgb(235, 238, 242),
                ForeColor = Color.FromArgb(33, 37, 41),
                FlatStyle = FlatStyle.Flat
            };
            btnMoveUpAction.FlatAppearance.BorderColor = Color.FromArgb(206, 212, 218);
            btnMoveUpAction.Click += BtnMoveUpAction_Click;

            btnMoveDownAction = new Button
            {
                Text = "▼",
                Size = new Size(40, 28),
                BackColor = Color.FromArgb(235, 238, 242),
                ForeColor = Color.FromArgb(33, 37, 41),
                FlatStyle = FlatStyle.Flat
            };
            btnMoveDownAction.FlatAppearance.BorderColor = Color.FromArgb(206, 212, 218);
            btnMoveDownAction.Click += BtnMoveDownAction_Click;

            btnTestAction = new Button
            {
                Text = "▶ 조작 1회 테스트",
                Size = new Size(125, 28),
                BackColor = Color.FromArgb(13, 110, 253),
                ForeColor = Color.White,
                FlatStyle = FlatStyle.Flat
            };
            btnTestAction.FlatAppearance.BorderSize = 0;
            btnTestAction.Click += BtnTestAction_Click;

            actionBar.Controls.AddRange(new Control[] {
                btnAddClickAction, btnAddDragAction, btnAddCustomAction, btnEditAction, btnDeleteAction,
                btnMoveUpAction, btnMoveDownAction, btnTestAction
            });

            panel.Controls.Add(lvActions);
            panel.Controls.Add(lblHeader);
            panel.Controls.Add(actionBar);

            return panel;
        }

        private Control CreateBottomDashboard()
        {
            Panel panel = new Panel
            {
                Dock = DockStyle.Fill,
                BackColor = Color.FromArgb(240, 243, 246),
                Padding = new Padding(8)
            };

            bottomLayout = new TableLayoutPanel
            {
                Dock = DockStyle.Fill,
                RowCount = 1,
                ColumnCount = 2
            };
            bottomLayout.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 422));
            bottomLayout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));

            // 좌측: 시작/정지 제어 카드
            Panel controlCard = new Panel
            {
                Dock = DockStyle.Fill,
                BackColor = Color.White,
                Padding = new Padding(10)
            };

            lblEngineStatus = new Label
            {
                Text = "⏹ 오토 정지 상태 (대기 중)",
                Font = new Font("맑은 고딕", 12F, FontStyle.Bold),
                ForeColor = Color.FromArgb(217, 119, 6),
                Location = new Point(10, 10),
                AutoSize = true
            };

            btnStartEngine = new Button
            {
                Text = "🚀 오토 감시 및 실행 시작 (F6)",
                Location = new Point(10, 42),
                Size = new Size(400, 48),
                Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right,
                BackColor = Color.FromArgb(25, 135, 84),
                ForeColor = Color.White,
                Font = new Font("맑은 고딕", 12F, FontStyle.Bold),
                FlatStyle = FlatStyle.Flat,
                Cursor = Cursors.Hand
            };
            btnStartEngine.FlatAppearance.BorderSize = 0;
            btnStartEngine.Click += (s, e) => StartMacro();

            btnStopEngine = new Button
            {
                Text = "⏹ 오토 정지 (F7) / 🚨 긴급 정지 (ESC)",
                Location = new Point(10, 96),
                Size = new Size(400, 42),
                Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right,
                BackColor = Color.FromArgb(220, 53, 69),
                ForeColor = Color.White,
                Font = new Font("맑은 고딕", 10.5F, FontStyle.Bold),
                FlatStyle = FlatStyle.Flat,
                Cursor = Cursors.Hand
            };
            btnStopEngine.FlatAppearance.BorderSize = 0;
            btnStopEngine.Click += (s, e) => StopMacro();

            controlCard.Controls.AddRange(new Control[] { lblEngineStatus, btnStartEngine, btnStopEngine });

            // 우측: 실시간 로그 창
            Panel logPanel = new Panel { Dock = DockStyle.Fill, Padding = new Padding(4) };

            Label lblLogTitle = new Label
            {
                Text = "📊 실시간 동작, 화면 판단 및 분기 로그:",
                ForeColor = Color.FromArgb(73, 80, 87),
                Font = new Font("맑은 고딕", 9F, FontStyle.Bold),
                Dock = DockStyle.Top,
                Height = 20
            };

            rtbLog = new RichTextBox
            {
                Dock = DockStyle.Fill,
                BackColor = Color.White,
                ForeColor = Color.FromArgb(33, 37, 41),
                Font = new Font("Consolas", 9F),
                ReadOnly = true,
                BorderStyle = BorderStyle.FixedSingle
            };

            logPanel.Controls.Add(rtbLog);
            logPanel.Controls.Add(lblLogTitle);

            bottomLayout.Controls.Add(controlCard, 0, 0);
            bottomLayout.Controls.Add(logPanel, 1, 0);

            panel.Controls.Add(bottomLayout);
            return panel;
        }

        // ==========================================
        // 타겟 윈도우 관리
        // ==========================================
        private void RefreshOpenWindows()
        {
            _isUpdatingWindowsList = true;
            try
            {
                cmbWindows.Items.Clear();
                var windows = WindowHelper.GetOpenWindows();

                int selectIndex = -1;
                for (int i = 0; i < windows.Count; i++)
                {
                    cmbWindows.Items.Add(windows[i]);
                    if (_currentTargetHWnd != IntPtr.Zero && windows[i].HWnd == _currentTargetHWnd)
                    {
                        selectIndex = i;
                    }
                    else if (selectIndex < 0 && _profile != null && !string.IsNullOrEmpty(_profile.TargetWindowTitle) &&
                        windows[i].Title.Contains(_profile.TargetWindowTitle))
                    {
                        selectIndex = i;
                    }
                }

                if (selectIndex >= 0)
                {
                    cmbWindows.SelectedIndex = selectIndex;
                }
                else if (cmbWindows.Items.Count > 0)
                {
                    cmbWindows.SelectedIndex = 0;
                }
            }
            finally
            {
                _isUpdatingWindowsList = false;
            }

            if (cmbWindows.SelectedItem is WindowInfo win)
            {
                SetTargetWindow(win.HWnd, win.Title, win.ProcessName);
            }
        }

        private void CmbWindows_SelectedIndexChanged(object sender, EventArgs e)
        {
            if (_isUpdatingWindowsList) return;
            if (cmbWindows.SelectedItem is WindowInfo win)
            {
                SetTargetWindow(win.HWnd, win.Title, win.ProcessName);
            }
        }

        private void BtnPickWindow_Click(object sender, EventArgs e)
        {
            using (var picker = new WindowTargetPickerOverlayForm())
            {
                if (picker.ShowDialog() == DialogResult.OK && picker.SelectedHWnd != IntPtr.Zero)
                {
                    SetTargetWindow(picker.SelectedHWnd, picker.SelectedTitle, picker.SelectedProcessName);
                }
            }
        }

        private void SetTargetWindow(IntPtr hWnd, string title, string procName)
        {
            if (hWnd == IntPtr.Zero) return;
            _currentTargetHWnd = hWnd;
            if (_profile != null)
            {
                _profile.TargetWindowTitle = title;
                _profile.TargetProcessName = procName;
            }

            // cmbWindows 선택 항목 동기화
            _isUpdatingWindowsList = true;
            try
            {
                bool found = false;
                for (int i = 0; i < cmbWindows.Items.Count; i++)
                {
                    if (cmbWindows.Items[i] is WindowInfo win && win.HWnd == hWnd)
                    {
                        cmbWindows.SelectedIndex = i;
                        found = true;
                        break;
                    }
                }
                if (!found)
                {
                    var newWin = new WindowInfo { HWnd = hWnd, Title = title, ProcessName = procName };
                    cmbWindows.Items.Insert(0, newWin);
                    cmbWindows.SelectedIndex = 0;
                }
            }
            finally
            {
                _isUpdatingWindowsList = false;
            }

            Size clientSize = WindowHelper.GetClientSize(hWnd);
            lblWindowStatus.Text = $"✓ 선택된 창: [{procName}] {title} | 게임 렌더링 영역: {clientSize.Width} x {clientSize.Height} (기준좌표: 0,0)";
            lblWindowStatus.ForeColor = Color.FromArgb(13, 110, 253);

            AppendLog($"🎯 대상 창 설정 완료: [{procName}] {title} ({clientSize.Width}x{clientSize.Height})", Color.FromArgb(13, 110, 253));
        }

        private void BtnAlwaysOnTop_Click(object sender, EventArgs e)
        {
            this.TopMost = !this.TopMost;
            if (_profile != null) _profile.AlwaysOnTop = this.TopMost;

            btnAlwaysOnTop.Text = this.TopMost ? "📌 항상 위 [ON]" : "📌 항상 위 [OFF]";
            btnAlwaysOnTop.BackColor = this.TopMost ? Color.FromArgb(25, 135, 84) : Color.FromArgb(235, 238, 242);
            btnAlwaysOnTop.ForeColor = this.TopMost ? Color.White : Color.FromArgb(33, 37, 41);
        }

        private void BtnDisableHotkeys_Click(object sender, EventArgs e)
        {
            SetHotkeysDisabled(!_hotkeysDisabled);
        }

        private void SetHotkeysDisabled(bool disabled)
        {
            _hotkeysDisabled = disabled;
            if (_profile != null) _profile.HotkeysDisabled = disabled;

            if (_hotkeysDisabled)
            {
                btnDisableHotkeys.Text = "🔇 단축키 [비활성]";
                btnDisableHotkeys.BackColor = Color.FromArgb(220, 53, 69);
                btnDisableHotkeys.ForeColor = Color.White;
                toolTip.SetToolTip(btnDisableHotkeys, "모든 단축키(ESC 긴급정지, F6 시작, F7 정지)가 비활성화되었습니다.\n클릭하면 단축키를 다시 활성화합니다.");
                AppendLog("🔇 모든 단축키(ESC, F6, F7)가 비활성화되었습니다.", Color.FromArgb(220, 53, 69));
            }
            else
            {
                btnDisableHotkeys.Text = "⌨️ 단축키 [활성]";
                btnDisableHotkeys.BackColor = Color.FromArgb(235, 238, 242);
                btnDisableHotkeys.ForeColor = Color.FromArgb(33, 37, 41);
                toolTip.SetToolTip(btnDisableHotkeys, "단축키(ESC 긴급정지, F6 시작, F7 정지) 사용 중입니다.\n클릭하면 모든 단축키를 비활성화합니다.");
                AppendLog("⌨️ 단축키(ESC 긴급정지, F6 시작, F7 정지)가 활성화되었습니다.", Color.FromArgb(25, 135, 84));
            }
        }

        // ==========================================
        // 창 크기 및 화면 분할 비율(레이아웃) 관리
        // ==========================================
        private void ApplyLayoutSettings()
        {
            var layout = _profile?.WindowLayout ?? new WindowLayoutSettings();

            if (layout.WindowWidth >= this.MinimumSize.Width && layout.WindowHeight >= this.MinimumSize.Height)
            {
                this.Size = new Size(layout.WindowWidth, layout.WindowHeight);
            }
            else
            {
                this.Size = new Size(1166, 973);
            }

            if (layout.IsMaximized)
            {
                this.WindowState = FormWindowState.Maximized;
            }

            SetColumnWidths(lvPresets, layout.PresetColumnWidths);
            SetColumnWidths(lvColorConditions, layout.ConditionColumnWidths);
            SetColumnWidths(lvActions, layout.ActionColumnWidths);
        }

        private void RestoreSplitterDistances()
        {
            var layout = _profile?.WindowLayout ?? new WindowLayoutSettings();
            try
            {
                if (splitMain != null && splitMain.Width > 500)
                {
                    splitMain.Panel1MinSize = 250;
                    splitMain.Panel2MinSize = 400;

                    int mainDist = layout.MainSplitterDistance > 100 ? layout.MainSplitterDistance : 422;
                    int maxMain = Math.Max(splitMain.Panel1MinSize, splitMain.Width - splitMain.Panel2MinSize);
                    splitMain.SplitterDistance = Math.Max(splitMain.Panel1MinSize, Math.Min(maxMain, mainDist));
                }

                if (splitDetail != null && splitDetail.Height > 300)
                {
                    splitDetail.Panel1MinSize = 180;
                    splitDetail.Panel2MinSize = 120;

                    int detailDist = layout.DetailSplitterDistance > 100 ? layout.DetailSplitterDistance : 467;
                    int maxDetail = Math.Max(splitDetail.Panel1MinSize, splitDetail.Height - splitDetail.Panel2MinSize);
                    splitDetail.SplitterDistance = Math.Max(splitDetail.Panel1MinSize, Math.Min(maxDetail, detailDist));
                }

                if (bottomLayout != null && splitMain != null && bottomLayout.ColumnStyles.Count > 0)
                {
                    bottomLayout.ColumnStyles[0].Width = splitMain.SplitterDistance;
                    btnStartEngine.Width = Math.Max(200, splitMain.SplitterDistance - 20);
                    btnStopEngine.Width = Math.Max(200, splitMain.SplitterDistance - 20);
                }
            }
            catch { }
        }

        private void SaveCurrentLayout()
        {
            if (_profile == null) return;
            if (_profile.WindowLayout == null) _profile.WindowLayout = new WindowLayoutSettings();

            if (this.WindowState == FormWindowState.Normal)
            {
                _profile.WindowLayout.WindowWidth = this.Width;
                _profile.WindowLayout.WindowHeight = this.Height;
            }
            _profile.WindowLayout.IsMaximized = (this.WindowState == FormWindowState.Maximized);

            if (splitMain != null && splitMain.SplitterDistance > 100)
            {
                _profile.WindowLayout.MainSplitterDistance = splitMain.SplitterDistance;
            }
            if (splitDetail != null && splitDetail.SplitterDistance > 100)
            {
                _profile.WindowLayout.DetailSplitterDistance = splitDetail.SplitterDistance;
            }

            try
            {
                _profile.WindowLayout.PresetColumnWidths = GetColumnWidths(lvPresets);
                _profile.WindowLayout.ConditionColumnWidths = GetColumnWidths(lvColorConditions);
                _profile.WindowLayout.ActionColumnWidths = GetColumnWidths(lvActions);
            }
            catch { }

            ConfigManager.SaveDefault(_profile);
        }

        private void BtnSaveLayout_Click(object sender, EventArgs e)
        {
            SaveCurrentLayout();

            btnSaveLayout.Text = "✔ 저장 완료!";
            btnSaveLayout.BackColor = Color.FromArgb(25, 135, 84);
            btnSaveLayout.ForeColor = Color.White;
            btnSaveLayout.FlatAppearance.BorderColor = Color.FromArgb(25, 135, 84);

            var revertTimer = new FormsTimer();
            revertTimer.Interval = 1500;
            revertTimer.Tick += (s, ev) =>
            {
                revertTimer.Stop();
                revertTimer.Dispose();
                btnSaveLayout.Text = "💾 비율 저장";
                btnSaveLayout.BackColor = Color.FromArgb(240, 244, 248);
                btnSaveLayout.ForeColor = Color.FromArgb(13, 110, 253);
                btnSaveLayout.FlatAppearance.BorderColor = Color.FromArgb(13, 110, 253);
            };
            revertTimer.Start();

            AppendLog($"💾 [화면 비율 저장 완료] 창 크기({this.Width}x{this.Height}), 가운데 창 분할 비율(좌우:{splitMain?.SplitterDistance}px, 상하:{splitDetail?.SplitterDistance}px)이 저장되었습니다.", Color.FromArgb(25, 135, 84));
        }

        private int[] GetColumnWidths(ListView lv)
        {
            if (lv == null || lv.Columns.Count == 0) return null;
            int[] widths = new int[lv.Columns.Count];
            for (int i = 0; i < lv.Columns.Count; i++)
            {
                widths[i] = lv.Columns[i].Width;
            }
            return widths;
        }

        private void SetColumnWidths(ListView lv, int[] widths)
        {
            if (lv == null || widths == null) return;
            for (int i = 0; i < Math.Min(lv.Columns.Count, widths.Length); i++)
            {
                if (widths[i] > 20) lv.Columns[i].Width = widths[i];
            }
        }

        // ==========================================
        // 시나리오 프리셋 데이터 바인딩
        // ==========================================
        private void ApplyProfileToUI()
        {
            if (_profile == null) return;

            this.TopMost = _profile.AlwaysOnTop;
            btnAlwaysOnTop.Text = this.TopMost ? "📌 항상 위 [ON]" : "📌 항상 위 [OFF]";
            btnAlwaysOnTop.BackColor = this.TopMost ? Color.FromArgb(25, 135, 84) : Color.FromArgb(235, 238, 242);
            btnAlwaysOnTop.ForeColor = this.TopMost ? Color.White : Color.FromArgb(33, 37, 41);

            SetHotkeysDisabled(_profile.HotkeysDisabled);

            cmbDefaultPivot.SelectedIndex = (int)_profile.DefaultPivot;
            numCheckInterval.Value = Math.Max(20, Math.Min(5000, _profile.CheckIntervalMs));

            UpdatePresetListItems();

            if (_profile.Presets.Count > 0)
            {
                _selectedPreset = _profile.Presets[0];
                LoadPresetToDetail(_selectedPreset);
            }
        }

        private void UpdatePresetListItems()
        {
            lvPresets.BeginUpdate();
            lvPresets.Items.Clear();

            foreach (var preset in _profile.Presets)
            {
                var lvi = new ListViewItem(preset.ScenarioNumber.ToString());
                lvi.Checked = preset.IsEnabled;
                lvi.SubItems.Add(preset.Name);

                string branchSummary = FormatBranchSummary(preset);
                lvi.SubItems.Add(branchSummary);
                lvi.SubItems.Add(preset.Actions.Count.ToString());
                lvi.Tag = preset;
                lvPresets.Items.Add(lvi);
            }
            lvPresets.EndUpdate();
        }

        private string FormatBranchSummary(ScenarioPreset preset)
        {
            if (preset.OnMismatchBranch == BranchAction.JumpToScenario)
            {
                return $"불일치 ➔ #{preset.OnMismatchJumpNumber} 점프";
            }
            if (preset.OnMatchBranch == BranchAction.JumpToScenario)
            {
                return $"일치 ➔ #{preset.OnMatchJumpNumber} 점프";
            }
            return "일치 ➔ 액션 실행";
        }

        private void LvPresets_ItemChecked(object sender, ItemCheckedEventArgs e)
        {
            if (e.Item.Tag is ScenarioPreset preset)
            {
                preset.IsEnabled = e.Item.Checked;
            }
        }

        private void LvPresets_SelectedIndexChanged(object sender, EventArgs e)
        {
            if (lvPresets.SelectedItems.Count > 0 && lvPresets.SelectedItems[0].Tag is ScenarioPreset preset)
            {
                _selectedPreset = preset;
                LoadPresetToDetail(preset);
            }
        }

        private void LoadPresetToDetail(ScenarioPreset preset)
        {
            numScenarioNumber.Value = preset.ScenarioNumber;
            txtPresetName.Text = preset.Name;
            cmbConditionMode.SelectedIndex = (int)preset.MatchMode;
            numCooldown.Value = Math.Max(0, Math.Min(60000, preset.CooldownMs));

            cmbOnMatchBranch.SelectedIndex = BranchActionToIndex(preset.OnMatchBranch);
            numOnMatchJump.Value = Math.Max(1, preset.OnMatchJumpNumber);
            numOnMatchJump.Visible = (preset.OnMatchBranch == BranchAction.JumpToScenario);

            cmbOnMismatchBranch.SelectedIndex = MismatchBranchActionToIndex(preset.OnMismatchBranch);
            numOnMismatchJump.Value = Math.Max(1, preset.OnMismatchJumpNumber);
            numOnMismatchJump.Visible = (preset.OnMismatchBranch == BranchAction.JumpToScenario);

            UpdateColorConditionList();
            UpdateActionList();
        }

        private BranchAction IndexToBranchAction(int index)
        {
            switch (index)
            {
                case 0: return BranchAction.ExecuteActions;
                case 1: return BranchAction.JumpToScenario;
                case 2: return BranchAction.StopMacro;
                case 3: return BranchAction.PauseWait;
                default: return BranchAction.ExecuteActions;
            }
        }

        private int BranchActionToIndex(BranchAction action)
        {
            switch (action)
            {
                case BranchAction.ExecuteActions: return 0;
                case BranchAction.JumpToScenario: return 1;
                case BranchAction.StopMacro: return 2;
                case BranchAction.PauseWait: return 3;
                default: return 0;
            }
        }

        private BranchAction IndexToMismatchBranchAction(int index)
        {
            switch (index)
            {
                case 0: return BranchAction.DoNothing;
                case 1: return BranchAction.JumpToScenario;
                case 2: return BranchAction.StopMacro;
                case 3: return BranchAction.ExecuteActions;
                default: return BranchAction.DoNothing;
            }
        }

        private int MismatchBranchActionToIndex(BranchAction action)
        {
            switch (action)
            {
                case BranchAction.DoNothing: return 0;
                case BranchAction.JumpToScenario: return 1;
                case BranchAction.StopMacro: return 2;
                case BranchAction.ExecuteActions: return 3;
                default: return 0;
            }
        }

        private void BtnAddPreset_Click(object sender, EventArgs e)
        {
            int nextNumber = (_profile.Presets.Count > 0) ? _profile.Presets.Max(p => p.ScenarioNumber) + 1 : 1;
            var newPreset = new ScenarioPreset
            {
                ScenarioNumber = nextNumber,
                Name = $"시나리오 {nextNumber}",
                IsEnabled = true
            };
            _profile.Presets.Add(newPreset);
            UpdatePresetListItems();

            lvPresets.Items[lvPresets.Items.Count - 1].Selected = true;
        }

        private void BtnClonePreset_Click(object sender, EventArgs e)
        {
            if (_selectedPreset == null) return;
            var clone = _selectedPreset.Clone();
            clone.ScenarioNumber = _profile.Presets.Max(p => p.ScenarioNumber) + 1;
            _profile.Presets.Add(clone);
            UpdatePresetListItems();

            lvPresets.Items[lvPresets.Items.Count - 1].Selected = true;
        }

        private void BtnDeletePreset_Click(object sender, EventArgs e)
        {
            if (_selectedPreset == null) return;
            if (_profile.Presets.Count <= 1)
            {
                MessageBox.Show("최소 1개의 시나리오는 유지되어야 합니다.", "안내", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }

            if (MessageBox.Show($"'{_selectedPreset.Name}' 시나리오를 삭제하시겠습니까?", "삭제 확인", MessageBoxButtons.YesNo, MessageBoxIcon.Question) == DialogResult.Yes)
            {
                int index = _profile.Presets.IndexOf(_selectedPreset);
                _profile.Presets.Remove(_selectedPreset);
                UpdatePresetListItems();

                int nextSelect = Math.Min(index, _profile.Presets.Count - 1);
                if (nextSelect >= 0) lvPresets.Items[nextSelect].Selected = true;
            }
        }

        private void BtnMoveUpPreset_Click(object sender, EventArgs e)
        {
            if (_selectedPreset == null) return;
            int idx = _profile.Presets.IndexOf(_selectedPreset);
            if (idx > 0)
            {
                _profile.Presets.RemoveAt(idx);
                _profile.Presets.Insert(idx - 1, _selectedPreset);
                UpdatePresetListItems();
                lvPresets.Items[idx - 1].Selected = true;
            }
        }

        private void BtnMoveDownPreset_Click(object sender, EventArgs e)
        {
            if (_selectedPreset == null) return;
            int idx = _profile.Presets.IndexOf(_selectedPreset);
            if (idx >= 0 && idx < _profile.Presets.Count - 1)
            {
                _profile.Presets.RemoveAt(idx);
                _profile.Presets.Insert(idx + 1, _selectedPreset);
                UpdatePresetListItems();
                lvPresets.Items[idx + 1].Selected = true;
            }
        }

        private void BtnExportConfig_Click(object sender, EventArgs e)
        {
            using (var sfd = new SaveFileDialog())
            {
                sfd.Filter = "JSON 설정 파일 (*.json)|*.json";
                sfd.FileName = "fgoa_auto_macro_config.json";
                if (sfd.ShowDialog() == DialogResult.OK)
                {
                    ConfigManager.SaveToFile(sfd.FileName, _profile);
                    MessageBox.Show("설정 내보내기가 완료되었습니다.", "완료", MessageBoxButtons.OK, MessageBoxIcon.Information);
                }
            }
        }

        private void BtnImportConfig_Click(object sender, EventArgs e)
        {
            using (var ofd = new OpenFileDialog())
            {
                ofd.Filter = "JSON 설정 파일 (*.json)|*.json";
                if (ofd.ShowDialog() == DialogResult.OK)
                {
                    try
                    {
                        _profile = ConfigManager.LoadFromFile(ofd.FileName);
                        ApplyProfileToUI();
                        MessageBox.Show("설정 가져오기가 완료되었습니다.", "완료", MessageBoxButtons.OK, MessageBoxIcon.Information);
                    }
                    catch (Exception ex)
                    {
                        MessageBox.Show($"설정 파일을 불러오는 중 오류가 발생했습니다: {ex.Message}", "오류", MessageBoxButtons.OK, MessageBoxIcon.Error);
                    }
                }
            }
        }

        // ==========================================
        // [Eye & Brain] 컬러 감지 조건 관리
        // ==========================================
        private void UpdateColorConditionList()
        {
            lvColorConditions.BeginUpdate();
            lvColorConditions.Items.Clear();

            if (_selectedPreset != null)
            {
                foreach (var cond in _selectedPreset.ColorConditions)
                {
                    var lvi = new ListViewItem(cond.Name);
                    lvi.SubItems.Add(cond.Shape == ColorPointShape.Point ? "점" : $"선({cond.SampleCount}점)");
                    lvi.SubItems.Add(cond.Pivot == CoordinatePivot.WindowRelative ? "창 상대" : "화면 절대");

                    string coordStr = cond.Shape == ColorPointShape.Point
                        ? $"({cond.X}, {cond.Y})"
                        : $"({cond.X},{cond.Y})➔({cond.EndX},{cond.EndY})";
                    lvi.SubItems.Add(coordStr);

                    lvi.SubItems.Add(cond.TargetColorHex);
                    lvi.SubItems.Add($"±{cond.Tolerance}");
                    lvi.SubItems.Add("-");
                    lvi.SubItems.Add("-");
                    lvi.Tag = cond;
                    lvColorConditions.Items.Add(lvi);
                }
            }

            lvColorConditions.EndUpdate();
        }

        private void PickColorCondition(bool isLineMode)
        {
            if (_selectedPreset == null)
            {
                MessageBox.Show("시나리오를 먼저 선택해 주세요.", "안내", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }

            CoordinatePivot pivot = _selectedPreset.DefaultPivot;
            if (pivot == CoordinatePivot.WindowRelative && _currentTargetHWnd == IntPtr.Zero)
            {
                MessageBox.Show("창 상대좌표를 사용하려면 대상 게임 창을 먼저 지정해 주세요.", "안내", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            this.WindowState = FormWindowState.Minimized;
            System.Threading.Thread.Sleep(200);

            using (var picker = new ColorPickerOverlayForm(_currentTargetHWnd, pivot, isLineMode))
            {
                if (picker.ShowDialog() == DialogResult.OK)
                {
                    var newCond = new ColorCondition
                    {
                        Name = isLineMode ? $"선 감지 {_selectedPreset.ColorConditions.Count + 1}" : $"포인트 {_selectedPreset.ColorConditions.Count + 1}",
                        Shape = isLineMode ? ColorPointShape.Line : ColorPointShape.Point,
                        Pivot = pivot,
                        X = picker.SelectedPoint.X,
                        Y = picker.SelectedPoint.Y,
                        EndX = picker.SelectedEndPoint.X,
                        EndY = picker.SelectedEndPoint.Y,
                        TargetColorHex = $"#{picker.SelectedColor.R:X2}{picker.SelectedColor.G:X2}{picker.SelectedColor.B:X2}",
                        Tolerance = 15,
                        MustMatch = true
                    };

                    _selectedPreset.ColorConditions.Add(newCond);
                    UpdateColorConditionList();
                    UpdatePresetListItems();
                }
            }

            this.WindowState = FormWindowState.Normal;
            this.BringToFront();
        }

        private void BtnEditCondition_Click(object sender, EventArgs e)
        {
            if (lvColorConditions.SelectedItems.Count == 0 || !(lvColorConditions.SelectedItems[0].Tag is ColorCondition cond))
            {
                MessageBox.Show("수정할 감지 포인트를 선택해 주세요.", "안내", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }

            using (var dlg = new Form())
            {
                dlg.Text = "감지 조건 상세 수정";
                dlg.Size = new Size(340, 310);
                dlg.StartPosition = FormStartPosition.CenterParent;
                dlg.FormBorderStyle = FormBorderStyle.FixedDialog;
                dlg.MaximizeBox = false;
                dlg.MinimizeBox = false;

                Label lblName = new Label { Text = "포인트 이름:", Location = new Point(15, 15), AutoSize = true };
                TextBox txtName = new TextBox { Text = cond.Name, Location = new Point(110, 12), Width = 180 };

                Label lblX = new Label { Text = "좌표 X / Y:", Location = new Point(15, 48), AutoSize = true };
                NumericUpDown numX = new NumericUpDown { Value = cond.X, Minimum = -5000, Maximum = 10000, Location = new Point(110, 45), Width = 85 };
                NumericUpDown numY = new NumericUpDown { Value = cond.Y, Minimum = -5000, Maximum = 10000, Location = new Point(205, 45), Width = 85 };

                Label lblColor = new Label { Text = "목표 색상(HEX):", Location = new Point(15, 82), AutoSize = true };
                TextBox txtColor = new TextBox { Text = cond.TargetColorHex, Location = new Point(110, 79), Width = 110 };
                Button btnPalette = new Button { Text = "색상표", Location = new Point(225, 78), Size = new Size(65, 24) };
                btnPalette.Click += (s, ev) =>
                {
                    using (var cd = new ColorDialog())
                    {
                        cd.Color = cond.TargetColor;
                        if (cd.ShowDialog() == DialogResult.OK)
                        {
                            txtColor.Text = $"#{cd.Color.R:X2}{cd.Color.G:X2}{cd.Color.B:X2}";
                        }
                    }
                };

                Label lblTol = new Label { Text = "허용 오차(±):", Location = new Point(15, 116), AutoSize = true };
                NumericUpDown numTol = new NumericUpDown { Value = cond.Tolerance, Minimum = 0, Maximum = 255, Location = new Point(110, 113), Width = 85 };

                Label lblPivot = new Label { Text = "좌표 기준:", Location = new Point(15, 150), AutoSize = true };
                ComboBox cmbPivot = new ComboBox { DropDownStyle = ComboBoxStyle.DropDownList, Location = new Point(110, 147), Width = 180 };
                cmbPivot.Items.AddRange(new object[] { "창 상대좌표", "화면 절대좌표" });
                cmbPivot.SelectedIndex = (int)cond.Pivot;

                CheckBox chkMustMatch = new CheckBox { Text = "이 색상과 일치해야 함 (체크 해제 시: 불일치해야 함)", Checked = cond.MustMatch, Location = new Point(15, 185), Width = 300 };

                Button btnOk = new Button { Text = "확인", DialogResult = DialogResult.OK, Location = new Point(120, 225), Size = new Size(80, 30), BackColor = Color.FromArgb(13, 110, 253), ForeColor = Color.White, FlatStyle = FlatStyle.Flat };
                Button btnCancel = new Button { Text = "취소", DialogResult = DialogResult.Cancel, Location = new Point(210, 225), Size = new Size(80, 30) };

                dlg.Controls.AddRange(new Control[] { lblName, txtName, lblX, numX, numY, lblColor, txtColor, btnPalette, lblTol, numTol, lblPivot, cmbPivot, chkMustMatch, btnOk, btnCancel });
                dlg.AcceptButton = btnOk;
                dlg.CancelButton = btnCancel;

                if (dlg.ShowDialog(this) == DialogResult.OK)
                {
                    cond.Name = txtName.Text;
                    cond.X = (int)numX.Value;
                    cond.Y = (int)numY.Value;
                    cond.TargetColorHex = txtColor.Text;
                    cond.Tolerance = (int)numTol.Value;
                    cond.Pivot = (CoordinatePivot)cmbPivot.SelectedIndex;
                    cond.MustMatch = chkMustMatch.Checked;

                    UpdateColorConditionList();
                }
            }
        }

        private void BtnDeleteCondition_Click(object sender, EventArgs e)
        {
            if (lvColorConditions.SelectedItems.Count == 0 || !(lvColorConditions.SelectedItems[0].Tag is ColorCondition cond)) return;
            if (_selectedPreset == null) return;

            _selectedPreset.ColorConditions.Remove(cond);
            UpdateColorConditionList();
            UpdatePresetListItems();
        }

        private void BtnTestCondition_Click(object sender, EventArgs e)
        {
            if (_selectedPreset == null || _selectedPreset.ColorConditions.Count == 0)
            {
                MessageBox.Show("테스트할 감지 조건이 없습니다.", "안내", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }

            AppendLog($"🔍 [{_selectedPreset.ScenarioNumber}번: {_selectedPreset.Name}] 조건 즉시 판별 테스트 시작:", Color.FromArgb(13, 110, 253));

            int matchCount = 0;
            for (int i = 0; i < _selectedPreset.ColorConditions.Count; i++)
            {
                var cond = _selectedPreset.ColorConditions[i];
                Color actual = WindowHelper.GetPixelColor(_currentTargetHWnd, cond.X, cond.Y, cond.Pivot);
                bool match = false;

                if (cond.Shape == ColorPointShape.Point)
                {
                    match = WindowHelper.IsColorMatch(actual, cond.TargetColor, cond.Tolerance);
                }
                else
                {
                    match = WindowHelper.IsLineColorMatch(_currentTargetHWnd, cond.X, cond.Y, cond.EndX, cond.EndY, cond.SampleCount, cond.TargetColor, cond.Tolerance, cond.Pivot);
                }

                if (!cond.MustMatch) match = !match;
                if (match) matchCount++;

                string resultText = match ? "✓ 일치(성공)" : "❌ 불일치(실패)";
                Color resultColor = match ? Color.FromArgb(25, 135, 84) : Color.FromArgb(220, 53, 69);
                AppendLog($"  • [{cond.Name}] 목표:{cond.TargetColorHex} | 감지:#{actual.R:X2}{actual.G:X2}{actual.B:X2} (오차:±{cond.Tolerance}) ➔ {resultText}", resultColor);
            }

            bool finalSuccess = (_selectedPreset.MatchMode == ConditionMatchMode.AllPoints)
                ? (matchCount == _selectedPreset.ColorConditions.Count)
                : (matchCount > 0);

            if (finalSuccess)
            {
                AppendLog($"🎉 [최종 판정: 참(TRUE)] ➔ 다음 행동: {_selectedPreset.OnMatchBranch} (점프대상: #{_selectedPreset.OnMatchJumpNumber})", Color.FromArgb(25, 135, 84));
            }
            else
            {
                AppendLog($"⚠️ [최종 판정: 거짓(FALSE)] ➔ 다음 행동: {_selectedPreset.OnMismatchBranch} (점프대상: #{_selectedPreset.OnMismatchJumpNumber})", Color.FromArgb(220, 53, 69));
            }
        }

        // ==========================================
        // [Hand] 액션 시퀀스 관리
        // ==========================================
        private void UpdateActionList()
        {
            lvActions.BeginUpdate();
            lvActions.Items.Clear();

            if (_selectedPreset != null)
            {
                for (int i = 0; i < _selectedPreset.Actions.Count; i++)
                {
                    var act = _selectedPreset.Actions[i];
                    var lvi = new ListViewItem((i + 1).ToString());
                    lvi.SubItems.Add(act.ActionType.ToString());
                    lvi.SubItems.Add(act.Pivot == CoordinatePivot.WindowRelative ? "창 상대" : "화면 절대");

                    string coordStr = (act.ActionType == ActionType.MouseDrag)
                        ? $"({act.X},{act.Y})➔({act.EndX},{act.EndY})"
                        : $"({act.X}, {act.Y})";
                    lvi.SubItems.Add(coordStr);

                    lvi.SubItems.Add($"{act.DelayMs}ms");

                    string desc = act.Description;
                    if (act.ActionType == ActionType.JumpScenario) desc = $"➔ [{act.JumpTargetScenarioNumber}번 시나리오로 점프]";
                    else if (act.ActionType == ActionType.KeyPress) desc = $"키 입력: [{act.KeyCode}] {desc}";
                    else if (act.ActionType == ActionType.TextTyping) desc = $"타이핑: \"{act.TextToType}\" {desc}";

                    lvi.SubItems.Add(desc);
                    lvi.Tag = act;
                    lvActions.Items.Add(lvi);
                }
            }

            lvActions.EndUpdate();
        }

        private void AddPickerAction(bool isDragMode)
        {
            if (_selectedPreset == null)
            {
                MessageBox.Show("시나리오를 먼저 선택해 주세요.", "안내", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }

            CoordinatePivot pivot = _selectedPreset.DefaultPivot;
            if (pivot == CoordinatePivot.WindowRelative && _currentTargetHWnd == IntPtr.Zero)
            {
                MessageBox.Show("창 상대좌표를 사용하려면 대상 게임 창을 먼저 지정해 주세요.", "안내", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            this.WindowState = FormWindowState.Minimized;
            System.Threading.Thread.Sleep(200);

            using (var picker = new CoordinatePickerOverlayForm(_currentTargetHWnd, pivot, isDragMode))
            {
                if (picker.ShowDialog() == DialogResult.OK)
                {
                    var act = new PresetAction
                    {
                        ActionType = isDragMode ? ActionType.MouseDrag : ActionType.LeftClick,
                        Pivot = pivot,
                        X = picker.SelectedPoint.X,
                        Y = picker.SelectedPoint.Y,
                        EndX = picker.SelectedEndPoint.X,
                        EndY = picker.SelectedEndPoint.Y,
                        DragDurationMs = 300,
                        DelayMs = 200,
                        Description = isDragMode ? "화면 드래그" : "좌클릭"
                    };

                    _selectedPreset.Actions.Add(act);
                    UpdateActionList();
                    UpdatePresetListItems();
                }
            }

            this.WindowState = FormWindowState.Normal;
            this.BringToFront();
        }

        private void BtnAddCustomAction_Click(object sender, EventArgs e)
        {
            if (_selectedPreset == null) return;
            ShowActionEditDialog(new PresetAction { Pivot = _selectedPreset.DefaultPivot }, isNew: true);
        }

        private void BtnEditAction_Click(object sender, EventArgs e)
        {
            if (lvActions.SelectedItems.Count == 0 || !(lvActions.SelectedItems[0].Tag is PresetAction act))
            {
                MessageBox.Show("수정할 액션을 선택해 주세요.", "안내", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }
            ShowActionEditDialog(act, isNew: false);
        }

        private void ShowActionEditDialog(PresetAction act, bool isNew)
        {
            using (var dlg = new Form())
            {
                dlg.Text = isNew ? "새 조작 액션 추가" : "조작 액션 수정";
                dlg.Size = new Size(360, 360);
                dlg.StartPosition = FormStartPosition.CenterParent;
                dlg.FormBorderStyle = FormBorderStyle.FixedDialog;
                dlg.MaximizeBox = false;
                dlg.MinimizeBox = false;

                Label lblType = new Label { Text = "조작 방식:", Location = new Point(15, 15), AutoSize = true };
                ComboBox cmbType = new ComboBox { DropDownStyle = ComboBoxStyle.DropDownList, Location = new Point(110, 12), Width = 210 };
                cmbType.Items.AddRange(new object[] { "LeftClick (좌클릭)", "DoubleClick (더블클릭)", "RightClick (우클릭)", "MouseDrag (드래그)", "KeyPress (키 입력)", "TextTyping (텍스트)", "Delay (대기)", "JumpScenario (시나리오 점프)" });
                cmbType.SelectedIndex = (int)act.ActionType;

                Label lblCoord = new Label { Text = "좌표 (X, Y):", Location = new Point(15, 50), AutoSize = true };
                NumericUpDown numX = new NumericUpDown { Value = act.X, Minimum = -5000, Maximum = 10000, Location = new Point(110, 48), Width = 100 };
                NumericUpDown numY = new NumericUpDown { Value = act.Y, Minimum = -5000, Maximum = 10000, Location = new Point(220, 48), Width = 100 };

                Label lblEndCoord = new Label { Text = "드래그 끝점:", Location = new Point(15, 85), AutoSize = true };
                NumericUpDown numEndX = new NumericUpDown { Value = act.EndX, Minimum = -5000, Maximum = 10000, Location = new Point(110, 82), Width = 100 };
                NumericUpDown numEndY = new NumericUpDown { Value = act.EndY, Minimum = -5000, Maximum = 10000, Location = new Point(220, 82), Width = 100 };

                Label lblKey = new Label { Text = "키보드 키:", Location = new Point(15, 120), AutoSize = true };
                ComboBox cmbKey = new ComboBox { DropDownStyle = ComboBoxStyle.DropDownList, Location = new Point(110, 117), Width = 210 };
                cmbKey.Items.Add(Keys.None);
                foreach (Keys k in Enum.GetValues(typeof(Keys)))
                {
                    if (!cmbKey.Items.Contains(k)) cmbKey.Items.Add(k);
                }
                cmbKey.SelectedItem = act.KeyCode;

                Label lblText = new Label { Text = "타이핑 문구:", Location = new Point(15, 155), AutoSize = true };
                TextBox txtText = new TextBox { Text = act.TextToType, Location = new Point(110, 152), Width = 210 };

                Label lblJump = new Label { Text = "점프 대상 No:", Location = new Point(15, 190), AutoSize = true };
                NumericUpDown numJump = new NumericUpDown { Value = Math.Max(1, act.JumpTargetScenarioNumber), Minimum = 1, Maximum = 9999, Location = new Point(110, 187), Width = 100 };

                Label lblDelay = new Label { Text = "실행 후 대기:", Location = new Point(15, 225), AutoSize = true };
                NumericUpDown numDelay = new NumericUpDown { Value = act.DelayMs, Minimum = 0, Maximum = 60000, Location = new Point(110, 222), Width = 100 };
                Label lblDelayMs = new Label { Text = "ms", Location = new Point(215, 225), AutoSize = true };

                Label lblDesc = new Label { Text = "동작 설명:", Location = new Point(15, 260), AutoSize = true };
                TextBox txtDesc = new TextBox { Text = act.Description, Location = new Point(110, 257), Width = 210 };

                Button btnOk = new Button { Text = "확인", DialogResult = DialogResult.OK, Location = new Point(140, 290), Size = new Size(85, 30), BackColor = Color.FromArgb(13, 110, 253), ForeColor = Color.White, FlatStyle = FlatStyle.Flat };
                Button btnCancel = new Button { Text = "취소", DialogResult = DialogResult.Cancel, Location = new Point(235, 290), Size = new Size(85, 30) };

                dlg.Controls.AddRange(new Control[] {
                    lblType, cmbType, lblCoord, numX, numY, lblEndCoord, numEndX, numEndY,
                    lblKey, cmbKey, lblText, txtText, lblJump, numJump, lblDelay, numDelay, lblDelayMs,
                    lblDesc, txtDesc, btnOk, btnCancel
                });
                dlg.AcceptButton = btnOk;
                dlg.CancelButton = btnCancel;

                if (dlg.ShowDialog(this) == DialogResult.OK)
                {
                    act.ActionType = (ActionType)cmbType.SelectedIndex;
                    act.X = (int)numX.Value;
                    act.Y = (int)numY.Value;
                    act.EndX = (int)numEndX.Value;
                    act.EndY = (int)numEndY.Value;
                    act.KeyCode = (Keys)(cmbKey.SelectedItem ?? Keys.None);
                    act.TextToType = txtText.Text;
                    act.JumpTargetScenarioNumber = (int)numJump.Value;
                    act.DelayMs = (int)numDelay.Value;
                    act.Description = txtDesc.Text;

                    if (isNew)
                    {
                        _selectedPreset.Actions.Add(act);
                    }

                    UpdateActionList();
                    UpdatePresetListItems();
                }
            }
        }

        private void BtnDeleteAction_Click(object sender, EventArgs e)
        {
            if (lvActions.SelectedItems.Count == 0 || !(lvActions.SelectedItems[0].Tag is PresetAction act)) return;
            if (_selectedPreset == null) return;

            _selectedPreset.Actions.Remove(act);
            UpdateActionList();
            UpdatePresetListItems();
        }

        private void BtnMoveUpAction_Click(object sender, EventArgs e)
        {
            if (lvActions.SelectedItems.Count == 0 || !(lvActions.SelectedItems[0].Tag is PresetAction act)) return;
            int idx = _selectedPreset.Actions.IndexOf(act);
            if (idx > 0)
            {
                _selectedPreset.Actions.RemoveAt(idx);
                _selectedPreset.Actions.Insert(idx - 1, act);
                UpdateActionList();
                lvActions.Items[idx - 1].Selected = true;
            }
        }

        private void BtnMoveDownAction_Click(object sender, EventArgs e)
        {
            if (lvActions.SelectedItems.Count == 0 || !(lvActions.SelectedItems[0].Tag is PresetAction act)) return;
            int idx = _selectedPreset.Actions.IndexOf(act);
            if (idx >= 0 && idx < _selectedPreset.Actions.Count - 1)
            {
                _selectedPreset.Actions.RemoveAt(idx);
                _selectedPreset.Actions.Insert(idx + 1, act);
                UpdateActionList();
                lvActions.Items[idx + 1].Selected = true;
            }
        }

        private void BtnTestAction_Click(object sender, EventArgs e)
        {
            if (lvActions.SelectedItems.Count == 0 || !(lvActions.SelectedItems[0].Tag is PresetAction act))
            {
                MessageBox.Show("테스트할 액션을 선택해 주세요.", "안내", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }

            AppendLog($"▶ 액션 1회 테스트 실행: {act}", Color.FromArgb(111, 66, 193));

            System.Threading.Tasks.Task.Run(() =>
            {
                switch (act.ActionType)
                {
                    case ActionType.LeftClick:
                    case ActionType.DoubleClick:
                    case ActionType.RightClick:
                        InputSimulator.Click(_currentTargetHWnd, act.X, act.Y, act.Pivot, act.ActionType);
                        break;
                    case ActionType.MouseDrag:
                        InputSimulator.Drag(_currentTargetHWnd, act.X, act.Y, act.EndX, act.EndY, act.DragDurationMs, act.Pivot, System.Threading.CancellationToken.None);
                        break;
                    case ActionType.KeyPress:
                        InputSimulator.KeyPress(act.KeyCode);
                        break;
                    case ActionType.TextTyping:
                        InputSimulator.TypeText(act.TextToType, System.Threading.CancellationToken.None);
                        break;
                }
            });
        }

        // ==========================================
        // 엔진 제어 및 실시간 모니터링
        // ==========================================
        private void StartMacro()
        {
            if (_engine.IsRunning) return;

            if (_profile == null || _profile.Presets.Count == 0)
            {
                MessageBox.Show("등록된 시나리오가 없습니다.", "안내", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            int startNo = _selectedPreset != null ? _selectedPreset.ScenarioNumber : 1;
            _engine.Start(_profile, _currentTargetHWnd, startNo);
        }

        private void StopMacro()
        {
            _engine.Stop();
        }

        private void Engine_StatusChanged(bool isRunning)
        {
            if (this.InvokeRequired)
            {
                this.BeginInvoke(new Action(() => Engine_StatusChanged(isRunning)));
                return;
            }

            if (isRunning)
            {
                lblEngineStatus.Text = $"▶ 오토 실행 중... [시나리오 #{_engine.CurrentScenarioNumber}]";
                lblEngineStatus.ForeColor = Color.FromArgb(25, 135, 84);
                btnStartEngine.Enabled = false;
                btnStopEngine.Enabled = true;
            }
            else
            {
                lblEngineStatus.Text = "⏹ 오토 정지 상태 (대기 중)";
                lblEngineStatus.ForeColor = Color.FromArgb(217, 119, 6);
                btnStartEngine.Enabled = true;
                btnStopEngine.Enabled = true;
            }
        }

        private void Engine_ActiveScenarioChanged(int scenarioNumber)
        {
            if (this.InvokeRequired)
            {
                this.BeginInvoke(new Action(() => Engine_ActiveScenarioChanged(scenarioNumber)));
                return;
            }

            if (_engine.IsRunning)
            {
                lblEngineStatus.Text = $"▶ 오토 실행 중... [시나리오 #{scenarioNumber}]";
            }
        }

        private void Engine_LogMessage(string message, Color color)
        {
            if (this.InvokeRequired)
            {
                this.BeginInvoke(new Action(() => Engine_LogMessage(message, color)));
                return;
            }
            AppendLog(message, color);
        }

        private void Engine_PointEvaluated(ColorCondition cond, Color actual, bool isMatch)
        {
            // 실시간 리스트뷰 업데이트
            if (this.InvokeRequired)
            {
                this.BeginInvoke(new Action(() => Engine_PointEvaluated(cond, actual, isMatch)));
                return;
            }

            foreach (ListViewItem item in lvColorConditions.Items)
            {
                if (item.Tag == cond)
                {
                    item.SubItems[6].Text = $"#{actual.R:X2}{actual.G:X2}{actual.B:X2}";
                    item.SubItems[7].Text = isMatch ? "✓ 일치" : "❌ 불일치";
                    item.SubItems[7].ForeColor = isMatch ? Color.Green : Color.Red;
                    break;
                }
            }
        }

        private void RealtimeMonitorTimer_Tick(object sender, EventArgs e)
        {
            if (_selectedPreset == null || _engine.IsRunning) return;

            // 매크로 정지 상태에서도 편집창 리스트뷰에 현재 감지되는 색상을 실시간 표시
            foreach (ListViewItem item in lvColorConditions.Items)
            {
                if (item.Tag is ColorCondition cond)
                {
                    Color actual = WindowHelper.GetPixelColor(_currentTargetHWnd, cond.X, cond.Y, cond.Pivot);
                    bool match = false;
                    if (cond.Shape == ColorPointShape.Point)
                    {
                        match = WindowHelper.IsColorMatch(actual, cond.TargetColor, cond.Tolerance);
                    }
                    else
                    {
                        match = WindowHelper.IsLineColorMatch(_currentTargetHWnd, cond.X, cond.Y, cond.EndX, cond.EndY, cond.SampleCount, cond.TargetColor, cond.Tolerance, cond.Pivot);
                    }

                    if (!cond.MustMatch) match = !match;

                    item.SubItems[6].Text = $"#{actual.R:X2}{actual.G:X2}{actual.B:X2}";
                    item.SubItems[7].Text = match ? "✓ 일치" : "❌ 불일치";
                    item.SubItems[7].ForeColor = match ? Color.Green : Color.Red;
                }
            }
        }

        private void AppendLog(string message, Color color)
        {
            if (rtbLog.IsDisposed) return;

            string time = DateTime.Now.ToString("HH:mm:ss");
            rtbLog.SelectionStart = rtbLog.TextLength;
            rtbLog.SelectionLength = 0;
            rtbLog.SelectionColor = Color.FromArgb(108, 117, 125);
            rtbLog.AppendText($"[{time}] ");

            rtbLog.SelectionStart = rtbLog.TextLength;
            rtbLog.SelectionLength = 0;
            rtbLog.SelectionColor = color;
            rtbLog.AppendText(message + "\n");
            rtbLog.ScrollToCaret();

            // 1000줄 넘으면 자동 정리
            if (rtbLog.Lines.Length > 1000)
            {
                rtbLog.Text = rtbLog.Text.Substring(rtbLog.Text.Length / 2);
            }
        }
    }

    /// <summary>
    /// .NET 10 WinForms SplitContainer.RepaintSplitterRect의 알려진 GDI+ 버그(dotnet/winforms PR #14565)를
    /// 안전하게 방어하는 SplitContainer 래퍼
    /// </summary>
    public class SafeSplitContainer : SplitContainer
    {
        public SafeSplitContainer()
        {
            this.DoubleBuffered = true;
        }

        protected override void OnLayout(LayoutEventArgs e)
        {
            try
            {
                base.OnLayout(e);
            }
            catch (System.Runtime.InteropServices.ExternalException)
            {
                // .NET 10 GDI+ 버그 무시
            }
            catch (Exception ex) when (ex.Message.Contains("GDI+"))
            {
                // .NET 10 GDI+ 버그 무시
            }
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            try
            {
                base.OnPaint(e);
            }
            catch (Exception)
            {
            }
        }
    }
}
