"""Clear-sky index kc = GHI / GHI_clear on the 5-min grid (config/solar_reference.yaml clear_sky_index).

kc is the definition ratio of the measured 5-min GHI (outside pipeline) to the 5-min Ineichen clear-sky
GHI (clearsky pipeline) on the same ``timestamp``. It is computed only where

    sun elevation at the bin centre >= clear_sky_index.min_sun_elevation_deg, and
    the measured GHI status is in clear_sky_index.ghi_statuses;

elsewhere kc is NaN and ``kc_status`` says why. No upper bound is applied (upper_bound = none).
``kc_input`` applies the same rules to the causal GHI input columns (forecast inputs only).

Note: kc is relative to the *sensor* reading, which departs from true GHI with sun elevation
(docs/CLEARSKY_REFERENCE.md section 3); kc of a clear sky is therefore not 1 at every elevation.
"""

import numpy as np
import pandas as pd

KC_STATUSES = ("valid", "night", "low_sun", "ghi_not_observed")


def _kc(ghi, ghi_status, frame, min_elevation, accepted):
    status = np.full(len(frame), "valid", dtype=object)
    status[~ghi_status.isin(accepted).to_numpy()] = "ghi_not_observed"
    status[(frame.sun_elevation_deg < min_elevation).to_numpy()] = "low_sun"
    status[(frame.ghi_clear <= 0).to_numpy()] = "night"
    valid = status == "valid"
    kc = np.where(valid, ghi.to_numpy() / np.where(valid, frame.ghi_clear.to_numpy(), 1.0), np.nan)
    return kc, pd.Series(status, dtype="str")


def clear_sky_index(outside_5min, clearsky_5min, config):
    """Table keyed by ``timestamp``: ghi, ghi_status, ghi_clear, sun_elevation_deg, sun_azimuth_deg,
    kc, kc_status (forecast targets, full QC status) and kc_input, kc_input_status (forecast inputs,
    causal QC status; ingestion/qc.py). Both inputs must share the same timestamp grid."""
    columns = ["timestamp", "ghi", "ghi_status", "ghi_input", "ghi_input_status"]
    measured = outside_5min[columns].reset_index(drop=True)
    reference = clearsky_5min[["timestamp", "ghi_clear", "sun_elevation_deg", "sun_azimuth_deg"]].reset_index(drop=True)
    if len(measured) != len(reference) or not (measured.timestamp.to_numpy() == reference.timestamp.to_numpy()).all():
        raise ValueError("outside and clear-sky 5-min tables must have identical timestamp grids")
    frame = measured.join(reference.drop(columns="timestamp"))

    min_elevation = float(config.value("clear_sky_index.min_sun_elevation_deg"))
    accepted = set(config.value("clear_sky_index.ghi_statuses"))
    frame["kc"], frame["kc_status"] = _kc(frame.ghi, frame.ghi_status, frame, min_elevation, accepted)
    frame["kc_input"], frame["kc_input_status"] = _kc(frame.ghi_input, frame.ghi_input_status, frame,
                                                      min_elevation, accepted)
    return frame
