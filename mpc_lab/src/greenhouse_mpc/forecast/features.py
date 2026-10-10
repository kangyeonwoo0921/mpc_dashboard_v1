"""Training / evaluation samples for the direct per-horizon model (config ``features``).

One sample per issue bin ``t`` (forecast issued when bin ``t`` closes) and horizon ``h``:

    measured inputs     kc_input of bins t, t-1, ..., t-(L-1)      (causal QC status, same KST day only)
                        means of the last n of them (all n required)
    known in advance    sun elevation at t, sun elevation and azimuth at t+h (deterministic geometry)
    target              kc(t+h) (full QC status), ghi(t+h), ghi_clear(t+h)

A sample exists when kc_input(t) and kc(t+h) are valid and t+h is on the same KST day as t. Measured
values are never taken from rows after t; only the target and the deterministic geometry look ahead.
"""

import numpy as np
import pandas as pd

from .split import day_of

STEP = pd.Timedelta(minutes=5)


def build_samples(table, h, config):
    frame = table.set_index("timestamp") if "timestamp" in table.columns else table
    if not (frame.index.to_series().diff().dropna() == STEP).all():
        raise ValueError("kc table must be on a complete, regular 5-min grid")
    day = pd.Series(day_of(frame.index), index=frame.index)
    kc_in = frame.kc_input.where(frame.kc_input_status.eq("valid"))
    kc_target = frame.kc.where(frame.kc_status.eq("valid"))

    columns = {}
    lags = int(config.value("features.kc_lags"))
    for i in range(lags):
        same_day = day.shift(i) == day
        columns[f"kc_lag_{i}"] = kc_in.shift(i).where(same_day)          # past rows only
    for n in config.value("features.window_means"):
        if n > lags:
            raise ValueError("window means cannot exceed the number of lags")
        columns[f"kc_mean_{n}"] = pd.concat([columns[f"kc_lag_{i}"] for i in range(n)], axis=1).mean(axis=1, skipna=False)
    geometry = config.value("features.sun_geometry")
    if "sun_elevation_issue" in geometry:
        columns["sun_elevation_issue"] = frame.sun_elevation_deg
    if "sun_elevation_target" in geometry:
        columns["sun_elevation_target"] = frame.sun_elevation_deg.shift(-h)   # deterministic
    if "sun_azimuth_target" in geometry:
        columns["sun_azimuth_target"] = frame.sun_azimuth_deg.shift(-h)       # deterministic
    features = pd.DataFrame(columns, index=frame.index)

    target_same_day = day.shift(-h) == day
    out = features.assign(
        target_kc=kc_target.shift(-h).where(target_same_day),
        target_ghi=frame.ghi.shift(-h).where(target_same_day),
        target_ghi_clear=frame.ghi_clear.shift(-h).where(target_same_day),
        target_elevation=frame.sun_elevation_deg.shift(-h),
        target_time=frame.index + h * STEP,
        issue_day=day,
    )
    available = out.kc_lag_0.notna() & out.target_kc.notna()
    out = out[available].copy()
    out.index.name = "issue_time"
    return out, list(features.columns)
