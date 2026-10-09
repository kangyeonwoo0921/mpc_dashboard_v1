import copy
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from live_data.sources import get_live_snapshot
from physics.builder import build_physics_input
from physics.contracts import (Actuators, DirectionPhysics, GreenhouseState, PhysicsInput,
                               Radiation, RadiationGrid, RadiationOutput, SolarOutput, Sun, Weather)
from physics.parameters import load_physics_config
from physics.validation import PhysicsValidationError, opening_to_deployment

STAMP = "2026-09-28T13:00:00+09:00"


class PhysicsContractTests(unittest.TestCase):
    def test_minimal_missing_values_serialize_without_zero_fill(self):
        data = PhysicsInput(STAMP)
        result = json.loads(json.dumps(data.to_dict(), allow_nan=False))
        self.assertEqual(result["schema_version"], 1)
        self.assertIsNone(result["weather"]["global_horizontal_irradiance_w_m2"])
        self.assertIsNone(result["actuators"]["shade_screen_1_deployment_fraction"])
        self.assertEqual(data.quality.status, "missing_input")
        self.assertIn("parameter_missing", data.quality.statuses)
        self.assertIn("site.latitude_deg", data.quality.missing_inputs)
        self.assertIn("site.latitude_deg", data.quality.unverified_inputs)

    def test_timezone_required(self):
        for value in (None, "invalid", "2026-09-28", "2026-09-28T13:00:00"):
            with self.subTest(value=value), self.assertRaisesRegex(PhysicsValidationError, "timestamp"):
                PhysicsInput(value)
        PhysicsInput("2026-09-28T04:00:00Z")

    def test_invalid_ranges_are_not_clamped_or_marked_missing(self):
        for call in (
            lambda: GreenhouseState(indoor_relative_humidity_pct=101),
            lambda: Weather(relative_humidity_pct=-1),
            lambda: Weather(global_horizontal_irradiance_w_m2=-1),
            lambda: Weather(direct_normal_irradiance_w_m2=-1),
            lambda: Weather(diffuse_horizontal_irradiance_w_m2=-1),
            lambda: Weather(wind_speed_m_s=-1),
            lambda: Weather(wind_direction_deg=360),
            lambda: Actuators(roof_vent_left_pct=101),
            lambda: Actuators(shade_screen_1_pct=-1),
        ):
            with self.subTest(call=call), self.assertRaises(PhysicsValidationError):
                call()

    def test_nonfinite_bool_and_string_not_numbers(self):
        for value in (float("nan"), float("inf"), True, "23"):
            with self.subTest(value=value), self.assertRaises(PhysicsValidationError):
                GreenhouseState(indoor_temperature_c=value)

    def test_screen_semantics(self):
        for opening, deployment in ((100, 0), (50, 0.5), (0, 1), (None, None)):
            self.assertEqual(opening_to_deployment(opening), deployment)
            result = Actuators(shade_screen_1_pct=opening, shade_screen_2_pct=opening)
            self.assertEqual(result.shade_screen_1_deployment_fraction, deployment)
            self.assertEqual(result.shade_screen_2_deployment_fraction, deployment)

    def test_zero_solar_is_a_measurement_and_needs_decomposition(self):
        data = PhysicsInput(STAMP, weather=Weather(global_horizontal_irradiance_w_m2=0))
        self.assertNotIn("weather.global_horizontal_irradiance_w_m2", data.quality.missing_inputs)
        self.assertIn("decomposition_required", data.quality.statuses)
        data = PhysicsInput(STAMP, weather=Weather(global_horizontal_irradiance_w_m2=0,
                            direct_normal_irradiance_w_m2=0, diffuse_horizontal_irradiance_w_m2=0))
        self.assertNotIn("decomposition_required", data.quality.statuses)

    def test_output_contracts_are_uncomputed(self):
        result = RadiationOutput(STAMP).to_dict()
        self.assertEqual(result["quality"]["status"], "not_computed")
        self.assertEqual(result["radiation"]["grid"]["values_w_m2"], [])
        self.assertIsNone(result["radiation"]["mean_inside_irradiance_w_m2"])
        self.assertIsNone(SolarOutput().sun.altitude_deg)
        json.dumps(result, allow_nan=False)

    def test_solar_direction_and_angles(self):
        Sun(altitude_deg=90, zenith_deg=0, direction_physics=DirectionPhysics(0, 0, 1))
        for call in (lambda: DirectionPhysics(1, 1, 0), lambda: DirectionPhysics(0, None, 1),
                     lambda: Sun(altitude_deg=30, zenith_deg=30), lambda: Sun(azimuth_deg=360)):
            with self.assertRaises(PhysicsValidationError):
                call()

    def test_future_grid_contract_has_shape_and_range_validation(self):
        RadiationGrid(rows=1, cols=2, values_w_m2=[None, 0], sunlit_mask=[0, 1])
        for call in (lambda: RadiationGrid(cell_size_m=0), lambda: RadiationGrid(rows=1),
                     lambda: RadiationGrid(rows=1, cols=1, values_w_m2=[1, 2]),
                     lambda: RadiationGrid(rows=1, cols=1, sunlit_mask=[2]),
                     lambda: Radiation(mean_inside_irradiance_w_m2=-1)):
            with self.assertRaises(PhysicsValidationError):
                call()


class PhysicsBuilderTests(unittest.TestCase):
    def setUp(self):
        self.site, self.optics, _ = load_physics_config()

    def test_existing_mock_boundary_no_mutation_or_network(self):
        for source in ("mock_static", "mock_dynamic"):
            dto = get_live_snapshot(source, now=datetime(2026, 9, 28, tzinfo=timezone.utc))
            before = copy.deepcopy(dto)
            with patch("socket.socket", side_effect=AssertionError("network forbidden")):
                result = build_physics_input(dto, self.site, self.optics)
            self.assertEqual(dto, before)
            self.assertEqual(result.greenhouse_state.indoor_relative_humidity_pct, dto["environment"]["indoor_rh_pct"])
            self.assertEqual(result.weather.global_horizontal_irradiance_w_m2, dto["environment"]["solar_w_m2"])
            self.assertEqual(result.actuators.roof_vent_left_pct, dto["actuators"]["roof_vent_left_pct"])
            self.assertIn("provenance.mock_data", result.quality.unverified_inputs)
            self.assertIn("weather.global_horizontal_irradiance_w_m2", result.quality.unverified_inputs)
            self.assertIsNone(result.weather.relative_humidity_pct)
            self.assertIsNone(result.weather.wind_direction_deg)
            self.assertIsNone(result.weather.direct_normal_irradiance_w_m2)
            result.site.provenance["latitude_deg"]["notes"] = "copy only"
            self.assertNotIn("notes", self.site.provenance["latitude_deg"])
            self.assertEqual(dto, get_live_snapshot(source, now=datetime(2026, 9, 28, tzinfo=timezone.utc)))

    def test_missing_sections_and_disconnection(self):
        result = build_physics_input({"timestamp": STAMP, "connected": False}, self.site, self.optics)
        self.assertIsNone(result.actuators.roof_vent_left_pct)
        self.assertIsNone(result.weather.global_horizontal_irradiance_w_m2)
        self.assertIn("disconnected", result.quality.statuses)

    def test_timestamp_override_and_invalid_source_value(self):
        result = build_physics_input({}, self.site, self.optics, datetime.now(timezone.utc))
        self.assertIn("+00:00", result.timestamp)
        with self.assertRaisesRegex(PhysicsValidationError, "timestamp"):
            build_physics_input({}, self.site, self.optics)
        with self.assertRaisesRegex(PhysicsValidationError, "indoor_relative_humidity_pct"):
            build_physics_input({"timestamp": STAMP, "environment": {"indoor_rh_pct": 110}}, self.site, self.optics)

    def test_rejects_rendering_properties_as_physics_config(self):
        with self.assertRaises(PhysicsValidationError):
            build_physics_input({"timestamp": STAMP}, self.site, {"visual_opacity": 0.2})
