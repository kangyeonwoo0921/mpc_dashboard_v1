# Outside Data Pipeline (Step 1A)

Requirement source: `docs/mpc_reference/claude_code_step1A_outside_preprocessing_prompt.md`.
Code: `src/greenhouse_mpc/ingestion/`. Contract and rules: `config/outside_data.yaml`.
Tests: `tests/test_outside_ingestion.py`.

```text
raw exports (read-only)  data/ouside_data/outside_*.csv
  → parsed rows          one row per raw row: source file/line, raw text, layout, schema status, dedup status
  → observations         one per timestamp, per-variable value / flags / status
  → canonical 1-min      complete minute grid
  → canonical 5-min      complete 5-min grid, coverage per variable
```

Run (mpc_lab directory, `sfes` environment):

```powershell
python -m greenhouse_mpc.ingestion.outside_pipeline            # writes data/processed/outside/
python -m greenhouse_mpc.ingestion.outside_pipeline --no-write # summary only
```

Outputs (`data/processed/outside/`, git-ignored, regenerated on every run): `parsed_rows.parquet`,
`outside_1min.parquet`, `outside_5min.parquet`, `outside_5min.csv` (review copy), `qc_summary.json`,
`qc_daily.csv`, `dataset_manifest.json`.

## 1. Continuous accumulation

- Every run reprocesses **all** files in the raw folder. Adding a new export (overlapping or not) and
  re-running produces the merged canonical dataset. File names are never used for date ranges.
- Deterministic and idempotent: sorted inputs, explicit tie-breaks, no wall-clock values in outputs
  (verified: two runs give byte-identical files).
- `outside_pipeline.preprocess(parsed, config)` is the single shared entry point. The retraining path
  calls it on all exports; the real-time path will call it on a recent window of parsed rows (the
  live adapter only has to produce the same parsed-row columns). Rolling rules (freeze) need history
  inside that window.
- Volume: ~1 400 rows/day; a full rerun of two months takes ~10 s, so incremental state is not needed
  yet. Parquet outputs allow switching to partitioned/incremental writes later without a format change.

### Dataset version (`ingestion/versioning.py`)

- `dataset_id` = sha256 over {pipeline name, `PIPELINE_VERSION`, sha256 of every input file,
  config fingerprint}, first 16 hex characters. The config fingerprint (`outside_schema.config_fingerprint`)
  covers every loaded value that can change the data (layouts, contract, QC values and statuses, site)
  and excludes file locations.
- Not part of the id, recorded as provenance: git commit, whether `src/` or `config/` had uncommitted
  changes, Python/library versions.
- Written to `qc_summary.json` (`dataset_version`), `dataset_manifest.json` (plus sha256 of every output
  file) and the schema metadata of each Parquet file (`versioning.read_parquet_version`).
- Bump `PIPELINE_VERSION` in `outside_pipeline.py` whenever parsing, QC or resampling logic changes.
- Reproduce a version: `python -m greenhouse_mpc.ingestion.outside_pipeline --files <inputs listed in
  the manifest>` with the same config and pipeline version gives the same `dataset_id` and data.
- A trained model must store the `dataset_id` (and a copy of the manifest) it was trained on.

## 2. Raw schema (observed 2026-10-10)

| Export | Header | Row shapes |
|---|---|---|
| `outside_2026-07-28_2026-08-31.csv` | 7 columns incl. 외부습도 | 7 fields with RH (to 2026-08-03); 6 fields without RH; 7 fields = 6 + empty trailing; 7 fields = 6 + extra value |
| `outside_2026-09-01_2026-10-09.csv` | 6 columns | 6 fields; 7 fields = 6 + empty trailing; 7 fields = 6 + extra value |

Layout rule (`outside_reader.match_layout`): the header is not trusted. A row matches a layout when its
field count equals the layout length **and** the wind-direction token (`"<deg>° <compass>"`) sits at the
layout's wind position. Exactly one empty trailing field is removed first (auto-correction, counted).
Anything else is `schema_status = anomaly`: raw text kept, values not parsed, observation flagged
SCHEMA_ANOMALY. The 103 "6 values + extra value" rows are left as anomalies because the extra value
cannot be attributed with certainty.

## 3. Canonical variables (data contract)

| canonical | raw | unit | 5-min aggregation | note |
|---|---|---|---|---|
| `ghi` | 일사센서 | W/m² | mean | instantaneous global shortwave above the cover |
| `t_out` | 외부온도 | °C | mean | |
| `rh_out` | 외부습도 | % | mean | only until 2026-08-03 in the delivered exports |
| `wind_speed` | 외부풍속 | **unresolved** | mean | unit not stated |
| `wind_dir` | 외부풍향 | deg | circular mean (+ `wind_dir_r`) | 16-point compass; degrees printed truncated (22, 67, …) and used as given |
| `solar_energy_cumulative` | 누적일사량 | **unresolved** | last | not GHI; resets at irregular times (mostly ~05:30 and ~00:00); never averaged |

Timestamps: Korean local time, stored timezone-aware (`Asia/Seoul`). 1-min and 5-min bins are
left-closed and labelled by their start.

## 4. Deduplication policy

| Case | Handling |
|---|---|
| Same timestamp, identical values | first by (file name, line) kept; others `dedup_status = duplicate`; observation flag DUPLICATE |
| Same timestamp, different values | **no value adopted**; all rows `conflicting`; observation values missing, flag CONFLICTING_DUPLICATE |
| Schema-anomaly row only | observation with missing values, flag SCHEMA_ANOMALY |
| Unparseable timestamp | row kept in `parsed_rows` as `unplaced` |

## 5. QC flags and statuses

Per variable: `<var>` (usable value), `<var>_raw` (observation level), `<var>_flags` (bit mask),
`<var>_status`.

| Flag | Bit | Rule (config) | Effect |
|---|---|---|---|
| MISSING | 1 | no value | status missing |
| DUPLICATE | 2 | exact duplicates merged | info |
| CONFLICTING_DUPLICATE | 4 | §4 | missing |
| SCHEMA_ANOMALY | 8 | §2, or a non-numeric field | missing |
| SENSOR_FREEZE | 16 | `ghi` identical and > 0 for ≥ `freeze_min_duration_minutes.ghi` (60, provisional), run reaching daylight; runs continue across data gaps (stale value after an outage) | **suspect, value kept** |

**Causal input status (pipeline 1A.2).** The freeze test flags the whole run once it lasts the minimum duration, so the first part of a run is flagged using later data. For forecast inputs every variable also has `<var>_input_status` (observation, 1-min, 5-min) and `<var>_input` (1-min, 5-min): identical rules, except a row is freeze-flagged only when the run up to and including it already lasts the minimum duration (and, for GHI, has already reached daylight), and interpolated minutes are never used. Targets keep `<var>_status`. Conflicting duplicates are still resolved with all rows (later-arriving rows; negligible, documented).
| OUT_OF_RANGE | 32 | outside `ranges` (impossible values only), or `ghi > 0` with sun below `night_elevation_deg` (−6°) | invalid → NaN |
| SUSPECTED_COMMUNICATION_ERROR | 64 | `t_out = wind_speed = wind_dir = ghi = 0` (and RH 0 or absent) together | invalid for all variables |
| INTERPOLATED | 128 | optional gap fill (off) | status interpolated |
| SUSPICIOUS_ZERO | 256 | `ghi == 0` with sun above `daylight_elevation_deg` (5°, provisional), not a communication row | **suspect, value kept** |
| LOW_COVERAGE | 512 | 5-min coverage below `min_coverage_5min` (unset) | info |

Statuses: `observed`, `suspect` (flag only), `invalid` (value NaN, raw kept), `missing`,
`interpolated`. Night GHI = 0 is valid. Daylight is computed with pvlib from the site in
`config/greenhouse.yaml` (lat 35.837, lon 126.709, 3 m; operator report, provisional).

## 6. Resampling

- **1-min:** complete minute grid from the first to the last observed minute; minutes without rows
  are explicit `missing` rows (`n_rows = 0`) so lags and windows see real gaps. Several rows in one
  minute (sub-minute bursts on 2026-07-28, 08-03, 08-04) are aggregated with the same rules as 5-min.
  `first_source` points to the raw file:line.
- **5-min:** from the 1-min table by timestamp. Best member status wins; value = aggregate of usable
  members (observed, interpolated; suspect excluded while `aggregate_suspect` is false, a bin with only
  suspect members keeps their aggregate as suspect). `<var>_n_obs`, `<var>_n_interp`,
  `<var>_coverage = n_obs / 5`, OR-ed flags, `sun_elevation_deg` at the bin centre.
- Interpolation: off by default for every variable; never for `ghi`, `wind_dir`, cumulative.

## 7. Unresolved (not filled with assumed values)

- `wind_speed` unit; `solar_energy_cumulative` unit and reset logic
- sensor manufacturers and measuring ranges (upper GHI, temperature, wind limits not checked)
- freeze threshold (60 min for GHI is provisional; other variables off)
- daylight-zero elevation (5°) and night elevation (−6°) are provisional
- interpolation maximum gaps (off); 5-min minimum coverage (not set; coverage always reported)
- exact weather-station coordinates (greenhouse site coordinates are used)
- conflicting duplicates: no value adopted (1 case: a valid row vs an all-zero row)
- outdoor humidity is absent after 2026-08-03 in the delivered exports
