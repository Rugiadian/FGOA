@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_shortcut.ps1"
echo.
pause
exit /b %ERRORLEVEL%
