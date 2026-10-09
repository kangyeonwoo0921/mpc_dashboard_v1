"""v1 radiation per crop cell (spec sections 8, 20, 21, 23).

Adapted conceptually from Zhang et al. (2020):
  Eq. 6     cos(theta_i) = n_i . s       (2-D roof slope -> 3-D surface normal)
  Eq. 7/24  beam on the horizontal crop plane: DNI * max(0, n_crop . s)
  Eq. 19-21 entering radiation split into direct and diffuse parts
  Eq. 30    I_total = I_dir + I_diff     (reflections excluded in v1)

  I_dir,j  = DNI * max(0, n_crop,j . s) * tau_cover * T_screen,j * S_j
  I_diff,j = DHI * tau_cover,diff * T_screen,diff,j * F_sky,j      (F_sky = 1 in v1)

Missing inputs stay None; they are never replaced by zero.
"""

from dataclasses import dataclass

import numpy as np

from .screens import crosses_deployed, deployment_fraction


@dataclass(frozen=True)
class RadiationCellResult:
    cell_id: str
    sunlit: bool
    direct_W_m2: float | None
    diffuse_W_m2: float | None
    total_W_m2: float | None


def decompose_ghi(ghi_W_m2, solar_state, weather_context):
    """GHI -> (DNI, DHI). Candidates: Erbs, Reindl, DIRINT; to be chosen after a literature review."""
    raise NotImplementedError("GHI decomposition algorithm not selected yet (spec section 23)")


def weather_status(weather):
    if weather.get("dni_W_m2") is not None and weather.get("dhi_W_m2") is not None:
        return "ok"
    if weather.get("ghi_W_m2") is not None:
        return "decomposition_required"
    return "missing_input"


def _product(values):
    """Multiply transmittances; None if any factor is unknown."""
    result = 1.0
    for value in values:
        if value is None:
            return None
        result *= value
    return result


def cell_screen_diffuse(grid, scene, optics, actuators):
    """T_screen,diff,j: product of diffuse transmittances of deployed fabric directly above each cell."""
    centers = grid.centers
    factors = np.ones(len(centers))
    unknown = np.zeros(len(centers), bool)
    for layer in scene.screens:
        fraction = deployment_fraction(actuators.get(layer.channel))
        tau = optics[layer.optics_name].tau_diffuse
        if fraction is None:
            unknown[:] = True
            continue
        above = crosses_deployed(layer, fraction, centers[:, 0], centers[:, 1])
        if tau is None:
            unknown |= above
        else:
            factors = np.where(above, factors * tau, factors)
    return [None if u else float(f) for f, u in zip(factors, unknown)]


def compute_cells(grid, solar, weather, optics, scene, actuators, rays):
    """Per-cell direct, diffuse and total irradiance plus the set of status flags raised."""
    flags = set()
    dni, dhi = weather.get("dni_W_m2"), weather.get("dhi_W_m2")
    status = weather_status(weather)
    if status != "ok":
        flags.add(status)
    cover = optics["cover"]
    screen_tau = {layer.key: optics[layer.optics_name].tau_direct for layer in scene.screens}
    screen_diffuse = cell_screen_diffuse(grid, scene, optics, actuators)
    if cover.tau_diffuse is None:
        flags.add("parameter_missing:cover.diffuse_transmittance")

    results = []
    for i, cell in enumerate(grid.cells):
        sunlit = bool(solar.is_day and not rays.blocked[i])
        # Direct (spec section 20): zero at night; zero when an opaque blocker sets S_j = 0.
        if not solar.is_day:
            direct = 0.0
        elif dni is None:
            direct = None
        elif rays.blocked[i]:
            direct = 0.0
        elif rays.unknown_hits[i] or not rays.vent_state_known[i]:
            direct = None
            flags.add("unresolved_path:unknown_optics_or_vent_state")
        else:
            crossed = [screen_tau[k] if hit[i] else 1.0 for k, hit in rays.screen_hits.items() if hit is not None]
            if any(hit is None for hit in rays.screen_hits.values()):
                crossed.append(None)
                flags.add("missing_input:screen_state")
            tau_cover = (cover.tau_direct if rays.cover_hits[i] else 1.0)
            if tau_cover is None:
                flags.add("parameter_missing:cover.direct_transmittance")
            transmission = _product([tau_cover, *crossed])
            if transmission is None:
                flags.add("parameter_missing:screen.direct_transmittance")
            cos_crop = max(0.0, float(np.dot(cell.normal_xyz, solar.sun_direction_greenhouse)))
            direct = None if transmission is None else dni * cos_crop * transmission  # S_j = 1 here
        # Diffuse (spec section 21), F_sky = 1.
        diffuse = None
        if dhi is not None:
            factor = _product([cover.tau_diffuse, screen_diffuse[i]])
            diffuse = None if factor is None else dhi * factor
        total = None if direct is None or diffuse is None else direct + diffuse
        results.append(RadiationCellResult(cell.cell_id, sunlit, direct, diffuse, total))
    return results, flags
