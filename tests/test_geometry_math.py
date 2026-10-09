import math
import unittest
from src.geometry_math import (make_stations,secondary_stations,span_bounds,span_centers,
                               generate_arch_points,bed_y_positions,clamp_percent,vent_angle,screen_scale)


class GeometryMathTests(unittest.TestCase):
    def test_stations_preserve_extent(self):
        for length,spacing,count in ((97.5,4.5,23),(97.5,1.125,88),(9,4.5,3),(1,4.5,2)):
            with self.subTest(length=length,spacing=spacing):
                xs=make_stations(length,spacing)
                self.assertEqual(len(xs),count)
                self.assertEqual(xs[0],-length/2)
                self.assertEqual(xs[-1],length/2)
                self.assertTrue(all(0<b-a<=spacing+1e-8 for a,b in zip(xs,xs[1:])))
        with self.assertRaises(ValueError):
            make_stations(1,0)

    def test_secondary_no_overlap(self):
        main=make_stations(97.5,4.5)
        second=secondary_stations(97.5,2.25,4.5)
        self.assertEqual(len(second),22)
        self.assertFalse(set(main)&set(second))

    def test_span_and_arch(self):
        self.assertEqual(span_centers(4,8),[-12,-4,4,12])
        self.assertEqual(span_bounds(3,8),[-12,-4,4,12])
        points=generate_arch_points(8,4.2,5,24)
        self.assertEqual(points[0],(-4,4.2))
        self.assertEqual(points[12],(0,5))
        self.assertEqual(points[-1],(4,4.2))
        for a,b in zip(points,reversed(points)):
            self.assertAlmostEqual(a[1],b[1])

    def test_beds(self):
        self.assertEqual(bed_y_positions(4,8,0),[])
        self.assertEqual(bed_y_positions(4,8,1),[4])
        ys=bed_y_positions(0,8,5)
        self.assertEqual(len(ys),5)
        self.assertAlmostEqual(ys[0],-3.2)
        self.assertAlmostEqual(ys[-1],3.2)
        with self.assertRaises(ValueError):
            bed_y_positions(0,8,5,4)

    def test_control_endpoints(self):
        self.assertEqual(clamp_percent(-1),0)
        self.assertEqual(clamp_percent(120),100)
        self.assertAlmostEqual(vent_angle(20,35),math.radians(7))
        self.assertAlmostEqual(vent_angle(100,35,"negative_y"),-math.radians(35))
        self.assertEqual([screen_scale(p) for p in (0,50,100)],[1,0.5,1e-6])
        with self.assertRaises(ValueError):
            clamp_percent(float("nan"))


if __name__=="__main__":
    unittest.main()
