# UTF-8 Encoding
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "         FGOA 시작 메뉴 바로가기 등록             " -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

$appDir = $PSScriptRoot
$mainPy = Join-Path $appDir "main.py"
$iconFile = Join-Path $appDir "ui\assets\app_icon.ico"
$programsDir = [Environment]::GetFolderPath([Environment+SpecialFolder]::Programs)
$shortcutPath = Join-Path $programsDir "FGOA.lnk"

# Python 실행 파일 탐색 (pythonw.exe 우선)
$pythonw = $null
$defaultPython = "$env:LOCALAPPDATA\Programs\Python\Python312\pythonw.exe"
if (Test-Path $defaultPython) {
    $pythonw = $defaultPython
} else {
    $cmd = Get-Command pythonw -ErrorAction SilentlyContinue
    if ($cmd) {
        $pythonw = $cmd.Source
    } else {
        $found = Get-ChildItem "$env:LOCALAPPDATA\Programs\Python" -Filter "pythonw.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) {
            $pythonw = $found.FullName
        } else {
            $pyCmd = Get-Command python -ErrorAction SilentlyContinue
            if ($pyCmd) {
                $pythonw = $pyCmd.Source
            }
        }
    }
}

if (-not $pythonw) {
    Write-Host "[오류] Python 실행 파일을 찾을 수 없습니다." -ForegroundColor Red
    Write-Host "Python이 시스템에 설치되어 있는지 확인해 주세요." -ForegroundColor Yellow
    exit 1
}

Write-Host "[1/2] 등록 정보 확인:" -ForegroundColor Green
Write-Host "  - 프로젝트 경로 : $appDir"
Write-Host "  - Python 실행기 : $pythonw"
Write-Host "  - 바로가기 위치 : $shortcutPath"
Write-Host ""

try {
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut($shortcutPath)
    $Shortcut.TargetPath = $pythonw
    $Shortcut.Arguments = "`"$mainPy`""
    $Shortcut.WorkingDirectory = $appDir
    if (Test-Path $iconFile) {
        $Shortcut.IconLocation = "$iconFile,0"
    }
    $Shortcut.Description = "FGOA - Fate/Grand Order Automation"
    $Shortcut.Save()

    Write-Host "[2/2] 성공: 시작 메뉴에 FGOA 바로가기가 등록되었습니다!" -ForegroundColor Green
    Write-Host ""
    Write-Host "이제 Windows 시작 메뉴에서 'FGOA'를 검색하거나 클릭하여 바로 실행할 수 있습니다." -ForegroundColor Gray
} catch {
    Write-Host "[오류] 바로가기 생성 중 오류 발생: $_" -ForegroundColor Red
    exit 1
}
