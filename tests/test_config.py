import copy
import json
import unittest
from src.config_loader import ConfigError, PROJECT_ROOT, load_config, validate_config, resolve_outputs


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((PROJECT_ROOT/"config/greenhouse.json").read_text(encoding="utf-8"))

    def test_default_and_original_spec_defaults(self):
        self.assertEqual(load_config(PROJECT_ROOT/"config/greenhouse.json")["greenhouse"]["length"],97.5)
        for key in ("panel_length_ratio","panel_width_ratio","x_center_ratio","side","assumption"):
            del self.config["roof_vents"][key]
        self.assertEqual(validate_config(self.config)["roof_vents"]["panel_length_ratio"],0.8)

    def test_invalid_fields(self):
        cases = [("greenhouse","span_count",True),("greenhouse","length",0),
                 ("greenhouse","span_width",float("nan")),("structure","rafter_spacing",float("inf")),
                 ("roof_vents","opening_percent",101),("cover","opacity",-0.1),
                 ("crop_beds","rows_per_span",1.5),("crop_beds","show_plants",True),
                 ("crop_beds","width",8),("crop_beds","length_margin",50),
                 ("roof_vents","x_center_ratio",0),("roof_vents","panel_width_ratio",0.6)]
        for group,key,value in cases:
            with self.subTest(field=key):
                cfg = copy.deepcopy(self.config)
                cfg[group][key]=value
                with self.assertRaisesRegex(ConfigError,group+r"\."+key):
                    validate_config(cfg)

    def test_missing_unknown_and_height(self):
        del self.config["ground"]["margin"]
        with self.assertRaisesRegex(ConfigError,"ground.margin"):
            validate_config(self.config)
        self.setUp()
        self.config["greenhouse"]["lenght"]=97.5
        with self.assertRaisesRegex(ConfigError,"lenght"):
            validate_config(self.config)
        self.setUp()
        self.config["greenhouse"]["ridge_height"]["value"]=4.0
        with self.assertRaisesRegex(ConfigError,"must be greater"):
            validate_config(self.config)

    def test_segments_and_zero_rows(self):
        self.config["crop_beds"]["rows_per_span"]=0
        validate_config(self.config)
        self.config["greenhouse"]["roof"]["segments_per_span"]=5
        with self.assertRaisesRegex(ConfigError,"multipleOf"):
            validate_config(self.config)

    def test_paths(self):
        paths = resolve_outputs(self.config,"tmp/test-output")
        self.assertEqual(paths["glb_path"],PROJECT_ROOT/"tmp/test-output/greenhouse.glb")
        self.config["export"]["glb_path"]="dist/greenhouse.blend"
        with self.assertRaisesRegex(ConfigError,"distinct"):
            resolve_outputs(self.config)


if __name__=="__main__":
    unittest.main()
