"""Psychrometric helpers derived from air temperature and relative humidity.

Uses the Tetens/Magnus form with a single constant set so VPD and dew point
stay mutually consistent.
"""

from __future__ import annotations

import math

_A_KPA = 0.6108
_B = 17.27
_C_C = 237.3


def saturation_vapor_pressure_kpa(temperature_c: float) -> float:
    return _A_KPA * math.exp(_B * temperature_c / (temperature_c + _C_C))


def vpd_kpa(temperature_c: float, rh_pct: float) -> float:
    rh = min(100.0, max(0.0, rh_pct))
    return saturation_vapor_pressure_kpa(temperature_c) * (1.0 - rh / 100.0)


def dew_point_c(temperature_c: float, rh_pct: float) -> float | None:
    rh = min(100.0, rh_pct)
    if rh <= 0.0:
        return None
    gamma = math.log(rh / 100.0) + _B * temperature_c / (temperature_c + _C_C)
    return _C_C * gamma / (_B - gamma)
