"""Reference (naive) forecasts of the clear-sky index on the regular 5-min grid.

Time convention: the kc table is labelled by 5-min bin start. A forecast issued when bin ``t``
closes uses bins ``t, t-1, ...`` and targets bin ``t + h`` (h >= 1 steps; h = 1 is the next bin).
GHI forecast = kc forecast x clear-sky GHI of the target bin (Yang 2019 section 3; Chu et al. 2021).

Methods (originals read):

    persistence          kc_hat(t+h) = kc(t)
                         Yang (2019, 2020) "h-step-ahead (clear-sky) persistence"; Alonso-Suarez
                         et al. (2022) "persistence"; Chu et al. (2021) call the same GHI forecast
                         "smart persistence". Yang et al. (2020) use "smart persistence" for a
                         different (cloudiness-index) reference, so the code avoids the term.
    climatology          kc_hat = mu                          single-valued internal climatology
    convex_combination   kc_hat(t+h) = rho(h) kc(t) + (1 - rho(h)) mu      Yang (2019) Eq. 5, 8
    window_mean (n)      kc_hat(t+h) = (1/n) sum_{i=0}^{n-1} kc(t-i)
                         Alonso-Suarez et al. "smart persistence with varying n"; Yang (2019)
                         section 4: a multiple-valued climatology, not persistence. Comparison only.

Internal statistics (Yang et al. 2020 section 4.2/4.3): mu and sigma^2 from the valid (filtered) kc
of the table being verified; rho(h) = cov(kc_t, kc_{t-h}) / sigma^2 from pairs h steps apart on the
regular grid (temporal spacing preserved; values below the elevation filter are not used, see
docs). Forecast inputs are the causal ``kc_input`` (valid when ``kc_input_status == "valid"``);
targets and the internal statistics use ``kc`` / ``kc_status``. A forecast exists only when its
inputs and the target are valid; nothing is filled.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .metrics import mae, mbe, rmse, skill

STEP = pd.Timedelta(minutes=5)
METHODS = ("persistence", "climatology", "convex_combination")


@dataclass(frozen=True)
class InternalStatistics:
    mu: float
    sigma2: float
    rho: dict          # h -> lag-h autocorrelation
    pairs: dict        # h -> number of pairs used


def _valid_kc(table):
    """(frame, target kc, input kc), invalid entries NaN."""
    frame = table.set_index("timestamp") if "timestamp" in table.columns else table
    if not (frame.index.to_series().diff().dropna() == STEP).all():
        raise ValueError("kc table must be on a complete, regular 5-min grid")
    return (frame, frame.kc.where(frame.kc_status.eq("valid")),
            frame.kc_input.where(frame.kc_input_status.eq("valid")))


def internal_statistics(table, horizons):
    _, kc, _ = _valid_kc(table)
    values = kc.to_numpy()
    mu = float(np.nanmean(values))
    sigma2 = float(np.nanmean((values - mu) ** 2))
    rho, pairs = {}, {}
    for h in horizons:
        a, b = values[h:], values[:-h]
        both = np.isfinite(a) & np.isfinite(b)
        rho[h] = float(np.mean((a[both] - mu) * (b[both] - mu)) / sigma2)
        pairs[h] = int(both.sum())
    return InternalStatistics(mu, sigma2, rho, pairs)


def forecast_kc(table, h, method, stats=None, n=1):
    """kc forecast indexed by target timestamp (NaN where its inputs are not valid)."""
    if h < 1:
        raise ValueError("h must be >= 1 step")
    _, _, kc = _valid_kc(table)
    if method == "persistence":
        return kc.shift(h)
    if method == "window_mean":
        return kc.rolling(n, min_periods=n).mean().shift(h)
    if stats is None:
        raise ValueError(f"{method} needs internal statistics")
    if method == "climatology":
        return pd.Series(stats.mu, index=kc.index)
    if method == "convex_combination":
        return stats.rho[h] * kc.shift(h) + (1.0 - stats.rho[h]) * stats.mu
    raise ValueError(f"unknown method {method!r}")


def evaluate(table, horizons, reference="convex_combination", window_ns=()):
    """MBE/MAE/RMSE of GHI per horizon and method, normalised by the mean measured GHI of the set,
    plus RMSE skill against ``reference``. Per horizon all methods are scored on the same target bins
    (target valid and every method's inputs valid). Returns (results, internal statistics)."""
    frame, kc, _ = _valid_kc(table)
    stats = internal_statistics(table, horizons)
    methods = [(m, 1) for m in METHODS] + [("window_mean", n) for n in window_ns]
    rows = []
    for h in horizons:
        kc_hats = {(m, n): forecast_kc(table, h, m, stats, n) for m, n in methods}
        common = kc.notna().to_numpy() & np.logical_and.reduce([s.notna().to_numpy() for s in kc_hats.values()])
        observed = frame.ghi.to_numpy()[common]
        clear = frame.ghi_clear.to_numpy()[common]
        scores = {}
        for key, s in kc_hats.items():
            predicted = s.to_numpy()[common] * clear
            scores[key] = {"mbe": mbe(predicted, observed), "mae": mae(predicted, observed),
                           "rmse": rmse(predicted, observed)}
        mean_obs = float(observed.mean())
        for (m, n), s in scores.items():
            rows.append({"horizon_min": int(h * STEP.total_seconds() // 60), "h_steps": h, "method": m,
                         "n": n if m == "window_mean" else None, "count": int(common.sum()),
                         "mean_ghi": mean_obs, **s, "nrmse": s["rmse"] / mean_obs,
                         "rho_h": stats.rho[h], "skill": skill(s["rmse"], scores[(reference, 1)]["rmse"])})
    return pd.DataFrame(rows), stats
