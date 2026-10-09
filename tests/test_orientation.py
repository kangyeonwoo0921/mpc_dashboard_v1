import copy
import unittest
from src.config_loader import load_config,validate_config,ConfigError,PROJECT_ROOT
from src.orientation import end_positions,door_dimensions

class OrientationTests(unittest.TestCase):
    def test_ends_follow_length_not_camera(self):
        c=load_config(PROJECT_ROOT/'config/greenhouse.json')
        self.assertEqual(end_positions(c)['front'],(-48.75,0,0))
        self.assertEqual(end_positions(c)['rear'],(48.75,0,0))
        c['greenhouse']['length']=60
        self.assertEqual(end_positions(c)['front'][0],-30)
        self.assertEqual(end_positions(c)['rear'][0],30)

    def test_reversal_rejected(self):
        c=load_config(PROJECT_ROOT/'config/greenhouse.json')
        c['orientation']['front_end']='positive_x'
        with self.assertRaises(ConfigError): validate_config(c)

    def test_door_in_drawing_region(self):
        c=load_config(PROJECT_ROOT/'config/greenhouse.json')
        y,w,h=door_dimensions(c)
        self.assertGreater(y-w/2,0)
        self.assertLess(y+w/2,8)
        self.assertLess(h,c['greenhouse']['eave_height']['value'])
