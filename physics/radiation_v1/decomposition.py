"""GHI -> DNI/DHI separation with Engerer2 (spec section 23).

Source (original checked, mpc_lab/reference/papers/Yang(2022).pdf):
  Yang D. (2022), Estimating 1-min beam and diffuse irradiance from the global irradiance:
  A review and an extensive worldwide comparison of latest separation models at 126 stations,
  Renewable and Sustainable Energy Reviews 159:112195, Eqs. (4)-(7) and Table 1.
  The model itself is Engerer N.A. (2015), Solar Energy 116:215-237 (original not checked).

  k_d = C + (1 - C) / (1 + exp(b0 + b1 k_t + b2 AST + b3 Z + b4 dk_tc)) + b5 k_de     (Eq. 6)
  k_t = G_h / E_0, k_tc = G_csky / E_0, dk_tc = k_tc - k_t, k_de = max(0, 1 - G_csky / G_h)
  DHI = k_d G_h, DNI = (G_h - DHI) / cos Z

Yang4 (the review's best model) needs an hourly Engerer2 estimate whose computation is only in
Yang (2021), J. Renew. Sustain. Energy 13:056101, which was not available, so it is not used.

Deviations, reported with every result:
  - G_csky: pvlib Ineichen-Perez with the SoDa Linke turbidity climatology (the mpc_lab clear-sky
    reference), not McClear as in Yang (2022).
  - Coefficients were fitted on 1-min data; the field sensor gives instantaneous readings.
  - Z >= 85 deg is not separated (no DNI); Lee et al. (2017), Energies 10:594, excluded those
    angles for the same reason (cos Z near zero amplifies errors).
  - k_d is clipped to [0, 1].
"""

import math

import pandas as pd
import pvlib

MODEL_ID = "engerer2"
COEFFICIENTS = {"C": 0.042336, "b0": -3.7912, "b1": 7.5479, "b2": -0.010036,
                "b3": 0.003148, "b4": -5.3146, "b5": 1.7073}
SOURCE = "Engerer2 (Engerer 2015) as given in Yang (2022), RSER 159:112195, Eq. 6-7"
MAX_ZENITH_DEG = 85.0
STANDARD_MERIDIAN_DEG = 135.0  # KST = UTC+9, no daylight saving


def solar_terms(timestamp, site):
    """Zenith, E_0, clear-sky GHI and apparent solar time for one aware timestamp."""
    times = pd.DatetimeIndex([timestamp])
    if times.tz is None:
        raise ValueError("timestamp must be timezone-aware")
    position = pvlib.solarposition.get_solarposition(times, site.latitude_deg, site.longitude_deg,
                                                     altitude=site.elevation_m or 0, method="nrel_numpy")
    zenith = float(position["apparent_zenith"].iloc[0])
    pressure = pvlib.atmosphere.alt2pres(site.elevation_m or 0)
    airmass = pvlib.atmosphere.get_absolute_airmass(
        pvlib.atmosphere.get_relative_airmass(position["apparent_zenith"], model="kastenyoung1989"), pressure)
    turbidity = pvlib.clearsky.lookup_linke_turbidity(times, site.latitude_deg, site.longitude_deg, interp_turbidity=True)
    dni_extra = pvlib.irradiance.get_extra_radiation(times)
    clear = pvlib.clearsky.ineichen(position["apparent_zenith"], airmass, turbidity,
                                    altitude=site.elevation_m or 0, dni_extra=dni_extra)
    standard = times.tz_convert("Etc/GMT-9")[0]
    clock_h = standard.hour + standard.minute / 60 + standard.second / 3600
    eot_min = float(position["equation_of_time"].iloc[0])
    ast_h = (clock_h + (4 * (site.longitude_deg - STANDARD_MERIDIAN_DEG) + eot_min) / 60) % 24
    cos_z = math.cos(math.radians(zenith))
    return {"zenith_deg": zenith, "e0_W_m2": float(dni_extra.iloc[0]) * max(cos_z, 0.0),
            "ghi_clear_W_m2": float(clear["ghi"].iloc[0]), "ast_h": ast_h}


def engerer2(ghi, zenith_deg, e0, ghi_clear, ast_h, c=COEFFICIENTS):
    """Diffuse fraction k_d (clipped to [0, 1]) for one instant with G_h > 0 and E_0 > 0."""
    kt = ghi / e0
    dktc = ghi_clear / e0 - kt
    kde = max(0.0, 1 - ghi_clear / ghi)
    exponent = c["b0"] + c["b1"] * kt + c["b2"] * ast_h + c["b3"] * zenith_deg + c["b4"] * dktc
    kd = c["C"] + (1 - c["C"]) / (1 + math.exp(exponent)) + c["b5"] * kde
    return min(1.0, max(0.0, kd)), {"kt": kt, "dktc": dktc, "kde": kde}


def decompose_ghi(ghi_W_m2, timestamp, site):
    """(dni, dhi, info). dni/dhi stay None when the separation is not defined; info explains why."""
    info = {"model": MODEL_ID, "source": SOURCE, "estimated": True,
            "clear_sky": "pvlib Ineichen-Perez, SoDa Linke turbidity (McClear in the source)"}
    if ghi_W_m2 is None:
        return None, None, {**info, "status": "missing_input"}
    terms = solar_terms(timestamp, site)
    info.update({k: round(v, 4) for k, v in terms.items()})
    if terms["zenith_deg"] >= 90:
        return 0.0, 0.0, {**info, "status": "night"}
    if terms["zenith_deg"] >= MAX_ZENITH_DEG:
        return None, None, {**info, "status": "out_of_range:zenith_ge_85"}
    if ghi_W_m2 <= 0:
        return 0.0, 0.0, {**info, "status": "ok", "kd": None}
    kd, parts = engerer2(ghi_W_m2, terms["zenith_deg"], terms["e0_W_m2"], terms["ghi_clear_W_m2"], terms["ast_h"])
    dhi = kd * ghi_W_m2
    dni = (ghi_W_m2 - dhi) / math.cos(math.radians(terms["zenith_deg"]))
    info.update({"status": "ok", "kd": round(kd, 4), **{k: round(v, 4) for k, v in parts.items()}})
    return dni, dhi, info
