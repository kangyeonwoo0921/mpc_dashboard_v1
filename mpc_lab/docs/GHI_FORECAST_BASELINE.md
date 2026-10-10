# GHI Forecast Baselines (forecast step 2)

Code: `src/greenhouse_mpc/forecast/` (`baselines.py`, `metrics.py`, `config.py`, `baseline_pipeline.py`).
Config: `config/ghi_forecast.yaml`. Tests: `tests/test_forecast_baselines.py`.
Input: `data/processed/clear_sky_index/kc_5min.parquet` (CLEARSKY_REFERENCE.md section 4).

```powershell
python -m greenhouse_mpc.forecast.baseline_pipeline   # -> data/processed/forecast_baseline/
```

## 1. Sources (originals read; PDFs in `mpc_lab/reference/papers/`, git-excluded)

| Source | Used for |
|---|---|
| Yang (2019), Making reference solar forecasts with climatology, persistence, and their optimal convex combination, *Solar Energy* 193:981–985, doi:10.1016/j.solener.2019.10.006 | RMSE skill `s = 1 − RMSE(f,x)/RMSE(r,x)` (Eq. 2); climatology RMSE = σ (Eq. 3); h-step persistence RMSE = σ·√(2[1−ρ(h)]) (Eq. 4); convex combination `α x_{i−h} + (1−α) µ` (Eq. 5) with optimal `α = ρ(h)` (Eq. 8); applied to the clear-sky index, GHI = kc forecast × clear-sky GHI; 5-min data at 15–75 min ahead (CAISO RTED case); zenith filter Z < 85°; window averages are multiple-valued climatology, not persistence (section 4) |
| Yang et al. (2020), Verification of deterministic solar forecasts, *Solar Energy* 210:20–37 | RMSE skill against the optimal CC of single-valued internal climatology and h-step-ahead clear-sky persistence "strongly recommended"; internal = derived from the samples being verified; mean from filtered data, lag-h autocorrelation keeping the original temporal spacing; night excluded (e.g. Z < 85°); out-of-sample tests for verification; no trimming because of large errors; mean-normalised nRMSE not valid for comparing skill across situations, normalisation values must be tabulated; small MBE is a prerequisite, not a critical metric; "smart persistence" (Inman et al.) there means cloudiness-index persistence |
| Chu et al. (2021), *iScience* 24(10):103136 | `I_hat(t+FH) = I(t)/I_clr(t) · I_clr(t+FH)` (called smart persistence there); MBE, MAE, RMSE; intra-hour = horizon < 1 h |
| Alonso-Suárez et al. (2022), arXiv:2203.13819 | window mean of the last n kc ("smart persistence with varying n"); CC best benchmark at 10-min basis, window mean close to it in the first hour |

The same n = 1 forecast is "smart persistence" in Chu et al. and "persistence"/"clear-sky persistence"
in Yang and Alonso-Suárez, while Yang et al. (2020) use "smart persistence" for another reference.
The code therefore says `persistence` (Yang's term) and never "smart persistence".

## 2. Decisions and conventions

| Item | Value | Basis |
|---|---|---|
| Horizons | 1–12 steps = 5–60 min | user decision 2026-10-10 (option A) |
| Primary reference | `convex_combination` | Yang (2019); Yang et al. (2020) |
| Also reported | persistence, climatology; window mean n = 3, 6, 12 (comparison only) | as above; Alonso-Suárez et al. |
| Low-sun filter | sun elevation ≥ 20° (Z ≤ 70°) | stricter than Z < 85° (Yang) / Z ≤ 83° (Gueymard 2017) because of this sensor |

- 5-min bins labelled by start; issued when bin `t` closes; target bin `t + h`.
- Internal statistics from the evaluated table: µ, σ² over valid kc; ρ(h) from pairs exactly h steps apart
  on the regular grid (no gap bridged). Deviation: Yang et al. suggest ρ(h) on unfiltered data; here
  values below 20° are excluded because the sensor distorts them (CLEARSKY_REFERENCE.md section 3).
- Per horizon every method is scored on the same targets (target valid and all methods' inputs valid;
  the window mean n = 12 sets the common set).
- These reference forecasts use internal (in-sample) statistics by definition. The XGBoost model must
  be verified out-of-sample (chronological split, decided later).
- GHI is the sensor reading (angular response not corrected).

## 3. Results (baseline dataset 7b09b9b94ab3adea from kc 186a4c04d154f8fb)

µ = 0.697, σ² = 0.0683. Mean measured GHI of each evaluation set (normaliser) 458–465 W/m².

| Horizon (min) | n | ρ(h) | RMSE climatology | RMSE persistence | RMSE CC | MBE CC | MAE CC | nRMSE CC |
|---|---|---|---|---|---|---|---|---|
| 5 | 4938 | 0.877 | 151.2 | 81.6 | 78.7 | 2.2 | 48.8 | 0.172 |
| 10 | 4880 | 0.787 | 151.3 | 103.9 | 97.9 | 3.9 | 65.1 | 0.213 |
| 15 | 4826 | 0.733 | 151.6 | 112.5 | 104.7 | 5.1 | 72.2 | 0.228 |
| 30 | 4664 | 0.630 | 152.1 | 128.6 | 117.0 | 7.7 | 84.5 | 0.254 |
| 45 | 4505 | 0.569 | 152.3 | 134.1 | 120.9 | 8.4 | 89.8 | 0.261 |
| 60 | 4341 | 0.529 | 152.4 | 135.5 | 122.1 | 9.5 | 91.2 | 0.262 |

(W/m²; all horizons in `baseline_metrics.csv`.)

RMSE skill against CC: persistence −0.04 (5 min) to −0.11 (60 min); climatology −0.92 to −0.25; window
mean between −0.05 and +0.02 after 10 min (n = 6 best at 15–45 min, +0.01 to +0.02). As in Yang (2019),
ρ(h) > 0.5 at every horizon, so persistence beats climatology and CC beats both.

**Benchmark for the XGBoost model:** RMSE skill against CC per horizon (≈ 79–122 W/m² RMSE to beat),
computed on the model's out-of-sample test period.
