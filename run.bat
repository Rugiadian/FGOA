@echo off
chcp 65001 > nul
echo ===================================================
echo   FGOA - 화면 인식 스마트 윈도우 오토 툴 시작
echo ===================================================

set PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe

if exist "%PYTHON_EXE%" (
    "%PYTHON_EXE%" main.py
) else (
    python main.py
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo 실행 중 오류가 발생했습니다.
    pause
)
