import importlib.util
import os
import unittest
from datetime import datetime

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "greenhouse_web.settings")
import django  # noqa: E402

django.setup()
from django.test import Client, SimpleTestCase  # noqa: E402

HAS_EMBREE = importlib.util.find_spec("embreex") is not None
NOON = datetime.fromisoformat("2026-10-01T12:30+09:00")
OPEN = {"shade_screen_1_pct": 100, "shade_screen_2_pct": 100, "roof_vent_left_pct": 0, "roof_vent_right_pct": 0}


@unittest.skipUnless(HAS_EMBREE, "3-D light model needs the Embree ray backend for practical speed")
class LightModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from physics.light_model import shared_model
        cls.model = shared_model()

    def mean(self, **changes):
        return self.model.evaluate(NOON, {**OPEN, **changes}, irradiance=400)["mean"]

    def test_structure_screens_and_vents_change_canopy_light(self):
        open_ = self.mean()
        self.assertLess(open_["sunlit_fraction"], 1.0)   # frame members shade part of the canopy
        self.assertGreater(open_["sunlit_fraction"], 0.6)
        # 차광커튼2 = 70 % aluminium shade layer
        self.assertLess(self.mean(shade_screen_2_pct=0)["par_w_m2"], open_["par_w_m2"] * 0.4)
        self.assertGreater(self.mean(roof_vent_left_pct=100, roof_vent_right_pct=100)["par_w_m2"], open_["par_w_m2"])

    def test_grid_respects_stepped_footprint(self):
        grid = self.model.evaluate(NOON, OPEN, irradiance=400)["grid"]
        values = grid["global_w_m2"].reshape(grid["rows"], grid["cols"])
        self.assertTrue(all(v != v for v in values[0, :5]))  # front notch (-Y spans S01-S02 near X1) is outside
        self.assertTrue(values[-1, 0] > 0)                    # +Y spans run from X1


@unittest.skipUnless(HAS_EMBREE, "3-D light model needs the Embree ray backend for practical speed")
class SolarApiTests(SimpleTestCase):
    def test_solar_endpoint(self):
        response = Client().get("/api/digital-twin/solar/", {"time": "2026-10-01T12:30"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["outside"]["source"], "clear_sky_model")
        self.assertAlmostEqual(payload["sun"]["altitude_deg"], 51.3, delta=0.5)
        self.assertEqual(len(payload["grid"]["par_w_m2"]), payload["grid"]["rows"] * payload["grid"]["cols"])
        self.assertFalse(payload["provenance"]["validated"])
        self.assertEqual(Client().get("/api/digital-twin/solar/", {"time": "bad"}).status_code, 400)
        self.assertEqual(Client().post("/api/digital-twin/solar/").status_code, 405)
