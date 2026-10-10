# GHI Forecast Model (forecast step 3, XGBoost)

Code: `src/greenhouse_mpc/forecast/` (`split.py`, `features.py`, `model_pipeline.py`). Config:
`config/ghi_forecast.yaml` (`split`, `features`, `model`, `evaluation`). Tests: `tests/test_forecast_model.py`.
References and definitions: GHI_FORECAST_BASELINE.md.

```powershell
python -m greenhouse_mpc.forecast.model_pipeline --role development
python -m greenhouse_mpc.forecast.model_pipeline --role checkpoint    # once; logged
python -m greenhouse_mpc.forecast.model_pipeline --role final         # once, sealed; logged
```

## 1. Split (user decision 2026-10-10, option C)

| Fold | Role | Training | Validation (early stopping) | Test |
|---|---|---|---|---|
| development_1 | development | 07-28 – 08-23 | 08-24 – 08-30 | 08-31 – 09-06 |
| development_2 | development | 07-28 – 08-30 | 08-31 – 09-06 | 09-07 – 09-13 |
| development_3 | development | 07-28 – 09-06 | 09-07 – 09-13 | 09-14 – 09-27 (2-day week merged) |
| checkpoint_1 | checkpoint | 07-28 – 09-20 | 09-21 – 09-27 | 09-28 – 10-04 |
| final_1 | final | 07-28 – 09-27 | 09-28 – 10-04 | 10-05 – 10-09 |

Expanding window, retrained before every test week (operational setting, Alonso-Suárez et al. 2022).
Design decisions use only development folds. Checkpoint: run once, no design change afterwards (a change
is logged and leaves only the final test). Final: sealed, run once. `records/forecast_run_log.jsonl` (tracked in git) records every run
(config hash, kc dataset id, folds, git state); a second checkpoint/final run needs `--rerun-reason`.
New data: extend the role dates in the config; folds follow automatically (weekly, short weeks merged).

## 2. Leakage controls

| Path | Control |
|---|---|
| Time overlap | whole KST days; inputs ≤ 60 min back and targets ≤ 60 min ahead stay on the issue day (night ≥ 12 h); asserted per fold |
| Future measurements | inputs only from bins ≤ t (`kc_input`); only the target and deterministic sun geometry use t+h; tested by altering all data after t |
| Look-ahead QC | inputs use the causal QC status (outside pipeline 1A.2); targets the full status |
| Model choices | early stopping on the validation week inside the training window; hyperparameters fixed, not searched |
| Later roles | `table_for_role` cuts the kc table at the role end; a development run never reads checkpoint/final days |
| References | climatology / CC statistics internal to the test fold (definition, Yang et al. 2020); not model inputs |
| Preprocessing decisions | 20° exclusion and no cap re-derived from data before 09-28 only: same result (kc max 1.59 at ≥ 20°; all maxima in development days) |

## 3. Model (project choices, not tuned)

- Direct strategy: one model per horizon step h = 1..12 (5–60 min); target kc(t+h); GHI = kc × clear-sky GHI.
- Features (17): kc_input lags 0..11 (60 min; Chu et al. 2021: lagged 30–60 min inputs at 1–5 min), means
  of the last 3/6/12 (Alonso-Suárez et al. window), sun elevation at t, sun elevation and azimuth at t+h
  (this sensor's kc depends on elevation). A sample needs kc_input(t) and kc(t+h) valid; other lags may be
  missing (XGBoost handles NaN).
- XGBoost 3.2.0, `reg:squarederror`, depth 4, learning rate 0.05, ≤ 2000 trees, early stopping 50,
  subsample 0.8, colsample 0.8, min_child_weight 5, lambda 1, hist, seed 0, 1 thread (deterministic).

## 4. Development results (kc dataset a8c65f07b5269339; 3 folds, 18 test days)

Test-week weather: dev_1 kc mean 0.66 (variable), dev_2 0.86 (clear, 4 days), dev_3 0.62 (variable, 8 days).

| Horizon | n | RMSE XGB | RMSE CC | RMSE persistence | skill vs CC | skill vs persistence | MBE XGB | MBE CC | days better than CC |
|---|---|---|---|---|---|---|---|---|---|
| 5 min | 1837 | 63.1 | 66.4 | 68.3 | 0.050 | 0.077 | −1.7 | 2.4 | 15/18 |
| 15 min | 1801 | 84.4 | 90.8 | 96.2 | 0.071 | 0.123 | −3.4 | 5.2 | 14/18 |
| 30 min | 1748 | 96.3 | 102.4 | 111.3 | 0.060 | 0.135 | −6.1 | 7.7 | 13/18 |
| 45 min | 1694 | 102.4 | 106.7 | 117.7 | 0.040 | 0.130 | −7.2 | 10.6 | 12/18 |
| 60 min | 1640 | 106.8 | 108.0 | 120.9 | 0.011 | 0.117 | −9.5 | 13.6 | 12/18 |

(W/m²; pooled over the development folds; mean measured GHI of the set 426–438 W/m². All horizons, per-fold,
daily and elevation-band tables in `data/processed/forecast_runs/development/`.)

- Positive RMSE skill against CC at every horizon, largest at 10–30 min (0.06–0.07), close to zero at
  55–60 min. Daily skill varies widely (min −0.24, max +0.37); 11–15 of 18 days better than CC.
- Per fold at 60 min: −0.004, +0.031, +0.017 → no reliable gain at 60 min.
- By target elevation (h = 12): gains at 20–45° (+0.08 to +0.09), losses at ≥ 45° (−0.04 to −0.07).
- Bias: XGBoost slightly negative (−2 to −10 W/m²), CC positive (+2 to +14 W/m²).
- Early stopping chose 62–181 trees.

Not yet run: checkpoint and final.

## 5. Checkpoint result (run once 2026-10-10; design unchanged)

Test 2026-09-28 – 10-04 (6 days, kc mean 0.74). Models retrained on data to 09-27 (validation 09-21 – 09-27).

| Horizon | n | RMSE XGB | RMSE CC | RMSE persistence | skill vs CC | skill vs persistence | days better than CC |
|---|---|---|---|---|---|---|---|
| 5 min | 561 | 64.2 | 66.0 | 69.3 | +0.028 | +0.074 | 3/6 |
| 10 min | 555 | 76.8 | 79.7 | 86.1 | +0.037 | +0.109 | 4/6 |
| 15 min | 549 | 83.9 | 85.3 | 93.9 | +0.016 | +0.107 | 3/6 |
| 30 min | 531 | 94.5 | 94.7 | 109.7 | +0.002 | +0.138 | 4/6 |
| 45 min | 513 | 100.8 | 100.2 | 122.4 | −0.006 | +0.176 | 3/6 |
| 60 min | 495 | 101.6 | 97.9 | 123.4 | −0.037 | +0.177 | 4/6 |

Consistent with the development uncertainty: gain over CC at 5–15 min, none at 20–35 min, slight loss at
40–60 min; better than persistence at every horizon. Final test (10-05 – 10-09) not run.

## 6. Final test result (sealed, run once 2026-10-10; design unchanged)

Test 2026-10-05 – 10-09 (5 days, kc mean 0.82, mostly clear with variable spells). Models retrained on data
to 10-04 (validation 09-28 – 10-04).

| Horizon | n | RMSE XGB | RMSE CC | RMSE persistence | skill vs CC | skill vs persistence | days better than CC | MBE XGB | MBE CC | MAE XGB | MAE CC |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 5 min | 479 | 86.1 | 89.2 | 96.5 | +0.036 | +0.108 | 5/5 | −9.0 | 2.2 | 52.4 | 50.9 |
| 10 min | 474 | 99.7 | 105.3 | 120.3 | +0.053 | +0.171 | 5/5 | −14.3 | 3.7 | 65.3 | 62.4 |
| 15 min | 469 | 104.8 | 108.1 | 125.8 | +0.030 | +0.167 | 4/5 | −18.9 | 4.7 | 73.0 | 66.6 |
| 30 min | 454 | 109.2 | 117.4 | 147.4 | +0.070 | +0.259 | 5/5 | −20.3 | 9.6 | 78.5 | 75.1 |
| 45 min | 439 | 113.5 | 116.8 | 150.9 | +0.028 | +0.248 | 1/5 | −31.7 | 13.1 | 89.1 | 76.0 |
| 60 min | 424 | 113.2 | 111.9 | 141.7 | −0.012 | +0.201 | 1/5 | −32.8 | 15.6 | 89.9 | 72.0 |

By target elevation: gains at 30–45° (+0.06 to +0.19), losses at 45–60° (−0.04 to −0.09) for h ≥ 3.

## 7. Conclusions over the three evaluations

| Horizon | development (18 d) | checkpoint (6 d) | final (5 d) |
|---|---|---|---|
| 5 min | +0.050 | +0.028 | +0.036 |
| 10 min | +0.071 | +0.037 | +0.053 |
| 15 min | +0.071 | +0.016 | +0.030 |
| 30 min | +0.060 | +0.002 | +0.070 |
| 45 min | +0.040 | −0.006 | +0.028 |
| 60 min | +0.011 | −0.037 | −0.012 |

(RMSE skill against CC.)

- 5–15 min: positive in all three, +0.02 to +0.07. 20–45 min: positive on average but not consistent
  (checkpoint ≈ 0; final 45 min better only on 1 of 5 days). 60 min: no skill.
- Better than persistence at every horizon in every evaluation (+0.07 to +0.26).
- Final test: XGBoost negative bias growing with horizon (−9 to −33 W/m²) while CC is slightly positive;
  MAE worse than CC, RMSE better (fewer large errors, more small ones). Losses at 45–60° elevation in all
  roles at longer horizons. The final period has lower sun than most training data (seasonal shift), and
  this sensor's kc depends on elevation; this is a likely but untested cause.
- Any design change made now can only be tested on data after 2026-10-09 (new sealed period).
