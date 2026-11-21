@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\normalize-vbs.ps1"
if errorlevel 1 (
    echo Encoding check failed. Launcher was not started.
    pause
    exit /b 1
)
"%SystemRoot%\System32\wscript.exe" "%~dp0scripts\start-codex.vbs"
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" (
    echo Launcher failed. See output\logs\vbs.log and output\logs\launch.log.
    pause
)
exit /b %RESULT%
