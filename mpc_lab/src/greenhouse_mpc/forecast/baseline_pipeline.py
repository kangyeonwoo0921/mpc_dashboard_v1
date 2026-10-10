"""Reference-forecast evaluation on the kc table.

    python -m greenhouse_mpc.forecast.baseline_pipeline     # writes data/processed/forecast_baseline/

Writes ``baseline_metrics.csv`` (per horizon x method) and ``dataset_manifest.json`` (internal
statistics, config, and the kc ``dataset_id`` evaluated in ``derived_from``).
"""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from ..ingestion.outside_schema import MPC_LAB_DIR
from ..ingestion.versioning import build_version, file_sha256, read_parquet_version
from .baselines import evaluate
from .config import load_forecast_config

PIPELINE = "forecast_baseline"
PIPELINE_VERSION = "1.1"       # 1.1: causal kc_input as forecast input
KC_FILE = MPC_LAB_DIR / "data" / "processed" / "clear_sky_index" / "kc_5min.parquet"
OUTPUT_DIR = MPC_LAB_DIR / "data" / "processed" / "forecast_baseline"


def run_baseline_pipeline(config=None, kc_file=KC_FILE, output_dir=OUTPUT_DIR, write=True):
    config = config or load_forecast_config()
    kc_file = Path(kc_file)
    table = pd.read_parquet(kc_file)
    results, stats = evaluate(table, config.value("horizon_steps"), config.value("reference"),
                              config.value("supplementary_window_n"))
    meta = {"file": f"{kc_file.parent.name}/{kc_file.name}", "sha256": file_sha256(kc_file), "data_rows": len(table)}
    version = build_version(PIPELINE, PIPELINE_VERSION, [meta], config.fingerprint(), MPC_LAB_DIR)
    source = read_parquet_version(kc_file)
    version["derived_from"] = None if source is None else {"pipeline": source["pipeline"], "dataset_id": source["dataset_id"]}
    statistics = asdict(stats)
    statistics["rho"] = {str(k): v for k, v in stats.rho.items()}
    statistics["pairs"] = {str(k): v for k, v in stats.pairs.items()}
    version["internal_statistics"] = statistics
    version["reference"] = config.value("reference")
    if write:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        results.to_csv(output_dir / "baseline_metrics.csv", index=False, float_format="%.6g", lineterminator="\n")
        version["outputs"] = {"baseline_metrics.csv": file_sha256(output_dir / "baseline_metrics.csv")}
        (output_dir / "dataset_manifest.json").write_text(
            json.dumps(version, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return results, version


def method_label(row):
    return row.method if pd.isna(row.n) else f"{row.method}_{int(row.n)}"


def main(argv=None):
    parser = argparse.ArgumentParser(description="reference GHI forecasts (persistence, climatology, CC)")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args(argv)
    results, version = run_baseline_pipeline(output_dir=args.output_dir, write=not args.no_write)
    print(json.dumps({"dataset_id": version["dataset_id"], "derived_from": version["derived_from"],
                      "mu": version["internal_statistics"]["mu"]}, indent=2))
    results["label"] = results.apply(method_label, axis=1)
    print(results.pivot(index="horizon_min", columns="label", values="skill").round(3).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
