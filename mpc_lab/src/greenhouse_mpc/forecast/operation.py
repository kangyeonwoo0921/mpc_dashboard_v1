"""Operational GHI forecasting: weekly update with candidate comparison, and live forecasts.

    python -m greenhouse_mpc.forecast.operation update --as-of 2026-10-10
    python -m greenhouse_mpc.forecast.operation forecast --at "2026-10-09 12:00"
    python -m greenhouse_mpc.forecast.operation replay --start 2026-08-31 --end 2026-10-09 --sandbox DIR

Weekly ``update(as_of)`` (config ``operation``):

1. gate: for every horizon in ``model_horizon_steps``, compare each candidate's *live* forecasts of the
   last ``gate_window_days`` (out-of-sample by construction) with the reference forecasts; the best
   candidate whose RMSE is not above the reference is used, otherwise the reference. Fewer than
   ``gate_min_valid_days`` days with valid targets: the previous choice is kept. Other horizons always
   use the reference. Before any live record exists, model horizons use the first candidate.
2. reference statistics (mu, rho(h)) from the data before ``as_of``.
3. every candidate is retrained on the days before ``as_of`` (last ``split.validation_days`` for early
   stopping) and activated only if it passes the sanity checks; otherwise its previous model stays.
   The RMSE check compares the new and the active model on the *same* validation days (unseen by both;
   the active model was trained before them), so it compares models, not weeks.

``forecast_at(issue_times)`` gives, for each issue time and horizon, every active candidate's and the
reference's kc / GHI forecast and the method chosen by the policy, and appends them to the live log.
Targets are sensor GHI (CLEARSKY_REFERENCE.md section 3). Target-time sun geometry and clear-sky GHI are
computed from the clear-sky model, so forecasts do not need future rows.

State: ``records/forecast_operation_state.json`` and ``records/forecast_operation_log.jsonl`` (tracked);
models and the live log under ``data/processed/`` (not tracked).
"""

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

from ..ingestion.outside_schema import MPC_LAB_DIR
from ..paths import processed_dir
from ..ingestion.versioning import read_parquet_version
from ..solar.clearsky import clearsky_five_minute, load_clearsky_config
from .baselines import internal_statistics
from .config import load_forecast_config
from .features import feature_frame
from .metrics import rmse
from .split import day_of

KC_FILE = processed_dir() / "clear_sky_index" / "kc_5min.parquet"
STEP = pd.Timedelta(minutes=5)


@dataclass(frozen=True)
class OperationPaths:
    state: Path
    log: Path
    models: Path
    live: Path

    @classmethod
    def default(cls):
        return cls(MPC_LAB_DIR / "records" / "forecast_operation_state.json",
                   MPC_LAB_DIR / "records" / "forecast_operation_log.jsonl",
                   processed_dir() / "forecast_models",
                   processed_dir() / "forecast_live" / "forecasts.parquet")

    @classmethod
    def sandbox(cls, root):
        root = Path(root)
        return cls(root / "state.json", root / "operation_log.jsonl", root / "models", root / "forecasts.parquet")


# ---------------------------------------------------------------- state and logs

def load_state(paths):
    if not paths.state.exists():
        return {"active": {}, "policy": {}, "reference_statistics": None, "last_update": None}
    return json.loads(paths.state.read_text(encoding="utf-8"))


def _save_state(paths, state):
    paths.state.parent.mkdir(parents=True, exist_ok=True)
    paths.state.write_text(json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _append_log(paths, record):
    paths.log.parent.mkdir(parents=True, exist_ok=True)
    with paths.log.open("a", encoding="utf-8") as log:
        log.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def load_live(paths):
    return pd.read_parquet(paths.live) if paths.live.exists() else None


def _append_live(paths, frame):
    if frame.empty:
        return
    previous = load_live(paths)
    combined = frame if previous is None else pd.concat([previous, frame], ignore_index=True)
    combined = combined.drop_duplicates(["issue_time", "h_steps"], keep="last").sort_values(["issue_time", "h_steps"])
    paths.live.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(paths.live, index=False)


# ---------------------------------------------------------------- training

def _days_before(table, end_day, window_days=None):
    days = pd.Series(day_of(table.timestamp), index=table.index)
    keep = days < end_day
    if window_days:
        keep &= days >= end_day - timedelta(days=int(window_days))
    return table[keep.to_numpy()].reset_index(drop=True)


def train_candidate(config, table, candidate, as_of, models_dir, kc_dataset_id=None, active_model_id=None):
    """Models for every horizon from the days before ``as_of`` (optionally only the last
    ``training_window_days``). Returns metadata including validation kc range and RMSE per horizon, and
    the active model's RMSE on the same validation samples (``active_model_id``)."""
    data = _days_before(table, as_of, candidate.get("training_window_days"))
    validation_days = int(config.value("split.validation_days"))
    validation_start = as_of - timedelta(days=validation_days)
    params = config.section("model.xgboost")
    stopping = params.pop("early_stopping_rounds")
    tag = hashlib.sha256(json.dumps({"candidate": candidate, "as_of": str(as_of), "kc": kc_dataset_id,
                                     "config": config.fingerprint("features", "model", "split")},
                                    sort_keys=True).encode()).hexdigest()[:8]
    model_id = f"{candidate['name']}_{as_of:%Y%m%d}_{tag}"
    out_dir = Path(models_dir) / model_id
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = {"model_id": model_id, "candidate": candidate, "as_of": str(as_of), "kc_dataset_id": kc_dataset_id,
            "data_first_day": str(min(day_of(data.timestamp))), "data_last_day": str(max(day_of(data.timestamp))),
            "validation_start": str(validation_start), "horizons": {}}
    active = _load_models(models_dir, active_model_id, config.value("horizon_steps")) if active_model_id else None
    meta["active_model_id"] = active_model_id
    for h in config.value("horizon_steps"):
        samples, features = feature_frame(data, h, config)
        samples = samples[samples.kc_lag_0.notna() & samples.target_kc.notna()]
        train = samples[samples.issue_day < validation_start]
        validation = samples[samples.issue_day >= validation_start]
        if train.empty or validation.empty:
            raise ValueError(f"{model_id} h={h}: empty training or validation set")
        model = xgb.XGBRegressor(**params, early_stopping_rounds=stopping)
        model.fit(train[features], train.target_kc, eval_set=[(validation[features], validation.target_kc)], verbose=False)
        model.save_model(out_dir / f"h{h:02d}.json")
        predicted = model.predict(validation[features]).astype(float)
        meta["horizons"][str(h)] = {"train_samples": len(train), "validation_samples": len(validation),
                                    "best_iteration": int(model.best_iteration),
                                    "validation_kc_rmse": rmse(predicted, validation.target_kc.to_numpy()),
                                    "validation_kc_min": float(predicted.min()), "validation_kc_max": float(predicted.max())}
        if active is not None:
            same = active[h].predict(validation[features]).astype(float)
            meta["horizons"][str(h)]["active_validation_kc_rmse"] = rmse(same, validation.target_kc.to_numpy())
    meta["features"] = features
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return meta


def _sanity(config, meta):
    low, high = config.value("operation.sanity_kc_range")
    ratio = float(config.value("operation.sanity_max_validation_rmse_ratio"))
    problems = []
    for h, info in meta["horizons"].items():
        if not (np.isfinite(info["validation_kc_rmse"]) and low <= info["validation_kc_min"] and info["validation_kc_max"] <= high):
            problems.append(f"h={h}: validation kc outside [{low}, {high}] or not finite")
        if "active_validation_kc_rmse" in info and info["validation_kc_rmse"] > ratio * info["active_validation_kc_rmse"]:
            problems.append(f"h={h}: validation RMSE above {ratio} x the active model on the same days")
    return problems


def _load_models(models_dir, model_id, horizons):
    models = {}
    for h in horizons:
        model = xgb.XGBRegressor()
        model.load_model(Path(models_dir) / model_id / f"h{h:02d}.json")
        models[h] = model
    return models


# ---------------------------------------------------------------- gate

def gate(config, state, live, table, as_of):
    """Per-horizon method from the live record of the last ``gate_window_days`` before ``as_of``."""
    horizons = config.value("horizon_steps")
    allowed = set(config.value("operation.model_horizon_steps"))
    candidates = [c["name"] for c in config.value("operation.candidates")]
    reference = config.value("operation.reference")
    window = int(config.value("operation.gate_window_days"))
    minimum = int(config.value("operation.gate_min_valid_days"))
    previous = state.get("policy") or {}
    policy, evidence = {}, {}

    observed = table.set_index("timestamp")
    observed = observed.kc.where(observed.kc_status.eq("valid")) * observed.ghi_clear
    recent = None
    if live is not None and not live.empty:
        days = pd.Series(day_of(live.target_time), index=live.index)
        recent = live[((days >= as_of - timedelta(days=window)) & (days < as_of)).to_numpy()].copy()
        recent["ghi"] = observed.reindex(pd.DatetimeIndex(recent.target_time)).to_numpy()
        recent = recent[recent.ghi.notna()]

    for h in horizons:
        key = str(h)
        if h not in allowed:
            policy[key] = {"method": reference, "reason": "horizon not enabled for models"}
            continue
        if recent is None:
            policy[key] = previous.get(key) or {"method": candidates[0], "reason": "initial: no live record yet"}
            continue
        rows = recent[recent.h_steps == h]
        columns = [f"ghi_hat_{name}" for name in [reference, *candidates]]
        rows = rows.dropna(subset=[c for c in columns if c in rows.columns])
        valid_days = int(pd.Series(day_of(rows.target_time)).nunique()) if len(rows) else 0
        if valid_days < minimum:
            policy[key] = {**(previous.get(key) or {"method": candidates[0]}),
                           "reason": f"kept: {valid_days} valid days < {minimum}"}
            continue
        scores = {name: rmse(rows[f"ghi_hat_{name}"], rows.ghi) for name in [reference, *candidates]
                  if f"ghi_hat_{name}" in rows.columns}
        evidence[key] = {"valid_days": valid_days, "samples": len(rows), "rmse": scores}
        best = min((name for name in candidates if name in scores), key=lambda n: scores[n], default=None)
        if best is not None and scores[best] <= scores[reference]:
            policy[key] = {"method": best, "reason": f"live RMSE {scores[best]:.1f} <= reference {scores[reference]:.1f}"}
        else:
            policy[key] = {"method": reference, "reason": "no candidate at or below the reference live RMSE"}
    return policy, evidence


# ---------------------------------------------------------------- update

def update(config, table, as_of, paths, kc_dataset_id=None):
    """Weekly update; returns the new state (also saved) and the log record."""
    as_of = pd.Timestamp(as_of).date() if not isinstance(as_of, date) else as_of
    state = load_state(paths)
    horizons = config.value("horizon_steps")
    policy, evidence = gate(config, state, load_live(paths), table, as_of)

    history = _days_before(table, as_of)
    stats = internal_statistics(history, horizons)
    reference_statistics = {"mu": stats.mu, "sigma2": stats.sigma2, "rho": {str(h): stats.rho[h] for h in horizons},
                            "estimated_from": [str(min(day_of(history.timestamp))), str(max(day_of(history.timestamp)))]}

    active = dict(state.get("active") or {})
    training = {}
    for candidate in config.value("operation.candidates"):
        name = candidate["name"]
        try:
            meta = train_candidate(config, table, candidate, as_of, paths.models, kc_dataset_id, active.get(name))
        except ValueError as error:
            training[name] = {"activated": False, "problems": [str(error)]}
            continue
        problems = _sanity(config, meta)
        if not problems:
            active[name] = meta["model_id"]
        training[name] = {"model_id": meta["model_id"], "activated": not problems, "problems": problems}

    for key, choice in policy.items():                       # a candidate without an active model cannot be used
        if choice["method"] not in active and choice["method"] != config.value("operation.reference"):
            policy[key] = {"method": config.value("operation.reference"), "reason": f"{choice['method']} has no active model"}

    new_state = {"active": active, "policy": policy, "reference_statistics": reference_statistics,
                 "last_update": str(as_of), "config_sha256": config.fingerprint(), "kc_dataset_id": kc_dataset_id}
    _save_state(paths, new_state)
    record = {"as_of": str(as_of), "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "policy": policy, "gate_evidence": evidence, "training": training, "active": active,
              "reference_statistics": reference_statistics, "config_sha256": config.fingerprint(),
              "kc_dataset_id": kc_dataset_id}
    _append_log(paths, record)
    return new_state, record


# ---------------------------------------------------------------- forecast

def forecast_at(config, table, issue_times, paths, clearsky_config=None, log=True):
    """Forecasts for the given issue bins (labelled by bin start; issued when the bin closes)."""
    state = load_state(paths)
    if not state.get("last_update"):
        raise RuntimeError("no operational state: run update first")
    clearsky_config = clearsky_config or load_clearsky_config()
    horizons = config.value("horizon_steps")
    reference = config.value("operation.reference")
    stats = state["reference_statistics"]
    issue_times = pd.DatetimeIndex(issue_times)
    history = table[table.timestamp <= issue_times.max()].reset_index(drop=True)
    models = {name: _load_models(paths.models, model_id, horizons) for name, model_id in state["active"].items()}

    rows = []
    for h in horizons:
        frame, features = feature_frame(history, h, config)
        frame = frame.reindex(issue_times)
        targets = issue_times + h * STEP
        geometry = clearsky_five_minute(targets, clearsky_config).set_index("timestamp")
        frame["sun_elevation_target"] = geometry.sun_elevation_deg.to_numpy()
        frame["sun_azimuth_target"] = geometry.sun_azimuth_deg.to_numpy()
        same_day = pd.Series(day_of(targets)) == pd.Series(day_of(issue_times))
        usable = frame.kc_lag_0.notna().to_numpy() & same_day.to_numpy() & (geometry.ghi_clear.to_numpy() > 0)
        clear = geometry.ghi_clear.to_numpy()
        out = pd.DataFrame({"issue_time": issue_times, "h_steps": h, "target_time": targets, "ghi_clear": clear,
                            "target_elevation": geometry.sun_elevation_deg.to_numpy()})
        kc_now = frame.kc_lag_0.to_numpy()
        kc_ref = stats["rho"][str(h)] * kc_now + (1 - stats["rho"][str(h)]) * stats["mu"]
        out[f"kc_hat_{reference}"] = np.where(usable, kc_ref, np.nan)
        for name, per_h in models.items():
            predicted = per_h[h].predict(frame[features]).astype(float)
            out[f"kc_hat_{name}"] = np.where(usable, predicted, np.nan)
        method = state["policy"][str(h)]["method"]
        out["method"] = method
        out["kc_hat"] = out[f"kc_hat_{method}"]
        for column in [c for c in out.columns if c.startswith("kc_hat")]:
            out[column.replace("kc_hat", "ghi_hat")] = out[column] * out.ghi_clear
        out["model_id"] = state["active"].get(method)
        rows.append(out)
    result = pd.concat(rows, ignore_index=True)
    result["policy_update"] = state["last_update"]
    if log:
        _append_live(paths, result)
    return result


# ---------------------------------------------------------------- replay (simulated operation)

def replay(config, table, start, end, paths, kc_dataset_id=None):
    """Weekly updates from ``start`` and live forecasts for every issue bin up to ``end`` (inclusive),
    as the operation would have run. Writes only under ``paths`` (use a sandbox)."""
    start, end = pd.Timestamp(start).date(), pd.Timestamp(end).date()
    interval = int(config.value("operation.retrain_interval_days"))
    clearsky_config = load_clearsky_config()
    records, as_of = [], start
    while as_of <= end:
        _, record = update(config, table, as_of, paths, kc_dataset_id)
        records.append(record)
        week_end = min(as_of + timedelta(days=interval - 1), end)
        days = pd.Series(day_of(table.timestamp))
        week = table[((days >= as_of) & (days <= week_end)).to_numpy()]
        issue = week.timestamp[week.kc_input_status.eq("valid")]
        if len(issue):
            forecast_at(config, table, issue, paths, clearsky_config)
        as_of += timedelta(days=interval)
    return records


# ---------------------------------------------------------------- CLI

def main(argv=None):
    parser = argparse.ArgumentParser(description="operational GHI forecasting")
    sub = parser.add_subparsers(dest="command", required=True)
    u = sub.add_parser("update")
    u.add_argument("--as-of", required=True)
    f = sub.add_parser("forecast")
    f.add_argument("--at", required=True, help="issue bin start, KST, e.g. '2026-10-09 12:00'")
    r = sub.add_parser("replay")
    r.add_argument("--start", required=True)
    r.add_argument("--end", required=True)
    r.add_argument("--sandbox", required=True)
    args = parser.parse_args(argv)

    config = load_forecast_config()
    table = pd.read_parquet(KC_FILE)
    source = read_parquet_version(KC_FILE)
    kc_id = None if source is None else source["dataset_id"]
    if args.command == "update":
        state, record = update(config, table, args.as_of, OperationPaths.default(), kc_id)
        print(json.dumps({"active": state["active"], "policy": state["policy"], "training": record["training"]}, indent=2))
    elif args.command == "forecast":
        at = pd.Timestamp(args.at, tz="Asia/Seoul")
        result = forecast_at(config, table, [at], OperationPaths.default())
        print(result[["h_steps", "target_time", "method", "kc_hat", "ghi_hat", "ghi_clear"]].round(3).to_string(index=False))
    else:
        records = replay(config, table, args.start, args.end, OperationPaths.sandbox(args.sandbox), kc_id)
        for record in records:
            print(record["as_of"], {h: p["method"] for h, p in record["policy"].items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
