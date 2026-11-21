# ASCII-only for Windows PowerShell 5.1 encoding compatibility.
$ErrorActionPreference = 'Stop'
$scanOnly = $args -ccontains '--scan-only'
$helpOnly = ($args -ccontains '--help') -or ($args -ccontains '-h')
if (!$scanOnly -and !$helpOnly) {
    & (Join-Path $PSScriptRoot 'normalize-vbs.ps1')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
$pythonCheck = if ($scanOnly -or $helpOnly) { 'import tomllib' } else { 'import tomllib,websockets' }
$candidates = @()
$installs = Join-Path $env:LOCALAPPDATA 'hermes\installs'
if (Test-Path $installs) {
    $candidates += @(Get-ChildItem "$installs\*\environments\*\venv\Scripts\python.exe" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | ForEach-Object FullName)
}
foreach ($name in @('python.exe', 'python3.exe')) {
    $candidates += @(Get-Command $name -CommandType Application -All -ErrorAction SilentlyContinue | ForEach-Object Source)
}
$python = $null
foreach ($candidate in ($candidates | Select-Object -Unique)) {
    if ($candidate -like '*\Microsoft\WindowsApps\*') { continue }
    & $candidate -c $pythonCheck 2>$null
    if ($LASTEXITCODE -eq 0) { $python = $candidate; break }
}
if (!$python) {
    $requirement = if ($scanOnly -or $helpOnly) { 'Python 3.11+' } else { 'Python 3.11+ with websockets' }
    Write-Host "$requirement was not found. Check Hermes or your Python environment." -ForegroundColor Red
    exit 1
}
Write-Host "Python: $python"
if (!$scanOnly -and !$helpOnly) {
    Write-Host 'Scanning the installed Codex. If necessary, the launcher may restart Codex. Do not run during an active task.'
}
$env:PYTHONUTF8 = '1'
& $python (Join-Path $PSScriptRoot 'repair_codex.py') @args
exit $LASTEXITCODE
