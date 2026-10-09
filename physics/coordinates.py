"""World points/vectors in meters, no translation. See README for local nodes."""

import math

from .validation import number, require


def _vector(vector):
    require(isinstance(vector, (list, tuple)) and len(vector) == 3,
            "vector", vector, "three finite components")
    for index, value in enumerate(vector):
        number(value, f"vector[{index}]", nullable=False)
    return tuple(vector)


def blender_to_physics(vector):
    return _vector(vector)


def physics_to_blender(vector):
    return _vector(vector)


def physics_to_threejs(vector):
    x, y, z = _vector(vector)
    return x, z, -y


def threejs_to_physics(vector):
    x, y, z = _vector(vector)
    return x, -z, y


blender_to_glb = physics_to_threejs
glb_to_blender = threejs_to_physics
physics_to_glb = physics_to_threejs
glb_to_physics = threejs_to_physics


def normalized_direction(vector):
    values = _vector(vector)
    magnitude = math.hypot(*values)
    require(magnitude > 0 and math.isfinite(magnitude), "direction", vector,
            "nonzero finite magnitude")
    return tuple(value / magnitude for value in values)


def enu_from_altitude_azimuth(altitude_deg, azimuth_deg):
    """Unit vector toward a sky point in geographic ENU (azimuth clockwise from true north)."""
    h, az = math.radians(altitude_deg), math.radians(azimuth_deg)
    return math.cos(h) * math.sin(az), math.cos(h) * math.cos(az), math.sin(h)


def enu_to_greenhouse(vector, long_axis_azimuth_deg):
    """Geographic ENU -> greenhouse physics axes.

    +X is the long axis (X1 -> X23) at ``long_axis_azimuth_deg`` true north clockwise,
    i.e. ENU (sin A, cos A, 0); +Y is its left, ENU (-cos A, sin A, 0); +Z is up.
    """
    east, north, up = _vector(vector)
    a = math.radians(long_axis_azimuth_deg)
    return (east * math.sin(a) + north * math.cos(a),
            -east * math.cos(a) + north * math.sin(a),
            up)
