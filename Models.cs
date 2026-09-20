using System;
using System.Collections.Generic;
using System.Drawing;
using System.Text.Json.Serialization;
using System.Windows.Forms;

namespace RD_GameAuto_FGOA
{
    public enum CoordinatePivot
    {
        WindowRelative,  // 특정 게임 창의 클라이언트 왼쪽 위 (0, 0) 기준 상대좌표
        ScreenAbsolute   // 모니터 전체 화면의 왼쪽 위 (0, 0) 기준 절대좌표
    }

    public enum ColorPointShape
    {
        Point,  // 단일 점 (X, Y)
        Line    // 선 형태 (X1, Y1) ~ (X2, Y2) 다중 픽셀 샘플링
    }

    public enum ConditionMatchMode
    {
        AllPoints,  // 모든 포인트가 일치해야 함 (AND)
        AnyPoint    // 하나라도 일치하면 됨 (OR)
    }

    public enum BranchAction
    {
        ExecuteActions,     // 액션 시퀀스 실행
        JumpToScenario,     // 다른 시나리오 번호로 즉시 점프
        StopMacro,          // 매크로 즉시 정지
        PauseWait,          // 일시 대기
        DoNothing           // 아무 동작 안 함 (다음 시나리오로 패스)
    }

    public enum ActionType
    {
        LeftClick,      // 마우스 좌클릭
        DoubleClick,    // 마우스 더블클릭
        RightClick,     // 마우스 우클릭
        MouseDrag,      // 마우스 드래그 (시작 좌표 -> 끝 좌표)
        KeyPress,       // 키보드 단일 키 입력
        TextTyping,     // 키보드 문자열 타이핑
        Delay,          // 단순 지연 (ms 대기)
        JumpScenario    // 다른 시나리오로 점프
    }

    public class ColorCondition
    {
        public string Id { get; set; } = Guid.NewGuid().ToString();
        public string Name { get; set; } = "포인트";
        public ColorPointShape Shape { get; set; } = ColorPointShape.Point;
        public CoordinatePivot Pivot { get; set; } = CoordinatePivot.WindowRelative;

        public int X { get; set; }
        public int Y { get; set; }

        // 선(Line) 형태일 때 사용
        public int EndX { get; set; }
        public int EndY { get; set; }
        public int SampleCount { get; set; } = 5;

        public string TargetColorHex { get; set; } = "#FFFFFF";
        public int Tolerance { get; set; } = 15;
        public bool MustMatch { get; set; } = true; // true: 색상이 일치해야 함, false: 색상이 달라야 함

        [JsonIgnore]
        public Color TargetColor
        {
            get
            {
                try { return ColorTranslator.FromHtml(TargetColorHex); }
                catch { return Color.White; }
            }
            set
            {
                TargetColorHex = $"#{value.R:X2}{value.G:X2}{value.B:X2}";
            }
        }

        public ColorCondition Clone()
        {
            return new ColorCondition
            {
                Id = Guid.NewGuid().ToString(),
                Name = this.Name,
                Shape = this.Shape,
                Pivot = this.Pivot,
                X = this.X,
                Y = this.Y,
                EndX = this.EndX,
                EndY = this.EndY,
                SampleCount = this.SampleCount,
                TargetColorHex = this.TargetColorHex,
                Tolerance = this.Tolerance,
                MustMatch = this.MustMatch
            };
        }
    }

    public class PresetAction
    {
        public string Id { get; set; } = Guid.NewGuid().ToString();
        public ActionType ActionType { get; set; } = ActionType.LeftClick;
        public CoordinatePivot Pivot { get; set; } = CoordinatePivot.WindowRelative;

        public int X { get; set; }
        public int Y { get; set; }

        // 드래그 시 끝 좌표 및 소요 시간
        public int EndX { get; set; }
        public int EndY { get; set; }
        public int DragDurationMs { get; set; } = 300;

        // 키보드 키 또는 텍스트 입력
        public Keys KeyCode { get; set; } = Keys.None;
        public string TextToType { get; set; } = "";

        // 점프 대상 시나리오 번호 (JumpScenario 일 때)
        public int JumpTargetScenarioNumber { get; set; } = 1;

        public int DelayMs { get; set; } = 200;
        public string Description { get; set; } = "";

        public PresetAction Clone()
        {
            return new PresetAction
            {
                Id = Guid.NewGuid().ToString(),
                ActionType = this.ActionType,
                Pivot = this.Pivot,
                X = this.X,
                Y = this.Y,
                EndX = this.EndX,
                EndY = this.EndY,
                DragDurationMs = this.DragDurationMs,
                KeyCode = this.KeyCode,
                TextToType = this.TextToType,
                JumpTargetScenarioNumber = this.JumpTargetScenarioNumber,
                DelayMs = this.DelayMs,
                Description = this.Description
            };
        }

        public override string ToString()
        {
            string pivotStr = Pivot == CoordinatePivot.WindowRelative ? "창상대" : "화면절대";
            switch (ActionType)
            {
                case ActionType.LeftClick:
                    return $"좌클릭 ({X}, {Y}) [{pivotStr}] [대기 {DelayMs}ms]";
                case ActionType.DoubleClick:
                    return $"더블클릭 ({X}, {Y}) [{pivotStr}] [대기 {DelayMs}ms]";
                case ActionType.RightClick:
                    return $"우클릭 ({X}, {Y}) [{pivotStr}] [대기 {DelayMs}ms]";
                case ActionType.MouseDrag:
                    return $"드래그 ({X},{Y} ➔ {EndX},{EndY}) [{DragDurationMs}ms] [대기 {DelayMs}ms]";
                case ActionType.KeyPress:
                    return $"키 입력 [{KeyCode}] [대기 {DelayMs}ms]";
                case ActionType.TextTyping:
                    return $"텍스트 타이핑 \"{TextToType}\" [대기 {DelayMs}ms]";
                case ActionType.Delay:
                    return $"⏳ 대기: {DelayMs}ms";
                case ActionType.JumpScenario:
                    return $"➔ [{JumpTargetScenarioNumber}번 시나리오로 점프]";
                default:
                    return $"{ActionType} ({X}, {Y})";
            }
        }
    }

    public class ScenarioPreset
    {
        public string Id { get; set; } = Guid.NewGuid().ToString();
        public int ScenarioNumber { get; set; } = 1; // 1, 2, 3, 5 등 고유 번호
        public string Name { get; set; } = "시나리오";
        public bool IsEnabled { get; set; } = true;
        public CoordinatePivot DefaultPivot { get; set; } = CoordinatePivot.WindowRelative;

        // [Eye & Brain] 조건 판별 설정
        public ConditionMatchMode MatchMode { get; set; } = ConditionMatchMode.AllPoints;
        public List<ColorCondition> ColorConditions { get; set; } = new List<ColorCondition>();

        // [Brain 분기 처리]
        // 1. 조건이 일치(TRUE)할 때
        public BranchAction OnMatchBranch { get; set; } = BranchAction.ExecuteActions;
        public int OnMatchJumpNumber { get; set; } = 1;

        // 2. 조건이 불일치(FALSE)할 때
        public BranchAction OnMismatchBranch { get; set; } = BranchAction.DoNothing;
        public int OnMismatchJumpNumber { get; set; } = 1;

        // [Hand 액션 실행 목록]
        public List<PresetAction> Actions { get; set; } = new List<PresetAction>();
        public int CooldownMs { get; set; } = 500;

        [JsonIgnore]
        public DateTime LastExecutedTime { get; set; } = DateTime.MinValue;

        public ScenarioPreset Clone()
        {
            var clone = new ScenarioPreset
            {
                Id = Guid.NewGuid().ToString(),
                ScenarioNumber = this.ScenarioNumber,
                Name = this.Name + " (복사본)",
                IsEnabled = this.IsEnabled,
                DefaultPivot = this.DefaultPivot,
                MatchMode = this.MatchMode,
                OnMatchBranch = this.OnMatchBranch,
                OnMatchJumpNumber = this.OnMatchJumpNumber,
                OnMismatchBranch = this.OnMismatchBranch,
                OnMismatchJumpNumber = this.OnMismatchJumpNumber,
                CooldownMs = this.CooldownMs,
                ColorConditions = new List<ColorCondition>(),
                Actions = new List<PresetAction>()
            };

            foreach (var cond in this.ColorConditions)
            {
                clone.ColorConditions.Add(cond.Clone());
            }

            foreach (var act in this.Actions)
            {
                clone.Actions.Add(act.Clone());
            }

            return clone;
        }
    }

    public class WindowLayoutSettings
    {
        public int WindowWidth { get; set; } = 1166;
        public int WindowHeight { get; set; } = 973;
        public bool IsMaximized { get; set; } = false;
        public int MainSplitterDistance { get; set; } = 422;
        public int DetailSplitterDistance { get; set; } = 467;
        public int[] PresetColumnWidths { get; set; } = new int[] { 45, 160, 95, 65 };
        public int[] ConditionColumnWidths { get; set; } = new int[] { 130, 75, 100, 90, 60, 90, 70 };
        public int[] ActionColumnWidths { get; set; } = new int[] { 40, 85, 130, 80, 200 };
    }

    public class MacroProfile
    {
        public string TargetProcessName { get; set; } = "";
        public string TargetWindowTitle { get; set; } = "";
        public int CheckIntervalMs { get; set; } = 100;
        public bool AlwaysOnTop { get; set; } = true;
        public bool HotkeysDisabled { get; set; } = false;
        public CoordinatePivot DefaultPivot { get; set; } = CoordinatePivot.WindowRelative;
        public List<ScenarioPreset> Presets { get; set; } = new List<ScenarioPreset>();
        public WindowLayoutSettings WindowLayout { get; set; } = new WindowLayoutSettings();
    }
}
