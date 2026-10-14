"""Engerer2 separation (physics/radiation_v1/decomposition.py), equations from Yang (2022) Eq. 6-7."""

import math
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from physics.radiation_v1.config import load_site
from physics.radiation_v1.decomposition import COEFFICIENTS, MAX_ZENITH_DEG, decompose_ghi, engerer2, solar_terms

KST = ZoneInfo("Asia/Seoul")
SITE = load_site()
NOON = datetime(2026, 10, 12, 12, 0, tzinfo=KST)


class Engerer2Tests(unittest.TestCase):
    def test_equation_by_hand(self):
        c = COEFFICIENTS
        kt, ktc, ast, z = 0.5, 0.7, 12.0, 40.0
        e0 = 1000.0
        expected = c["C"] + (1 - c["C"]) / (1 + math.exp(c["b0"] + c["b1"] * kt + c["b2"] * ast + c["b3"] * z
                                                         + c["b4"] * (ktc - kt)))
        kd, parts = engerer2(kt * e0, z, e0, ktc * e0, ast)
        self.assertAlmostEqual(kd, expected, places=10)
        self.assertEqual(parts["kde"], 0.0)

    def test_cloud_enhancement_term_is_additive_and_clipped(self):
        kd_plain, _ = engerer2(700.0, 40.0, 1000.0, 700.0, 12.0)
        kd_enh, parts = engerer2(900.0, 40.0, 1000.0, 700.0, 12.0)
        self.assertAlmostEqual(parts["kde"], 1 - 700 / 900)
        self.assertGreater(kd_enh, 0.0)
        self.assertLessEqual(kd_enh, 1.0)
        self.assertNotEqual(kd_plain, kd_enh)

    def test_closure_and_overcast(self):
        dni, dhi, info = decompose_ghi(650.0, NOON, SITE)
        self.assertEqual(info["status"], "ok")
        self.assertAlmostEqual(dhi + dni * math.cos(math.radians(info["zenith_deg"])), 650.0, places=2)               # info rounds the zenith
        dni_low, dhi_low, _ = decompose_ghi(100.0, NOON, SITE)
        self.assertLess(dni_low, 5.0)                                        # overcast: almost all diffuse
        self.assertGreater(dhi_low, 95.0)

    def test_apparent_solar_time_for_site(self):
        terms = solar_terms(NOON, SITE)
        # 126.7 E is 8.3 deg west of the KST meridian (~33 min) and the October equation of time is ~+13.6 min.
        self.assertAlmostEqual(terms["ast_h"], 12 + (-33.2 + 13.6) / 60, delta=0.05)

    def test_out_of_range_and_missing(self):
        dawn = datetime(2026, 10, 12, 6, 45, tzinfo=KST)
        self.assertGreaterEqual(solar_terms(dawn, SITE)["zenith_deg"], MAX_ZENITH_DEG)
        dni, dhi, info = decompose_ghi(20.0, dawn, SITE)
        self.assertEqual((dni, dhi, info["status"]), (None, None, "out_of_range:zenith_ge_85"))
        self.assertEqual(decompose_ghi(None, NOON, SITE)[2]["status"], "missing_input")
        night = datetime(2026, 10, 12, 22, 0, tzinfo=KST)
        self.assertEqual(decompose_ghi(0.0, night, SITE)[:2], (0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
