@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\repair-entry.ps1"
set "result=%errorlevel%"
echo.
if not "%result%"=="0" echo Repair failed. See output\logs\repair-report.json or the error above.
pause
exit /b %result%
