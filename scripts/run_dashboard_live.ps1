<#
Dashboard with real field data and the live GHI forecast (read-only; any machine with the synced folder).

  powershell -ExecutionPolicy Bypass -File .\scripts\run_dashboard_live.ps1
Without this script the dashboard keeps its mock data.

Python: -PythonExe if given; otherwise the project .venv when it works on this machine; otherwise the
conda env sfes. (.venv lives in the synced project folder, so a venv rebuilt on another PC can point to a
Python that does not exist here; it is not modified by this script.)
#>
param(
    [string]$SharedDir = "",
    [int]$Port = 8010,
    [string]$PythonExe = ""
)
$ErrorActionPreference = "Stop"
if (-not $SharedDir) {
    # Google Drive for desktop mirror folder: "My Drive" or the Korean name (built from code points so
    # this file stays ASCII for Windows PowerShell 5.1).
    $korean = -join [char[]](0xB0B4, 0x20, 0xB4DC, 0xB77C, 0xC774, 0xBE0C)
    foreach ($name in @("My Drive", $korean)) {
        $candidate = Join-Path (Join-Path $env:USERPROFILE $name) "GreenhouseFieldData"
        if (Test-Path $candidate) { $SharedDir = $candidate; break }
    }
    if (-not $SharedDir) { throw "GreenhouseFieldData not found in the Google Drive folder; pass -SharedDir" }
}
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not $PythonExe) {
    $venv = ".\.venv\Scripts\python.exe"
    $sfes = Join-Path $env:USERPROFILE "anaconda3\envs\sfes\python.exe"
    $ErrorActionPreference = "Continue"
    if (Test-Path $venv) { & $venv -c "import django, trimesh" 2>$null }
    $venvOk = (Test-Path $venv) -and ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = "Stop"
    if ($venvOk) { $PythonExe = $venv }
    elseif (Test-Path $sfes) { $PythonExe = $sfes }
    else { throw "No working Python: .venv does not run on this machine and the conda env sfes was not found; pass -PythonExe" }
}
Write-Host "Python: $PythonExe"
Write-Host "Shared folder: $SharedDir"
$env:LIVE_DATA_SOURCE = "field_collector"
$env:LIVE_DATA_FILE = Join-Path $SharedDir "latest.json"
$env:GHI_FORECAST_FILE = Join-Path $SharedDir "latest_forecast.json"
& $PythonExe manage.py runserver $Port
