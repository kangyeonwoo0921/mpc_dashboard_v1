import copy
import unittest
from src.config_loader import load_config, validate_config, ConfigError, PROJECT_ROOT
from src.refinement_math import screen_visible_width
from src.geometry_math import arch_height, roof_arch_radius


class RefinementTests(unittest.TestCase):
    def setUp(self): self.c=load_config(PROJECT_ROOT/'config/greenhouse.json')

    def test_sampled_roof_clipping(self):
        for key in ('shade_screen','diffuse_screen'):
            g=self.c['greenhouse']; h=self.c[key]['height']; w=screen_visible_width(self.c,h)
            self.assertGreater(w,0); self.assertLessEqual(w,8)
            self.assertGreaterEqual(arch_height(w/2,8,g['eave_height']['value'],g['ridge_height']['value'],roof_arch_radius(g)),h+0.025-1e-9)
            self.assertEqual(self.c[key]['height'],h)

    def test_legacy_defaults(self):
        for name in ('phase1.json','phase1_5.json'):
            c=load_config(PROJECT_ROOT/'tests/fixtures'/name)
            self.assertFalse(c['sidewalls']['enabled'])
            self.assertFalse(c['visual_refinement']['clip_screens_to_interior'])
            self.assertEqual(c['crops']['lod'],'standard')
            self.assertEqual(screen_visible_width(c,4.8),8)

    def test_invalid_refinement(self):
        g=self.c['greenhouse']
        for section,key,value in (('sidewalls','fixed_lower_wall_height',g['eave_height']['value']+0.1),('crops','lod','ultra'),('shade_screen','height',g['ridge_height']['value'])):
            c=copy.deepcopy(self.c); c[section][key]=value
            with self.assertRaises(ConfigError): validate_config(c)

    def test_dashboard_density(self):
        self.assertEqual(self.c['crops']['max_visual_plants_per_bed'],45)
        self.assertEqual(self.c['crops']['lod'],'dashboard')

if __name__=='__main__': unittest.main()
