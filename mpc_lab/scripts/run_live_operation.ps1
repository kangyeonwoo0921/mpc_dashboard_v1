<#
Live GHI forecasting on the operations PC (docs/LIVE_OPERATION.md).
Data locations are set for this process only (no machine-wide environment change):
  processed data, models, live log  -> $DataDir   (local, outside OneDrive)
  field collector files + latest_forecast.json -> $SharedDir (synced folder)

  powershell -ExecutionPolicy Bypass -File .\scripts\run_live_operation.ps1 -Once
  powershell -ExecutionPolicy Bypass -File .\scripts\run_live_operation.ps1
Run it on ONE machine only (records/ and the weekly update must not run twice).
#>
param(
    [string]$DataDir = "C:\GreenhouseOps",
    [string]$SharedDir = (Join-Path $env:OneDriveCommercial "GreenhouseFieldData"),
    [string]$PythonExe = (Join-Path $env:USERPROFILE "anaconda3\envs\sfes\python.exe"),
    [switch]$Once
)
$ErrorActionPreference = "Stop"
$env:GREENHOUSE_DATA_DIR = $DataDir
$env:GREENHOUSE_SHARED_DIR = $SharedDir
Set-Location (Split-Path $PSScriptRoot -Parent)
$mode = if ($Once) { "--once" } else { "--loop" }
& $PythonExe -m greenhouse_mpc.forecast.live_runner $mode --field-dir $SharedDir
exit $LASTEXITCODE
