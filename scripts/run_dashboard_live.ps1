<#
Dashboard with real field data and the live GHI forecast (read-only; any machine with the synced folder).

  powershell -ExecutionPolicy Bypass -File .\scripts\run_dashboard_live.ps1
Without this script the dashboard keeps its mock data.
#>
param(
    [string]$SharedDir = (Join-Path $env:OneDriveCommercial "GreenhouseFieldData"),
    [int]$Port = 8010
)
$ErrorActionPreference = "Stop"
$env:LIVE_DATA_SOURCE = "field_collector"
$env:LIVE_DATA_FILE = Join-Path $SharedDir "latest.json"
$env:GHI_FORECAST_FILE = Join-Path $SharedDir "latest_forecast.json"
Set-Location (Split-Path $PSScriptRoot -Parent)
& .\.venv\Scripts\python.exe manage.py runserver $Port
