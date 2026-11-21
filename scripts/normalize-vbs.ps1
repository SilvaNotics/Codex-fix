# ASCII-only for Windows PowerShell 5.1.
$ErrorActionPreference = 'Stop'
$temporary = $null
try {
    $path = Join-Path $PSScriptRoot 'start-codex.vbs'
    $bytes = [IO.File]::ReadAllBytes($path)
    $utf16 = [Text.UnicodeEncoding]::new($false, $true, $true)
    $alreadyUtf16 = $bytes.Length -ge 2 -and $bytes[0] -eq 255 -and $bytes[1] -eq 254
    if ($alreadyUtf16) {
        $text = $utf16.GetString($bytes, 2, $bytes.Length - 2)
    } else {
        $utf8 = [Text.UTF8Encoding]::new($false, $true)
        $hasBom = $bytes.Length -ge 3 -and $bytes[0] -eq 239 -and $bytes[1] -eq 187 -and $bytes[2] -eq 191
        $offset = if ($hasBom) { 3 } else { 0 }
        $text = $utf8.GetString($bytes, $offset, $bytes.Length - $offset)
    }
    if ($text.IndexOf([char]0) -ge 0) { throw 'Unexpected NUL in start-codex.vbs.' }
    if ($alreadyUtf16) { exit 0 }

    $backupDir = Join-Path (Split-Path -Parent $PSScriptRoot) 'output\backups'
    [IO.Directory]::CreateDirectory($backupDir) | Out-Null
    $backup = Join-Path $backupDir 'start-codex.vbs.bak-encoding'
    $temporary = Join-Path $PSScriptRoot ('start-codex.vbs.' + [Guid]::NewGuid() + '.tmp')
    [IO.File]::WriteAllText($temporary, $text, $utf16)
    if ([Convert]::ToBase64String([IO.File]::ReadAllBytes($path)) -cne [Convert]::ToBase64String($bytes)) {
        throw 'start-codex.vbs changed during conversion. Run the launcher again.'
    }
    if (![IO.File]::Exists($backup)) {
        $backupStream = [IO.File]::Open($backup, [IO.FileMode]::CreateNew)
        try { $backupStream.Write($bytes, 0, $bytes.Length) } finally { $backupStream.Dispose() }
    }
    [IO.File]::Replace($temporary, $path, [NullString]::Value)
    Write-Host 'Encoding fixed: scripts\start-codex.vbs'
    exit 0
} catch {
    Write-Host "VBS encoding check failed: $_" -ForegroundColor Red
    exit 1
} finally {
    if ($temporary -and [IO.File]::Exists($temporary)) { [IO.File]::Delete($temporary) }
}
