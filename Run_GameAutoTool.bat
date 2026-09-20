@echo off
chcp 65001 >nul
title RD GameAuto FGOA Launcher

cd /d "%~dp0"

if exist "Publish\RD_GameAuto_FGOA.exe" (
    start "" "Publish\RD_GameAuto_FGOA.exe"
    exit /b 0
)

if exist "bin\Release\net10.0-windows\RD_GameAuto_FGOA.exe" (
    start "" "bin\Release\net10.0-windows\RD_GameAuto_FGOA.exe"
    exit /b 0
)

if exist "bin\Debug\net10.0-windows\RD_GameAuto_FGOA.exe" (
    start "" "bin\Debug\net10.0-windows\RD_GameAuto_FGOA.exe"
    exit /b 0
)

echo [FGOA] 실행 파일이 없어 dotnet 빌드를 시작합니다...
dotnet build -c Release
if %ERRORLEVEL% equ 0 (
    start "" "bin\Release\net10.0-windows\RD_GameAuto_FGOA.exe"
) else (
    echo [FGOA] 빌드에 실패하였습니다.
    pause
)
