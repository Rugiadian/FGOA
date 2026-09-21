@echo off
chcp 65001 > nul
setlocal

set PYTHONW_EXE=%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe

if exist "%PYTHONW_EXE%" (
    start "" "%PYTHONW_EXE%" "%~dp0main.py"
    exit /b 0
)

where pythonw >nul 2>&1
if %ERRORLEVEL% equ 0 (
    start "" pythonw "%~dp0main.py"
    exit /b 0
)

set PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe
if exist "%PYTHON_EXE%" (
    start "" "%PYTHON_EXE%" "%~dp0main.py"
    exit /b 0
)

start "" python "%~dp0main.py"
exit /b 0
