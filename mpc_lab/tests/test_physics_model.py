"""Balances (8.2, 8.10), component activation, typed structures, variable registry consistency."""

import importlib
import inspect
import unittest

from greenhouse_mpc.physics import balances, structures, variables
from greenhouse_mpc.physics._validation import MissingParameterError, PhysicsInputError

ACT = balances.ComponentActivation(frozenset({"H_can_air", "R_glob_sun_air", "H_air_flr", "H_air_out",
                                              "MV_can_air", "MV_air_out"}))
EQUATION_MODULES = ("psychrometrics", "heat_transfer", "moisture_transfer", "ventilation",
                    "crop_transpiration", "shade_screen", "diffuse_optics", "balances")


class BalanceTests(unittest.TestCase):
    def test_8_2_gains_minus_losses(self):
        rhs = balances.eq_8_2_temperature_rhs(ACT, H_can_air=10.0, R_glob_sun_air=50.0, H_air_flr=5.0, H_air_out=30.0)
        self.assertAlmostEqual(rhs, 25.0)
        self.assertAlmostEqual(balances.eq_8_2_dT_air_dt(rhs, 5000.0), 0.005)

    def test_8_2_zero_fluxes(self):
        self.assertEqual(balances.eq_8_2_temperature_rhs(ACT, H_can_air=0, R_glob_sun_air=0, H_air_flr=0, H_air_out=0), 0.0)

    def test_inactive_term_rejects_value_active_term_requires_value(self):
        with self.assertRaises(PhysicsInputError):
            balances.eq_8_2_temperature_rhs(ACT, H_can_air=1, R_glob_sun_air=1, H_air_flr=1, H_air_out=1, H_pipe_air=5)
        with self.assertRaises(MissingParameterError):
            balances.eq_8_2_temperature_rhs(ACT, H_can_air=1, R_glob_sun_air=1, H_air_flr=1)

    def test_8_10(self):
        rhs = balances.eq_8_10_vapour_rhs(ACT, MV_can_air=3e-5, MV_air_out=1e-5)
        self.assertAlmostEqual(rhs, 2e-5)
        with self.assertRaises(PhysicsInputError):
            balances.eq_8_10_dVP_air_dt(rhs, 0.0)

    def test_source_term_lists_are_complete(self):
        self.assertEqual(len(balances.TEMPERATURE_GAIN_TERMS) + len(balances.TEMPERATURE_LOSS_TERMS), 13)
        self.assertEqual(len(balances.MOISTURE_GAIN_TERMS) + len(balances.MOISTURE_LOSS_TERMS), 9)

    def test_site_component_file(self):
        activation = balances.load_component_activation()
        self.assertIn("MV_air_out", activation.active)
        self.assertNotIn("H_pipe_air", activation.active)


class StructureTests(unittest.TestCase):
    def test_field_parameters_default_to_none(self):
        for cls in (structures.GreenhouseGeometry, structures.VentilationParameters, structures.CoverParameters,
                    structures.ShadeScreenParameters, structures.SemiPermanentShadeLayer,
                    structures.DiffuseScreenParameters, structures.CropParameters,
                    structures.ThermophysicalProperties, structures.ControlInput, structures.WeatherInput):
            instance = cls()
            self.assertEqual(len(instance.missing()), len(inspect.signature(cls).parameters), cls.__name__)
            with self.assertRaises(MissingParameterError):
                instance.require()

    def test_range_checks(self):
        with self.assertRaises(PhysicsInputError):
            structures.ControlInput(u_roof=1.2)
        with self.assertRaises(PhysicsInputError):
            structures.ClimateState(T_air=20.0, VP_air=-1.0)
        with self.assertRaises(MissingParameterError):
            structures.ClimateState(T_air=None, VP_air=1000.0)


class RegistryTests(unittest.TestCase):
    def test_every_variable_has_unit_and_category(self):
        for v in variables.REGISTRY:
            self.assertTrue(v.unit)
            self.assertIn(v.category, variables.CATEGORIES)

    def test_state_is_T_air_and_VP_air(self):
        self.assertEqual([v.name for v in variables.REGISTRY if v.category == "STATE"], ["T_air", "VP_air"])

    def test_function_arguments_are_registered(self):
        known = set(variables.BY_NAME) | set(variables.GENERIC_SYMBOLS)
        for module_name in EQUATION_MODULES:
            module = importlib.import_module(f"greenhouse_mpc.physics.{module_name}")
            for name, func in inspect.getmembers(module, inspect.isfunction):
                if name.startswith("_") or func.__module__ != module.__name__ or name.startswith("load_"):
                    continue
                for param in inspect.signature(func).parameters:
                    self.assertIn(param, known, f"{module_name}.{name}({param})")

    def test_structure_fields_are_registered_or_documented(self):
        aliases = {"tau_PAR", "rho_PAR", "tau_NIR", "rho_NIR", "tau_FIR", "K_screen", "u_perm", "h_perm",
                   "lambda_perm", "sigma", "R", "M_water", "g"}
        known = set(variables.BY_NAME) | aliases
        for name, cls in inspect.getmembers(structures, inspect.isclass):
            if cls.__module__ == structures.__name__ and not name.startswith("_"):
                for param in inspect.signature(cls).parameters:
                    self.assertIn(param, known, f"{name}.{param}")


if __name__ == "__main__":
    unittest.main()
