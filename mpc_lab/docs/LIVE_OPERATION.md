# Live Operation (field data → forecast → dashboard / MPC)

```text
field PC   dashboard GET /api/live ──(1/min, read-only)── field_collector/collector.py
                                                          └─ output_dir (sync folder): latest.json, outside/, raw/
laptop     sync folder ─┬─ Django  LIVE_DATA_SOURCE=field_collector ─ /api/digital-twin/live/ (3D twin, MPC current)
                        └─ mpc_lab live_runner (every 5 min)
                             outside → clear sky → kc → weekly update (when due) → forecast of the last bin
                             └─ data/processed/forecast_live/latest_forecast.json ─ Django /api/forecast/ghi/
```

Code: `src/greenhouse_mpc/forecast/live_runner.py`. Config: `config/live.yaml`. Tests: `tests/test_live_runner.py`.
Collector: `field_collector/README.md`. Dashboard API: `markdown/frontend_api_contract.md`.

## Running (laptop)

```powershell
# mpc_lab (conda env sfes); field dir = the synced collector output_dir
cd mpc_lab
python -m greenhouse_mpc.forecast.live_runner --once --field-dir "C:\...\GreenhouseCollector\data"
python -m greenhouse_mpc.forecast.live_runner --loop --field-dir "C:\...\GreenhouseCollector\data"

# dashboard (project .venv), second terminal
$env:LIVE_DATA_SOURCE = "field_collector"
$env:LIVE_DATA_FILE = "C:\...\GreenhouseCollector\data\latest.json"
$env:GHI_FORECAST_FILE = "<project>\mpc_lab\data\processed\forecast_live\latest_forecast.json"
.\.venv\Scripts\python.exe manage.py runserver 8010
```

The laptop must be on for forecasts; the collector keeps recording on the field PC meanwhile.

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
- First run on 2026-10-11 without field data: model `xgb_expanding_20261011_6efb4475` (data to 10-09),
  status `data_stale`.
