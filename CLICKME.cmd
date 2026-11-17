@echo off
setlocal
set "CODEX_LAUNCH_ROOT=%~dp0"
rem Strict UTF-8 decode; back up and normalize VBS before launching.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "try { $ErrorActionPreference='Stop'; $utf8=New-Object System.Text.UTF8Encoding($false,$true); $path=Join-Path $env:CODEX_LAUNCH_ROOT 'scripts\start-codex.vbs'; $bytes=[IO.File]::ReadAllBytes($path); if($bytes.Length -ge 2 -and $bytes[0] -eq 255 -and $bytes[1] -eq 254) { $text=[Text.Encoding]::Unicode.GetString($bytes,2,$bytes.Length-2) } elseif($bytes.Length -ge 3 -and $bytes[0] -eq 239 -and $bytes[1] -eq 187 -and $bytes[2] -eq 191) { $text=$utf8.GetString($bytes,3,$bytes.Length-3) } else { $text=$utf8.GetString($bytes) }; $enc=[Text.Encoding]::Unicode; $out=[byte[]]($enc.GetPreamble()+$enc.GetBytes($text)); if([Convert]::ToBase64String($bytes) -ne [Convert]::ToBase64String($out)) { $backupDir=Join-Path $env:CODEX_LAUNCH_ROOT 'output\backups'; [IO.Directory]::CreateDirectory($backupDir)|Out-Null; $backup=Join-Path $backupDir 'start-codex.vbs.bak-encoding'; if(!(Test-Path -LiteralPath $backup)) { [IO.File]::Copy($path,$backup) }; [IO.File]::WriteAllBytes($path,$out); Write-Host 'Encoding fixed: scripts\start-codex.vbs' } } catch { Write-Host $_ -ForegroundColor Red; exit 1 }"
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
