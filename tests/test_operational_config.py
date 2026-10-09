import copy
import unittest
from src.config_loader import PROJECT_ROOT,ConfigError,load_config,validate_config


class OperationalConfigTests(unittest.TestCase):
    def setUp(self):
        self.config=load_config(PROJECT_ROOT/"config/greenhouse.json")

    def test_legacy_phase1_defaults(self):
        old=load_config(PROJECT_ROOT/"tests/fixtures/phase1.json")
        self.assertEqual(old["metadata"]["phase"],1)
        for key in ("crops","fertigation","sensors","side_curtains"):
            self.assertFalse(old[key]["enabled"])
        self.assertFalse(old["scene_cleanup"]["remove_default_cube"])
        self.assertFalse(old["roof_vents"]["mechanism_enabled"])
        self.assertEqual(old["visualization"]["cover_opacity"],old["cover"]["opacity"])

    def test_partial_new_sections_get_defaults(self):
        self.config["crops"]={"enabled":True}
        result=validate_config(self.config)
        self.assertEqual(result["crops"]["max_visual_plants_per_bed"],80)
        self.assertEqual(result["crops"]["instance_mode"],"linked")
        self.assertNotIn("max_visual_plants_per_bed",self.config["crops"])

    def test_invalid_operational_values(self):
        cases=[("crops","plant_spacing",0),("crops","max_visual_plants_per_bed",0),
               ("crops","plant_height",5),("crops","instance_mode","unique"),
               ("side_curtains","opening_percent",101),("side_curtains","bottom_height",6),
               ("visualization","cover_mode","invisible"),("sensors","verified_positions",True)]
        for group,key,value in cases:
            cfg=copy.deepcopy(self.config); cfg[group][key]=value
            with self.subTest(field=key),self.assertRaisesRegex(ConfigError,group+r"\."+key):
                validate_config(cfg)

    def test_sensor_identity_and_position_rules(self):
        cases=[("id","bad id"),("verified",True),("position",[0,1]),("position",[0,1,float("inf")]),("position",[0,1,-1])]
        for key,value in cases:
            cfg=copy.deepcopy(self.config); cfg["sensors"]["items"][0][key]=value
            with self.subTest(field=key),self.assertRaises(ConfigError):
                validate_config(cfg)
        self.config["sensors"]["items"].append(copy.deepcopy(self.config["sensors"]["items"][0]))
        with self.assertRaisesRegex(ConfigError,"unique"):
            validate_config(self.config)

    def test_placement_is_unverified_and_reserves_space(self):
        self.config["fertigation"]["placement"]["verified"]=True
        with self.assertRaisesRegex(ConfigError,"verified"):
            validate_config(self.config)
        self.config["fertigation"]["placement"]["verified"]=False
        self.config["crop_beds"]["length_margin"]=1
        with self.assertRaisesRegex(ConfigError,"service strip"):
            validate_config(self.config)


if __name__=="__main__":
    unittest.main()
