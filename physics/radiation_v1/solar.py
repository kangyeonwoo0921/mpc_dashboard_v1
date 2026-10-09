"""Solar position via pvlib (NREL SPA), as the spec requires (section 9).

No astronomy formulas are implemented here.
"""

from dataclasses import dataclass
from datetime import timedelta

import pandas as pd
import pvlib

from ..coordinates import enu_from_altitude_azimuth, enu_to_greenhouse, normalized_direction


@dataclass(frozen=True)
class SolarState:
    altitude_deg: float
    azimuth_deg: float
    sun_direction_world: tuple[float, float, float]       # ENU
    sun_direction_greenhouse: tuple[float, float, float]  # physics +X long axis, +Y left, +Z up

    @property
    def is_day(self):
        return self.altitude_deg > 0


def _positions(timestamps, site):
    if site.latitude_deg is None or site.longitude_deg is None:
        raise ValueError("site latitude and longitude are required for solar position")
    index = pd.DatetimeIndex(timestamps)
    if index.tz is None:
        raise ValueError("timestamps must be timezone-aware")
    return pvlib.solarposition.get_solarposition(index, site.latitude_deg, site.longitude_deg,
                                                 altitude=site.elevation_m if site.elevation_m is not None else 0)


def calculate_solar_state(timestamp, site):
    """Apparent (refraction-corrected) altitude and azimuth for one aware timestamp."""
    if site.greenhouse_long_axis_azimuth_deg is None:
        raise ValueError("greenhouse_long_axis_azimuth_deg is required")
    row = _positions([timestamp], site).iloc[0]
    altitude, azimuth = float(row["apparent_elevation"]), float(row["azimuth"])
    world = normalized_direction(enu_from_altitude_azimuth(altitude, azimuth))
    local = normalized_direction(enu_to_greenhouse(world, site.greenhouse_long_axis_azimuth_deg))
    return SolarState(altitude, azimuth, world, local)


def daily_sun_path(timestamp, site, step_minutes=20):
    """Greenhouse-axis sun directions above the horizon for the timestamp's local day."""
    start = timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
    times = [start + timedelta(minutes=m) for m in range(0, 24 * 60, step_minutes)]
    path = []
    for (_, row), moment in zip(_positions(times, site).iterrows(), times):
        if row["apparent_elevation"] > 0:
            world = enu_from_altitude_azimuth(row["apparent_elevation"], row["azimuth"])
            path.append(normalized_direction(enu_to_greenhouse(world, site.greenhouse_long_axis_azimuth_deg)))
    return path
