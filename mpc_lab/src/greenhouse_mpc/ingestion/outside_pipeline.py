"""Step 1A outside pipeline: raw exports -> canonical 1-min / 5-min outside data + QC reports.

Run (mpc_lab directory, sfes environment):

    python -m greenhouse_mpc.ingestion.outside_pipeline            # all exports in config.raw_dir
    python -m greenhouse_mpc.ingestion.outside_pipeline --no-write # summary only
    python -m greenhouse_mpc.ingestion.outside_pipeline --files a.csv b.csv   # reproduce a version

Every run reprocesses *all* raw exports in the raw folder, so adding a new (possibly overlapping)
export and re-running gives the merged canonical dataset; identical inputs give identical outputs
(deterministic ordering, no wall-clock values in the outputs). ``preprocess`` is the shared entry point
for batch/retraining datasets and for the real-time path on a recent window of parsed rows.

Each run records a dataset version (versioning.py): ``dataset_id`` in qc_summary.json, in
dataset_manifest.json (with output file hashes) and embedded in every Parquet file.
"""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .outside_reader import read_outside_exports
from .outside_schema import MPC_LAB_DIR, VARIABLES, config_fingerprint, load_outside_config
from .qc import QC, apply_qc, deduplicate
from .resample import to_five_minute, to_minute
from .versioning import build_version, file_sha256, write_parquet

PIPELINE = "outside"
# Bump when the processing logic changes in a way that can change outputs (parsing, QC, resampling).
PIPELINE_VERSION = "1A.2"       # 1A.2: causal <var>_input / <var>_input_status columns

OUTPUT_FILES = {"parsed": "parsed_rows.parquet", "minute": "outside_1min.parquet",
                "five_min": "outside_5min.parquet", "five_min_csv": "outside_5min.csv",
                "summary": "qc_summary.json", "daily": "qc_daily.csv", "manifest": "dataset_manifest.json"}


@dataclass
class OutsideResult:
    parsed: pd.DataFrame          # every raw row with schema / dedup status (traceability)
    observations: pd.DataFrame    # one QC'd observation per timestamp
    minute: pd.DataFrame          # canonical 1-min
    five_min: pd.DataFrame        # canonical 5-min
    summary: dict
    daily: pd.DataFrame
    version: dict                 # dataset version record (versioning.build_version)


def preprocess(parsed, config):
    """Shared preprocessing: parsed rows -> (parsed with dedup status, QC'd observations, 1-min, 5-min)."""
    parsed, observations = deduplicate(parsed)
    observations = apply_qc(observations, config)
    minute = to_minute(observations, config)
    five_min = to_five_minute(minute, config)
    return parsed, observations, minute, five_min


def _flag_count(frame, name, flag):
    return int(((frame[f"{name}_flags"] & int(flag)) != 0).sum())


def build_summary(parsed, observations, minute, five_min, metas, config):
    placed = parsed[parsed["timestamp_ok"]]
    anomalies = parsed[parsed["schema_status"] == "anomaly"]
    per_variable = {}
    for name in VARIABLES:
        statuses = observations[f"{name}_status"].value_counts().to_dict()
        per_variable[name] = {
            "unit": config.variables[name]["unit"],
            "observations": {s: int(statuses.get(s, 0)) for s in ("observed", "suspect", "invalid", "missing")},
            "flags": {flag.name: _flag_count(observations, name, flag)
                      for flag in (QC.OUT_OF_RANGE, QC.SUSPECTED_COMMUNICATION_ERROR, QC.SENSOR_FREEZE,
                                   QC.SUSPICIOUS_ZERO, QC.SCHEMA_ANOMALY, QC.CONFLICTING_DUPLICATE)},
            "minute_status": {k: int(v) for k, v in minute[f"{name}_status"].value_counts().sort_index().items()},
            "five_min_mean_coverage": round(float(five_min[f"{name}_coverage"].mean()), 4),
            "five_min_bins_with_data": int((five_min[f"{name}_n_obs"] > 0).sum()),
        }
    comm = observations["ghi_flags"].to_numpy() & int(QC.SUSPECTED_COMMUNICATION_ERROR)
    return {
        "dataset_version": build_version(PIPELINE, PIPELINE_VERSION, metas, config_fingerprint(config), MPC_LAB_DIR),
        "input_files": metas,
        "actual_start": placed["timestamp"].min().isoformat() if len(placed) else None,
        "actual_end": placed["timestamp"].max().isoformat() if len(placed) else None,
        "raw_row_count": int(len(parsed)),
        "parsed_row_count": int(parsed["layout"].notna().sum()),
        "unplaced_rows_bad_timestamp": int((~parsed["timestamp_ok"]).sum()),
        "layout_counts": {str(k): int(v) for k, v in parsed["layout"].fillna("none").value_counts().sort_index().items()},
        "schema_status_counts": {k: int(v) for k, v in parsed["schema_status"].value_counts().sort_index().items()},
        "schema_anomaly_count": int(len(anomalies)),
        "schema_anomaly_examples": [f"{r.source_file}:{r.source_line} {r.raw_text}" for r in anomalies.head(5).itertuples()],
        "duplicate_count": int((parsed["dedup_status"] == "duplicate").sum()),
        "conflicting_duplicate_rows": int((parsed["dedup_status"] == "conflicting").sum()),
        "conflicting_duplicate_timestamps": int(parsed.loc[parsed["dedup_status"] == "conflicting", "timestamp"].nunique()),
        "observation_count": int(len(observations)),
        "variables": per_variable,
        "freeze_flagged_ghi_observations": _flag_count(observations, "ghi", QC.SENSOR_FREEZE),
        "suspected_communication_error_observations": int((comm != 0).sum()),
        "minute_row_count": int(len(minute)),
        "minute_rows_without_observation": int((minute["n_rows"] == 0).sum()),
        "five_min_row_count": int(len(five_min)),
        "site_for_daylight": None if config.site is None else vars(config.site),
        "actions": {
            "auto_corrected": {
                "trailing_empty_field_removed_rows": int((parsed["schema_status"] == "trailing_empty_removed").sum()),
                "exact_duplicate_rows_merged": int((parsed["dedup_status"] == "duplicate").sum()),
                "wind_direction_text_to_degrees": "all parsed rows ('<deg>° <compass>' -> deg)",
            },
            "invalidated_value_set_nan_raw_kept": ["OUT_OF_RANGE", "SUSPECTED_COMMUNICATION_ERROR"],
            "flag_only_value_kept": ["SENSOR_FREEZE", "SUSPICIOUS_ZERO", "DUPLICATE"],
            "not_adopted": ["CONFLICTING_DUPLICATE (no value chosen)", "SCHEMA_ANOMALY rows (kept unparsed)"],
            "unresolved_config": config.unresolved(),
            "unresolved_units": sorted(n for n, spec in config.variables.items() if spec["unit"] is None),
        },
    }


def build_daily(parsed, observations, minute, five_min):
    day = lambda ts: ts.dt.date.astype(str)
    rows = parsed[parsed["timestamp_ok"]]
    daily = pd.DataFrame({
        "raw_rows": rows.groupby(day(rows["timestamp"])).size(),
        "schema_anomalies": rows[rows["schema_status"] == "anomaly"].groupby(day(rows["timestamp"])).size(),
        "duplicates": rows[rows["dedup_status"] == "duplicate"].groupby(day(rows["timestamp"])).size(),
        "conflicts": rows[rows["dedup_status"] == "conflicting"].groupby(day(rows["timestamp"])).size(),
        "minutes_with_obs": minute[minute["n_rows"] > 0].groupby(day(minute["timestamp"])).size(),
    })
    obs_day = day(observations["timestamp"])
    for name, flag in (("ghi_freeze", QC.SENSOR_FREEZE), ("comm_error", QC.SUSPECTED_COMMUNICATION_ERROR),
                       ("ghi_out_of_range", QC.OUT_OF_RANGE), ("ghi_daylight_zero", QC.SUSPICIOUS_ZERO)):
        hit = (observations["ghi_flags"] & int(flag)) != 0
        daily[name] = hit.groupby(obs_day).sum()
    minute_day = day(minute["timestamp"])
    for name in VARIABLES:
        for status in ("observed", "suspect", "invalid", "missing"):
            daily[f"{name}_{status}_min"] = (minute[f"{name}_status"] == status).groupby(minute_day).sum()
    daily["ghi_5min_mean_coverage"] = five_min.groupby(day(five_min["timestamp"]))["ghi_coverage"].mean().round(3)
    daily = daily.fillna(0)
    daily[[c for c in daily.columns if c != "ghi_5min_mean_coverage"]] = daily[[c for c in daily.columns if c != "ghi_5min_mean_coverage"]].astype(np.int64)
    daily.index.name = "date"
    return daily.reset_index()


def write_outputs(result, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_parquet(result.parsed, output_dir / OUTPUT_FILES["parsed"], result.version)
    write_parquet(result.minute, output_dir / OUTPUT_FILES["minute"], result.version)
    write_parquet(result.five_min, output_dir / OUTPUT_FILES["five_min"], result.version)
    csv = result.five_min.copy()
    csv["timestamp"] = csv["timestamp"].map(lambda t: t.isoformat())
    csv.to_csv(output_dir / OUTPUT_FILES["five_min_csv"], index=False, encoding="utf-8-sig", lineterminator="\n")
    (output_dir / OUTPUT_FILES["summary"]).write_text(
        json.dumps(result.summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result.daily.to_csv(output_dir / OUTPUT_FILES["daily"], index=False, encoding="utf-8-sig", lineterminator="\n")
    outputs = {name: file_sha256(output_dir / name) for key, name in sorted(OUTPUT_FILES.items()) if key != "manifest"}
    manifest = {**result.version, "outputs": outputs}
    (output_dir / OUTPUT_FILES["manifest"]).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {key: output_dir / name for key, name in OUTPUT_FILES.items()}


def run_outside_pipeline(config=None, paths=None, output_dir=None, write=True):
    config = config or load_outside_config()
    parsed, metas = read_outside_exports(config, paths)
    if parsed.empty:
        raise ValueError(f"no outside rows found in {config.raw_dir} ({config.file_glob})")
    parsed, observations, minute, five_min = preprocess(parsed, config)
    summary = build_summary(parsed, observations, minute, five_min, metas, config)
    result = OutsideResult(parsed, observations, minute, five_min, summary,
                           build_daily(parsed, observations, minute, five_min), summary["dataset_version"])
    if write:
        write_outputs(result, output_dir or config.output_dir)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", help="outside_data.yaml path (default: mpc_lab/config)")
    parser.add_argument("--output-dir", help="override output directory")
    parser.add_argument("--no-write", action="store_true", help="only print the summary")
    parser.add_argument("--files", nargs="+", help="process only these exports (e.g. the inputs of a manifest)")
    args = parser.parse_args(argv)
    result = run_outside_pipeline(load_outside_config(args.config), paths=args.files,
                                  output_dir=args.output_dir, write=not args.no_write)
    print(json.dumps(result.summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
