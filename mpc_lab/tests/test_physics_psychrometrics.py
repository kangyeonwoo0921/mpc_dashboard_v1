import math
import unittest

from greenhouse_mpc.physics import psychrometrics as psy
from greenhouse_mpc.physics._validation import MissingParameterError, PhysicsInputError

P_ATM = 101325.0   # test input only; no pressure value is configured in the model


class SaturationTests(unittest.TestCase):
    def test_magnus_at_zero_is_6112_hPa(self):           # exp(0) = 1
        self.assertAlmostEqual(psy.saturation_vapour_pressure_hPa(0.0), 6.112)
        self.assertAlmostEqual(psy.saturation_vapour_pressure(0.0), 611.2)

    def test_pa_is_100_times_hpa(self):
        for T in (-10.0, 15.0, 35.0):
            self.assertAlmostEqual(psy.saturation_vapour_pressure(T), 100 * psy.saturation_vapour_pressure_hPa(T))

    def test_monotonic_increase(self):
        self.assertLess(psy.saturation_vapour_pressure(10.0), psy.saturation_vapour_pressure(20.0))

    def test_invalid(self):
        with self.assertRaises(MissingParameterError):
            psy.saturation_vapour_pressure(None)
        with self.assertRaises(PhysicsInputError):
            psy.saturation_vapour_pressure(-300.0)
        with self.assertRaises(PhysicsInputError):
            psy.saturation_vapour_pressure(float("nan"))


class ConversionTests(unittest.TestCase):
    def test_rh_100_gives_saturation(self):
        self.assertAlmostEqual(psy.rh_to_vp(100.0, 22.0), psy.saturation_vapour_pressure(22.0))

    def test_rh_0_gives_zero(self):
        self.assertEqual(psy.rh_to_vp(0.0, 22.0), 0.0)

    def test_rh_roundtrip(self):
        self.assertAlmostEqual(psy.vp_to_rh(psy.rh_to_vp(63.0, 18.0), 18.0), 63.0)

    def test_rh_out_of_range(self):
        with self.assertRaises(PhysicsInputError):
            psy.rh_to_vp(101.0, 20.0)

    def test_humidity_ratio_roundtrip_and_zero(self):
        X = psy.vp_to_humidity_ratio(1500.0, P_ATM)
        self.assertAlmostEqual(psy.humidity_ratio_to_vp(X, P_ATM), 1500.0)
        self.assertEqual(psy.vp_to_humidity_ratio(0.0, P_ATM), 0.0)

    def test_humidity_ratio_requires_pressure(self):
        with self.assertRaises(MissingParameterError):
            psy.vp_to_humidity_ratio(1500.0, None)
        with self.assertRaises(PhysicsInputError):
            psy.vp_to_humidity_ratio(P_ATM, P_ATM)

    def test_vpd_zero_at_saturation_and_sign(self):
        P_sat = psy.saturation_vapour_pressure(25.0)
        self.assertAlmostEqual(psy.vpd(25.0, P_sat), 0.0)
        self.assertGreater(psy.vpd(25.0, 0.5 * P_sat), 0.0)

    def test_dew_point_inverts_magnus(self):
        for T in (-5.0, 10.0, 28.0):
            self.assertAlmostEqual(psy.dew_point(psy.saturation_vapour_pressure(T)), T, places=9)

    def test_dew_point_below_air_temperature_when_unsaturated(self):
        self.assertLess(psy.dew_point(psy.rh_to_vp(60.0, 20.0)), 20.0)

    def test_dew_point_invalid(self):
        with self.assertRaises(PhysicsInputError):
            psy.dew_point(0.0)                            # ln(0) undefined

    def test_unit_helpers(self):
        self.assertEqual(psy.hpa_to_pa(1.0), 100.0)
        self.assertTrue(math.isclose(psy.pa_to_hpa(100.0), 1.0))


if __name__ == "__main__":
    unittest.main()
