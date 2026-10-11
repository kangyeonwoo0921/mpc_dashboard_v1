"""Out-of-sample evaluation of the XGBoost kc model against the reference forecasts.

    python -m greenhouse_mpc.forecast.model_pipeline --role development
    python -m greenhouse_mpc.forecast.model_pipeline --role checkpoint     # once (logged)
    python -m greenhouse_mpc.forecast.model_pipeline --role final          # once, sealed (logged)

For each fold of the role (split.py) and each horizon h: train on days before the validation days,
early-stop on the validation days, predict the test days. References on the same samples:
persistence, climatology and the convex combination with internal statistics of the test fold
(Yang 2019; Yang et al. 2020). Only the kc table up to the end of the role is read.

Outputs in ``data/processed/forecast_runs/<role>/``: predictions.parquet, metrics.csv (per fold and
pooled), daily_skill.csv, elevation_bands.csv, folds.json, models/, manifest.json. Every run is appended
to ``records/forecast_run_log.jsonl`` (tracked in git as the evidence for sealed runs); checkpoint and
final refuse a second run unless a reason is given, which is logged.
"""

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

from ..ingestion.outside_schema import MPC_LAB_DIR
from ..paths import processed_dir
from ..ingestion.versioning import file_sha256, git_state, library_versions, read_parquet_version
from .baselines import internal_statistics
from .config import load_forecast_config
from .features import build_samples
from .metrics import mae, mbe, rmse, skill
from .split import ROLES, day_of, make_folds, table_for_role

PIPELINE_VERSION = "1.0"
KC_FILE = processed_dir() / "clear_sky_index" / "kc_5min.parquet"
RUNS_DIR = processed_dir() / "forecast_runs"
LOG_FILE = MPC_LAB_DIR / "records" / "forecast_run_log.jsonl"
SEALED = ("checkpoint", "final")
FORECASTS = ("xgboost", "persistence", "climatology", "convex_combination")


class SealedRunError(RuntimeError):
    """A checkpoint/final role was already run; a logged reason is required to run it again."""


def _days(samples, start, end):
    d = samples.issue_day
    return samples[(d >= start) & (d <= end)]


def _fit(config, train, validation, features):
    params = config.section("model.xgboost")
    stopping = params.pop("early_stopping_rounds")
    model = xgb.XGBRegressor(**params, early_stopping_rounds=stopping)
    model.fit(train[features], train.target_kc, eval_set=[(validation[features], validation.target_kc)], verbose=False)
    return model


def _weather(table, start, end):
    frame = table[(pd.Series(day_of(table.timestamp)) >= start).to_numpy() & (pd.Series(day_of(table.timestamp)) <= end).to_numpy()]
    kc = frame.kc.where(frame.kc_status.eq("valid"))
    return {"valid_bins": int(kc.notna().sum()), "valid_days": int(pd.Series(day_of(frame.timestamp[kc.notna()])).nunique()),
            "kc_mean": float(kc.mean()), "kc_std": float(kc.std()), "mean_abs_step_change": float(kc.diff().abs().mean())}


def run_fold(config, table, fold, horizons, model_dir=None):
    """Predictions of every forecast for one fold, plus fold information."""
    test_table = table[(pd.Series(day_of(table.timestamp)) >= fold.test_start).to_numpy()
                       & (pd.Series(day_of(table.timestamp)) <= fold.test_end).to_numpy()].reset_index(drop=True)
    stats = internal_statistics(test_table, horizons)
    rows, info = [], {**fold.as_dict(), "weather": _weather(table, fold.test_start, fold.test_end),
                      "internal_statistics": {"mu": stats.mu, "sigma2": stats.sigma2,
                                              "rho": {str(h): stats.rho[h] for h in horizons}},
                      "horizons": {}}
    for h in horizons:
        samples, features = build_samples(table, h, config)
        train = samples[samples.issue_day < fold.validation_start]
        validation = _days(samples, fold.validation_start, fold.test_start - timedelta(days=1))
        test = _days(samples, fold.test_start, fold.test_end)
        if train.empty or validation.empty or test.empty:
            raise ValueError(f"{fold.name} h={h}: empty train/validation/test set")
        # leakage guards: whole-day separation and targets on the issue day
        assert train.issue_day.max() < fold.validation_start <= validation.issue_day.min()
        assert validation.issue_day.max() < fold.test_start <= test.issue_day.min()
        for part in (train, validation, test):
            assert (pd.Series(day_of(part.target_time), index=part.index) == part.issue_day).all()
        model = _fit(config, train, validation, features)
        if model_dir is not None:
            model.save_model(Path(model_dir) / f"{fold.name}_h{h:02d}.json")
        kc_hat = {"xgboost": model.predict(test[features]).astype(float),
                  "persistence": test.kc_lag_0.to_numpy(),
                  "climatology": np.full(len(test), stats.mu),
                  "convex_combination": stats.rho[h] * test.kc_lag_0.to_numpy() + (1 - stats.rho[h]) * stats.mu}
        frame = pd.DataFrame({"fold": fold.name, "h_steps": h, "issue_time": test.index, "target_time": test.target_time,
                              "day": test.issue_day.astype(str), "target_elevation": test.target_elevation.to_numpy(),
                              "ghi": test.target_ghi.to_numpy(), "ghi_clear": test.target_ghi_clear.to_numpy(),
                              "kc": test.target_kc.to_numpy()})
        for name, value in kc_hat.items():
            frame[f"kc_hat_{name}"] = value
            frame[f"ghi_hat_{name}"] = value * frame.ghi_clear
        rows.append(frame)
        info["horizons"][str(h)] = {"train_samples": len(train), "validation_samples": len(validation),
                                    "test_samples": len(test), "best_iteration": int(model.best_iteration)}
    return pd.concat(rows, ignore_index=True), info


def _scores(group):
    out = {"count": len(group), "mean_ghi": float(group.ghi.mean())}
    for name in FORECASTS:
        predicted = group[f"ghi_hat_{name}"].to_numpy()
        out[f"rmse_{name}"] = rmse(predicted, group.ghi.to_numpy())
        out[f"mbe_{name}"] = mbe(predicted, group.ghi.to_numpy())
        out[f"mae_{name}"] = mae(predicted, group.ghi.to_numpy())
    out["nrmse_xgboost"] = out["rmse_xgboost"] / out["mean_ghi"]
    out["skill_vs_cc"] = skill(out["rmse_xgboost"], out["rmse_convex_combination"])
    out["skill_vs_persistence"] = skill(out["rmse_xgboost"], out["rmse_persistence"])
    return pd.Series(out)


def summarise(predictions, bands):
    per_fold = predictions.groupby(["fold", "h_steps"]).apply(_scores, include_groups=False).reset_index()
    pooled = predictions.groupby("h_steps").apply(_scores, include_groups=False).reset_index().assign(fold="pooled")
    metrics = pd.concat([per_fold, pooled], ignore_index=True)
    metrics.insert(2, "horizon_min", metrics.h_steps * 5)

    daily = predictions.groupby(["h_steps", "day"]).apply(_scores, include_groups=False).reset_index()
    daily_summary = daily.groupby("h_steps").agg(days=("skill_vs_cc", "size"),
                                                 days_better_than_cc=("skill_vs_cc", lambda s: int((s > 0).sum())),
                                                 median_daily_skill_vs_cc=("skill_vs_cc", "median"),
                                                 min_daily_skill_vs_cc=("skill_vs_cc", "min"),
                                                 max_daily_skill_vs_cc=("skill_vs_cc", "max")).reset_index()

    labelled = predictions.assign(band=pd.cut(predictions.target_elevation, bands, right=False))
    elevation = labelled.groupby(["h_steps", "band"], observed=True).apply(_scores, include_groups=False).reset_index()
    elevation["band"] = elevation.band.astype(str)
    return metrics, daily, daily_summary, elevation


def _previous_runs(path, role):
    path = Path(path)
    if not path.exists():
        return []
    return [r for r in map(json.loads, path.read_text(encoding="utf-8").splitlines()) if r["role"] == role]


def run_model_pipeline(role="development", config=None, kc_file=KC_FILE, runs_dir=RUNS_DIR, rerun_reason=None,
                       log_file=LOG_FILE):
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}")
    config = config or load_forecast_config()
    runs_dir = Path(runs_dir)
    previous = _previous_runs(log_file, role)
    if role in SEALED and previous and not rerun_reason:
        raise SealedRunError(f"{role} was already run {len(previous)} time(s) "
                             f"(first {previous[0]['timestamp_utc']}); pass a rerun reason to run it again (it is logged)")
    kc_file = Path(kc_file)
    table = table_for_role(pd.read_parquet(kc_file), config, role)
    folds = [f for f in make_folds(config, table, role) if f.role == role]
    horizons = config.value("horizon_steps")
    out_dir = runs_dir / role
    model_dir = out_dir / "models"
    model_dir.mkdir(parents=True, exist_ok=True)

    predictions, fold_info = [], []
    for fold in folds:
        p, info = run_fold(config, table, fold, horizons, model_dir)
        predictions.append(p)
        fold_info.append(info)
    predictions = pd.concat(predictions, ignore_index=True)
    metrics, daily, daily_summary, elevation = summarise(predictions, config.value("evaluation.elevation_bands_deg"))

    predictions.to_parquet(out_dir / "predictions.parquet", index=False)
    for name, frame in (("metrics", metrics), ("daily_skill", daily), ("daily_skill_summary", daily_summary),
                        ("elevation_bands", elevation)):
        frame.to_csv(out_dir / f"{name}.csv", index=False, float_format="%.6g", lineterminator="\n")
    (out_dir / "folds.json").write_text(json.dumps(fold_info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    source = read_parquet_version(kc_file)
    commit, dirty = git_state(MPC_LAB_DIR)
    record = {"role": role, "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "pipeline_version": PIPELINE_VERSION, "config_sha256": config.fingerprint(),
              "kc_dataset_id": None if source is None else source["dataset_id"], "kc_file_sha256": file_sha256(kc_file),
              "folds": [f.as_dict() for f in folds], "rerun_reason": rerun_reason,
              "git_commit": commit, "git_dirty": dirty, "libraries": {**library_versions(), "xgboost": xgb.__version__}}
    (out_dir / "manifest.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    with Path(log_file).open("a", encoding="utf-8") as log:
        log.write(json.dumps(record, ensure_ascii=False) + "\n")
    return predictions, metrics, daily_summary, elevation, fold_info


def main(argv=None):
    parser = argparse.ArgumentParser(description="XGBoost kc forecast: out-of-sample evaluation")
    parser.add_argument("--role", choices=ROLES, default="development")
    parser.add_argument("--rerun-reason", default=None)
    args = parser.parse_args(argv)
    _, metrics, daily_summary, _, folds = run_model_pipeline(args.role, rerun_reason=args.rerun_reason)
    for info in folds:
        print(info["name"], info["test_start"], "..", info["test_end"], json.dumps(info["weather"]))
    pooled = metrics[metrics.fold == "pooled"]
    print(pooled[["horizon_min", "count", "rmse_xgboost", "rmse_convex_combination", "rmse_persistence",
                  "skill_vs_cc", "skill_vs_persistence"]].round(3).to_string(index=False))
    print(daily_summary.round(3).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
