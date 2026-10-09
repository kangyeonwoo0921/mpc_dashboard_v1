"""Direct-ray classification against the physics scene.

Adapted conceptually from Zhang et al. (2020), Eq. 23: the 2-D sunray path
y = k(x - xp) + yp is generalized to the 3-D ray r(lambda) = p + lambda * s, lambda >= 0.
"""

from dataclasses import dataclass

import numpy as np
import trimesh

from .geometry import COVER, GLTF_TO_PHYSICS, OPAQUE, UNKNOWN_OPTICS
from .screens import crosses_deployed, deployment_fraction, vent_rotation_gltf


@dataclass(frozen=True)
class RayTraceResult:
    blocked: bool
    opaque_hits: tuple
    cover_hits: tuple
    screen_hits: tuple
    unknown_optics_hits: tuple = ()


@dataclass(frozen=True)
class RayBatch:
    """Per-ray outcome for many origins sharing one direction."""
    blocked: np.ndarray            # opaque geometry on the path -> S = 0
    cover_hits: np.ndarray         # transparent cover crossings
    unknown_hits: np.ndarray       # surfaces whose optics are unknown
    vent_state_known: np.ndarray   # False when a vent on the path has no actuator value
    screen_hits: dict              # layer key -> crossed deployed fabric (None if state unknown)


def _hits(mesh, semantics, origins, direction):
    """(ray index, semantic, distance) for every intersection along each ray."""
    if mesh is None or len(origins) == 0:
        return np.array([], int), np.array([]), np.array([])
    directions = np.tile(direction, (len(origins), 1))
    tri, ray, loc = mesh.ray.intersects_id(origins, directions, multiple_hits=True, return_locations=True)
    distance = np.einsum("ij,ij->i", loc - origins[ray], directions[ray])
    keep = distance > 1e-6
    return ray[keep], semantics[tri[keep]], distance[keep]


def vent_mesh(scene, actuators):
    """Vent leaves posed for the actuator state; leaves with unknown state are reported separately."""
    parts, semantics, unknown = [], [], []
    for leaf in scene.vents:
        percent = actuators.get(leaf.channel)
        if percent is None or scene.max_vent_angle_deg is None:
            unknown.append(leaf)
            continue
        mesh = leaf.mesh_gltf.copy()
        mesh.apply_transform(GLTF_TO_PHYSICS @ vent_rotation_gltf(leaf, percent, scene.max_vent_angle_deg))
        parts.append(mesh)
        semantics.append(leaf.semantics)
    if not parts:
        return None, np.array([]), unknown
    return trimesh.util.concatenate(parts), np.concatenate(semantics), unknown


def trace_direct_rays(origins, sun_direction, scene, actuators):
    origins = np.asarray(origins, float)
    direction = np.asarray(sun_direction, float)
    n = len(origins)
    blocked = np.zeros(n, bool)
    cover = np.zeros(n, int)
    unknown = np.zeros(n, int)
    envelope = np.full(n, np.inf)  # distance to the first cover/unknown surface (where the ray leaves)

    static = _hits(scene.static_mesh, scene.static_semantics, origins, direction)
    vents, vent_semantics, unknown_leaves = vent_mesh(scene, actuators)
    moving = _hits(vents, vent_semantics, origins, direction)
    for ray, semantic, distance in (static, moving):
        blocked[ray[semantic == OPAQUE]] = True
        np.add.at(cover, ray[semantic == COVER], 1)
        np.add.at(unknown, ray[semantic == UNKNOWN_OPTICS], 1)
        skin = semantic != OPAQUE
        np.minimum.at(envelope, ray[skin], distance[skin])

    # With any vent state unknown, a ray that leaves through an opening (no skin crossed)
    # may have met that leaf, so it cannot be resolved.
    vent_known = np.ones(n, bool)
    if unknown_leaves:
        vent_known = blocked | (cover > 0) | (unknown > 0)

    screen_hits = {}
    for layer in scene.screens:
        fraction = deployment_fraction(actuators.get(layer.channel))
        if fraction is None:
            screen_hits[layer.key] = None
            continue
        t = (layer.height_m - origins[:, 2]) / max(direction[2], 1e-9)
        p = origins + direction * t[:, None]
        screen_hits[layer.key] = (t > 0) & (t < envelope) & crosses_deployed(layer, fraction, p[:, 0], p[:, 1])
    return RayBatch(blocked, cover, unknown, vent_known, screen_hits)


def trace_direct_ray(origin_xyz, sun_direction_xyz, scene, actuators=None):
    """Single-ray form of the spec signature (section 19)."""
    batch = trace_direct_rays([origin_xyz], sun_direction_xyz, scene, actuators or {})
    screens = tuple(k for k, v in batch.screen_hits.items() if v is not None and v[0])
    return RayTraceResult(bool(batch.blocked[0]), ("opaque",) if batch.blocked[0] else (),
                          ("cover",) * int(batch.cover_hits[0]), screens, ("unknown",) * int(batch.unknown_hits[0]))
