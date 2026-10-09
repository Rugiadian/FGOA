@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $p = Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::Programs)) 'FGOA.lnk'; if (Test-Path $p) { Remove-Item -Force $p; Write-Host '[성공] 시작 메뉴에서 FGOA 바로가기가 제거되었습니다.' -ForegroundColor Green } else { Write-Host '[안내] 시작 메뉴에 등록된 FGOA 바로가기가 없습니다.' -ForegroundColor Yellow }"
echo.
pause
