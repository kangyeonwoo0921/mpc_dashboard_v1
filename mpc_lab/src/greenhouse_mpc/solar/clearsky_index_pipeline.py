"""Clear-sky index table on the 5-min grid.

    python -m greenhouse_mpc.solar.clearsky_index_pipeline     # writes data/processed/clear_sky_index/

Joins ``outside/outside_5min.parquet`` (measured GHI) and ``clearsky/clearsky_5min.parquet`` on
``timestamp`` and writes ``kc_5min.parquet`` + ``dataset_manifest.json``. The dataset id depends on both
input files, the clear-sky config including the clear_sky_index section, and the pipeline version;
both source dataset ids are recorded in ``derived_from``.
"""

import argparse
import json
from pathlib import Path

import pandas as pd

from ..ingestion.outside_schema import MPC_LAB_DIR
from ..paths import processed_dir
from ..ingestion.versioning import build_version, file_sha256, read_parquet_version, write_parquet
from .clearsky import load_clearsky_config
from .clearsky_index import KC_STATUSES, clear_sky_index

PIPELINE = "clear_sky_index"
PIPELINE_VERSION = "1.1"       # 1.1: kc_input / kc_input_status (causal inputs)
PROCESSED = processed_dir()
OUTSIDE_FILE = PROCESSED / "outside" / "outside_5min.parquet"
CLEARSKY_FILE = PROCESSED / "clearsky" / "clearsky_5min.parquet"
OUTPUT_DIR = PROCESSED / "clear_sky_index"


def _source(path):
    version = read_parquet_version(path)
    return None if version is None else {"pipeline": version["pipeline"], "dataset_id": version["dataset_id"]}


def run_clearsky_index_pipeline(config=None, outside_file=OUTSIDE_FILE, clearsky_file=CLEARSKY_FILE,
                                output_dir=OUTPUT_DIR, write=True):
    config = config or load_clearsky_config()
    outside_file, clearsky_file = Path(outside_file), Path(clearsky_file)
    outside = pd.read_parquet(outside_file, columns=["timestamp", "ghi", "ghi_status", "ghi_input", "ghi_input_status"])
    clearsky = pd.read_parquet(clearsky_file, columns=["timestamp", "ghi_clear", "sun_elevation_deg", "sun_azimuth_deg"])
    frame = clear_sky_index(outside, clearsky, config)
    metas = [{"file": f"{p.parent.name}/{p.name}", "sha256": file_sha256(p), "data_rows": int(n)}
             for p, n in ((outside_file, len(outside)), (clearsky_file, len(clearsky)))]
    version = build_version(PIPELINE, PIPELINE_VERSION, metas, config.fingerprint(include_index=True), MPC_LAB_DIR)
    version["derived_from"] = [_source(outside_file), _source(clearsky_file)]
    counts = frame.kc_status.value_counts()
    input_counts = frame.kc_input_status.value_counts()
    summary = {"kc_status_counts": {s: int(counts.get(s, 0)) for s in KC_STATUSES},
               "kc_input_status_counts": {s: int(input_counts.get(s, 0)) for s in KC_STATUSES},
               "kc": {k: float(v) for k, v in frame.kc.describe().items()}}
    if write:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        write_parquet(frame, output_dir / "kc_5min.parquet", version)
        (output_dir / "dataset_manifest.json").write_text(json.dumps(
            {**version, "summary": summary, "outputs": {"kc_5min.parquet": file_sha256(output_dir / "kc_5min.parquet")}},
            ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return frame, version, summary


def main(argv=None):
    parser = argparse.ArgumentParser(description="clear-sky index (kc) table")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args(argv)
    frame, version, summary = run_clearsky_index_pipeline(output_dir=args.output_dir, write=not args.no_write)
    print(json.dumps({"dataset_id": version["dataset_id"], "derived_from": version["derived_from"],
                      "rows": len(frame), **summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
