import copy
import unittest
from dataclasses import asdict

from physics.parameters import (OpticalConfig, PhysicalParameter, SiteConfig, load_physics_config,
                                parse_optical_config, parse_site_config, validate_radiation_config)
from physics.validation import PhysicsValidationError


class PhysicsParametersTests(unittest.TestCase):
    def test_default_configs_stay_unverified_with_sources(self):
        site, optics, radiation = load_physics_config()
        for name in ("latitude_deg", "longitude_deg", "elevation_m"):
            info = site.provenance[name]
            self.assertFalse(info["verified"])
            if getattr(site, name) is not None:
                self.assertTrue(info["source"])
                self.assertNotEqual(info["source_type"], "unknown")
        self.assertFalse(site.orientation.verified)
        if site.orientation.greenhouse_long_axis_azimuth_deg is not None:
            self.assertTrue(site.orientation.source)
            self.assertNotEqual(site.orientation.source_type, "unknown")
        for _, parameter in optics.items():
            self.assertFalse(parameter.verified)
            if parameter.value is None:
                self.assertEqual(parameter.source_type, "unknown")
            else:
                self.assertTrue(parameter.source)
                self.assertNotEqual(parameter.source_type, "unknown")
        self.assertIsNone(radiation["grid"]["reference_height_m"])
        self.assertEqual(parse_site_config(asdict(site)), site)
        self.assertEqual(parse_optical_config(asdict(optics)), optics)

    def test_site_ranges_and_orientation(self):
        for data in ({"latitude_deg": 91}, {"longitude_deg": -181}, {"latitude_deg": True},
                     {"orientation": {"greenhouse_long_axis_azimuth_deg": 360}},
                     {"orientation": {"verified": True}}, {"timezone": "unknown"},
                     {"latitdue_deg": 30}, {"provenance": {"latitude_deg": None}}):
            with self.subTest(data=data), self.assertRaises(PhysicsValidationError):
                parse_site_config(data)

    def test_optical_ranges_units_and_unknown_keys(self):
        for value in (-0.1, 1.1, True, float("inf")):
            with self.subTest(value=value), self.assertRaises(PhysicsValidationError):
                parse_optical_config({"roof_cover": {"solar_transmittance_direct": {"value": value}}})
        with self.assertRaises(PhysicsValidationError):
            parse_optical_config({"roof_cover": {"solar_transmittance_direct": {"unit": "%"}}})
        with self.assertRaises(PhysicsValidationError):
            parse_optical_config({"roof_cover": {"opacity": {"value": 0.5}}})
        for value in (0, 1, None):
            parse_optical_config({"roof_cover": {"solar_transmittance_direct": {"value": value}}})

    def test_provenance_is_not_inferred(self):
        parameter = PhysicalParameter(0.75, source_type="temporary_test_fixture", notes="Test only, not a greenhouse specification")
        self.assertFalse(parameter.verified)
        with self.assertRaises(PhysicsValidationError):
            PhysicalParameter(0.75, verified=True)
        with self.assertRaises(PhysicsValidationError):
            PhysicalParameter(None, verified=True, source="test", source_type="temporary_test_fixture")

    def test_radiation_configuration_validation(self):
        _, _, original = load_physics_config()
        for group, key, value in (("grid", "cell_size_m", 0), ("grid", "reference_height_m", -1),
                                  ("direct_radiation", "method", "other"), ("reflections", "enabled", True),
                                  ("diffuse_radiation", "enabled", "yes")):
            data = copy.deepcopy(original)
            data[group][key] = value
            with self.subTest(group=group, key=key), self.assertRaises(PhysicsValidationError):
                validate_radiation_config(data)
