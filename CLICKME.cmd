@echo off
setlocal
set "CODEX_SETUP_ROOT=%~dp0"
rem Strict UTF-8 decode; back up and normalize PS1/VBS before the existing installer.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "try { $ErrorActionPreference='Stop'; $utf8=New-Object System.Text.UTF8Encoding($false,$true); foreach($item in @(@('scripts\install.ps1',[Text.Encoding]::UTF8),@('scripts\start-codex.vbs',[Text.Encoding]::Unicode))) { $path=Join-Path $env:CODEX_SETUP_ROOT $item[0]; $bytes=[IO.File]::ReadAllBytes($path); if($bytes.Length -ge 2 -and $bytes[0] -eq 255 -and $bytes[1] -eq 254) { $text=[Text.Encoding]::Unicode.GetString($bytes,2,$bytes.Length-2) } elseif($bytes.Length -ge 3 -and $bytes[0] -eq 239 -and $bytes[1] -eq 187 -and $bytes[2] -eq 191) { $text=$utf8.GetString($bytes,3,$bytes.Length-3) } else { $text=$utf8.GetString($bytes) }; $enc=$item[1]; $out=[byte[]]($enc.GetPreamble()+$enc.GetBytes($text)); if([Convert]::ToBase64String($bytes) -ne [Convert]::ToBase64String($out)) { $backupDir=Join-Path $env:CODEX_SETUP_ROOT 'output\backups'; [IO.Directory]::CreateDirectory($backupDir)|Out-Null; $backup=Join-Path $backupDir ([IO.Path]::GetFileName($path)+'.bak-encoding'); if(!(Test-Path -LiteralPath $backup)) { [IO.File]::Copy($path,$backup) }; [IO.File]::WriteAllBytes($path,$out); Write-Host ('Encoding fixed: '+$item[0]) } }; $t=$null; $e=$null; [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $env:CODEX_SETUP_ROOT 'scripts\install.ps1'),[ref]$t,[ref]$e)|Out-Null; if($e.Count) { throw ($e|Out-String) }; Write-Host 'Encoding check passed.' } catch { Write-Host $_ -ForegroundColor Red; exit 1 }"
if errorlevel 1 (
    echo Encoding check failed. Installer was not run.
    pause
    exit /b 1
)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1" %*
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" echo Installation failed. See the error above.
pause
exit /b %RESULT%
