"""Heat transfer (8.19, 8.38, 8.40, 8.42), moisture transfer (8.43-8.45), crop (8.47-8.49)."""

import unittest

from greenhouse_mpc.physics import crop_transpiration as crop
from greenhouse_mpc.physics import heat_transfer as heat
from greenhouse_mpc.physics import moisture_transfer as mv
from greenhouse_mpc.physics._validation import MissingParameterError, PhysicsInputError
from greenhouse_mpc.physics.constants import M_WATER, R_GAS


class HeatTests(unittest.TestCase):
    def test_8_40_zero_sign_scale(self):
        self.assertEqual(heat.eq_8_40_sensible_heat_flux(5.0, 20.0, 20.0), 0.0)
        self.assertGreater(heat.eq_8_40_sensible_heat_flux(5.0, 25.0, 20.0), 0.0)
        self.assertLess(heat.eq_8_40_sensible_heat_flux(5.0, 15.0, 20.0), 0.0)
        self.assertAlmostEqual(heat.eq_8_40_sensible_heat_flux(5.0, 25.0, 20.0), 25.0)   # W m-2

    def test_8_40_invalid(self):
        with self.assertRaises(MissingParameterError):
            heat.eq_8_40_sensible_heat_flux(None, 25.0, 20.0)
        with self.assertRaises(PhysicsInputError):
            heat.eq_8_40_sensible_heat_flux(-1.0, 25.0, 20.0)

    def test_8_38_zero_sign_antisymmetry(self):
        self.assertEqual(heat.eq_8_38_fir_flux(1.0, 0.9, 0.9, 1.0, 10.0, 10.0), 0.0)
        forward = heat.eq_8_38_fir_flux(1.0, 0.9, 0.8, 0.5, 20.0, 5.0)
        self.assertGreater(forward, 0.0)
        self.assertAlmostEqual(forward, -heat.eq_8_38_fir_flux(1.0, 0.9, 0.8, 0.5, 5.0, 20.0))
        self.assertEqual(heat.eq_8_38_fir_flux(1.0, 0.9, 0.8, 0.0, 20.0, 5.0), 0.0)     # no view

    def test_8_38_invalid(self):
        with self.assertRaises(PhysicsInputError):
            heat.eq_8_38_fir_flux(1.0, 1.2, 0.8, 0.5, 20.0, 5.0)

    def test_8_42(self):
        self.assertEqual(heat.eq_8_42_latent_heat_flux(2.45e6, 0.0), 0.0)
        self.assertAlmostEqual(heat.eq_8_42_latent_heat_flux(2.0e6, 1e-5), 20.0)
        with self.assertRaises(MissingParameterError):
            heat.eq_8_42_latent_heat_flux(None, 1e-5)

    def test_8_19_without_perm_layer_is_conduction_of_roof(self):
        self.assertAlmostEqual(heat.eq_8_19_cover_conduction_hec(0.002, 0.4, 0.0, 0.001, 0.1), 200.0)
        thicker = heat.eq_8_19_cover_conduction_hec(0.002, 0.4, 1.0, 0.001, 0.1)
        self.assertLess(thicker, 200.0)
        with self.assertRaises(PhysicsInputError):
            heat.eq_8_19_cover_conduction_hec(0.0, 0.4, 0.0, 0.001, 0.1)


class MoistureTests(unittest.TestCase):
    def test_8_43_branches(self):
        self.assertEqual(mv.eq_8_43_condensation_flux(5.0, 1500.0, 1500.0), 0.0)
        self.assertEqual(mv.eq_8_43_condensation_flux(5.0, 1000.0, 1500.0), 0.0)
        self.assertAlmostEqual(mv.eq_8_43_condensation_flux(5.0, 1500.0, 1000.0), 6.4e-9 * 5.0 * 500.0)

    def test_8_43_invalid(self):
        with self.assertRaises(MissingParameterError):
            mv.eq_8_43_condensation_flux(None, 1500.0, 1000.0)

    def test_8_44_requires_slope_and_zero(self):
        with self.assertRaises(MissingParameterError):
            mv.eq_8_44_condensation_flux_smooth(5.0, 1500.0, 1000.0, None)
        self.assertEqual(mv.eq_8_44_condensation_flux_smooth(5.0, 1200.0, 1200.0, -0.1), 0.0)

    def test_8_45_zero_sign_scale(self):
        self.assertEqual(mv.eq_8_45_airflow_vapour_flux(0.01, 1500.0, 20.0, 1500.0, 20.0), 0.0)
        self.assertEqual(mv.eq_8_45_airflow_vapour_flux(0.0, 2000.0, 20.0, 800.0, 5.0), 0.0)
        out = mv.eq_8_45_airflow_vapour_flux(0.01, 2000.0, 20.0, 800.0, 5.0)
        self.assertGreater(out, 0.0)
        expected = M_WATER / R_GAS * 0.01 * (2000.0 / 293.15 - 800.0 / 278.15)
        self.assertAlmostEqual(out, expected)

    def test_8_45_invalid(self):
        with self.assertRaises(PhysicsInputError):
            mv.eq_8_45_airflow_vapour_flux(-0.01, 2000.0, 20.0, 800.0, 5.0)


class CropTests(unittest.TestCase):
    def test_8_47_zero_and_sign(self):
        self.assertEqual(crop.eq_8_47_transpiration(1e-8, 2000.0, 2000.0), 0.0)
        self.assertGreater(crop.eq_8_47_transpiration(1e-8, 2300.0, 2000.0), 0.0)
        self.assertLess(crop.eq_8_47_transpiration(1e-8, 1800.0, 2000.0), 0.0)

    def test_8_48_lai_zero_and_scaling(self):
        args = dict(rho_air=1.2, c_p_air=1000.0, delta_H=2.45e6, gamma=65.0, r_b=100.0, r_s=200.0)
        self.assertEqual(crop.eq_8_48_vec_can_air(LAI=0.0, **args), 0.0)
        self.assertAlmostEqual(crop.eq_8_48_vec_can_air(LAI=2.0, **args), 2 * crop.eq_8_48_vec_can_air(LAI=1.0, **args))

    def test_8_48_invalid(self):
        with self.assertRaises(MissingParameterError):
            crop.eq_8_48_vec_can_air(1.2, 1000.0, None, 2.45e6, 65.0, 100.0, 200.0)
        with self.assertRaises(PhysicsInputError):
            crop.eq_8_48_vec_can_air(1.2, 1000.0, 2.0, 2.45e6, 65.0, 0.0, 0.0)

    def test_8_49_product(self):
        self.assertAlmostEqual(crop.eq_8_49_stomatal_resistance(80.0, 1.5, 1.0, 2.0), 240.0)
        with self.assertRaises(MissingParameterError):
            crop.eq_8_49_stomatal_resistance(80.0, None, 1.0, 1.0)


if __name__ == "__main__":
    unittest.main()
