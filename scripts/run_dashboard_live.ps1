<#
Dashboard with real field data and the live GHI forecast (read-only; any machine with the synced folder).

  powershell -ExecutionPolicy Bypass -File .\scripts\run_dashboard_live.ps1
Without this script the dashboard keeps its mock data.
#>
param(
    [string]$SharedDir = "",
    [int]$Port = 8010
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
$env:LIVE_DATA_SOURCE = "field_collector"
$env:LIVE_DATA_FILE = Join-Path $SharedDir "latest.json"
$env:GHI_FORECAST_FILE = Join-Path $SharedDir "latest_forecast.json"
Set-Location (Split-Path $PSScriptRoot -Parent)
& .\.venv\Scripts\python.exe manage.py runserver $Port
