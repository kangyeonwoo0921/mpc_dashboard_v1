# Clear-Sky Reference (GHI forecasting, step 1)

Code: `src/greenhouse_mpc/solar/clearsky.py`, `clearsky_pipeline.py`. Config: `config/solar_reference.yaml`.
Tests: `tests/test_clearsky.py`. Site: `config/greenhouse.yaml` (35.837 N, 126.709 E, 3 m; provisional).

```powershell
python -m greenhouse_mpc.solar.clearsky_pipeline     # -> data/processed/clearsky/
```

## 1. Models (chosen by the user, 2026-10-10)

| Step | Literature | pvlib call |
|---|---|---|
| Solar position | Reda & Andreas (2004), NREL SPA | `solarposition.get_solarposition(method="nrel_numpy")`, apparent zenith |
| Pressure | standard atmosphere at site altitude (no site pressure, G-6) | `atmosphere.alt2pres` |
| Air mass | Kasten & Young (1989) | `get_relative_airmass(model="kastenyoung1989")` → `get_absolute_airmass` |
| Linke turbidity | Remund et al. (2003), SoDa monthly climatology | `clearsky.lookup_linke_turbidity(interp_turbidity=True)` |
| Extraterrestrial | Spencer (1971), solar constant 1366.1 W/m² | `irradiance.get_extra_radiation(method="spencer")` |
| Clear sky | Ineichen & Perez (2002) | `clearsky.ineichen(perez_enhancement=False)` |

Not in the user's reference list but required by the models (recorded as provisional): Spencer (1971)
extraterrestrial irradiance with solar constant 1366.1 W/m², standard-atmosphere pressure,
`perez_enhancement = false`. The explicit chain is tested to equal pvlib's standard
`Location.get_clearsky(model="ineichen")` result.

## 2. Outputs (`data/processed/clearsky/`, git-ignored)

`clearsky_1min.parquet`, `clearsky_5min.parquet`: same `timestamp` key as the outside tables (join on
it). Columns: `sun_zenith_apparent_deg`, `sun_elevation_deg`, `sun_azimuth_deg`, `pressure_pa`,
`airmass_relative`, `airmass_absolute`, `linke_turbidity`, `dni_extra_w_m2`, `ghi_clear`,
`dni_clear`, `dhi_clear` (W/m²).

- 1-min: evaluated at the bin centre (start + 30 s).
- 5-min: irradiance = mean of the five 1-min centre values (same rule as the measured 5-min mean);
  geometry at the bin centre (start + 150 s).
- `dataset_manifest.json`: own `dataset_id` (time grids + config fingerprint + pipeline version) and
  `derived_from` = the outside `dataset_id` whose grid was used.

The clear-sky index is computed by a separate pipeline (section 4).

## 3. Sensor check against the clear-sky reference (2026-10-10)

Clear days chosen objectively: daytime coverage > 95 %, variability index (Stein et al. 2012) 2.1–3.5,
daily energy ratio 0.86–0.92 → 2026-09-07, 09-08, 09-15, 10-08. Independent reference: ERA5
reanalysis hourly GHI (Open-Meteo archive, cloud cover 0 %).

| Solar elevation | Sensor | ERA5 | Ineichen | Sensor / ERA5 | Ineichen / ERA5 |
|---|---|---|---|---|---|
| 2–10° | 67 | 36 | 22 | 1.67 | 0.63 |
| 10–20° | 250 | 196 | 182 | 1.24 | 0.93 |
| 20–30° | 403 | 396 | 391 | 1.01 | 0.99 |
| 30–45° | 506 | 585 | 580 | 0.85 | 0.99 |
| 45–60° | 608 | 786 | 774 | 0.77 | 0.99 |

(hourly means, W/m²)

- Ineichen agrees with ERA5 within 1–7 % above 10° elevation; the sensor departs systematically
  (high at low sun, about −23 % near noon), symmetric morning/afternoon.
- Ruled out: clock offset, cloud enhancement, constant offset (night = 0), Linke turbidity error
  (changing TL cannot fit both ends), clear-sky model error, east–west tilt.
- Most consistent: non-cosine angular response of the sensor (log-log slope vs sin(elevation) 0.85
  measured vs 1.32 model); calibration gain possibly also off. Field information needed: sensor make /
  model, levelling, surroundings (photo). A measured reference (KMA ASOS) would confirm.
- Consequence: forecasting the sensor value is possible (consistent response), but sensor GHI is not
  true GHI; it must not enter ray tracing / Vanthoor energy terms as W/m² without correction.

## 4. Clear-sky index kc (2026-10-10)

Code: `src/greenhouse_mpc/solar/clearsky_index.py`, `clearsky_index_pipeline.py`. Config:
`solar_reference.yaml` → `clear_sky_index`. Tests: `tests/test_clearsky_index.py`.

```powershell
python -m greenhouse_mpc.solar.clearsky_index_pipeline   # -> data/processed/clear_sky_index/
```

`kc = GHI / GHI_clear` (definition; 5-min measured mean / 5-min clear-sky mean, same `timestamp`).

| Setting | Value | Basis |
|---|---|---|
| Low-sun exclusion | sun elevation at bin centre < 20° → no kc | site data (section 3: sensor / ERA5 1.24–1.67 below 20°). Literature (originals read): Z < 85° (Yang 2019; Yang et al. 2020); Z ≤ 83°, cosine error rising sharply beyond, especially photodiodes (Gueymard 2017). 20° is stricter because of this sensor |
| Upper bound | none | Gueymard (2017), *Solar Energy* 153:755–765: measured 1-min KT (GHI / extraterrestrial horizontal) up to 1.30 thermopile, 1.37 photodiode. Kept bins: kc max 1.59, KT max 0.935 |
| Accepted GHI | status `observed` only | interpolated / suspect / invalid / missing bins give no kc |

`kc_status`: `valid`, `night` (GHI_clear = 0), `low_sun`, `ghi_not_observed`.
Output `kc_5min.parquet`: timestamp, ghi, ghi_status, ghi_clear, sun_elevation_deg, sun_azimuth_deg, kc,
kc_status. The dataset id covers both input files and the full config; the clear_sky_index section is
excluded from the clear-sky table's own fingerprint, so kc settings do not change that table.

Result on the current data (dataset `186a4c04d154f8fb`, from outside `c4f4d28fe07aa1d2` + clearsky
`3c8fa6e136f09dfb`): 21,134 bins; valid 5,666, night 9,806, low_sun 3,088, ghi_not_observed 2,574.
kc mean 0.70, median 0.75, max 1.59; kc > 1 in 10.4 %, > 1.2 in 1.9 % of valid bins.

| Sun elevation | n | median kc | 95 % | 99 % |
|---|---|---|---|---|
| 20–30° | 1007 | 0.99 | 1.27 | 1.39 |
| 30–45° | 1687 | 0.81 | 1.00 | 1.09 |
| 45–60° | 2018 | 0.75 | 0.88 | 0.96 |
| > 60° | 954 | 0.70 | 0.81 | 0.86 |

The falling upper percentiles with elevation repeat the sensor's angular response (section 3): kc is
relative to the sensor, so a clear sky gives about 1.0 at 20–30° and about 0.8 near noon. Forecasting
models therefore receive sun elevation as an input. If the sensor is later corrected, kc and every
model trained on it are regenerated (new dataset id).
