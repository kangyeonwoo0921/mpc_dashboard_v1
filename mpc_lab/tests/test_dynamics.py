"""Time discretization / numerical propagation (greenhouse_mpc.dynamics).

All numerical values below are test fixtures, not site parameters. Flux providers are built from the
source equation functions (Eq. 8.40, 8.45, 8.65) with fixed test coefficients, so the reference
solutions are exact solutions of those source equations.
"""

import math
import unittest

from greenhouse_mpc.config_loader import build_integrator_settings, load_config_file
from greenhouse_mpc.dynamics.integrators import (IntegrationError, IntegratorSettings, integrate_interval,
                                                 stability_diagnostic)
from greenhouse_mpc.dynamics.model import ClimateODE
from greenhouse_mpc.dynamics.propagation import derived_humidity, propagate, step
from greenhouse_mpc.dynamics.signals import LinearInterpolationWeather, ZeroOrderHoldWeather
from greenhouse_mpc.physics import psychrometrics as psy
from greenhouse_mpc.physics.balances import ComponentActivation
from greenhouse_mpc.physics.constants import KELVIN_OFFSET, M_WATER, R_GAS
from greenhouse_mpc.physics.heat_transfer import eq_8_40_sensible_heat_flux
from greenhouse_mpc.physics.moisture_transfer import eq_8_45_airflow_vapour_flux
from greenhouse_mpc.physics.structures import ClimateState, ControlInput, WeatherInput
from greenhouse_mpc.physics.ventilation import eq_8_65_roof_ventilation
from greenhouse_mpc.physics._validation import MissingParameterError, PhysicsInputError

DT = 300.0                                     # target control interval [s]
ACT = ComponentActivation(frozenset({"H_air_out", "MV_air_out"}))
RADAU = IntegratorSettings("radau", rtol=1e-8, atol_T_air=1e-8, atol_VP_air=1e-6)
CAP_AIR, CAP_VP = 5000.0, 3e-5                 # fixtures [J K-1 m-2], [kg m-2 Pa-1]
WEATHER = WeatherInput(T_out=10.0, VP_out=900.0, wind_speed=2.0, wind_direction=45.0, solar_radiation=0.0, rain=False)


def model(HEC=10.0, f_air=0.01, seen=None):
    def h_out(t, s, u, d):
        if seen is not None:
            seen.append((t, u, d))
        return eq_8_40_sensible_heat_flux(HEC, s.T_air, d.T_out)

    def mv_out(t, s, u, d):
        return eq_8_45_airflow_vapour_flux(f_air, s.VP_air, s.T_air, d.VP_out, d.T_out)

    return ClimateODE(ACT, {"H_air_out": h_out, "MV_air_out": mv_out},
                      cap_air=lambda *a: CAP_AIR, cap_VP_air=lambda *a: CAP_VP)


def weather_signal(*samples, times=None):
    samples = samples or (WEATHER, WEATHER)
    times = times or [i * DT for i in range(len(samples))]
    return ZeroOrderHoldWeather(times, samples)


class ModelAssemblyTests(unittest.TestCase):
    def test_providers_must_match_activation(self):
        with self.assertRaises(MissingParameterError):
            ClimateODE(ACT, {"H_air_out": lambda *a: 0.0}, lambda *a: 1.0, lambda *a: 1.0)
        with self.assertRaises(PhysicsInputError):
            ClimateODE(ACT, {"H_air_out": lambda *a: 0.0, "MV_air_out": lambda *a: 0.0,
                             "H_pipe_air": lambda *a: 0.0}, lambda *a: 1.0, lambda *a: 1.0)

    def test_derivatives_follow_balances(self):
        dT, dVP = model().derivatives(0.0, ClimateState(20.0, 1500.0), ControlInput(), WEATHER)
        self.assertAlmostEqual(dT, -10.0 * 10.0 / CAP_AIR)
        expected = -M_WATER / R_GAS * 0.01 * (1500.0 / (20 + KELVIN_OFFSET) - 900.0 / (10 + KELVIN_OFFSET)) / CAP_VP
        self.assertAlmostEqual(dVP, expected)


class IntegratorTests(unittest.TestCase):
    def test_settings_required(self):
        with self.assertRaises(MissingParameterError):
            IntegratorSettings("radau")
        with self.assertRaises(MissingParameterError):
            IntegratorSettings("rk4")
        with self.assertRaises(PhysicsInputError):
            IntegratorSettings("euler")
        with self.assertRaises(PhysicsInputError):
            IntegratorSettings("rk4", n_substeps=0)

    def test_equilibrium_is_preserved(self):           # zero driving force -> no change
        state = ClimateState(T_air=10.0, VP_air=900.0)
        for settings in (RADAU, IntegratorSettings("rk4", n_substeps=4)):
            result = step(model(), state, ControlInput(), 0.0, DT, weather_signal(), settings)
            self.assertAlmostEqual(result.state_end.T_air, 10.0, places=9)
            self.assertAlmostEqual(result.state_end.VP_air, 900.0, places=6)

    def test_matches_exact_solution_of_eq_8_40_balance(self):
        # dT/dt = -HEC (T - T_out) / cap  ->  T(t) = T_out + (T0 - T_out) exp(-HEC t / cap)
        result = step(model(), ClimateState(20.0, 900.0 * 293.15 / 283.15), ControlInput(), 0.0, DT,
                      weather_signal(), RADAU)
        exact = 10.0 + 10.0 * math.exp(-10.0 * DT / CAP_AIR)
        self.assertAlmostEqual(result.state_end.T_air, exact, places=6)

    def test_matches_exact_solution_of_eq_8_45_balance(self):
        # T_air == T_out: dVP/dt = -(M/R) f (VP - VP_out) / ((T + 273.15) cap_VP)
        rate = M_WATER / R_GAS * 0.01 / ((10 + KELVIN_OFFSET) * CAP_VP)
        result = step(model(), ClimateState(10.0, 1500.0), ControlInput(), 0.0, DT, weather_signal(), RADAU)
        self.assertAlmostEqual(result.state_end.VP_air, 900.0 + 600.0 * math.exp(-rate * DT), places=4)

    def test_rk4_converges_at_fourth_order(self):
        exact = 10.0 + 10.0 * math.exp(-10.0 * DT / CAP_AIR)
        errors = []
        for n in (2, 4):
            result = step(model(), ClimateState(20.0, 900.0), ControlInput(), 0.0, DT, weather_signal(),
                          IntegratorSettings("rk4", n_substeps=n))
            errors.append(abs(result.state_end.T_air - exact))
        self.assertGreater(errors[0] / errors[1], 12.0)    # ~16 for a 4th-order method

    def test_stiff_case_radau_stable_and_diagnostic(self):
        stiff = model(HEC=CAP_AIR / 10.0)                   # thermal time constant 10 s << 300 s
        state = ClimateState(20.0, 900.0)
        radau = step(stiff, state, ControlInput(), 0.0, DT, weather_signal(), RADAU)
        self.assertAlmostEqual(radau.state_end.T_air, 10.0, places=6)

        def rhs(t, x):
            return stiff.derivatives(t, ClimateState(*x), ControlInput(), WEATHER)
        diag = stability_diagnostic(rhs, 0.0, (20.0, 900.0), DT)
        self.assertAlmostEqual(diag["fastest_time_constant_s"], 10.0, places=3)
        n = diag["rk4_min_substeps_for_stability"]
        self.assertEqual(n, math.ceil(DT / 10.0 / 2.785))
        with self.assertRaises(IntegrationError):            # diverges; reported, never clamped
            step(stiff, state, ControlInput(), 0.0, DT, weather_signal(), IntegratorSettings("rk4", n_substeps=1))
        # at the stability minimum RK4 no longer diverges, but is not yet accurate (|R(h*lambda)| close to 1)
        stable = step(stiff, state, ControlInput(), 0.0, DT, weather_signal(), IntegratorSettings("rk4", n_substeps=n))
        self.assertLess(abs(stable.state_end.T_air - 10.0), 10.0)
        accurate = step(stiff, state, ControlInput(), 0.0, DT, weather_signal(), IntegratorSettings("rk4", n_substeps=4 * n))
        self.assertLess(abs(accurate.state_end.T_air - 10.0), 1e-3)

    def test_physics_domain_error_is_not_clamped(self):
        def vent(t, s, u, d):
            f = eq_8_65_roof_ventilation(u.u_roof, 100.0, 0.5, 1000.0, 1.0, s.T_air, d.T_out,
                                         (s.T_air + d.T_out) / 2, 0.1, d.wind_speed)
            return eq_8_45_airflow_vapour_flux(f, s.VP_air, s.T_air, d.VP_out, d.T_out)
        ode = ClimateODE(ACT, {"H_air_out": lambda *a: 0.0, "MV_air_out": vent}, lambda *a: CAP_AIR, lambda *a: CAP_VP)
        calm_warm = WeatherInput(T_out=25.0, VP_out=900.0, wind_speed=0.0, wind_direction=0.0, solar_radiation=0.0, rain=False)
        with self.assertRaises(IntegrationError):
            step(ode, ClimateState(15.0, 1200.0), ControlInput(u_roof=0.5), 0.0, DT,
                 weather_signal(calm_warm, calm_warm), RADAU)

    def test_integrate_interval_validation(self):
        with self.assertRaises(PhysicsInputError):
            integrate_interval(lambda t, x: (0.0, 0.0), (20.0, 1000.0), 10.0, 10.0, RADAU)


class SignalTests(unittest.TestCase):
    def test_control_and_weather_held_over_interval(self):
        seen = []
        later = WeatherInput(T_out=30.0, VP_out=900.0, wind_speed=2.0, wind_direction=45.0, solar_radiation=0.0, rain=False)
        step(model(seen=seen), ClimateState(20.0, 1000.0), ControlInput(u_roof=0.3), 0.0, DT,
             weather_signal(WEATHER, later), RADAU)
        self.assertTrue(seen)
        self.assertTrue(all(u.u_roof == 0.3 for _, u, _ in seen))
        self.assertTrue(all(d.T_out == 10.0 for _, _, d in seen))       # t_end sample not used under ZOH
        self.assertTrue(all(0.0 <= t <= DT for t, _, _ in seen))

    def test_linear_interpolation_option(self):
        later = WeatherInput(T_out=20.0, VP_out=1100.0, wind_speed=4.0, wind_direction=90.0, solar_radiation=100.0, rain=True)
        signal = LinearInterpolationWeather([0.0, DT], [WEATHER, later])
        mid = signal(DT / 2)
        self.assertAlmostEqual(mid.T_out, 15.0)
        self.assertAlmostEqual(mid.VP_out, 1000.0)
        self.assertEqual(mid.wind_direction, 45.0)                      # held, not interpolated
        self.assertFalse(mid.rain)

    def test_no_extrapolation(self):
        with self.assertRaises(PhysicsInputError):
            step(model(), ClimateState(20.0, 1000.0), ControlInput(), 0.0, 2 * DT, weather_signal(), RADAU)

    def test_unsorted_weather_rejected(self):
        with self.assertRaises(PhysicsInputError):
            ZeroOrderHoldWeather([DT, 0.0], [WEATHER, WEATHER])


class PropagationTests(unittest.TestCase):
    def test_multi_interval_grid_and_consistency(self):
        signal = weather_signal(WEATHER, WEATHER, WEATHER)
        traj = propagate(model(), ClimateState(20.0, 1500.0), [ControlInput(), ControlInput()], 0.0, DT, signal, RADAU)
        self.assertEqual(traj.times_s, (0.0, DT, 2 * DT))
        self.assertEqual(len(traj.states), 3)
        once = step(model(), ClimateState(20.0, 1500.0), ControlInput(), 0.0, 2 * DT, signal, RADAU)
        self.assertAlmostEqual(traj.states[-1].T_air, once.state_end.T_air, places=6)
        self.assertAlmostEqual(traj.states[-1].VP_air, once.state_end.VP_air, places=4)

    def test_derived_humidity_from_state(self):
        state = ClimateState(20.0, psy.rh_to_vp(70.0, 20.0))
        derived = derived_humidity(state)
        self.assertAlmostEqual(derived.RH_air, 70.0)
        self.assertIsNone(derived.X_air)                                  # P_atm not supplied
        self.assertAlmostEqual(derived.VPD_air, psy.vpd(20.0, state.VP_air))
        self.assertIsNotNone(derived_humidity(state, P_atm_Pa=101325.0).X_air)

    def test_empty_controls_rejected(self):
        with self.assertRaises(PhysicsInputError):
            propagate(model(), ClimateState(20.0, 1000.0), [], 0.0, DT, weather_signal(), RADAU)


class ConfigTests(unittest.TestCase):
    def test_numerical_settings_not_yet_configured(self):
        controller = load_config_file("controller")
        self.assertEqual(controller["numerical_integration"]["method"].value, "radau")
        with self.assertRaises(MissingParameterError):
            build_integrator_settings(controller)


if __name__ == "__main__":
    unittest.main()
