import unittest
from datetime import datetime

from physics.light_sample import fresnel_transmittance, simulate_cross_section, solar_position

NOON = datetime.fromisoformat("2026-10-01T12:30+09:00")
OPEN = {"shade_screen_1_pct": 100, "shade_screen_2_pct": 100}


class LightSampleTests(unittest.TestCase):
    def test_reference_values(self):
        # Zhang et al. (2020) Table 1: PO film tau_b max ~0.915, tau_d 0.84.
        self.assertAlmostEqual(fresnel_transmittance(0), 0.915, places=3)
        self.assertAlmostEqual(fresnel_transmittance(60), 0.84, places=2)
        altitude, azimuth = solar_position(NOON, 35.837, 126.709)
        self.assertAlmostEqual(altitude, 51.3, delta=0.5)
        self.assertAlmostEqual(azimuth, 180, delta=5)

    def test_screens_reduce_canopy_light(self):
        open_ = simulate_cross_section(NOON, 400, OPEN)["mean"]["par_w_m2"]
        shaded = simulate_cross_section(NOON, 400, {"shade_screen_2_pct": 0, "shade_screen_1_pct": 100})["mean"]["par_w_m2"]
        self.assertLess(open_, 400)
        self.assertLess(shaded, open_ * 0.4)
        self.assertGreater(shaded, 0)

    def test_night_is_dark(self):
        result = simulate_cross_section(datetime.fromisoformat("2026-10-01T00:00+09:00"), 0, OPEN)
        self.assertEqual(result["mean"]["global_w_m2"], 0)
        self.assertTrue(all(v >= 0 for v in result["global_w_m2"]))
