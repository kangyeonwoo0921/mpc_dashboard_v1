"""Orchestration for the v1 model: configuration + scene cache + one evaluation.

Pure physics lives in the sibling modules; this layer only wires them together
so the Django view stays free of physics code (spec section 31, rule 3).
"""

import math

from src.config_loader import PROJECT_ROOT, load_config

from ..coordinates import physics_to_threejs
from .aggregation import summarize
from .config import load_optics, load_radiation, load_site
from .decomposition import decompose_ghi
from .geometry import build_crop_grid, load_scene
from .radiation import compute_cells
from .raytrace import trace_direct_rays
from .solar import calculate_solar_state, daily_sun_path


class RadiationModelV1:
    def __init__(self):
        self.config = load_config(PROJECT_ROOT / "config/greenhouse.json")
        self.site = load_site()
        self.optics = load_optics()
        self.radiation = load_radiation()
        if self.radiation.crop_reference_height_m is None:
            raise ValueError("crop_reference_height_m is required to place the crop grid")
        self.grid = build_crop_grid(self.config, self.radiation.grid_resolution_m,
                                    self.radiation.crop_reference_height_m)
        self.scene = load_scene(self.config)

    def separate(self, timestamp, weather):
        """Fill DNI/DHI from GHI with the separation model when they are not measured (estimated values)."""
        if weather.get("dni_W_m2") is not None and weather.get("dhi_W_m2") is not None:
            return weather, None
        dni, dhi, info = decompose_ghi(weather.get("ghi_W_m2"), timestamp, self.site)
        return {**weather, "dni_W_m2": dni, "dhi_W_m2": dhi, "decomposition": info}, info

    def evaluate(self, timestamp, weather, actuators):
        weather, separation = self.separate(timestamp, weather)
        solar = calculate_solar_state(timestamp, self.site)
        if solar.is_day:
            rays = trace_direct_rays(self.grid.centers, solar.sun_direction_greenhouse, self.scene, actuators)
        else:
            rays = None
        results, flags = compute_cells(self.grid, solar, weather, self.optics, self.scene, actuators,
                                       rays or _night_rays(len(self.grid.cells), self.scene))
        if separation and separation["status"].startswith("out_of_range"):
            flags.add(f"decomposition_{separation['status']}")
        summary = summarize(results, self.grid.cells)
        primary = "ok" if not flags else sorted(flags, key=_status_rank)[0]
        return {"solar": solar, "cells": results, "summary": summary, "status": primary, "statuses": sorted(flags),
                "weather": weather}

    def provenance(self):
        return {
            "site": dict(self.site.provenance, verified=self.site.verified),
            "cover": {"provenance": self.optics["cover"].provenance, "verified": self.optics["cover"].verified},
            "shade_screen_1": {"provenance": self.optics["shade_screen_1"].provenance,
                               "verified": self.optics["shade_screen_1"].verified},
            "shade_screen_2": {"provenance": self.optics["shade_screen_2"].provenance,
                               "verified": self.optics["shade_screen_2"].verified},
            "crop_reference_height": self.radiation.crop_reference_height_provenance,
        }

    def to_api(self, timestamp, weather, actuators):
        """Spec section 30 response plus the grid and sun path the viewer needs."""
        outcome = self.evaluate(timestamp, weather, actuators)
        solar = outcome["solar"]
        size = self.grid.rows * self.grid.cols

        def grid_values(attribute):
            values = [None] * size
            for index, result in zip(self.grid.flat_index, outcome["cells"]):
                value = getattr(result, attribute)
                values[index] = None if value is None else (float(value) if not isinstance(value, bool) else value)
            return [round(v, 2) if isinstance(v, float) and math.isfinite(v) else v for v in values]

        return {
            "model": "radiation_v1",
            "timestamp": timestamp.isoformat(),
            "solar": {
                "altitude_deg": solar.altitude_deg,
                "azimuth_deg": solar.azimuth_deg,
                "direction_greenhouse": list(solar.sun_direction_greenhouse),
                "direction_threejs": list(physics_to_threejs(solar.sun_direction_greenhouse)),
                "path_threejs": [list(physics_to_threejs(v)) for v in daily_sun_path(timestamp, self.site)],
            },
            "inputs": {"weather": outcome["weather"], "actuators": actuators},
            "radiation": {
                "status": outcome["status"],
                "statuses": outcome["statuses"],
                **outcome["summary"],
                "grid": {
                    "rows": self.grid.rows, "cols": self.grid.cols, "cell_size_m": self.grid.resolution_m,
                    "origin_xy_m": list(self.grid.origin_xy), "height_m": self.radiation.crop_reference_height_m,
                    "sunlit": grid_values("sunlit"), "direct_W_m2": grid_values("direct_W_m2"),
                    "diffuse_W_m2": grid_values("diffuse_W_m2"), "total_W_m2": grid_values("total_W_m2"),
                },
            },
            "provenance": self.provenance(),
        }


class _NightRays:
    def __init__(self, n, scene):
        import numpy as np
        self.blocked = np.zeros(n, bool)
        self.cover_hits = np.zeros(n, int)
        self.unknown_hits = np.zeros(n, int)
        self.vent_state_known = np.ones(n, bool)
        self.screen_hits = {layer.key: np.zeros(n, bool) for layer in scene.screens}


def _night_rays(n, scene):
    return _NightRays(n, scene)


def _status_rank(flag):
    order = ("missing_input", "decomposition", "parameter_missing", "unresolved_path")
    for rank, prefix in enumerate(order):
        if flag.startswith(prefix):
            return rank
    return len(order)


_shared = None


def shared_model():
    global _shared
    if _shared is None:
        _shared = RadiationModelV1()
    return _shared
