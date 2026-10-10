# GHI Forecast Operation (weekly update, candidate comparison)

Code: `src/greenhouse_mpc/forecast/operation.py`. Config: `config/ghi_forecast.yaml` → `operation`.
Tests: `tests/test_forecast_operation.py`. Evaluation background: GHI_FORECAST_MODEL.md.

```powershell
python -m greenhouse_mpc.forecast.operation update --as-of 2026-10-10        # weekly
python -m greenhouse_mpc.forecast.operation forecast --at "2026-10-09 12:00"  # issue bin start (KST)
python -m greenhouse_mpc.forecast.operation replay --start 2026-08-31 --end 2026-10-09 --sandbox DIR
```

## 1. Weekly update

1. **Gate** per horizon: live forecasts of the last 14 days (out-of-sample by construction, since each
   was made by the model active at the time) are scored against the observed GHI. A horizon in
   `model_horizon_steps` uses the best candidate whose RMSE is not above the reference's, else the
   reference. Fewer than 5 days with valid targets: previous choice kept. Other horizons: reference.
   No live record yet: model horizons use the first candidate.
2. **Reference statistics** µ, ρ(h) from all data before the update (operational CC cannot use the
   statistics of the period it forecasts; the evaluation CC did, by definition).
3. **Retraining** of every candidate on the days before the update (last 7 days for early stopping).
   Activated only if validation kc forecasts stay in [0, 2] and its validation RMSE is at most 1.5 × the
   active model's on the same validation days; otherwise the previous model stays.

Candidates: `operation.candidates` (now one: `xgb_expanding`, all data). New methods (recent-window
training, sensor-corrected input, …) are added there and compete on their live record; no code change.

## 2. Forecast output

Per issue bin and horizon h = 1..12: `target_time`, `method` (policy), `kc_hat`, `ghi_hat`
(= kc_hat × clear-sky GHI), `ghi_clear`, the forecasts of every active candidate and of the reference,
`model_id`, `policy_update`. NaN when kc_input(t) is not valid, the sun is below the clear-sky horizon,
or the target is on another day. Target-time geometry and clear-sky GHI come from the clear-sky model,
so no future rows are needed (tested). GHI is the **sensor reading** (angular response not corrected).

## 3. Files

| File | Tracked | Content |
|---|---|---|
| `records/forecast_operation_state.json` | yes | active models, per-horizon policy, reference statistics |
| `records/forecast_operation_log.jsonl` | yes | every update: gate evidence, training/sanity result, policy |
| `data/processed/forecast_models/<model_id>/` | no | `h01..h12.json` models, `meta.json` |
| `data/processed/forecast_live/forecasts.parquet` | no | live forecast log (input of the gate) |

## 4. Replay on 2026-08-31 – 10-09 (mechanics check, not new evidence)

Simulated weekly operation (sandbox). All 6 weekly models passed the sanity checks. Live RMSE skill of
`xgb_expanding` against the **operational** CC (statistics from past data only), all days:

| Horizon | 5 | 10 | 15 | 20 | 25 | 30 | 35 | 40 | 45 | 50 | 55 | 60 min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| skill | 0.055 | 0.084 | 0.076 | 0.066 | 0.093 | 0.093 | 0.083 | 0.074 | 0.072 | 0.062 | 0.049 | 0.051 |
| weeks > 0 (of 6) | 6 | 6 | 6 | 6 | 6 | 6 | 6 | 6 | 5 | 4 | 5 | 4 |

Against the evaluation CC (internal statistics, Yang et al. 2020) the 35–60 min gain was not significant;
the operational CC is weaker because it cannot know the forecast period's mean and autocorrelation.
`model_horizon_steps` (5–30 min) was set from the evaluation comparison; whether to extend it is a
user decision. These weeks were used during design, so the replay checks the mechanics only.

Correction made during the replay: the first sanity rule compared validation RMSE across different
weeks and blocked every model after a clear validation week (weather, not model quality). It now
compares new and active models on the same validation days.
