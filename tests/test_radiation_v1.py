"""Spec section 25 tests for physics.radiation_v1 (synthetic scenes use temporary fixtures only)."""

import importlib.util
import math
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import trimesh

from physics.coordinates import enu_from_altitude_azimuth, enu_to_greenhouse
from physics.radiation_v1.config import OpticalProperties, SiteConfig
from physics.radiation_v1.geometry import COVER, OPAQUE, CropCell, CropGrid, PhysicsScene, ScreenLayer
from physics.radiation_v1.radiation import compute_cells, decompose_ghi, weather_status
from physics.radiation_v1.raytrace import trace_direct_ray, trace_direct_rays
from physics.radiation_v1.solar import calculate_solar_state

KST = ZoneInfo("Asia/Seoul")
# Fixture site: +X east, +Y north, so directions read directly as compass directions.
SITE = SiteConfig(35.837, 126.709, 3, "Asia/Seoul", 90.0, "temporary_test_fixture")
FIXTURE = "temporary_test_fixture"


def plate(z, half=5.0):
    return trimesh.Trimesh(vertices=[(-half, -half, z), (half, -half, z), (half, half, z), (-half, half, z)],
                           faces=[(0, 1, 2), (0, 2, 3)])


def scene_of(*parts, screens=()):
    meshes = [m for m, _ in parts]
    semantics = np.concatenate([np.full(len(m.faces), s) for m, s in parts]) if parts else np.array([])
    return PhysicsScene(trimesh.util.concatenate(meshes) if meshes else None, semantics, [], list(screens), None)


def grid_of(points):
    cells = tuple(CropCell(f"c{i}", tuple(p), (0.0, 0.0, 1.0), 1.0) for i, p in enumerate(points))
    return CropGrid(cells, 1, len(cells), (0.0, 0.0), 1.0, np.arange(len(cells)), np.zeros(len(cells), int))


def optics(cover=0.8, cover_diffuse=0.7, screen=0.25, screen_diffuse=0.3):
    return {"cover": OpticalProperties(cover, cover_diffuse, provenance=FIXTURE),
            "shade_screen_1": OpticalProperties(screen, screen_diffuse, provenance=FIXTURE),
            "shade_screen_2": OpticalProperties(None, None, provenance=FIXTURE)}


class SolarAndCoordinates(unittest.TestCase):
    def test_noon_night_and_unit_vector(self):
        noon = calculate_solar_state(datetime(2026, 10, 1, 12, 30, tzinfo=KST), SITE)
        self.assertAlmostEqual(noon.altitude_deg, 51.0, delta=1.0)
        self.assertAlmostEqual(noon.azimuth_deg, 183, delta=3)
        self.assertLess(abs(np.linalg.norm(noon.sun_direction_greenhouse) - 1), 1e-9)
        self.assertLess(calculate_solar_state(datetime(2026, 10, 1, 3, 0, tzinfo=KST), SITE).altitude_deg, 0)
        morning = calculate_solar_state(datetime(2026, 10, 1, 9, 0, tzinfo=KST), SITE)
        self.assertLess(morning.altitude_deg, noon.altitude_deg)
        with self.assertRaises(ValueError):
            calculate_solar_state(datetime(2026, 10, 1, 12, 0), SITE)

    def test_enu_to_greenhouse_axes(self):
        self.assertTrue(np.allclose(enu_to_greenhouse(enu_from_altitude_azimuth(0, 284), 284), (1, 0, 0)))
        self.assertTrue(np.allclose(enu_to_greenhouse(enu_from_altitude_azimuth(0, 194), 284), (0, 1, 0)))
        self.assertTrue(np.allclose(enu_to_greenhouse(enu_from_altitude_azimuth(90, 0), 284), (0, 0, 1)))


class ShadowGeometry(unittest.TestCase):
    def shadow_points(self, when, height=4.0):
        pole = trimesh.creation.box((0.1, 0.1, height))
        pole.apply_translation((0, 0, height / 2))
        scene = scene_of((pole, OPAQUE))
        sun = calculate_solar_state(when, SITE)
        away = -np.array(sun.sun_direction_greenhouse[:2]) / np.linalg.norm(sun.sun_direction_greenhouse[:2])
        distances = np.arange(0.2, 30, 0.02)
        points = np.c_[distances[:, None] * away, np.full(len(distances), 1e-3)]
        blocked = trace_direct_rays(points, sun.sun_direction_greenhouse, scene, {}).blocked
        return sun, points[blocked], distances[blocked]

    def test_analytical_shadow_length(self):
        sun, _, distances = self.shadow_points(datetime(2026, 10, 1, 15, 0, tzinfo=KST))
        expected = 4.0 / math.tan(math.radians(sun.altitude_deg))  # L = H / tan(alpha)
        self.assertAlmostEqual(distances.max(), expected, delta=0.1)

    def test_morning_west_afternoon_east(self):
        _, morning, _ = self.shadow_points(datetime(2026, 10, 1, 8, 30, tzinfo=KST))
        _, afternoon, _ = self.shadow_points(datetime(2026, 10, 1, 16, 30, tzinfo=KST))
        self.assertTrue((morning[:, 0] < 0).all())    # +X is east in the fixture site
        self.assertTrue((afternoon[:, 0] > 0).all())


class RadiationSemantics(unittest.TestCase):
    noon = datetime(2026, 10, 1, 12, 30, tzinfo=KST)
    weather = {"ghi_W_m2": None, "dni_W_m2": 700.0, "dhi_W_m2": 100.0}

    def run_cells(self, scene, optic=None, actuators=None, weather=None):
        sun = calculate_solar_state(self.noon, SITE)
        grid = grid_of([(0, 0, 0)])
        rays = trace_direct_rays(grid.centers, sun.sun_direction_greenhouse, scene, actuators or {})
        results, flags = compute_cells(grid, sun, weather or self.weather, optic or optics(), scene, actuators or {}, rays)
        return sun, results[0], flags

    def test_opaque_blocker(self):
        sun, cell, _ = self.run_cells(scene_of((plate(3.0), OPAQUE)))
        self.assertFalse(cell.sunlit)
        self.assertEqual(cell.direct_W_m2, 0.0)

    def test_transparent_cover_attenuates(self):
        sun, cell, _ = self.run_cells(scene_of((plate(3.0), COVER)))
        self.assertTrue(cell.sunlit)
        expected = 700.0 * math.sin(math.radians(sun.altitude_deg)) * 0.8
        self.assertAlmostEqual(cell.direct_W_m2, expected, places=6)
        self.assertAlmostEqual(cell.diffuse_W_m2, 100.0 * 0.7, places=9)
        self.assertTrue(trace_direct_ray((0, 0, 0), sun.sun_direction_greenhouse, scene_of((plate(3.0), COVER))).cover_hits)

    def screen_layer(self):
        layer = ScreenLayer("shade_screen", "shade_screen_1", "shade_screen_1_opening_percent", 2.0, "across_span", -1)
        layer.spans.append((-50.0, 50.0, 0.0, 20.0))  # one wide span centred on the cell
        return layer

    def test_screen_retracted_and_deployed(self):
        scene = scene_of((plate(3.0), COVER), screens=[self.screen_layer()])
        _, open_, _ = self.run_cells(scene, actuators={"shade_screen_1_opening_percent": 100})
        _, closed, _ = self.run_cells(scene, actuators={"shade_screen_1_opening_percent": 0})
        self.assertAlmostEqual(closed.direct_W_m2, open_.direct_W_m2 * 0.25, places=6)
        self.assertAlmostEqual(closed.diffuse_W_m2, open_.diffuse_W_m2 * 0.3, places=6)

    def test_deployment_never_increases_direct(self):
        scene = scene_of((plate(3.0), COVER), screens=[self.screen_layer()])
        values = [self.run_cells(scene, actuators={"shade_screen_1_opening_percent": p})[1].direct_W_m2
                  for p in (100, 75, 50, 25, 0)]
        self.assertTrue(all(b <= a + 1e-9 for a, b in zip(values, values[1:])))

    def test_missing_data_is_not_zero(self):
        _, cell, flags = self.run_cells(scene_of((plate(3.0), COVER)), optic=optics(cover=None))
        self.assertIsNone(cell.direct_W_m2)
        self.assertIn("parameter_missing:cover.direct_transmittance", flags)
        _, cell, flags = self.run_cells(scene_of((plate(3.0), COVER)), weather={"ghi_W_m2": 500.0, "dni_W_m2": None, "dhi_W_m2": None})
        self.assertIsNone(cell.direct_W_m2)
        self.assertIsNone(cell.total_W_m2)
        self.assertIn("decomposition_required", flags)
        self.assertEqual(weather_status({}), "missing_input")
        with self.assertRaises(NotImplementedError):
            decompose_ghi(500.0, None, None)


@unittest.skipUnless(importlib.util.find_spec("embreex"), "full GLB scene needs Embree for practical speed")
class GreenhouseModel(unittest.TestCase):
    def test_full_model_statuses_and_footprint(self):
        from physics.radiation_v1.service import shared_model
        model = shared_model()
        vents = model.config["roof_vents"]
        stored = vents["opening_percent"] / 100 * vents["max_open_angle_deg"]   # GLB is exported at the configured opening
        self.assertEqual(sorted({round(math.degrees(v.stored_angle_rad), 3) for v in model.scene.vents}),
                         [round(-stored, 3), round(stored, 3)])
        api = model.to_api(datetime(2026, 10, 1, 12, 30, tzinfo=KST), {"ghi_W_m2": 400.0, "dni_W_m2": None, "dhi_W_m2": None},
                           {"roof_vent_left_percent": 0, "roof_vent_right_percent": 0,
                            "shade_screen_1_opening_percent": 100, "shade_screen_2_opening_percent": 100})
        radiation = api["radiation"]
        self.assertEqual(radiation["status"], "decomposition_required")
        self.assertIsNone(radiation["mean_W_m2"])
        self.assertGreater(radiation["sunlit_fraction"], 0.5)
        grid = radiation["grid"]
        self.assertIsNone(grid["sunlit"][0])                                  # front notch (-Y, X1) is outside the crop zone
        self.assertIsNotNone(grid["sunlit"][(grid["rows"] - 1) * grid["cols"]])  # +Y spans start at X1
