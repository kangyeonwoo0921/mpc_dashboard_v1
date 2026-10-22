"""Live GHI forecasting on the laptop from the field collector's synced files.

    python -m greenhouse_mpc.forecast.live_runner --once  [--field-dir DIR]
    python -m greenhouse_mpc.forecast.live_runner --loop  [--field-dir DIR]

One cycle (config/live.yaml):

1. outside pipeline over the historical exports (config/outside_data.yaml raw_dir) plus the collector's
   ``<field_dir>/outside/outside_*.csv``; then clear sky and clear-sky index (all re-run, ~20 s);
2. weekly forecast update (operation.update) when none has run for ``operation.retrain_interval_days``,
   or when an active model's files are not in this machine's data folder;
3. forecast issued for the last complete 5-min bin (operation.forecast_at, appended to the live log);
4. ``latest_forecast.json`` for the dashboard and the MPC: in ``GREENHOUSE_SHARED_DIR`` if set, else
   ``<data>/processed/forecast_live/`` (paths.py).

No forecast (status ``unavailable`` with a reason) when the newest observation is older than
``max_data_age_min``, at night / below the kc elevation limit, or when the bin's GHI is not observed.
A failing cycle writes its error to the same file and the loop continues.
"""

import argparse
import json
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yaml

from ..config_loader import CONFIG_DIR
from ..ingestion.outside_pipeline import run_outside_pipeline
from ..ingestion.outside_schema import load_outside_config
from ..ingestion.versioning import read_parquet_version
from ..paths import processed_dir, shared_dir
from ..provenance import Parameter, ProvenanceError, parse_parameters
from ..solar.clearsky_index_pipeline import run_clearsky_index_pipeline
from ..solar.clearsky_pipeline import run_clearsky_pipeline
from .config import load_forecast_config
from .operation import KC_FILE, OperationPaths, forecast_at, load_state, model_complete, update

KST = timezone(timedelta(hours=9))
SCHEMA_VERSION = "ghi-forecast/0.1"
LATEST_FILE = (shared_dir() / "latest_forecast.json" if shared_dir()
               else processed_dir() / "forecast_live" / "latest_forecast.json")


@dataclass(frozen=True)
class LiveConfig:
    tree: dict

    def value(self, key):
        node = self.tree[key]
        if not isinstance(node, Parameter):
            raise ProvenanceError(f"{key} is not a parameter record")
        return node.value


def load_live_config(path=None, config_dir=CONFIG_DIR):
    path = Path(path) if path else Path(config_dir) / "live.yaml"
    return LiveConfig(parse_parameters(yaml.safe_load(path.read_text(encoding="utf-8")), "live"))


def input_files(outside_config, field_dir):
    historical = sorted(Path(outside_config.raw_dir).glob(outside_config.file_glob))
    field = sorted((Path(field_dir) / "outside").glob("outside_*.csv")) if field_dir else []
    return historical + field


def last_complete_bin(now, minutes=5):
    now = pd.Timestamp(now).tz_convert("Asia/Seoul")
    return now.floor(f"{minutes}min") - pd.Timedelta(minutes=minutes)


def _write(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _payload(now, status, reason=None, **extra):
    return {"schema_version": SCHEMA_VERSION, "generated_at": pd.Timestamp(now).isoformat(), "status": status,
            "reason": reason, "units": {"ghi": "W/m2, sensor reading (angular response not corrected)", "kc": "-"},
            **extra}


def recent_observations(frame, issue, bins=12):
    """Measured 5-min GHI of the last ``bins`` bins up to the issue bin (for the screen recommendation and
    the dashboard chart). ``ghi`` is null unless the bin's status is ``observed``."""
    window = frame.loc[:issue].tail(bins)
    return [{"time": t.isoformat(), "ghi_w_m2": None if s != "observed" or pd.isna(v) else round(float(v), 1),
             "status": s} for t, v, s in zip(window.index, window.ghi, window.ghi_status)]


RAIN_KEY = "감우"   # rain sensor flag in the field dashboard status ("ON" / "OFF")


RAIN_STATE_FILE = processed_dir() / "forecast_live" / "rain_state.json"


def _read_rain(field_dir, now, max_age_min):
    """(flag, collected_at) from the collector's latest.json; flag None when unknown or stale."""
    if not field_dir:
        return None, None
    try:
        record = json.loads((Path(field_dir) / "latest.json").read_text(encoding="utf-8"))
        collected = pd.Timestamp(record["collected_at"])
        if collected < pd.Timestamp(now) - pd.Timedelta(minutes=max_age_min):
            return None, collected
        value = ((record.get("response") or {}).get("status") or {}).get(RAIN_KEY)
    except (OSError, ValueError, KeyError, TypeError):
        return None, None
    return {"ON": True, "OFF": False}.get(str(value).strip().upper()), collected


def rain_now(field_dir, now, max_age_min):
    """Field rain sensor state right now: True / False, None when unknown or stale."""
    return _read_rain(field_dir, now, max_age_min)[0]


def observe_rain(field_dir, now, max_age_min, state_file=RAIN_STATE_FILE):
    """Sample the rain sensor; remember the last minute it was ON (survives restarts). Returns the sample."""
    flag, collected = _read_rain(field_dir, now, max_age_min)
    if flag:
        try:
            Path(state_file).parent.mkdir(parents=True, exist_ok=True)
            Path(state_file).write_text(json.dumps({"last_on": collected.isoformat()}), encoding="utf-8")
        except OSError:
            pass
    return flag


def _last_on_from_raw(field_dir, now):
    """Last minute with the rain sensor ON in today's collector raw log (seeds the memory after a restart;
    the raw log reaches the sync folder less often than latest.json, so this may lag)."""
    path = Path(field_dir) / "raw" / f"live_{pd.Timestamp(now).strftime('%Y-%m-%d')}.jsonl"
    last = None
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if f'"{RAIN_KEY}": "ON"' not in line:
                    continue
                last = pd.Timestamp(json.loads(line)["collected_at"])
    except (OSError, ValueError, KeyError):
        return last
    return last


def rain_recent(field_dir, now, max_age_min, hold_min, state_file=RAIN_STATE_FILE):
    """Rain counts as ongoing if the sensor is ON now or was ON within ``hold_min`` (the sensor flickers in
    drizzle). False when OFF now and nothing recent; None when unknown and nothing recent."""
    current = observe_rain(field_dir, now, max_age_min, state_file)
    if current:
        return True
    try:
        last_on = pd.Timestamp(json.loads(Path(state_file).read_text(encoding="utf-8"))["last_on"])
    except (OSError, ValueError, KeyError, TypeError):
        last_on = _last_on_from_raw(field_dir, now) if field_dir else None      # no memory yet (first run)
    if last_on is not None and pd.Timestamp(now) - last_on <= pd.Timedelta(minutes=hold_min):
        return True
    return current


def forecast_payload(config, table, now, paths, max_age_min, rain=None):
    """Forecast for the last complete bin, as the dashboard/MPC payload."""
    issue = last_complete_bin(now, int(config.value("time_step_min")))
    frame = table.set_index("timestamp")
    received = frame.index[frame.ghi_input_status.ne("missing")]
    newest = received.max() if len(received) else None
    base = {"issue_time": issue.isoformat(), "data_last_timestamp": None if newest is None or pd.isna(newest) else newest.isoformat(),
            "recent_observations": recent_observations(frame, issue), "rain": rain}
    if newest is None or pd.isna(newest) or newest < pd.Timestamp(now) - pd.Timedelta(minutes=max_age_min):
        return _payload(now, "unavailable", "data_stale", horizons=None, **base)
    if issue not in frame.index:
        return _payload(now, "unavailable", "issue_bin_not_processed", horizons=None, **base)
    status = frame.at[issue, "kc_input_status"]
    if status != "valid":
        return _payload(now, "unavailable", status, horizons=None, **base)
    result = forecast_at(config, table, [issue], paths, rain=rain)
    state = load_state(paths)
    horizons = [{"h_steps": int(r.h_steps), "horizon_min": int(r.h_steps) * int(config.value("time_step_min")),
                 "target_time": pd.Timestamp(r.target_time).isoformat(), "method": r.method,
                 "ghi_w_m2": None if pd.isna(r.ghi_hat) else round(float(r.ghi_hat), 1),
                 "kc": None if pd.isna(r.kc_hat) else round(float(r.kc_hat), 4),
                 "ghi_clear_w_m2": round(float(r.ghi_clear), 1)} for r in result.itertuples()]
    return _payload(now, "ok", None, horizons=horizons, policy_update=state.get("last_update"),
                    active_models=state.get("active"), **base)


def run_cycle(now=None, field_dir=None, live_config=None, paths=None, latest_file=LATEST_FILE):
    now = pd.Timestamp(now or datetime.now(KST))
    live_config = live_config or load_live_config()
    field_dir = field_dir or live_config.value("field_data_dir")
    paths = paths or OperationPaths.default()
    try:
        outside_config = load_outside_config()
        run_outside_pipeline(outside_config, paths=input_files(outside_config, field_dir))
        run_clearsky_pipeline()
        run_clearsky_index_pipeline()
        config = load_forecast_config()
        table = pd.read_parquet(KC_FILE)
        source = read_parquet_version(KC_FILE)
        state = load_state(paths)
        interval = int(config.value("operation.retrain_interval_days"))
        last = state.get("last_update")
        horizons = config.value("horizon_steps")
        # an empty or half-written model folder (interrupted first run) counts as missing -> retrain
        models_missing = any(not model_complete(paths.models, model_id, horizons)
                             for model_id in (state.get("active") or {}).values())
        if last is None or models_missing or (now.date() - pd.Timestamp(last).date()).days >= interval:
            update(config, table, now.date(), paths, None if source is None else source["dataset_id"])
        max_age = float(live_config.value("max_data_age_min"))
        hold = config.value("operation.rain_hold_min")
        rain = (rain_recent(field_dir, now, max_age, float(hold)) if hold
                else rain_now(field_dir, now, max_age))
        payload = forecast_payload(config, table, now, paths, max_age, rain=rain)
        payload["field_data_dir_set"] = bool(field_dir)
    except Exception as error:                              # the loop must keep running
        payload = _payload(now, "error", f"{type(error).__name__}: {error}", horizons=None,
                           traceback=traceback.format_exc(limit=5))
    _write(latest_file, payload)
    return payload


def loop(field_dir=None):
    live_config = load_live_config()
    minutes = int(live_config.value("cycle_minutes"))
    delay = float(live_config.value("cycle_delay_s"))
    max_age = float(live_config.value("max_data_age_min"))
    field = field_dir or live_config.value("field_data_dir")
    while True:
        now = time.time()
        period = minutes * 60
        next_run = (now // period + 1) * period + delay
        # sample the rain sensor every minute until the next cycle (it flickers between cycles)
        while next_run - time.time() > 60:
            observe_rain(field, pd.Timestamp.now(tz=KST), max_age)
            time.sleep(60)
        time.sleep(max(0.0, next_run - time.time()))
        payload = run_cycle(field_dir=field_dir, live_config=live_config)
        print(payload["generated_at"], payload["status"], payload.get("reason") or "",
              "rain" if payload.get("rain") else "", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="live GHI forecasting from the field collector")
    parser.add_argument("--field-dir", help="synced collector output_dir (overrides config/live.yaml)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true")
    mode.add_argument("--loop", action="store_true")
    args = parser.parse_args(argv)
    if args.once:
        payload = run_cycle(field_dir=args.field_dir)
        print(json.dumps({k: v for k, v in payload.items() if k != "traceback"}, ensure_ascii=False, indent=2))
        return 0 if payload["status"] != "error" else 1
    loop(args.field_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
