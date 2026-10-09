"""Screen and vent state semantics (spec section 13).

opening_percent 100 = fully retracted, 0 = fully deployed;
deployment_fraction = 1 - opening_percent / 100. Missing stays None.
"""

import math

import numpy as np

from src.geometry_math import vent_angle


def deployment_fraction(opening_percent):
    return None if opening_percent is None else 1 - opening_percent / 100


def deployed_regions(layer, span_geometry, fraction):
    """Plan rectangles [(x0, x1, y0, y1)] of deployed fabric over one span, following the GLB contract.

    gather_sign -1 / +1: one piece stored at that gutter. gather_sign 0: two halves stored at both
    gutters, each deployed by ``fraction`` of half the width, meeting at the span centre when closed."""
    x0, x1, center_y, width = span_geometry
    if layer.travel == "across_span":
        if layer.gather_sign == 0:
            return [(x0, x1, center_y - width / 2, center_y - width / 2 + fraction * width / 2),
                    (x0, x1, center_y + width / 2 - fraction * width / 2, center_y + width / 2)]
        edge = center_y + layer.gather_sign * width / 2   # fabric is stored at this gutter
        y_a, y_b = sorted((edge, edge - layer.gather_sign * fraction * width))
        return [(x0, x1, y_a, y_b)]
    return [(x0, x0 + fraction * (x1 - x0), center_y - width / 2, center_y + width / 2)]


def crosses_deployed(layer, fraction, xs, ys):
    """Boolean per point: does (x, y) at the screen height lie on deployed fabric?"""
    hit = np.zeros(len(xs), bool)
    if not fraction:
        return hit
    for span_geometry in layer.spans:
        for x0, x1, y0, y1 in deployed_regions(layer, span_geometry, fraction):
            hit |= (xs >= x0) & (xs <= x1) & (ys >= y0) & (ys <= y1)
    return hit


def vent_rotation_gltf(leaf, opening_percent, max_angle_deg):
    """4x4 transform taking the stored leaf pose to the pose for ``opening_percent``.

    Uses the same percent -> angle contract as the generator and viewer
    (``vent_angle``: linear, 100 % = max angle); the real mapping is unverified.
    """
    side = "positive_y" if leaf.index == 1 else "negative_y"
    target = vent_angle(opening_percent, max_angle_deg, side)
    delta = target - leaf.stored_angle_rad
    c, s = math.cos(delta), math.sin(delta)
    rotation = np.array([[1, 0, 0, 0], [0, c, -s, 0], [0, s, c, 0], [0, 0, 0, 1]], dtype=float)
    to_origin, back = np.eye(4), np.eye(4)
    to_origin[:3, 3], back[:3, 3] = -leaf.hinge_gltf, leaf.hinge_gltf
    return back @ rotation @ to_origin
