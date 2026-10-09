"""3-D canopy light model on the viewer GLB (framework; not validated against measurements).

Extends ``light_sample`` from the 2-D section to the real geometry:

* Static occluders come from the same GLB as the viewer: frame members and the
  sandwich end panels are opaque; cover, windbreak and curtain surfaces are PO
  film with Fresnel transmittance (Zhang et al., 2020, Eqs 15-18).
* Vents and screens follow the live actuator state analytically, because the GLB
  only stores their default pose. Screens are fully diffusing layers (Miguel et
  al., 1994): beam light they transmit is re-emitted as diffuse light over the
  span below them.
* Diffuse light uses cosine-weighted sky directions. Their geometry-only part is
  traced once and cached; each update only applies vent and screen states.

Not modelled: interior reflections, outside ground reflection, canopy attenuation.
"""

import hashlib
import math
from pathlib import Path

import numpy as np
import trimesh

from src.config_loader import PROJECT_ROOT, load_config
from src.geometry_math import screen_deployed_y_ranges, span_bounds, span_centers, span_x_range, vent_bounds, vent_sides

from .light_sample import PAR_FRACTION_OF_GLOBAL, fresnel_transmittance, solar_position, split_global
from .parameters import load_physics_config

GLB_PATH = PROJECT_ROOT / "digital_twin/static/digital_twin/models/greenhouse.glb"
CACHE_DIR = PROJECT_ROOT / "tmp/light_cache"
OPAQUE_MATERIALS = {"MAT_FRAME_METAL", "MAT_END_CLADDING"}
FILM_MATERIALS = {"MAT_COVER", "MAT_END_WINDBREAK", "MAT_SIDEWALL_FIXED", "MAT_CURTAIN"}
OCCLUDER_PREFIXES = ("GH_RAFTER", "GH_TRUSS", "GH_COL_", "GH_GUTTER", "GH_RIDGE", "GH_ROOF_COVER",
                     "GH_FRONT_WALL", "GH_REAR_WALL", "GH_FRONT_STEP_WALL", "GH_SIDEWALL_", "GH_SIDE_CURTAIN_")
GLTF_TO_PHYSICS = np.array([[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], dtype=float)
CLEAR_SKY_TRANSPARENCY = 0.75  # atmosphere transparency coefficient P, Zhang et al. (2020) Eqs 10-11


def clear_sky(altitude_deg, doy, transparency=CLEAR_SKY_TRANSPARENCY):
    """Zhang et al. (2020) Eqs 10-11: horizontal beam and diffuse irradiance on a clear day."""
    sin_h = math.sin(math.radians(altitude_deg))
    if sin_h <= 0.01:
        return 0.0, 0.0
    i0 = 1367 * (1 + 0.033 * math.cos(2 * math.pi * doy / 365))
    beam = i0 * sin_h * transparency ** (1 / sin_h)
    diffuse = i0 * sin_h * (1 - transparency ** (1 / sin_h)) / (2 - 2.8 * math.log(transparency))
    return beam, diffuse


def sun_vector(altitude_deg, azimuth_deg, axis_azimuth_deg):
    """Unit vector toward the sun in physics axes (+X = X1 -> X23 at the axis azimuth)."""
    h, az, a = (math.radians(v) for v in (altitude_deg, azimuth_deg, axis_azimuth_deg))
    return np.array([math.cos(h) * math.cos(az - a), math.cos(h) * math.sin(a - az), math.sin(h)])


def _hemisphere(count):
    """Stratified cosine-weighted directions; each carries an equal share of sky light."""
    golden = math.pi * (3 - math.sqrt(5))
    k = np.arange(count) + 0.5
    sin_t = np.sqrt(k / count)
    phi = golden * k
    return np.stack([sin_t * np.cos(phi), sin_t * np.sin(phi), np.sqrt(1 - sin_t**2)], axis=1)


class LightModel:
    """Geometry cache plus per-state evaluation of canopy irradiance."""

    def __init__(self, config=None, glb_path=GLB_PATH, sky_directions=48):
        self.config = config or load_config(PROJECT_ROOT / "config/greenhouse.json")
        self.site, self.optics, radiation = load_physics_config()
        g = self.config["greenhouse"]
        beds, crops = self.config["crop_beds"], self.config["crops"]
        self.canopy_height = beds["z"] + beds["height"] + crops["plant_height"]
        self.cell = radiation["grid"]["cell_size_m"]
        self.cols, self.rows = int(g["length"] // self.cell), int(g["span_count"] * g["span_width"] // self.cell)
        self.origin = (-g["length"] / 2, -g["span_count"] * g["span_width"] / 2)
        xs = self.origin[0] + (np.arange(self.cols) + 0.5) * self.cell
        ys = self.origin[1] + (np.arange(self.rows) + 0.5) * self.cell
        gx, gy = np.meshgrid(xs, ys)  # row-major: rows along +Y, columns along +X
        self.span_of = np.clip(np.searchsorted(span_bounds(g["span_count"], g["span_width"]), gy, side="right") - 1,
                               0, g["span_count"] - 1)
        fronts = np.array([span_x_range(g, j + 1)[0] for j in range(g["span_count"])])
        self.mask = (gx >= fronts[self.span_of]).ravel()
        self.points = np.stack([gx.ravel(), gy.ravel(), np.full(gx.size, self.canopy_height)], axis=1)[self.mask]
        self.point_span = self.span_of.ravel()[self.mask]

        self.mesh, self.face_opaque = self._load_occluders(glb_path)
        self.intersector = self.mesh.ray  # Embree when embreex is installed, pure numpy otherwise
        self.tau_scale = self.optics.roof_cover.solar_transmittance_direct.value / fresnel_transmittance(0)
        self.tau_diffuse = self.tau_scale * fresnel_transmittance(60)
        self.vents = self._vent_regions()
        self.sky = self._sky_cache(glb_path, sky_directions)

    # ---- geometry -------------------------------------------------------------------------
    def _load_occluders(self, glb_path):
        scene = trimesh.load(glb_path, force="scene")
        meshes, opaque = [], []
        for node in scene.graph.nodes_geometry:
            if not node.startswith(OCCLUDER_PREFIXES):
                continue
            transform, name = scene.graph[node]
            mesh = scene.geometry[name]
            material = getattr(getattr(mesh.visual, "material", None), "name", None)
            if material not in OPAQUE_MATERIALS | FILM_MATERIALS:
                continue
            part = mesh.copy()
            part.apply_transform(GLTF_TO_PHYSICS @ transform)
            meshes.append(part)
            opaque.append(np.full(len(part.faces), material in OPAQUE_MATERIALS))
        return trimesh.util.concatenate(meshes), np.concatenate(opaque)

    def _vent_regions(self):
        """[(span index, x0, x1, y0, y1)] for each vent leaf opening in plan."""
        g = self.config["greenhouse"]
        if not self.config["roof_vents"]["enabled"]:
            return []
        regions = []
        for side in vent_sides(self.config):
            for j, c in enumerate(span_centers(g["span_count"], g["span_width"])):
                x0, x1, w = vent_bounds(self.config, side, j + 1)
                regions.append((j, side, x0, x1, *sorted((c, c + w))))
        return regions

    def _trace(self, origins, directions):
        """Static path data: (film-hit incidence cosines per ray, blocked, first exit distance)."""
        tri, ray, loc = self.intersector.intersects_id(origins, directions, multiple_hits=True, return_locations=True)
        blocked = np.zeros(len(origins), bool)
        blocked[ray[self.face_opaque[tri]]] = True
        distance = np.einsum("ij,ij->i", loc - origins[ray], directions[ray])
        exit_t = np.full(len(origins), np.inf)
        np.minimum.at(exit_t, ray, distance)
        film = ~self.face_opaque[tri]
        cosines = np.abs(np.einsum("ij,ij->i", self.mesh.face_normals[tri[film]], directions[ray[film]]))
        return ray[film], cosines, blocked, exit_t

    def _crossings(self, origins, directions, exit_t):
        """Plan position where each ray crosses the screen heights and the vent plane."""
        heights = [self.config[k]["height"] for k in ("shade_screen", "diffuse_screen")]
        heights.append(self.config["greenhouse"]["ridge_height"]["value"] - 0.3)
        out = []
        for h in heights:
            t = (h - origins[:, 2]) / np.maximum(directions[:, 2], 1e-9)
            p = origins + directions * t[:, None]
            out.append(np.stack([p[:, 0], p[:, 1], (t > 0) & (t < exit_t)], axis=1))
        return np.stack(out, axis=1)  # rays x [shade, diffuse, vent] x (x, y, valid)

    def _sky_cache(self, glb_path, count):
        digest = hashlib.sha256(Path(glb_path).read_bytes()).hexdigest()[:16]
        path = CACHE_DIR / f"sky_{digest}_{count}_{self.cell:g}_{self.canopy_height:g}.npz"
        if path.exists():
            data = np.load(path)
            return {k: data[k] for k in data.files}
        dirs = _hemisphere(count)
        origins = np.repeat(self.points, count, axis=0)
        directions = np.tile(dirs, (len(self.points), 1))
        film_ray, _, blocked, exit_t = self._trace(origins, directions)
        film_hits = np.bincount(film_ray, minlength=len(origins))
        tau = np.where(blocked, 0.0, self.tau_diffuse ** film_hits)  # diffuse film transmittance per crossing
        data = {"tau": tau.reshape(len(self.points), count),
                "cross": self._crossings(origins, directions, exit_t).reshape(len(self.points), count, 3, 3),
                "film_hits": film_hits.reshape(len(self.points), count)}
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, **data)
        return data

    # ---- state ----------------------------------------------------------------------------
    def _state_factors(self, cross, film_hits, base_tau, actuators):
        """Multiply static transmittance by vent openings and deployed screens."""
        g, v = self.config["greenhouse"], self.config["roof_vents"]
        factor = np.ones(cross.shape[:-2])
        screened = np.zeros(cross.shape[:-2], bool)
        # Vents: a ray leaving through a vent hole meets the leaf's film unless the leaf has swung clear.
        through_vent = (film_hits == 0) & (cross[..., 2, 2] > 0)
        for j, side, x0, x1, y0, y1 in self.vents:
            pct = actuators.get("roof_vent_left_pct" if side == "positive_y" else "roof_vent_right_pct")
            gap = 1 - math.cos(math.radians((pct or 0) / 100 * v["max_open_angle_deg"]))
            inside = through_vent & (cross[..., 2, 0] >= x0) & (cross[..., 2, 0] <= x1) & \
                     (cross[..., 2, 1] >= y0) & (cross[..., 2, 1] <= y1)
            factor = np.where(inside, base_tau * (1 - gap) + gap, factor)
        # 차광커튼2 = aluminium shade layer, 차광커튼1 = diffuse layer (operator report 2026-10-07).
        for layer, (key, channel, optic) in enumerate((("shade_screen", "shade_screen_2_pct", self.optics.shade_screen_2),
                                                       ("diffuse_screen", "shade_screen_1_pct", self.optics.shade_screen_1))):
            pct, tau_s = actuators.get(channel), optic.solar_transmittance_deployed.value
            if not self.config[key]["enabled"] or pct is None or tau_s is None:
                continue
            gather = self.config[key].get("gather_side", "negative_y")
            x, y, valid = cross[..., layer, 0], cross[..., layer, 1], cross[..., layer, 2] > 0
            for j, c in enumerate(span_centers(g["span_count"], g["span_width"])):
                x0, x1 = span_x_range(g, j + 1)
                for lo, hi in screen_deployed_y_ranges(c, g["span_width"], 1 - pct / 100, gather):
                    hit = valid & (x >= x0) & (x <= x1) & (y >= lo) & (y <= hi)
                    factor = np.where(hit, factor * tau_s, factor)
                    screened |= hit
        return factor, screened

    def evaluate(self, when, actuators, irradiance=None, input_basis="par", ground_reflectance=0.2,
                 screen_bottom_reflectance=0.0):
        """Canopy irradiance for one timestamp. ``irradiance=None`` uses the clear-sky model."""
        site = self.site
        altitude, azimuth = solar_position(when, site.latitude_deg, site.longitude_deg)
        doy = when.timetuple().tm_yday
        if irradiance is None:
            beam_h, diffuse_h = clear_sky(altitude, doy)
            source = "clear_sky_model"
        else:
            global_h = irradiance / PAR_FRACTION_OF_GLOBAL if input_basis == "par" else irradiance
            beam_h, diffuse_h = split_global(global_h, altitude, doy)
            source = "sensor"
        sun = sun_vector(altitude, azimuth, site.orientation.greenhouse_long_axis_azimuth_deg)
        n = len(self.points)

        # Diffuse sky light through the cached sky paths.
        sky_factor, _ = self._state_factors(self.sky["cross"], self.sky["film_hits"], self.tau_diffuse, actuators)
        diffuse = diffuse_h * (self.sky["tau"] * sky_factor).mean(axis=1)

        # Beam light traced toward the sun for this state.
        beam = np.zeros(n)
        sunlit = np.zeros(n)
        screen_pool = np.zeros(self.config["greenhouse"]["span_count"])
        if beam_h > 0 and sun[2] > 0:
            # Thin members cast narrow line shadows, so each cell averages a 3x3 sub-grid of beam rays.
            offsets = (np.arange(3) - 1) * self.cell / 3
            sub = np.array([(dx, dy, 0.0) for dx in offsets for dy in offsets])
            origins = (self.points[:, None, :] + sub[None]).reshape(-1, 3)
            owner = np.repeat(np.arange(n), len(sub))
            m = len(origins)
            directions = np.tile(sun, (m, 1))
            film_ray, cosines, blocked, exit_t = self._trace(origins, directions)
            tau_film = np.ones(m)
            np.multiply.at(tau_film, film_ray, self.tau_scale * np.array([fresnel_transmittance(math.degrees(math.acos(min(1.0, c)))) for c in cosines]))
            film_hits = np.bincount(film_ray, minlength=m)
            cosine_vent = np.full(m, fresnel_transmittance(math.degrees(math.acos(sun[2]))) * self.tau_scale)
            factor, screened = self._state_factors(self._crossings(origins, directions, exit_t), film_hits, cosine_vent, actuators)
            through = np.where(blocked, 0.0, beam_h * tau_film * factor)
            weight = 1 / len(sub)
            np.add.at(sunlit, owner, ((~blocked) & (~screened)) * weight)
            np.add.at(beam, owner, np.where(screened, 0.0, through) * weight)
            # Miguel et al. (1994): screen-transmitted beam is spread diffusely over its span.
            np.add.at(screen_pool, self.point_span[owner], np.where(screened, through, 0.0) * weight)
        cells_per_span = np.bincount(self.point_span, minlength=len(screen_pool))
        gain = 1 / (1 - screen_bottom_reflectance * ground_reflectance)
        screen_diffuse = (screen_pool / np.maximum(cells_per_span, 1) * gain)[self.point_span]
        total = beam + diffuse + screen_diffuse

        def grid(values):
            full = np.full(self.mask.size, np.nan)
            full[self.mask] = values
            return full

        return {
            "timestamp": when.isoformat(),
            "sun": {"altitude_deg": altitude, "azimuth_deg": azimuth, "direction_physics": sun.tolist()},
            "outside": {"source": source, "beam_h_w_m2": beam_h, "diffuse_h_w_m2": diffuse_h,
                        "global_h_w_m2": beam_h + diffuse_h},
            "canopy_height_m": self.canopy_height,
            "mean": {"global_w_m2": float(total.mean()), "par_w_m2": float(total.mean() * PAR_FRACTION_OF_GLOBAL),
                     "beam_w_m2": float(beam.mean()), "sky_diffuse_w_m2": float(diffuse.mean()),
                     "screen_diffuse_w_m2": float(screen_diffuse.mean()), "sunlit_fraction": float(sunlit.mean())},
            "grid": {"cell_size_m": self.cell, "rows": self.rows, "cols": self.cols, "origin_xy_m": list(self.origin),
                     "global_w_m2": grid(total), "sunlit": grid(sunlit)},
        }


_shared = None


def shared_model():
    """Process-wide model; the first call builds (or loads) the geometry cache."""
    global _shared
    if _shared is None:
        _shared = LightModel()
    return _shared
