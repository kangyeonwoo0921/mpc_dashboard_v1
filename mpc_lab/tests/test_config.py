import tempfile
import unittest
from pathlib import Path

from greenhouse_mpc.config_loader import (CONFIG_FILES, build_mpc_config, load_all, load_config_file,
                                          unresolved)
from greenhouse_mpc.provenance import Parameter, ProvenanceError, iter_parameters, parse_parameters


class ProvenanceRuleTests(unittest.TestCase):
    def test_null_needs_unknown_status(self):
        with self.assertRaises(ProvenanceError):
            Parameter(value=None, source_type="unknown", status="provisional")

    def test_unknown_status_cannot_carry_value(self):
        with self.assertRaises(ProvenanceError):
            Parameter(value=0.0, source_type="unknown", status="unknown")

    def test_verified_requires_calibrated_or_field_verified(self):
        with self.assertRaises(ProvenanceError):
            Parameter(value=1.0, source_type="operator_report", status="provisional", verified=True)

    def test_bad_enums_and_extra_fields(self):
        with self.assertRaises(ProvenanceError):
            Parameter(value=1.0, source_type="guess", status="provisional")
        with self.assertRaises(ProvenanceError):
            parse_parameters({"x": {"value": 1, "status": "provisional", "source_type": "unknown", "confidence": 1}})


class ShippedConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trees = load_all()

    def test_all_files_parse(self):
        self.assertEqual(set(self.trees), set(CONFIG_FILES))
        for tree in self.trees.values():
            self.assertTrue(list(iter_parameters(tree)))

    def test_nothing_is_verified(self):
        for tree in self.trees.values():
            for param in iter_parameters(tree):
                self.assertFalse(param.verified, param.path)

    def test_stop_items_remain_unresolved(self):          # DP §33
        missing = set(unresolved(self.trees["greenhouse"])) | set(unresolved(self.trees["actuators"])) \
            | set(unresolved(self.trees["safety"]))
        for path in ("greenhouse.thermal.U_cover", "greenhouse.thermal.delta_shade",
                     "greenhouse.ventilation.A_eff_map", "greenhouse.ventilation.infiltration",
                     "actuators.roof_vent.travel_time_full_s", "actuators.shade_screen.travel_time_full_s",
                     "safety.wind.maximum_safe_speed_m_s"):
            self.assertIn(path, missing)

    def test_safety_limits_are_field_required(self):
        safety = self.trees["safety"]
        self.assertEqual(safety["wind"]["maximum_safe_speed_m_s"].status, "field_required")
        rain = safety["rain"]["vent_max_percent"]                 # operator report 2026-10-07: vents close
        self.assertEqual((rain.value, rain.source_type, rain.verified), (0.0, "operator_report", False))

    def test_operator_values_are_provisional(self):
        self.assertEqual(self.trees["greenhouse"]["radiation"]["sensor_location"].status, "provisional")
        reference = self.trees["greenhouse"]["unverified_reference_values"]
        self.assertEqual(reference["shade_screen_transmittance"].value, 0.30)   # 70 % aluminium
        self.assertEqual(reference["diffuse_screen_transmittance"].value, 0.90)  # 10 % Ultra
        for param in reference.values():
            self.assertEqual(param.source_type, "operator_report")
            self.assertEqual(param.status, "provisional")
            self.assertFalse(param.verified)

    def test_screen_optics_for_physics_are_null(self):            # decision 2026-10-06
        radiation = self.trees["greenhouse"]["radiation"]
        for group in ("shade_screen_optics", "diffuse_screen_optics"):
            for param in radiation[group].values():
                self.assertIsNone(param.value, param.path)

    def test_physics_never_reads_unverified_values(self):
        from pathlib import Path
        physics_dir = Path(__file__).resolve().parents[1] / "src" / "greenhouse_mpc" / "physics"
        for source in physics_dir.glob("*.py"):
            text = source.read_text(encoding="utf-8")
            self.assertNotIn("unverified_reference_values", text, source.name)
            self.assertNotIn("greenhouse.yaml", text, source.name)

    def test_od2_diffuse_window_present(self):
        window = self.trees["crop_reference"]["screens"]["diffuse_night_window"]
        self.assertEqual(window.status, "field_guide_baseline")
        self.assertEqual(window.value["T_out_below_C"], 15.0)

    def test_mpc_config_from_yaml(self):
        config = build_mpc_config(self.trees["controller"])
        self.assertEqual((config.prediction_steps, config.control_steps), (12, 4))
        self.assertFalse(config.weights_ready())           # no final weights yet
        self.assertTrue(config.enable_diffuse_screen_control)

    def test_invalid_file_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "bad.yaml").write_text("x:\n  value: null\n  source_type: unknown\n  status: provisional\n",
                                              encoding="utf-8")
            with self.assertRaises(ProvenanceError):
                load_config_file("bad", tmp)


if __name__ == "__main__":
    unittest.main()
