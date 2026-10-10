"""Deduplication and per-variable quality flags for outside observations.

Flags (bit mask per variable, ``<var>_flags``) record *why*; the status (``<var>_status``) records
what a consumer may do with the value:

    observed      valid measurement                         value kept
    suspect       flagged only (freeze, daylight zero)      value kept, excluded from means by default
    invalid       impossible / communication error          value set to NaN (raw text kept)
    missing       no value (gap, schema anomaly, conflict)  NaN
    interpolated  filled by the optional gap interpolation (resample.py)

Nothing is deleted: duplicates and conflicts stay visible in the parsed-row table.

``<var>_input_status`` is the same status computed causally, i.e. only from observations up to that
row, for use as a forecast *input*. The only QC step that looks ahead is the freeze test: the full
status flags a whole run of identical values once the run has lasted the minimum duration, while the
causal status flags a row only when the run up to and including it has already lasted that long
(and, for GHI, has already reached daylight). Targets use ``<var>_status``.
"""

from enum import IntFlag

import numpy as np
import pandas as pd

from .outside_schema import VARIABLES


class QC(IntFlag):
    MISSING = 1
    DUPLICATE = 2                      # exact duplicates were merged into this observation
    CONFLICTING_DUPLICATE = 4          # same timestamp, different values -> no value adopted
    SCHEMA_ANOMALY = 8                 # row/field could not be mapped or parsed
    SENSOR_FREEZE = 16
    OUT_OF_RANGE = 32
    SUSPECTED_COMMUNICATION_ERROR = 64
    INTERPOLATED = 128
    SUSPICIOUS_ZERO = 256              # GHI == 0 while the sun is clearly up
    LOW_COVERAGE = 512                 # 5-min bin below the configured coverage (if configured)


STATUSES = ("observed", "interpolated", "suspect", "invalid", "missing")
INVALID_BITS = QC.OUT_OF_RANGE | QC.SUSPECTED_COMMUNICATION_ERROR
SUSPECT_BITS = QC.SENSOR_FREEZE | QC.SUSPICIOUS_ZERO
VALUE_COLUMNS = list(VARIABLES)


def _values_key(frame):
    """Hashable per-row value tuple (NaN compares equal to NaN)."""
    return frame[VALUE_COLUMNS].astype(float).round(9).fillna(-9.99e99).apply(tuple, axis=1)


def deduplicate(parsed):
    """Return (parsed with ``dedup_status``, one observation per timestamp).

    Policy (docs/OUTSIDE_DATA_PIPELINE.md §4):
    - identical rows at one timestamp: the first by (file name, line) is kept, others ``duplicate``
    - different values at one timestamp: none adopted; all rows ``conflicting``; the observation
      carries CONFLICTING_DUPLICATE with missing values
    - schema-anomaly rows with a valid timestamp and no parsed row at that timestamp produce an
      observation with SCHEMA_ANOMALY and missing values
    - rows without a parseable timestamp cannot be placed: ``unplaced``
    """
    parsed = parsed.copy()
    parsed["dedup_status"] = "unplaced"
    placed = parsed["timestamp_ok"].astype(bool)
    good = placed & parsed["layout"].notna()
    parsed.loc[placed & ~good, "dedup_status"] = "schema_anomaly"

    candidates = parsed[good].copy()
    candidates["_key"] = _values_key(candidates)
    groups = candidates.groupby("timestamp", sort=True)
    n_rows = groups["_key"].transform("size")
    n_distinct = groups["_key"].transform("nunique")
    first = ~candidates.duplicated("timestamp", keep="first")
    status = np.where(n_distinct > 1, "conflicting", np.where(first, "kept", "duplicate"))
    parsed.loc[candidates.index, "dedup_status"] = status

    kept = candidates[(n_distinct == 1) & first].copy()
    kept["obs_flags"] = np.where(n_rows[kept.index] > 1, int(QC.DUPLICATE), 0)
    conflicts = candidates[(n_distinct > 1) & first].copy()
    for name in VALUE_COLUMNS:
        conflicts[name] = np.nan
        conflicts[f"{name}_parse_error"] = False
    conflicts["obs_flags"] = int(QC.CONFLICTING_DUPLICATE)
    anomalies = parsed[placed & ~good]
    anomalies = anomalies[~anomalies["timestamp"].isin(candidates["timestamp"])]
    anomalies = anomalies.drop_duplicates("timestamp", keep="first").copy()
    anomalies["obs_flags"] = int(QC.SCHEMA_ANOMALY)

    columns = (["timestamp", "source_file", "source_line", "obs_flags", "wind_dir_compass"]
               + [c for name in VALUE_COLUMNS for c in (name, f"{name}_raw", f"{name}_parse_error")])
    observations = pd.concat([kept[columns], conflicts[columns], anomalies[columns]], ignore_index=True)
    observations = observations.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
    return parsed, observations


def sun_elevation(times, site):
    """Apparent solar elevation [deg] via pvlib (NREL SPA); NaN when the site is unknown."""
    if site is None or len(times) == 0:
        return np.full(len(times), np.nan)
    import pvlib
    index = pd.DatetimeIndex(times)
    position = pvlib.solarposition.get_solarposition(index, site.latitude_deg, site.longitude_deg,
                                                     altitude=site.elevation_m)
    return position["apparent_elevation"].to_numpy(dtype=float)


def _freeze_mask(times, values, min_minutes, eligible):
    """Rows inside runs of identical consecutive values lasting >= min_minutes.

    ``eligible`` limits which rows may belong to a run (e.g. GHI > 0); a run counts only if at least
    one of its rows satisfies ``eligible`` and the run spans the minimum duration."""
    mask = np.zeros(len(values), bool)
    if min_minutes is None or len(values) == 0:
        return mask
    valid = ~np.isnan(values) & eligible
    change = np.ones(len(values), bool)
    change[1:] = (values[1:] != values[:-1]) | ~valid[1:] | ~valid[:-1]
    run_id = np.cumsum(change)
    frame = pd.DataFrame({"run": run_id, "t": times, "valid": valid})
    spans = frame[frame["valid"]].groupby("run")["t"].agg(["min", "max"])
    long_runs = spans.index[(spans["max"] - spans["min"]) >= pd.Timedelta(minutes=float(min_minutes))]
    mask[np.isin(run_id, long_runs) & valid] = True
    return mask


def _freeze_mask_causal(times, values, min_minutes, eligible, daylight=None):
    """Rows whose run of identical values, counted up to and including the row, already spans
    ``min_minutes`` (and, if ``daylight`` is given, already contains a daylit row)."""
    mask = np.zeros(len(values), bool)
    if min_minutes is None or len(values) == 0:
        return mask
    valid = ~np.isnan(values) & eligible
    change = np.ones(len(values), bool)
    change[1:] = (values[1:] != values[:-1]) | ~valid[1:] | ~valid[:-1]
    run_id = np.cumsum(change)
    frame = pd.DataFrame({"run": run_id, "t": times})
    start = frame.groupby("run")["t"].transform("min").to_numpy()
    mask = valid & ((times - start) >= np.timedelta64(int(round(float(min_minutes) * 60e9)), "ns"))
    if daylight is not None:
        seen = pd.Series(daylight & valid).groupby(run_id).cummax().to_numpy()
        mask &= seen
    return mask


def _status(flags, values):
    status = np.full(len(values), "observed", dtype=object)
    status[(flags & SUSPECT_BITS) != 0] = "suspect"
    status[(flags & INVALID_BITS) != 0] = "invalid"
    status[np.isnan(values)] = "missing"
    return status


def apply_qc(observations, config):
    """Add ``<var>``, ``<var>_flags``, ``<var>_status`` (and ``sun_elevation_deg``) per observation."""
    obs = observations.copy()
    n = len(obs)
    times = obs["timestamp"]
    obs["sun_elevation_deg"] = sun_elevation(times, config.site)
    elevation = obs["sun_elevation_deg"].to_numpy()
    base = obs["obs_flags"].to_numpy(dtype=int)
    flags = {name: base.copy() for name in VALUE_COLUMNS}
    values = {name: obs[name].to_numpy(dtype=float) for name in VALUE_COLUMNS}

    for name in VALUE_COLUMNS:
        flags[name][np.isnan(values[name])] |= QC.MISSING
        flags[name][obs[f"{name}_parse_error"].to_numpy(dtype=bool)] |= QC.SCHEMA_ANOMALY
        low, high = config.qc_value("ranges", name)
        v = values[name]
        with np.errstate(invalid="ignore"):
            bad = np.zeros(n, bool)
            if low is not None:
                bad |= v < low
            if high is not None:
                bad |= (v >= high) if name == "wind_dir" else (v > high)
        flags[name][bad] |= QC.OUT_OF_RANGE

    if config.qc_value("communication_error_all_zero"):
        zero = np.ones(n, bool)
        for name in ("t_out", "wind_speed", "wind_dir", "ghi"):
            zero &= values[name] == 0
        rh = values["rh_out"]
        zero &= np.isnan(rh) | (rh == 0)
        for name in VALUE_COLUMNS:
            flags[name][zero] |= QC.SUSPECTED_COMMUNICATION_ERROR
    else:
        zero = np.zeros(n, bool)

    ghi = values["ghi"]
    night = config.qc_value("sun", "night_elevation_deg")
    day = config.qc_value("sun", "daylight_elevation_deg")
    with np.errstate(invalid="ignore"):
        if night is not None:
            flags["ghi"][(elevation < night) & (ghi > 0)] |= QC.OUT_OF_RANGE
        if day is not None:
            flags["ghi"][(elevation > day) & (ghi == 0) & ~zero] |= QC.SUSPICIOUS_ZERO

    t = times.to_numpy(dtype="datetime64[ns]")   # UTC instants; only differences are used
    causal_freeze = {}
    for name, node in config.qc["freeze_min_duration_minutes"].items():
        minutes = node.value
        if minutes is None:
            continue
        v = values[name]
        if name == "ghi":
            threshold = day if day is not None else 0.0
            with np.errstate(invalid="ignore"):
                eligible = (v > 0) & ~zero
                sunny = elevation > threshold
            mask = _freeze_mask(t, v, minutes, eligible)
            # a run counts only if it reaches daylight somewhere (night part is OUT_OF_RANGE anyway)
            run = np.cumsum(np.r_[True, (v[1:] != v[:-1]) | ~mask[1:] | ~mask[:-1]])
            daylit_runs = np.unique(run[mask & sunny])
            mask &= np.isin(run, daylit_runs)
            causal_freeze[name] = _freeze_mask_causal(t, v, minutes, eligible, daylight=sunny)
        else:
            mask = _freeze_mask(t, v, minutes, ~zero)
            causal_freeze[name] = _freeze_mask_causal(t, v, minutes, ~zero)
        flags[name][mask] |= QC.SENSOR_FREEZE

    for name in VALUE_COLUMNS:
        f = flags[name]
        status = _status(f, values[name])
        causal = f & ~int(QC.SENSOR_FREEZE)
        if name in causal_freeze:
            causal = causal | (causal_freeze[name].astype(np.int64) * int(QC.SENSOR_FREEZE))
        clean = values[name].copy()
        clean[status == "invalid"] = np.nan
        obs[name] = clean
        obs[f"{name}_flags"] = f.astype(np.int32)
        obs[f"{name}_status"] = status
        obs[f"{name}_input_status"] = _status(causal, values[name])
    return obs.drop(columns=["obs_flags"] + [f"{name}_parse_error" for name in VALUE_COLUMNS])


def decode_flags(value):
    """Flag names set in an integer mask (for reports)."""
    return [flag.name for flag in QC if value & flag]
