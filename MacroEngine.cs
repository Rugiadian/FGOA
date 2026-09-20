using System;
using System.Collections.Generic;
using System.Drawing;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace RD_GameAuto_FGOA
{
    public class MacroEngine
    {
        private Task _workerTask;
        private CancellationTokenSource _cts;

        public bool IsRunning { get; private set; } = false;
        public IntPtr TargetHWnd { get; set; } = IntPtr.Zero;
        public MacroProfile Profile { get; set; }

        public int CurrentScenarioNumber { get; set; } = 1;

        public event Action<bool> StatusChanged;
        public event Action<string, Color> LogMessage;
        public event Action<int> ActiveScenarioChanged;
        public event Action<ColorCondition, Color, bool> PointEvaluated;

        public void Start(MacroProfile profile, IntPtr hWnd, int startScenarioNumber = 0)
        {
            if (IsRunning) return;

            Profile = profile;
            TargetHWnd = hWnd;

            if (startScenarioNumber > 0)
            {
                CurrentScenarioNumber = startScenarioNumber;
            }
            else
            {
                var first = Profile?.Presets?.FirstOrDefault(p => p.IsEnabled);
                CurrentScenarioNumber = first?.ScenarioNumber ?? 1;
            }

            _cts = new CancellationTokenSource();
            IsRunning = true;
            StatusChanged?.Invoke(true);

            LogMessage?.Invoke("🚀 [FGOA 엔진 가동] 화면 색상 감지 및 시나리오 분기 평가를 시작합니다.", Color.FromArgb(25, 135, 84));

            _workerTask = Task.Run(() => WorkerLoop(_cts.Token), _cts.Token);
        }

        public void Stop()
        {
            if (!IsRunning) return;

            _cts?.Cancel();
            IsRunning = false;
            StatusChanged?.Invoke(false);

            LogMessage?.Invoke("⏹ [FGOA 엔진 정지] 오토 감시 및 실행이 정지되었습니다.", Color.FromArgb(220, 53, 69));
        }

        private async Task WorkerLoop(CancellationToken ct)
        {
            while (!ct.IsCancellationRequested)
            {
                try
                {
                    if (Profile == null || Profile.Presets == null || Profile.Presets.Count == 0)
                    {
                        await Task.Delay(200, ct);
                        continue;
                    }

                    // 현재 활성 시나리오 탐색
                    ScenarioPreset activePreset = Profile.Presets.FirstOrDefault(p => p.ScenarioNumber == CurrentScenarioNumber && p.IsEnabled);

                    if (activePreset == null)
                    {
                        // 지정된 번호가 비활성화이거나 없으면 첫 번째 활성 시나리오로 이동
                        activePreset = Profile.Presets.FirstOrDefault(p => p.IsEnabled);
                        if (activePreset != null)
                        {
                            CurrentScenarioNumber = activePreset.ScenarioNumber;
                        }
                    }

                    if (activePreset == null)
                    {
                        // 활성화된 시나리오가 하나도 없음
                        await Task.Delay(300, ct);
                        continue;
                    }

                    ActiveScenarioChanged?.Invoke(activePreset.ScenarioNumber);

                    // 쿨다운 체크
                    if ((DateTime.Now - activePreset.LastExecutedTime).TotalMilliseconds < activePreset.CooldownMs)
                    {
                        await Task.Delay(50, ct);
                        continue;
                    }

                    // 1. [Eye & Brain] 화면 조건 판별
                    bool isConditionMet = EvaluateConditions(activePreset, ct);

                    // 2. [Brain] 분기 처리
                    if (isConditionMet)
                    {
                        // 조건 일치 (TRUE) 분기
                        await HandleBranch(activePreset, activePreset.OnMatchBranch, activePreset.OnMatchJumpNumber, true, ct);
                    }
                    else
                    {
                        // 조건 불일치 (FALSE) 분기
                        await HandleBranch(activePreset, activePreset.OnMismatchBranch, activePreset.OnMismatchJumpNumber, false, ct);
                    }

                    int interval = Math.Max(20, Profile.CheckIntervalMs);
                    await Task.Delay(interval, ct);
                }
                catch (OperationCanceledException)
                {
                    break;
                }
                catch (Exception ex)
                {
                    LogMessage?.Invoke($"⚠️ 엔진 실행 중 예외: {ex.Message}", Color.Red);
                    await Task.Delay(200, ct);
                }
            }
        }

        private bool EvaluateConditions(ScenarioPreset preset, CancellationToken ct)
        {
            if (preset.ColorConditions == null || preset.ColorConditions.Count == 0)
            {
                // 감지 포인트가 없으면 기본적으로 참으로 간주
                return true;
            }

            int matchCount = 0;

            foreach (var cond in preset.ColorConditions)
            {
                if (ct.IsCancellationRequested) return false;

                bool match = false;
                Color actualColor = Color.Black;

                if (cond.Shape == ColorPointShape.Point)
                {
                    actualColor = WindowHelper.GetPixelColor(TargetHWnd, cond.X, cond.Y, cond.Pivot);
                    bool rawMatch = WindowHelper.IsColorMatch(actualColor, cond.TargetColor, cond.Tolerance);
                    match = cond.MustMatch ? rawMatch : !rawMatch;
                }
                else if (cond.Shape == ColorPointShape.Line)
                {
                    match = WindowHelper.IsLineColorMatch(
                        TargetHWnd, cond.X, cond.Y, cond.EndX, cond.EndY,
                        cond.SampleCount, cond.TargetColor, cond.Tolerance, cond.Pivot);
                    if (!cond.MustMatch) match = !match;

                    // 시작점 색상을 대표값으로 추출
                    actualColor = WindowHelper.GetPixelColor(TargetHWnd, cond.X, cond.Y, cond.Pivot);
                }

                PointEvaluated?.Invoke(cond, actualColor, match);

                if (match) matchCount++;
            }

            if (preset.MatchMode == ConditionMatchMode.AllPoints)
            {
                return matchCount == preset.ColorConditions.Count;
            }
            else
            {
                return matchCount > 0;
            }
        }

        private async Task HandleBranch(ScenarioPreset preset, BranchAction branch, int jumpNumber, bool isMatched, CancellationToken ct)
        {
            string condText = isMatched ? "조건 일치(TRUE)" : "조건 불일치(FALSE)";

            switch (branch)
            {
                case BranchAction.ExecuteActions:
                    LogMessage?.Invoke($"🎯 [{preset.ScenarioNumber}번: {preset.Name}] {condText} ➔ [액션 시퀀스 실행]", Color.FromArgb(13, 110, 253));
                    await ExecuteActionSequence(preset, ct);
                    preset.LastExecutedTime = DateTime.Now;
                    break;

                case BranchAction.JumpToScenario:
                    LogMessage?.Invoke($"🔀 [{preset.ScenarioNumber}번: {preset.Name}] {condText} ➔ [{jumpNumber}번 시나리오로 점프]", Color.FromArgb(217, 119, 6));
                    CurrentScenarioNumber = jumpNumber;
                    ActiveScenarioChanged?.Invoke(jumpNumber);
                    break;

                case BranchAction.StopMacro:
                    LogMessage?.Invoke($"🛑 [{preset.ScenarioNumber}번: {preset.Name}] {condText} ➔ [매크로 즉시 정지]", Color.FromArgb(220, 53, 69));
                    Stop();
                    break;

                case BranchAction.PauseWait:
                    LogMessage?.Invoke($"⏳ [{preset.ScenarioNumber}번: {preset.Name}] {condText} ➔ [1초 대기]", Color.Gray);
                    await Task.Delay(1000, ct);
                    break;

                case BranchAction.DoNothing:
                default:
                    // 조건 불일치 시 아무 동작 안 함 ➔ 다음 활성 시나리오 순차 검사
                    if (!isMatched)
                    {
                        MoveToNextEnabledScenario(preset);
                    }
                    break;
            }
        }

        private void MoveToNextEnabledScenario(ScenarioPreset current)
        {
            var enabledList = Profile?.Presets?.Where(p => p.IsEnabled).ToList();
            if (enabledList == null || enabledList.Count <= 1) return;

            int curIdx = enabledList.FindIndex(p => p.ScenarioNumber == current.ScenarioNumber);
            int nextIdx = (curIdx + 1) % enabledList.Count;
            CurrentScenarioNumber = enabledList[nextIdx].ScenarioNumber;
            ActiveScenarioChanged?.Invoke(CurrentScenarioNumber);
        }

        private async Task ExecuteActionSequence(ScenarioPreset preset, CancellationToken ct)
        {
            if (preset.Actions == null || preset.Actions.Count == 0) return;

            for (int i = 0; i < preset.Actions.Count; i++)
            {
                if (ct.IsCancellationRequested) break;

                var act = preset.Actions[i];
                LogMessage?.Invoke($"  ↳ [{i + 1}/{preset.Actions.Count}] {act}", Color.FromArgb(73, 80, 87));

                switch (act.ActionType)
                {
                    case ActionType.LeftClick:
                    case ActionType.DoubleClick:
                    case ActionType.RightClick:
                        InputSimulator.Click(TargetHWnd, act.X, act.Y, act.Pivot, act.ActionType);
                        break;

                    case ActionType.MouseDrag:
                        InputSimulator.Drag(TargetHWnd, act.X, act.Y, act.EndX, act.EndY, act.DragDurationMs, act.Pivot, ct);
                        break;

                    case ActionType.KeyPress:
                        InputSimulator.KeyPress(act.KeyCode);
                        break;

                    case ActionType.TextTyping:
                        InputSimulator.TypeText(act.TextToType, ct);
                        break;

                    case ActionType.JumpScenario:
                        CurrentScenarioNumber = act.JumpTargetScenarioNumber;
                        ActiveScenarioChanged?.Invoke(CurrentScenarioNumber);
                        LogMessage?.Invoke($"  ↳ 🔀 액션에 의해 [{CurrentScenarioNumber}번 시나리오로 점프]", Color.FromArgb(217, 119, 6));
                        return; // 점프 시 현재 시퀀스 종료
                }

                if (act.DelayMs > 0)
                {
                    await Task.Delay(act.DelayMs, ct);
                }
            }
        }
    }
}
