# Live Operation (field data → forecast → dashboard / MPC)

```text
field PC   dashboard GET /api/live ──(1/min, read-only)── field_collector/collector.py
                                                          └─ output_dir (sync folder): latest.json, outside/, raw/
laptop     sync folder ─┬─ Django  LIVE_DATA_SOURCE=field_collector ─ /api/digital-twin/live/ (3D twin, MPC current)
                        └─ mpc_lab live_runner (every 5 min)
                             outside → clear sky → kc → weekly update (when due) → forecast of the last bin
                             └─ <shared folder>/latest_forecast.json ─ Django /api/forecast/ghi/
```

Code: `src/greenhouse_mpc/forecast/live_runner.py`. Config: `config/live.yaml`. Tests: `tests/test_live_runner.py`.
Collector: `field_collector/README.md`. Dashboard API: `markdown/frontend_api_contract.md`.

## Machines and folders

| Machine | Role |
|---|---|
| Lab PC (always on) | **operations**: live runner loop. Only this machine runs it (records/ and the weekly update must not run twice) |
| Laptop / any PC with the synced folder | dashboard (read-only), development, demos |
| Field PC | collector only |

| Folder | Content | Synced |
|---|---|---|
| Google Drive `내 드라이브\GreenhouseFieldData\` (school Google account, Drive for desktop, mirroring; `GREENHOUSE_SHARED_DIR`) | collector output (`latest.json`, `outside/`, `raw/`) and `latest_forecast.json` | yes |
| `C:\GreenhouseOps\` (`GREENHOUSE_DATA_DIR`, lab PC) | processed data, models, live forecast log (rewritten every 5 min) | no |
| project `mpc_lab/records/` | operation state and logs (small, tracked in git) | yes (project) |

Paths: `src/greenhouse_mpc/paths.py`. Without the variables everything stays under `mpc_lab/data` (development).
The collector's `output_dir` must be the shared folder.

## Running

```powershell
# lab PC, mpc_lab folder: one cycle, then the loop
powershell -ExecutionPolicy Bypass -File .\scripts\run_live_operation.ps1 -Once
powershell -ExecutionPolicy Bypass -File .\scripts\run_live_operation.ps1

# any machine with the synced folder, project root: dashboard with field data + forecast
powershell -ExecutionPolicy Bypass -File .\scripts\run_dashboard_live.ps1
```

The scripts set the variables for their own process only. Defaults: `C:\GreenhouseOps`,
`%USERPROFILE%\My Drive` or `내 드라이브` `\GreenhouseFieldData` (Google Drive), Python of the conda env `sfes`; override with `-DataDir`,
`-SharedDir`, `-PythonExe`. If the active model files are not in this machine's data folder (first run on a
new machine), the cycle retrains them.

### Checking live forecasts against observations

```powershell
# mpc_lab folder; read-only report from the live forecast log (forecast_live/forecasts.parquet)
powershell -ExecutionPolicy Bypass -File .\scripts\evaluate_live_forecast.ps1            # all days
powershell -ExecutionPolicy Bypass -File .\scripts\evaluate_live_forecast.ps1 -Days 7    # last 7 days
powershell -ExecutionPolicy Bypass -File .\scripts\evaluate_live_forecast.ps1 -Csv C:	emp\pairs.csv
```

Per horizon: samples, days, observed mean, RMSE of the used forecast / xgb / CC / smart persistence, MAE and
bias of the used forecast, RMSE skill of the used forecast vs persistence and vs CC. Observed = sensor 5-min
mean where kc is valid (sun >= 20 deg), as in the weekly gate. Code: `src/greenhouse_mpc/forecast/live_eval.py`.

### Auto-start on the lab PC (optional, not registered yet)

Starts the loop at logon, never twice, restarts after a failure. Run once in PowerShell (project path
as on the lab PC):

```powershell
$script = "C:\Users\user\OneDrive - 전북대학교\바탕 화면\mpc_dashboard_v1\mpc_lab\scripts\run_live_operation.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5) -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName "GreenhouseLiveForecast" -Action $action -Trigger $trigger -Settings $settings
```

Status `Get-ScheduledTask GreenhouseLiveForecast | Get-ScheduledTaskInfo`; stop `Stop-ScheduledTask
GreenhouseLiveForecast`; remove `Unregister-ScheduledTask GreenhouseLiveForecast -Confirm:$false`.
Also: power plan "never sleep" and Windows Update active hours on the lab PC. The latest state is always in
`latest_forecast.json` (`status`, `reason`).

## Cycle (every 5 min, 2 min after the bin closes)

1. Outside pipeline over the historical exports and `<field_dir>/outside/outside_*.csv` (same column layout;
   collector rows and manual exports of the same minute are merged by the 1-min aggregation), clear sky,
   clear-sky index. About 20 s with 2.5 months of data; grows linearly.
2. `operation.update` when the last update is ≥ 7 days old (first run: immediately).
3. Forecast for the last complete 5-min bin → live log (gate input) and `latest_forecast.json`.

`latest_forecast.json` (`schema_version: ghi-forecast/0.1`): `status` `ok` / `unavailable` (reason:
`data_stale` when the newest observation is older than 15 min, `night`, `low_sun`, `ghi_not_observed`,
`issue_bin_not_processed`) / `error` (exception text; the loop continues). `horizons`: 12 entries with
`horizon_min`, `target_time`, `method`, `ghi_w_m2` (sensor scale), `kc`, `ghi_clear_w_m2`.

## Notes

- The last bin may hold fewer than 5 collected minutes if the sync is late (its value is the mean of the
  minutes present).
- The MPC is still a mock; it already receives the live current openings. The real controller will use the
  live snapshot and this forecast.
- First runs on 2026-10-11 without field data: model `xgb_expanding_20261011_6efb4475` (data to 10-09),
  status `data_stale`; lab PC set up with `C:\GreenhouseOps` and the shared folder the same day.
