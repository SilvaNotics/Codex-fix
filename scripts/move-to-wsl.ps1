# Keep this entrypoint ASCII for Windows PowerShell 5.1.
$ErrorActionPreference = 'Stop'
$candidates = @()
$installs = Join-Path $env:LOCALAPPDATA 'hermes\installs'
$candidates += @(Get-ChildItem "$installs\*\environments\*\venv\Scripts\python.exe" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | ForEach-Object FullName)
$uvHome = Join-Path $env:APPDATA 'uv\python'
$candidates += @(Get-ChildItem "$uvHome\cpython-*\python.exe" -ErrorAction SilentlyContinue | ForEach-Object FullName)
foreach ($name in @('python.exe', 'python3.exe', 'py.exe')) {
    $candidates += @(Get-Command $name -CommandType Application -All -ErrorAction SilentlyContinue | ForEach-Object Source)
}
$env:PYTHONUTF8 = '1'
foreach ($python in ($candidates | Select-Object -Unique)) {
    if ($python -like '*\Microsoft\WindowsApps\*') { continue }
    & $python -c 'import tomllib' 2>$null
    if ($LASTEXITCODE -eq 0) {
        & $python (Join-Path $PSScriptRoot 'move_to_wsl.py') @args
        exit $LASTEXITCODE
    }
}
Write-Host 'Python 3.11 or later was not found.' -ForegroundColor Red
exit 1
