import unittest
from datetime import datetime, timedelta, timezone

from greenhouse_mpc.types import (ActuatorState, GreenhouseState, InputValidationError, MPCConfig,
                                  MPCRecommendation, ReferenceSchedule, WeatherInput)

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 4, 12, 0, tzinfo=KST)
WEIGHTS = dict.fromkeys(("w_T", "w_H", "w_L", "w_Q", "w_DLI", "w_v", "w_d", "w_s"))


def weather(**overrides):
    values = dict(timestamp=NOW, T_out_C=15.0, RH_out_percent=60.0, solar_global_W_m2=400.0,
                  wind_speed_m_s=2.0, wind_direction_deg=45.0, rain_state="dry")
    values.update(overrides)
    return WeatherInput(**values)


class GreenhouseStateTests(unittest.TestCase):
    def test_naive_timestamp_rejected(self):
        with self.assertRaises(InputValidationError):
            GreenhouseState(datetime(2026, 10, 4, 12), 20.0, 70.0)

    def test_rh_out_of_range_rejected(self):
        with self.assertRaises(InputValidationError):
            GreenhouseState(NOW, 20.0, 101.0)

    def test_missing_is_not_invalid(self):
        state = GreenhouseState(NOW, None, 70.0)
        self.assertEqual(state.missing_critical(), ["T_in_C"])

    def test_nan_and_bool_rejected(self):
        for bad in (float("nan"), float("inf"), True, "20"):
            with self.assertRaises(InputValidationError):
                GreenhouseState(NOW, bad, 70.0)


class WeatherInputTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(weather().missing_critical(), [])

    def test_missing_outdoor_rh_reported(self):            # G-2
        self.assertEqual(weather(RH_out_percent=None).missing_critical(), ["RH_out_percent"])

    def test_negative_solar_rejected(self):
        with self.assertRaises(InputValidationError):
            weather(solar_global_W_m2=-1.0)

    def test_wind_direction_360_rejected(self):
        with self.assertRaises(InputValidationError):
            weather(wind_direction_deg=360.0)

    def test_negative_wind_speed_rejected(self):
        with self.assertRaises(InputValidationError):
            weather(wind_speed_m_s=-0.1)

    def test_rain_state_enum(self):
        with self.assertRaises(InputValidationError):
            weather(rain_state="drizzle")
        self.assertIn("rain_state", weather(rain_state=None).missing_critical())


class ActuatorStateTests(unittest.TestCase):
    def test_invalid_percent_is_validation_error(self):    # DP §31
        for field in ("roof_vent_percent", "diffuse_screen_open_percent", "shade_screen_open_percent"):
            values = dict(roof_vent_percent=10.0, diffuse_screen_open_percent=100.0, shade_screen_open_percent=100.0)
            values[field] = 120.0
            with self.assertRaises(InputValidationError):
                ActuatorState(**values)
            values[field] = -5.0
            with self.assertRaises(InputValidationError):
                ActuatorState(**values)

    def test_deployment_fraction_semantics(self):
        state = ActuatorState(0.0, 100.0, 20.0)
        self.assertEqual(state.diffuse_deployment_fraction, 0.0)   # 100 % open = retracted
        self.assertAlmostEqual(state.shade_deployment_fraction, 0.8)

    def test_missing_position(self):
        state = ActuatorState(10.0, None, 50.0)
        self.assertIsNone(state.diffuse_deployment_fraction)
        self.assertEqual(state.missing_critical(), ["diffuse_screen_open_percent"])


class ReferenceScheduleTests(unittest.TestCase):
    def test_unknown_fields_default_none(self):
        ref = ReferenceSchedule(NOW, "flowering_fruit_set", "october")
        self.assertIsNone(ref.T_ref_C)

    def test_bad_stage_and_inverted_band(self):
        with self.assertRaises(InputValidationError):
            ReferenceSchedule(NOW, "seedling", "october")
        with self.assertRaises(InputValidationError):
            ReferenceSchedule(NOW, "flowering_fruit_set", "october", VPD_soft_min_kPa=1.2, VPD_soft_max_kPa=0.5)


class MPCConfigTests(unittest.TestCase):
    def test_step_counts(self):
        config = MPCConfig(5, 60, 20, WEIGHTS)
        self.assertEqual((config.prediction_steps, config.control_steps), (12, 4))
        self.assertFalse(config.weights_ready())

    def test_control_longer_than_prediction_rejected(self):
        with self.assertRaises(InputValidationError):
            MPCConfig(5, 20, 60, WEIGHTS)

    def test_non_integer_steps_rejected(self):
        with self.assertRaises(InputValidationError):
            MPCConfig(7, 60, 21, WEIGHTS)

    def test_unknown_weight_rejected(self):
        with self.assertRaises(InputValidationError):
            MPCConfig(5, 60, 20, {**WEIGHTS, "w_screen": 1.0})

    def test_weights_ready_when_all_set(self):
        self.assertTrue(MPCConfig(5, 60, 20, dict.fromkeys(WEIGHTS, 1.0)).weights_ready())


class MPCRecommendationTests(unittest.TestCase):
    def test_unavailable_carries_no_actuator_values(self):
        with self.assertRaises(InputValidationError):
            MPCRecommendation(NOW, "recommendation_unavailable", recommendation=ActuatorState(0, 100, 100),
                              reasons=("missing RH_out_percent",))

    def test_unavailable_requires_reason(self):
        with self.assertRaises(InputValidationError):
            MPCRecommendation(NOW, "recommendation_unavailable")
        rec = MPCRecommendation(NOW, "recommendation_unavailable", reasons=("missing RH_out_percent",))
        self.assertIsNone(rec.recommendation)

    def test_mode_is_recommendation_only(self):
        with self.assertRaises(InputValidationError):
            MPCRecommendation(NOW, "ok", recommendation=ActuatorState(0, 100, 100), mode="actuate")


if __name__ == "__main__":
    unittest.main()
