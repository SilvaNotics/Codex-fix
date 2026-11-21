@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\move-to-wsl.ps1" %*
set "result=%ERRORLEVEL%"
if "%~1"=="" pause
exit /b %result%
