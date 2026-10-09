"""Ventilation (8.65, 8.68, 8.71), shade/thermal screen (8.14-8.17, 8.39, 8.41), Cabrera optics."""

import inspect
import math
import unittest

from greenhouse_mpc.physics import diffuse_optics as diff
from greenhouse_mpc.physics import shade_screen as shade
from greenhouse_mpc.physics import ventilation as vent
from greenhouse_mpc.physics._validation import MissingParameterError, PhysicsInputError

# test inputs only (not site values)
VENT = dict(A_roof=100.0, C_d=0.5, A_floor=1000.0, h_vent=1.0, C_w=0.1)


class VentilationTests(unittest.TestCase):
    def test_closed_vent_gives_zero(self):
        self.assertEqual(vent.eq_8_65_roof_ventilation(0.0, T_air=25, T_out=15, T_mean=20, wind_speed=3, **VENT), 0.0)
        self.assertEqual(vent.eq_8_68_roof_aperture(0.0, 100.0), 0.0)

    def test_no_driving_force_gives_zero(self):
        self.assertEqual(vent.eq_8_65_roof_ventilation(1.0, T_air=20, T_out=20, T_mean=20, wind_speed=0, **VENT), 0.0)

    def test_monotonic_in_drivers(self):
        base = vent.eq_8_65_roof_ventilation(0.5, T_air=22, T_out=15, T_mean=18.5, wind_speed=1, **VENT)
        self.assertGreater(vent.eq_8_65_roof_ventilation(1.0, T_air=22, T_out=15, T_mean=18.5, wind_speed=1, **VENT), base)
        self.assertGreater(vent.eq_8_65_roof_ventilation(0.5, T_air=22, T_out=15, T_mean=18.5, wind_speed=3, **VENT), base)
        self.assertGreater(vent.eq_8_65_roof_ventilation(0.5, T_air=28, T_out=15, T_mean=21.5, wind_speed=1, **VENT), base)

    def test_wind_only_value(self):
        f = vent.eq_8_65_roof_ventilation(1.0, T_air=20, T_out=20, T_mean=20, wind_speed=2, **VENT)
        self.assertAlmostEqual(f, 100.0 * 0.5 / 2000.0 * math.sqrt(0.1 * 4))

    def test_missing_parameter_and_negative_radicand(self):
        with self.assertRaises(MissingParameterError):
            vent.eq_8_65_roof_ventilation(0.5, T_air=22, T_out=15, T_mean=18.5, wind_speed=1, **{**VENT, "C_d": None})
        with self.assertRaises(PhysicsInputError):
            vent.eq_8_65_roof_ventilation(0.5, T_air=10, T_out=25, T_mean=17.5, wind_speed=0, **VENT)
        with self.assertRaises(PhysicsInputError):
            vent.eq_8_65_roof_ventilation(1.5, T_air=22, T_out=15, T_mean=18.5, wind_speed=1, **VENT)

    def test_no_wind_direction_argument(self):
        params = inspect.signature(vent.eq_8_65_roof_ventilation).parameters
        self.assertNotIn("wind_direction", params)

    def test_leakage_as_transcribed(self):
        self.assertEqual(vent.eq_8_71_leakage(1e-4, 0.1), 1e-4)
        self.assertAlmostEqual(vent.eq_8_71_leakage(1e-4, 2.0), 2e-4)
        with self.assertRaises(MissingParameterError):
            vent.eq_8_71_leakage(None, 2.0)

    def test_cw_table_is_data_only(self):
        table = vent.WindPressureCoefficientTable("cited study", "geometry", "0 deg = ...", (0.0,), (0.1,))
        public = [name for name in dir(table) if not name.startswith("_")]
        self.assertEqual(sorted(public), ["C_w_values", "angle_definition", "angles_deg", "geometry", "source"])
        with self.assertRaises(PhysicsInputError):
            vent.WindPressureCoefficientTable("", "geometry", "def", (0.0,), (0.1,))


class ShadeScreenTests(unittest.TestCase):
    MAT = dict(tau_shade=0.3, rho_shade=0.6, tau_shade_perm=0.8, rho_shade_perm=0.1)

    def test_retracted_screen_and_no_perm_layer_transmit_all(self):
        self.assertEqual(shade.eq_8_16_shade_screen_tau(0.0, u_shade_perm=0.0, **self.MAT), 1.0)
        self.assertEqual(shade.eq_8_17_shade_screen_rho(0.0, u_shade_perm=0.0, **self.MAT), 0.0)

    def test_fully_deployed_single_layer(self):
        self.assertAlmostEqual(shade.eq_8_16_shade_screen_tau(1.0, u_shade_perm=0.0, **self.MAT), 0.3)
        self.assertAlmostEqual(shade.eq_8_17_shade_screen_rho(1.0, u_shade_perm=0.0, **self.MAT), 0.6)

    def test_more_deployment_less_transmission(self):
        self.assertGreater(shade.eq_8_16_shade_screen_tau(0.2, u_shade_perm=0.0, **self.MAT),
                           shade.eq_8_16_shade_screen_tau(0.8, u_shade_perm=0.0, **self.MAT))

    def test_8_16_matches_8_14_when_both_deployed(self):
        self.assertAlmostEqual(shade.eq_8_16_shade_screen_tau(1.0, u_shade_perm=1.0, **self.MAT),
                               shade.eq_8_14_double_layer_tau(0.3, 0.6, 0.8, 0.1))
        self.assertAlmostEqual(shade.eq_8_17_shade_screen_rho(1.0, u_shade_perm=1.0, **self.MAT),
                               shade.eq_8_15_double_layer_rho(0.3, 0.6, 0.1))

    def test_missing_material(self):
        with self.assertRaises(MissingParameterError):
            shade.eq_8_16_shade_screen_tau(0.5, None, 0.6, 0.0, 0.8, 0.1)

    def test_8_39(self):
        self.assertEqual(shade.eq_8_39_thermal_screen_fir_tau(0.0, 0.1), 1.0)
        self.assertAlmostEqual(shade.eq_8_39_thermal_screen_fir_tau(1.0, 0.1), 0.1)

    def test_8_41_zero_driving_force(self):
        self.assertEqual(shade.eq_8_41_thermal_screen_airflow(1.0, 0.002, 18.0, 18.0, 1.2, 1.2, 1.2), 0.0)
        self.assertEqual(shade.eq_8_41_thermal_screen_airflow(0.0, 0.002, 18.0, 5.0, 1.22, 1.2, 1.2), 0.0)
        with self.assertRaises(MissingParameterError):
            shade.eq_8_41_thermal_screen_airflow(1.0, None, 18.0, 5.0, 1.22, 1.2, 1.25)


class DiffuseOpticsTests(unittest.TestCase):
    def test_definitions(self):
        self.assertAlmostEqual(diff.direct_to_direct_transmittance(300.0, 600.0), 0.5)
        self.assertAlmostEqual(diff.direct_converted_to_diffuse(200.0, 0.6, 100.0), 140.0)
        self.assertAlmostEqual(diff.direct_to_diffuse_transmittance(200.0, 0.6, 100.0, 700.0), 0.2)
        self.assertAlmostEqual(diff.total_direct_transmittance(0.5, 0.2), 0.7)

    def test_no_conversion_when_inside_diffuse_is_transmitted_outside_diffuse(self):
        self.assertEqual(diff.direct_converted_to_diffuse(60.0, 0.6, 100.0), 0.0)

    def test_invalid(self):
        with self.assertRaises(PhysicsInputError):
            diff.direct_to_direct_transmittance(300.0, 0.0)
        with self.assertRaises(MissingParameterError):
            diff.direct_converted_to_diffuse(200.0, None, 100.0)

    def test_no_opening_dependent_function(self):
        for name, func in inspect.getmembers(diff, inspect.isfunction):
            self.assertNotIn("u_diffuse_screen", inspect.signature(func).parameters, name)


if __name__ == "__main__":
    unittest.main()
