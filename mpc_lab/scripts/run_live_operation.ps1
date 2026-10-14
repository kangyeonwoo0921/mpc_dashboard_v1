<#
Live GHI forecasting on the operations PC (docs/LIVE_OPERATION.md).
Data locations are set for this process only (no machine-wide environment change):
  processed data, models, live log  -> $DataDir   (local, outside OneDrive)
  field collector files + latest_forecast.json -> $SharedDir (Google Drive GreenhouseFieldData)

  powershell -ExecutionPolicy Bypass -File .\scripts\run_live_operation.ps1 -Once
  powershell -ExecutionPolicy Bypass -File .\scripts\run_live_operation.ps1
Run it on ONE machine only (records/ and the weekly update must not run twice).
#>
param(
    [string]$DataDir = "C:\GreenhouseOps",
    [string]$SharedDir = "",
    [string]$PythonExe = (Join-Path $env:USERPROFILE "anaconda3\envs\sfes\python.exe"),
    [switch]$Once
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
$env:GREENHOUSE_DATA_DIR = $DataDir
$env:GREENHOUSE_SHARED_DIR = $SharedDir
Set-Location (Split-Path $PSScriptRoot -Parent)
$mode = if ($Once) { "--once" } else { "--loop" }
& $PythonExe -m greenhouse_mpc.forecast.live_runner $mode --field-dir $SharedDir
exit $LASTEXITCODE
