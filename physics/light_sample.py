"""Sample 2-D cross-section light model (framework only; not validated).

Treats the 97.5 m house as infinitely long and works in its Y-Z cross-section,
as both reference models do:

* Zhang et al. (2020), Energies 13:1108 -- solar geometry, Fresnel cover
  transmittance (Eqs 15-18, PO film Z=1.535), diffuse cover transmittance taken
  at 60 deg incidence, beam ray tracing to a horizontal canopy plane (Eq 23),
  2-D angular distribution for isotropic diffuse light (Eq 25).
* Miguel et al. (1994), J. agric. Engng Res. 59:61-72 -- screens as fully
  diffusing, partially transparent layers; light passing a screen is re-emitted
  diffusely below it with a screen/ground inter-reflection correction (Eq 15).

Not modelled yet: roof vents, structure shading, reflections between interior
surfaces, outside ground reflection, canopy attenuation, the stepped front.
"""

import math
from datetime import datetime

from src.config_loader import PROJECT_ROOT, load_config
from src.geometry_math import arch_height, roof_arch_radius, screen_deployed_y_ranges, span_centers

from .parameters import load_physics_config

PO_FILM_REFRACTIVE_INDEX = 1.535  # Zhang et al. (2020), ref. [35]
PAR_FRACTION_OF_GLOBAL = 0.47     # assumption until the sensor basis is confirmed


def solar_position(when, latitude_deg, longitude_deg):
    """Return (altitude_deg, azimuth_deg clockwise from north) with Spencer's series."""
    if when.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    doy = when.timetuple().tm_yday
    b = 2 * math.pi * (doy - 1) / 365
    decl = (0.006918 - 0.399912 * math.cos(b) + 0.070257 * math.sin(b) - 0.006758 * math.cos(2 * b)
            + 0.000907 * math.sin(2 * b) - 0.002697 * math.cos(3 * b) + 0.00148 * math.sin(3 * b))
    eot_min = 229.18 * (0.000075 + 0.001868 * math.cos(b) - 0.032077 * math.sin(b)
                        - 0.014615 * math.cos(2 * b) - 0.040849 * math.sin(2 * b))
    utc_offset_h = when.utcoffset().total_seconds() / 3600
    clock_h = when.hour + when.minute / 60 + when.second / 3600
    solar_h = clock_h + (4 * (longitude_deg - 15 * utc_offset_h) + eot_min) / 60
    hour_angle = math.radians(15 * (solar_h - 12))
    lat = math.radians(latitude_deg)
    sin_alt = math.sin(lat) * math.sin(decl) + math.cos(lat) * math.cos(decl) * math.cos(hour_angle)
    altitude = math.degrees(math.asin(max(-1.0, min(1.0, sin_alt))))
    azimuth = math.degrees(math.atan2(math.sin(hour_angle),
                                      math.cos(hour_angle) * math.sin(lat) - math.tan(decl) * math.cos(lat))) + 180
    return altitude, azimuth % 360


def split_global(ghi, altitude_deg, doy):
    """Erbs decomposition of horizontal global irradiance into (beam_h, diffuse_h)."""
    sin_h = math.sin(math.radians(altitude_deg))
    if ghi <= 0 or sin_h <= 0.01:
        return 0.0, max(ghi, 0.0)
    extraterrestrial = 1367 * (1 + 0.033 * math.cos(2 * math.pi * doy / 365)) * sin_h
    kt = min(ghi / extraterrestrial, 1.0)
    if kt <= 0.22:
        kd = 1 - 0.09 * kt
    elif kt <= 0.8:
        kd = 0.9511 - 0.1604 * kt + 4.388 * kt**2 - 16.638 * kt**3 + 12.336 * kt**4
    else:
        kd = 0.165
    return ghi * (1 - kd), ghi * kd


def fresnel_transmittance(incidence_deg, refractive_index=PO_FILM_REFRACTIVE_INDEX):
    """Zhang et al. (2020) Eqs 15-18: non-absorbing slab, both polarisations."""
    theta = math.radians(min(abs(incidence_deg), 89.999))
    if theta < 1e-6:
        r = ((refractive_index - 1) / (refractive_index + 1)) ** 2
        return (1 - r) / (1 + r)
    theta_z = math.asin(math.sin(theta) / refractive_index)
    p_perp = math.sin(theta_z - theta) ** 2 / math.sin(theta_z + theta) ** 2
    p_par = math.tan(theta_z - theta) ** 2 / math.tan(theta_z + theta) ** 2
    return 0.5 * ((1 - p_perp) / (1 + p_perp) + (1 - p_par) / (1 + p_par))


class CrossSection:
    """Roof and side walls of the greenhouse as 2-D segments (y, z)."""

    def __init__(self, config):
        g = config["greenhouse"]
        self.width = g["span_width"] * g["span_count"]
        self.span_width = g["span_width"]
        self.centers = span_centers(g["span_count"], g["span_width"])
        eave, ridge, radius = g["eave_height"]["value"], g["ridge_height"]["value"], roof_arch_radius(g)
        n = g["roof"]["segments_per_span"]
        self.segments = []  # (y0, z0, y1, z1)
        for c in self.centers:
            ys = [c - g["span_width"] / 2 + g["span_width"] * i / n for i in range(n + 1)]
            zs = [arch_height(y - c, g["span_width"], eave, ridge, radius) for y in ys]
            self.segments += [(ys[i], zs[i], ys[i + 1], zs[i + 1]) for i in range(n)]
        half = self.width / 2
        self.segments += [(-half, 0.0, -half, eave), (half, 0.0, half, eave)]

    def exit(self, y, z, dy, dz):
        """First envelope segment hit by a ray; returns (segment, unit normal (ny, nz))."""
        best = None
        for seg in self.segments:
            y0, z0, y1, z1 = seg
            ey, ez = y1 - y0, z1 - z0
            det = dy * (-ez) - dz * (-ey)
            if abs(det) < 1e-12:
                continue
            t = ((y0 - y) * (-ez) - (z0 - z) * (-ey)) / det
            u = (dy * (z0 - z) - dz * (y0 - y)) / det
            if t > 1e-9 and -1e-9 <= u <= 1 + 1e-9 and (best is None or t < best[0]):
                best = (t, seg)
        if best is None:
            return None, None
        y0, z0, y1, z1 = best[1]
        length = math.hypot(y1 - y0, z1 - z0)
        return best[1], (-(z1 - z0) / length, (y1 - y0) / length)


def screen_layers(config, optics, actuators):
    """[(height, transmittance, deployed (y0, y1) ranges)] for the two screen channels."""
    g = config["greenhouse"]
    layers = []
    # 차광커튼2 = aluminium shade layer, 차광커튼1 = diffuse layer (operator report 2026-10-07).
    for key, channel, optic in (("shade_screen", "shade_screen_2_pct", optics.shade_screen_2),
                                ("diffuse_screen", "shade_screen_1_pct", optics.shade_screen_1)):
        opening = actuators.get(channel)
        tau = optic.solar_transmittance_deployed.value
        if not config[key]["enabled"] or opening is None or tau is None:
            continue
        deployed = 1 - opening / 100
        gather = config[key].get("gather_side", "negative_y")
        ranges = []
        for c in span_centers(g["span_count"], g["span_width"]):
            ranges.extend(screen_deployed_y_ranges(c, g["span_width"], deployed, gather))
        layers.append((config[key]["height"], tau, ranges))
    return sorted(layers, reverse=True)


def screen_factor(layers, y, z, dy, dz, z_top):
    """Product of screen transmittances crossed between the canopy and the envelope."""
    factor = 1.0
    for height, tau, ranges in layers:
        if z < height < z_top:
            y_cross = y + (height - z) * dy / dz
            if any(a <= y_cross <= b for a, b in ranges):
                factor *= tau
    return factor


def simulate_cross_section(when, irradiance, actuators, *, input_basis="par", canopy_height=None,
                           ground_reflectance=0.2, screen_bottom_reflectance=0.0,
                           diffuse_directions=90, config=None, site=None, optics=None, radiation=None):
    """Canopy-plane irradiance across the house width for one timestamp."""
    config = config or load_config(PROJECT_ROOT / "config/greenhouse.json")
    if site is None or optics is None or radiation is None:
        site, optics, radiation = load_physics_config()
    if site.latitude_deg is None or site.longitude_deg is None or site.orientation.greenhouse_long_axis_azimuth_deg is None:
        raise ValueError("site latitude, longitude and orientation are required")
    tau_normal = optics.roof_cover.solar_transmittance_direct.value
    if tau_normal is None:
        raise ValueError("roof cover transmittance is required")
    if canopy_height is None:
        beds, crops = config["crop_beds"], config["crops"]
        canopy_height = beds["z"] + beds["height"] + crops["plant_height"]

    # Outside light: sensor value -> global equivalent -> beam/diffuse split.
    global_h = irradiance / PAR_FRACTION_OF_GLOBAL if input_basis == "par" else irradiance
    altitude, azimuth = solar_position(when, site.latitude_deg, site.longitude_deg)
    beam_h, diffuse_h = split_global(global_h, altitude, when.timetuple().tm_yday)

    # Sun direction in physics axes (+X = X1 -> X23 at azimuth A, +Y to its left).
    a, az, h = (math.radians(v) for v in (site.orientation.greenhouse_long_axis_azimuth_deg, azimuth, altitude))
    sun_y, sun_z = math.cos(h) * math.sin(a - az), math.sin(h)

    scale = tau_normal / fresnel_transmittance(0)
    tau_diffuse = scale * fresnel_transmittance(60)  # Zhang et al. (2020): diffuse ~ beam at 60 deg
    section = CrossSection(config)
    layers = screen_layers(config, optics, actuators)
    cell = radiation["grid"]["cell_size_m"]
    count = max(1, round(section.width / cell))
    ys = [-section.width / 2 + (i + 0.5) * section.width / count for i in range(count)]

    beam, sky, intercepted = [], [], [0.0] * len(section.centers)
    for y in ys:
        b = 0.0
        if beam_h > 0 and sun_z > 0:
            seg, normal = section.exit(y, canopy_height, sun_y, sun_z)
            if seg is not None:
                cos_inc = abs(normal[0] * sun_y + normal[1] * sun_z)
                through_cover = beam_h * scale * fresnel_transmittance(math.degrees(math.acos(min(1.0, cos_inc))))
                f = screen_factor(layers, y, canopy_height, sun_y, sun_z, max(seg[1], seg[3]))
                if f < 1.0:
                    # Miguel et al. (1994): a screen re-emits what it transmits as diffuse light.
                    span = min(range(len(section.centers)), key=lambda j: abs(section.centers[j] - y))
                    intercepted[span] += through_cover * f * cell
                else:
                    b = through_cover
        d = 0.0
        for k in range(diffuse_directions):
            delta = -math.pi / 2 + (k + 0.5) * math.pi / diffuse_directions
            dy, dz = math.sin(delta), math.cos(delta)
            seg, _ = section.exit(y, canopy_height, dy, dz)
            if seg is not None:
                weight = 0.5 * math.cos(delta) * math.pi / diffuse_directions  # 2-D view factor
                d += weight * tau_diffuse * screen_factor(layers, y, canopy_height, dy, dz, max(seg[1], seg[3]))
        beam.append(b)
        sky.append(diffuse_h * d)

    # Screen-diffused beam spread over each span, with screen/ground inter-reflection.
    reflection_gain = 1 / (1 - screen_bottom_reflectance * ground_reflectance)
    screen_diffuse = [intercepted[min(range(len(section.centers)), key=lambda j: abs(section.centers[j] - y))]
                      / section.span_width * reflection_gain for y in ys]
    total = [b + s + r for b, s, r in zip(beam, sky, screen_diffuse)]
    mean = lambda values: sum(values) / len(values)
    return {
        "timestamp": when.isoformat(),
        "sun": {"altitude_deg": altitude, "azimuth_deg": azimuth},
        "outside": {"global_h_w_m2": global_h, "beam_h_w_m2": beam_h, "diffuse_h_w_m2": diffuse_h},
        "canopy_height_m": canopy_height,
        "y_m": ys,
        "global_w_m2": total,
        "par_w_m2": [v * PAR_FRACTION_OF_GLOBAL for v in total],
        "mean": {"global_w_m2": mean(total), "par_w_m2": mean(total) * PAR_FRACTION_OF_GLOBAL,
                 "beam_w_m2": mean(beam), "sky_diffuse_w_m2": mean(sky), "screen_diffuse_w_m2": mean(screen_diffuse)},
        "assumptions": [
            "2-D cross-section of an infinitely long house; stepped front and end walls ignored",
            f"PAR = {PAR_FRACTION_OF_GLOBAL} x global; Erbs split applied to the global equivalent",
            "Cover transmittance follows Fresnel (Z=1.535) scaled to the reported normal value",
            "Screens fully diffusing; vents, structure shading and interior reflections not modelled",
        ],
    }


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Sample cross-section light model")
    parser.add_argument("--time", required=True, help="aware ISO time, e.g. 2026-10-01T12:00+09:00")
    parser.add_argument("--irradiance", type=float, required=True, help="outside sensor value, W/m2")
    parser.add_argument("--basis", choices=("par", "global"), default="par")
    parser.add_argument("--shade", type=float, default=100, help="shade screen opening %%")
    parser.add_argument("--diffuse", type=float, default=100, help="diffuse screen opening %%")
    args = parser.parse_args()
    result = simulate_cross_section(datetime.fromisoformat(args.time), args.irradiance,
                                    {"shade_screen_2_pct": args.shade, "shade_screen_1_pct": args.diffuse},
                                    input_basis=args.basis)
    print(json.dumps({k: result[k] for k in ("timestamp", "sun", "outside", "canopy_height_m", "mean")}, indent=2))
