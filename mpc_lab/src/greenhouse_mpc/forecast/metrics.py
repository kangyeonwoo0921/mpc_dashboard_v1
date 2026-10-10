"""Deterministic error metrics and skill (Chu et al. 2021, Assessment methods).

    MBE  = 1/n sum (I_hat - I)
    MAE  = 1/n sum |I_hat - I|
    RMSE = sqrt(1/n sum (I_hat - I)^2)
    s    = 1 - RMSE / RMSE_ref           (forecast skill against a reference forecast)

Relative errors divide by the mean measured value of the same evaluation set (one of the three
normalisations listed by Chu et al.; recorded as a project choice).
"""

import numpy as np


def _pair(forecast, observed):
    forecast, observed = np.asarray(forecast, dtype=float), np.asarray(observed, dtype=float)
    if forecast.shape != observed.shape:
        raise ValueError("forecast and observed must have the same shape")
    if not (np.isfinite(forecast).all() and np.isfinite(observed).all()):
        raise ValueError("metrics need finite values; select the evaluation set first")
    return forecast, observed


def mbe(forecast, observed):
    forecast, observed = _pair(forecast, observed)
    return float(np.mean(forecast - observed))


def mae(forecast, observed):
    forecast, observed = _pair(forecast, observed)
    return float(np.mean(np.abs(forecast - observed)))


def rmse(forecast, observed):
    forecast, observed = _pair(forecast, observed)
    return float(np.sqrt(np.mean((forecast - observed) ** 2)))


def skill(rmse_model, rmse_reference):
    return float(1.0 - rmse_model / rmse_reference)
