"""Timestamp-based resampling of QC'd outside observations: canonical 1-min, then 5-min.

Bins are left-closed and labelled by their start: the 1-min bin 12:03 holds observations in
[12:03:00, 12:04:00); the 5-min bin 12:05 holds the 1-min rows 12:05..12:09. Rows are never grouped
by position. Per variable (docs/OUTSIDE_DATA_PIPELINE.md §6):

    mean           ghi, t_out, rh_out, wind_speed
    circular_mean  wind_dir (unit-vector mean; ``wind_dir_r`` = resultant length 0..1)
    last           solar_energy_cumulative (never averaged)

A bin takes the best status among its members (observed > interpolated > suspect > invalid >
missing). Its value aggregates the usable members (observed, interpolated, and suspect only when
``qc.resample.aggregate_suspect`` is true); a bin with only suspect members keeps their aggregate as
a suspect value. Flags are OR-ed over all members.

Forecast-input columns ``<var>_input`` / ``<var>_input_status`` repeat the aggregation with the causal
status (qc.py) and never use interpolated minutes, since interpolation looks at later data.
"""

import numpy as np
import pandas as pd

from .outside_schema import VARIABLES
from .qc import QC, STATUSES, sun_elevation

RANK = {status: i for i, status in enumerate(STATUSES)}


def circular_mean_deg(degrees):
    """(mean direction [0, 360), resultant length 0..1) of an array of directions in degrees."""
    radians = np.deg2rad(np.asarray(degrees, dtype=float))
    radians = radians[~np.isnan(radians)]
    if radians.size == 0:
        return np.nan, np.nan
    s, c = np.sin(radians).mean(), np.cos(radians).mean()
    return float(np.rad2deg(np.arctan2(s, c)) % 360.0), float(np.hypot(s, c))


def _group(values, keys, how):
    if values.empty:
        return pd.Series(dtype=float), pd.Series(dtype=float)
    if how == "mean":
        return values.groupby(keys).mean(), None
    if how == "last":
        return values.groupby(keys).last(), None
    radians = np.deg2rad(values.to_numpy(dtype=float))
    s = pd.Series(np.sin(radians), index=values.index).groupby(keys).mean()
    c = pd.Series(np.cos(radians), index=values.index).groupby(keys).mean()
    return (np.rad2deg(np.arctan2(s, c)) % 360.0), np.hypot(s, c)


def _aggregate_variable(frame, keys, name, how, include_suspect, index):
    status = frame[f"{name}_status"]
    value = frame[name]
    usable_statuses = {"observed", "interpolated"} | ({"suspect"} if include_suspect else set())
    usable = status.isin(usable_statuses) & value.notna()
    suspect = (status == "suspect") & value.notna()
    usable_value, usable_r = _group(value[usable], keys[usable], how)
    suspect_value, suspect_r = _group(value[suspect], keys[suspect], how)

    rank = status.map(RANK).groupby(keys).min().reindex(index)
    out_status = rank.map(dict(enumerate(STATUSES))).fillna("missing")
    out_value = usable_value.reindex(index)
    only_suspect = out_value.isna() & (out_status == "suspect")
    out_value[only_suspect] = suspect_value.reindex(index)[only_suspect]
    flags = pd.Series(0, index=index, dtype=np.int64)
    raw_flags = frame[f"{name}_flags"]
    for bit in QC:
        present = ((raw_flags & int(bit)) != 0).groupby(keys).max().reindex(index, fill_value=False)
        flags |= present.astype(np.int64) * int(bit)
    result = {name: out_value.to_numpy(dtype=float), f"{name}_status": out_status.to_numpy(dtype=object),
              f"{name}_flags": flags.to_numpy(dtype=np.int32),
              f"{name}_n_obs": (status == "observed").groupby(keys).sum().reindex(index, fill_value=0).to_numpy(dtype=np.int32)}
    result[f"{name}_n_interp"] = (status == "interpolated").groupby(keys).sum().reindex(index, fill_value=0).to_numpy(dtype=np.int32)
    if how == "circular_mean":
        r = usable_r.reindex(index) if usable_r is not None else pd.Series(np.nan, index=index)
        if suspect_r is not None:
            r[only_suspect] = suspect_r.reindex(index)[only_suspect]
        result[f"{name}_r"] = r.to_numpy(dtype=float)
    return result


def _aggregate_input(frame, keys, name, how, include_suspect, index, value_column, status_column):
    """``<var>_input`` and ``<var>_input_status`` from causal statuses (interpolated never used)."""
    status = frame[status_column].where(frame[status_column] != "interpolated", "missing")
    view = pd.DataFrame({name: frame[value_column].where(status != "missing"), f"{name}_status": status,
                         f"{name}_flags": np.zeros(len(frame), dtype=np.int64)}, index=frame.index)
    result = _aggregate_variable(view, keys, name, how, include_suspect, index)
    return {f"{name}_input": result[name], f"{name}_input_status": result[f"{name}_status"]}


def _grid(start, end, freq):
    return pd.date_range(start, end, freq=freq, name="timestamp")


def _finish(index, columns, frame_counts):
    out = pd.DataFrame(columns, index=index)
    out.insert(0, "n_rows", frame_counts.reindex(index, fill_value=0).to_numpy(dtype=np.int32))
    for name in VARIABLES:
        empty = out[f"{name}_status"] == "missing"
        out.loc[empty, f"{name}_flags"] = out.loc[empty, f"{name}_flags"] | int(QC.MISSING)
    return out


def to_minute(observations, config):
    """Canonical 1-min table on a complete minute grid from the first to the last observed minute.

    Minutes without any observation are explicit rows with status ``missing`` so that downstream
    lags/windows see real gaps (documented in OUTSIDE_DATA_PIPELINE.md §6)."""
    if observations.empty:
        return pd.DataFrame()
    obs = observations.sort_values("timestamp", kind="mergesort")
    keys = obs["timestamp"].dt.floor("1min")
    index = _grid(keys.min(), keys.max(), "1min")
    include_suspect = bool(config.qc_value("resample", "aggregate_suspect"))
    columns = {}
    for name in VARIABLES:
        how = config.variables[name]["aggregation_5min"]
        columns.update(_aggregate_variable(obs, keys, name, how, include_suspect, index))
        columns.update(_aggregate_input(obs, keys, name, how, include_suspect, index, name, f"{name}_input_status"))
    minute = _finish(index, columns, keys.value_counts())
    first = obs.groupby(keys)[["source_file", "source_line"]].first().reindex(index)
    minute["first_source"] = [None if pd.isna(f) else f"{f}:{int(l)}" for f, l in zip(first["source_file"], first["source_line"])]
    minute = interpolate_gaps(minute, config)
    minute["sun_elevation_deg"] = sun_elevation(index + pd.Timedelta(seconds=30), config.site)
    return minute.reset_index()


def interpolate_gaps(minute, config):
    """Optional linear interpolation of short runs of *missing* minutes (never invalid/suspect ones).

    Off unless ``qc.interpolation_max_gap_minutes.<var>`` is set; filled minutes get status
    ``interpolated`` and the INTERPOLATED flag so they stay distinguishable from measurements."""
    for name, node in config.qc["interpolation_max_gap_minutes"].items():
        max_gap = node.value
        if max_gap is None:
            continue
        status = minute[f"{name}_status"]
        anchor = minute[name].where(status == "observed")
        missing = status == "missing"
        run = (missing != missing.shift()).cumsum()
        run_length = missing.groupby(run).transform("sum")
        bounded = anchor.ffill().notna() & anchor.bfill().notna()
        fill = missing & (run_length <= max_gap) & bounded
        if not fill.any():
            continue
        filled = anchor.interpolate(method="time", limit_area="inside")
        minute.loc[fill, name] = filled[fill]
        minute.loc[fill, f"{name}_status"] = "interpolated"
        minute.loc[fill, f"{name}_flags"] = (minute.loc[fill, f"{name}_flags"] & ~int(QC.MISSING)) | int(QC.INTERPOLATED)
    return minute


def to_five_minute(minute, config):
    """Canonical 5-min table from the canonical 1-min table (timestamp-based bins)."""
    if minute.empty:
        return pd.DataFrame()
    frame = minute.set_index("timestamp", drop=False)
    keys = frame["timestamp"].dt.floor("5min")
    index = _grid(keys.min(), keys.max(), "5min")
    include_suspect = bool(config.qc_value("resample", "aggregate_suspect"))
    columns = {}
    for name in VARIABLES:
        how = config.variables[name]["aggregation_5min"]
        columns.update(_aggregate_variable(frame, keys, name, how, include_suspect, index))
        columns.update(_aggregate_input(frame, keys, name, how, include_suspect, index,
                                        f"{name}_input", f"{name}_input_status"))
    five = pd.DataFrame(columns, index=index)
    five.insert(0, "n_rows", frame["n_rows"].groupby(keys).sum().reindex(index, fill_value=0).to_numpy(dtype=np.int32))
    minimum = config.qc_value("resample", "min_coverage_5min")
    for name in VARIABLES:
        coverage = five[f"{name}_n_obs"] / 5.0
        five[f"{name}_coverage"] = coverage.round(3)
        if minimum is not None:
            low = coverage < minimum
            five.loc[low, f"{name}_flags"] = five.loc[low, f"{name}_flags"] | int(QC.LOW_COVERAGE)
    five["sun_elevation_deg"] = sun_elevation(index + pd.Timedelta(seconds=150), config.site)
    return five.reset_index()
