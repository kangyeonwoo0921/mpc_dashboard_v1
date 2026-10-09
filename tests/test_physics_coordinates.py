import math
import unittest

from physics.coordinates import (blender_to_physics, physics_to_blender, physics_to_threejs,
                                 threejs_to_physics, blender_to_glb, glb_to_blender, normalized_direction)
from physics.validation import PhysicsValidationError


class PhysicsCoordinatesTests(unittest.TestCase):
    def test_basis_axes_and_roundtrip(self):
        for source, target in (((1, 0, 0), (1, 0, 0)), ((0, 1, 0), (0, 0, -1)), ((0, 0, 1), (0, 1, 0))):
            self.assertEqual(physics_to_threejs(source), target)
            self.assertEqual(threejs_to_physics(target), source)
            self.assertEqual(blender_to_physics(source), source)
            self.assertEqual(physics_to_blender(source), source)

    def test_world_position_roundtrip_determinism_and_front_rear(self):
        for point in ((-48.75, 0, 0), (48.75, 0, 0), (2, -8, 4.2)):
            self.assertEqual(glb_to_blender(blender_to_glb(point)), point)
            self.assertEqual(blender_to_glb(point), blender_to_glb(point))

    def test_normalized_direction(self):
        self.assertAlmostEqual(math.hypot(*normalized_direction((2, 3, 4))), 1)
        self.assertEqual(normalized_direction((0, 0, 5)), (0, 0, 1))
        for value in ((0, 0, 0), (1, 2), (True, 0, 1), (float("nan"), 0, 1)):
            with self.assertRaises(PhysicsValidationError):
                normalized_direction(value)
