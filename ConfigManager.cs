using System;
using System.IO;
using System.Text.Json;

namespace RD_GameAuto_FGOA
{
    public static class ConfigManager
    {
        private static readonly string DefaultConfigPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "fgoa_auto_macro_config.json");
        private static readonly JsonSerializerOptions JsonOptions = new JsonSerializerOptions
        {
            WriteIndented = true,
            PropertyNameCaseInsensitive = true
        };

        public static MacroProfile LoadDefault()
        {
            if (File.Exists(DefaultConfigPath))
            {
                try
                {
                    string json = File.ReadAllText(DefaultConfigPath);
                    var profile = JsonSerializer.Deserialize<MacroProfile>(json, JsonOptions);
                    if (profile != null)
                    {
                        if (profile.WindowLayout == null) profile.WindowLayout = new WindowLayoutSettings();
                        return profile;
                    }
                }
                catch { }
            }

            return CreateDefaultProfile();
        }

        public static void SaveDefault(MacroProfile profile)
        {
            try
            {
                string json = JsonSerializer.Serialize(profile, JsonOptions);
                File.WriteAllText(DefaultConfigPath, json);
            }
            catch { }
        }

        public static MacroProfile LoadFromFile(string filePath)
        {
            string json = File.ReadAllText(filePath);
            var profile = JsonSerializer.Deserialize<MacroProfile>(json, JsonOptions);
            if (profile != null && profile.WindowLayout == null)
            {
                profile.WindowLayout = new WindowLayoutSettings();
            }
            return profile;
        }

        public static void SaveToFile(string filePath, MacroProfile profile)
        {
            string json = JsonSerializer.Serialize(profile, JsonOptions);
            File.WriteAllText(filePath, json);
        }

        public static MacroProfile CreateDefaultProfile()
        {
            var profile = new MacroProfile
            {
                CheckIntervalMs = 100,
                AlwaysOnTop = true,
                DefaultPivot = CoordinatePivot.WindowRelative,
                WindowLayout = new WindowLayoutSettings
                {
                    WindowWidth = 1166,
                    WindowHeight = 973,
                    MainSplitterDistance = 422,
                    DetailSplitterDistance = 467
                }
            };

            // 💡 [시나리오 1]: 검은색 감지 시 좌클릭 1번 ➔ 3초 대기, 불일치 시 5번 시나리오로 점프
            var scenario1 = new ScenarioPreset
            {
                ScenarioNumber = 1,
                Name = "시나리오 1 (전투 진입 감지)",
                IsEnabled = true,
                DefaultPivot = CoordinatePivot.WindowRelative,
                MatchMode = ConditionMatchMode.AllPoints,
                OnMatchBranch = BranchAction.ExecuteActions,
                OnMismatchBranch = BranchAction.JumpToScenario,
                OnMismatchJumpNumber = 5,
                CooldownMs = 500
            };

            scenario1.ColorConditions.Add(new ColorCondition
            {
                Name = "A 포인트 (화면 로딩 검은색)",
                Shape = ColorPointShape.Point,
                Pivot = CoordinatePivot.WindowRelative,
                X = 500,
                Y = 600,
                TargetColorHex = "#000000",
                Tolerance = 15,
                MustMatch = true
            });

            scenario1.Actions.Add(new PresetAction
            {
                ActionType = ActionType.LeftClick,
                Pivot = CoordinatePivot.WindowRelative,
                X = 500,
                Y = 600,
                DelayMs = 3000,
                Description = "출격 버튼 좌클릭 1회 ➔ 3초 대기"
            });

            // 💡 [시나리오 5]: 5번 시나리오 예시
            var scenario5 = new ScenarioPreset
            {
                ScenarioNumber = 5,
                Name = "시나리오 5 (분기: 대체 동작/보상)",
                IsEnabled = true,
                DefaultPivot = CoordinatePivot.WindowRelative,
                MatchMode = ConditionMatchMode.AllPoints,
                OnMatchBranch = BranchAction.ExecuteActions,
                OnMismatchBranch = BranchAction.DoNothing,
                CooldownMs = 500
            };

            scenario5.ColorConditions.Add(new ColorCondition
            {
                Name = "B 포인트 (보상 버튼 노란색)",
                Shape = ColorPointShape.Point,
                Pivot = CoordinatePivot.WindowRelative,
                X = 400,
                Y = 500,
                TargetColorHex = "#FFCC00",
                Tolerance = 20,
                MustMatch = true
            });

            scenario5.Actions.Add(new PresetAction
            {
                ActionType = ActionType.LeftClick,
                Pivot = CoordinatePivot.WindowRelative,
                X = 400,
                Y = 500,
                DelayMs = 1000,
                Description = "보상 버튼 클릭 ➔ 1초 대기"
            });

            scenario5.Actions.Add(new PresetAction
            {
                ActionType = ActionType.JumpScenario,
                JumpTargetScenarioNumber = 1,
                DelayMs = 200,
                Description = "1번 시나리오로 복귀"
            });

            profile.Presets.Add(scenario1);
            profile.Presets.Add(scenario5);

            return profile;
        }
    }
}
