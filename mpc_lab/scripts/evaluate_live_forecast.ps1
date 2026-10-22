<#
Live GHI forecast vs observed: per-horizon MAE / RMSE / bias / skill (read-only report).

  powershell -ExecutionPolicy Bypass -File .\scripts\evaluate_live_forecast.ps1                 # all days
  powershell -ExecutionPolicy Bypass -File .\scripts\evaluate_live_forecast.ps1 -Days 7         # last 7 days
  powershell -ExecutionPolicy Bypass -File .\scripts\evaluate_live_forecast.ps1 -Csv pairs.csv  # + pairs for Excel

Reads the live forecast log and processed data under -DataDir (same default as run_live_operation.ps1).
#>
param(
    [string]$DataDir = "C:\GreenhouseOps",
    [int]$Days = 0,
    [string]$Start = "",
    [string]$End = "",
    [string]$Csv = "",
    [string]$PythonExe = (Join-Path $env:USERPROFILE "anaconda3\envs\sfes\python.exe")
)
$ErrorActionPreference = "Stop"
$env:GREENHOUSE_DATA_DIR = $DataDir
$env:PYTHONPATH = Join-Path (Split-Path $PSScriptRoot -Parent) "src"
$arguments = @("-m", "greenhouse_mpc.forecast.live_eval")
if ($Days -gt 0) { $arguments += @("--days", $Days) }
if ($Start) { $arguments += @("--start", $Start) }
if ($End) { $arguments += @("--end", $End) }
if ($Csv) { $arguments += @("--csv", $Csv) }
& $PythonExe @arguments
