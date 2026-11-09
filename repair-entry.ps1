# ASCII-only for Windows PowerShell 5.1 encoding compatibility.
$ErrorActionPreference = 'Stop'
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
    & $candidate -c 'import sys,websockets;sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>$null
    if ($LASTEXITCODE -eq 0) { $python = $candidate; break }
}
if (!$python) {
    Write-Host 'Python 3.11+ with websockets was not found. Open Hermes or install the dependency in your Python environment.' -ForegroundColor Red
    exit 1
}
Write-Host "Python: $python"
Write-Host 'Scanning the installed Codex. If necessary, the launcher may restart Codex. Do not run during an active task.'
$env:PYTHONUTF8 = '1'
& $python (Join-Path $PSScriptRoot 'repair_codex.py')
exit $LASTEXITCODE
