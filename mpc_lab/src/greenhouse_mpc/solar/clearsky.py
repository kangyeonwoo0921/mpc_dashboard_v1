"""Clear-sky irradiance with literature models implemented by pvlib (config/solar_reference.yaml).

Chain (each step explicit, no library default relied on):

    solar position      NREL SPA (Reda & Andreas 2004)               -> apparent zenith, azimuth
    pressure            standard atmosphere at the site altitude      -> p [Pa]
    airmass             Kasten & Young (1989), relative -> absolute   -> AM_abs
    Linke turbidity     Remund et al. (2003) monthly climatology      -> TL (daily interpolated)
    extraterrestrial    Spencer (1971), solar constant 1366.1 W/m2    -> I0n
    clear sky           Ineichen & Perez (2002)                      -> GHI_clear, DNI_clear, DHI_clear

Night (apparent zenith >= 90 deg) gives 0 W/m2 from the Ineichen model itself. The clear-sky index
is computed in ``clearsky_index``.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pvlib
import yaml

from ..config_loader import CONFIG_DIR, load_config_file
from ..ingestion.outside_schema import Site, _site
from ..provenance import Parameter, ProvenanceError, parse_parameters

SUPPORTED = {
    "solar_position": {"nrel_spa": "nrel_numpy"},
    "clear_sky_model": {"ineichen_perez": "ineichen"},
    "linke_turbidity": {"pvlib_monthly_climatology": "lookup"},
    "airmass_model": {"kastenyoung1989": "kastenyoung1989"},
    "extraterrestrial_irradiance": {"spencer_1971": "spencer"},
    "pressure": {"standard_atmosphere_from_altitude": "alt2pres"},
    "aggregation.five_min": {"mean_of_minute_centres": "mean"},
    "clear_sky_index.upper_bound": {"none": None},
}
IRRADIANCE = ("ghi_clear", "dni_clear", "dhi_clear")


@dataclass(frozen=True)
class ClearSkyConfig:
    tree: dict
    site: Site

    def value(self, dotted):
        node = self.tree
        for key in dotted.split("."):
            node = node[key]
        if not isinstance(node, Parameter):
            raise ProvenanceError(f"{dotted} is not a parameter record")
        return node.value

    def method(self, dotted):
        return SUPPORTED[dotted][self.value(dotted)]

    def fingerprint(self, include_index=False):
        """Clear-sky settings + site; the clear_sky_index section only when ``include_index`` (so kc
        settings do not change the clear-sky dataset id)."""
        def plain(node):
            if isinstance(node, Parameter):
                return {"value": node.value, "status": node.status}
            return {k: plain(v) for k, v in node.items()} if isinstance(node, dict) else node
        tree = {k: v for k, v in self.tree.items() if include_index or k != "clear_sky_index"}
        text = json.dumps({"config": plain(tree), "site": vars(self.site)}, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_clearsky_config(path=None, config_dir=CONFIG_DIR):
    path = Path(path) if path else Path(config_dir) / "solar_reference.yaml"
    tree = parse_parameters(yaml.safe_load(path.read_text(encoding="utf-8")), "solar_reference")
    config = ClearSkyConfig(tree, _site(load_config_file("greenhouse", config_dir)))
    if config.site is None:
        raise ProvenanceError("site latitude/longitude/elevation are required (config/greenhouse.yaml)")
    for dotted, allowed in SUPPORTED.items():
        if config.value(dotted) not in allowed:
            raise ProvenanceError(f"{dotted} = {config.value(dotted)!r} is not implemented (supported: {sorted(allowed)})")
    return config


def clearsky_at(times, config):
    """Clear-sky irradiance and its intermediate quantities at the given instants (tz-aware)."""
    times = pd.DatetimeIndex(times)
    if times.tz is None:
        raise ValueError("times must be timezone-aware")
    site = config.site
    position = pvlib.solarposition.get_solarposition(times, site.latitude_deg, site.longitude_deg,
                                                     altitude=site.elevation_m, method=config.method("solar_position"))
    pressure = pvlib.atmosphere.alt2pres(site.elevation_m)
    airmass_relative = pvlib.atmosphere.get_relative_airmass(position["apparent_zenith"], model=config.method("airmass_model"))
    airmass_absolute = pvlib.atmosphere.get_absolute_airmass(airmass_relative, pressure)
    turbidity = pvlib.clearsky.lookup_linke_turbidity(times, site.latitude_deg, site.longitude_deg, interp_turbidity=True)
    dni_extra = pvlib.irradiance.get_extra_radiation(times, solar_constant=config.value("solar_constant"),
                                                     method=config.method("extraterrestrial_irradiance"))
    clear = pvlib.clearsky.ineichen(position["apparent_zenith"], airmass_absolute, turbidity,
                                    altitude=site.elevation_m, dni_extra=dni_extra,
                                    perez_enhancement=bool(config.value("perez_enhancement")))
    return pd.DataFrame({
        "sun_zenith_apparent_deg": position["apparent_zenith"].to_numpy(),
        "sun_elevation_deg": position["apparent_elevation"].to_numpy(),
        "sun_azimuth_deg": position["azimuth"].to_numpy(),
        "pressure_pa": np.full(len(times), float(pressure)),
        "airmass_relative": np.asarray(airmass_relative, dtype=float),
        "airmass_absolute": np.asarray(airmass_absolute, dtype=float),
        "linke_turbidity": np.asarray(turbidity, dtype=float),
        "dni_extra_w_m2": np.asarray(dni_extra, dtype=float),
        "ghi_clear": clear["ghi"].to_numpy(dtype=float),
        "dni_clear": clear["dni"].to_numpy(dtype=float),
        "dhi_clear": clear["dhi"].to_numpy(dtype=float),
    }, index=times)


def clearsky_minute(bin_starts, config):
    """1-min table: values at the bin centre (start + minute_sample_offset_s), labelled by bin start."""
    starts = pd.DatetimeIndex(bin_starts)
    offset = pd.Timedelta(seconds=float(config.value("aggregation.minute_sample_offset_s")))
    frame = clearsky_at(starts + offset, config)
    frame.index = starts
    frame.index.name = "timestamp"
    return frame.reset_index()


def clearsky_five_minute(bin_starts, config):
    """5-min table: irradiance = mean of the five 1-min centre values (same rule as the measured
    5-min mean); geometry and other intermediates at the bin centre (start + 150 s)."""
    starts = pd.DatetimeIndex(bin_starts)
    offset = pd.Timedelta(seconds=float(config.value("aggregation.minute_sample_offset_s")))
    shifted = [starts + pd.Timedelta(minutes=k) + offset for k in range(5)]
    minutes = shifted[0].append(shifted[1:])          # k-major order; keeps tz and time unit
    values = clearsky_at(minutes, config)[list(IRRADIANCE)].to_numpy().reshape(5, len(starts), len(IRRADIANCE))
    frame = clearsky_at(starts + pd.Timedelta(seconds=150), config)
    frame[list(IRRADIANCE)] = values.mean(axis=0)
    frame.index = starts
    frame.index.name = "timestamp"
    return frame.reset_index()
