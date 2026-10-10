"""Clear-sky reference tables on the canonical outside time grids.

    python -m greenhouse_mpc.solar.clearsky_pipeline            # writes data/processed/clearsky/

Reads only the timestamps of ``outside_1min.parquet`` / ``outside_5min.parquet`` and writes
``clearsky_1min.parquet`` and ``clearsky_5min.parquet`` keyed by the same ``timestamp`` (join on it),
plus ``dataset_manifest.json``. The dataset id depends on the time grids, the clear-sky config and
the pipeline version; the outside ``dataset_id`` the grids came from is recorded as ``derived_from``.
"""

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from ..ingestion.outside_schema import MPC_LAB_DIR
from ..ingestion.versioning import build_version, file_sha256, read_parquet_version, write_parquet
from .clearsky import clearsky_five_minute, clearsky_minute, load_clearsky_config

PIPELINE = "clearsky"
PIPELINE_VERSION = "1.0"       # bump when the computation changes
OUTSIDE_DIR = MPC_LAB_DIR / "data" / "processed" / "outside"
OUTPUT_DIR = MPC_LAB_DIR / "data" / "processed" / "clearsky"


def _grid_meta(name, timestamps):
    text = "\n".join(t.isoformat() for t in timestamps)
    return {"file": name, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "data_rows": int(len(timestamps))}


def run_clearsky_pipeline(config=None, outside_dir=OUTSIDE_DIR, output_dir=OUTPUT_DIR, write=True):
    config = config or load_clearsky_config()
    outside_dir = Path(outside_dir)
    minute_path, five_path = outside_dir / "outside_1min.parquet", outside_dir / "outside_5min.parquet"
    minute_grid = pd.read_parquet(minute_path, columns=["timestamp"])["timestamp"]
    five_grid = pd.read_parquet(five_path, columns=["timestamp"])["timestamp"]
    minute = clearsky_minute(minute_grid, config)
    five = clearsky_five_minute(five_grid, config)
    metas = [_grid_meta("outside_1min.parquet:timestamp", minute_grid), _grid_meta("outside_5min.parquet:timestamp", five_grid)]
    version = build_version(PIPELINE, PIPELINE_VERSION, metas, config.fingerprint(), MPC_LAB_DIR)
    source = read_parquet_version(five_path)
    version["derived_from"] = None if source is None else {"pipeline": source["pipeline"], "dataset_id": source["dataset_id"]}
    if write:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        write_parquet(minute, output_dir / "clearsky_1min.parquet", version)
        write_parquet(five, output_dir / "clearsky_5min.parquet", version)
        outputs = {name: file_sha256(output_dir / name) for name in ("clearsky_1min.parquet", "clearsky_5min.parquet")}
        (output_dir / "dataset_manifest.json").write_text(
            json.dumps({**version, "outputs": outputs}, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return minute, five, version


def main(argv=None):
    parser = argparse.ArgumentParser(description="clear-sky reference tables")
    parser.add_argument("--outside-dir", default=str(OUTSIDE_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args(argv)
    minute, five, version = run_clearsky_pipeline(outside_dir=args.outside_dir, output_dir=args.output_dir, write=not args.no_write)
    print(json.dumps({"dataset_id": version["dataset_id"], "derived_from": version["derived_from"],
                      "minute_rows": len(minute), "five_min_rows": len(five)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
