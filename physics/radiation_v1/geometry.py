"""Crop-zone grid and physics scene classification (spec sections 11-13).

The scene reuses the viewer GLB so visualization and physics share one geometry.
"""

import math
import re
from dataclasses import dataclass, field

import numpy as np
import trimesh

from src.config_loader import PROJECT_ROOT, load_config
from src.geometry_math import span_bounds, span_centers, span_x_range
from src.refinement_math import screen_visible_width

GLB_PATH = PROJECT_ROOT / "digital_twin/static/digital_twin/models/greenhouse.glb"
GLTF_TO_PHYSICS = np.array([[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], dtype=float)

# Physics semantics (spec section 12) plus UNKNOWN_OPTICS for surfaces whose optics are not known yet.
OPAQUE = "OPAQUE_STRUCTURE"
COVER = "TRANSPARENT_COVER"
UNKNOWN_OPTICS = "UNKNOWN_OPTICS"
DECORATIVE = "DECORATIVE"

STRUCTURE_PREFIXES = ("GH_RAFTER", "GH_TRUSS", "GH_COL_", "GH_GUTTER", "GH_RIDGE",
                      "GH_FRONT_WALL_POST", "GH_FRONT_WALL_RAIL", "GH_REAR_WALL_POST", "GH_REAR_WALL_RAIL")
VENT_LEAF = re.compile(r"^GH_VENT_S(\d{2})_(\d{2})(_FRAME)?$")


def classify(node, material):
    """Semantic class of one static GLB node (vents are handled separately)."""
    if node.startswith(STRUCTURE_PREFIXES) and material == "MAT_FRAME_METAL":
        return OPAQUE
    if material == "MAT_END_CLADDING":            # sandwich panel 75T, drawing page 6
        return OPAQUE
    if material == "MAT_COVER":                    # roof PO film
        return COVER
    if material in ("MAT_END_WINDBREAK", "MAT_SIDEWALL_FIXED", "MAT_CURTAIN"):
        return UNKNOWN_OPTICS                      # windbreak / side wall / curtain optics unknown
    return DECORATIVE                              # mechanisms, crops, beds, equipment, labels, ground


@dataclass(frozen=True)
class CropCell:
    cell_id: str
    center_xyz: tuple[float, float, float]
    normal_xyz: tuple[float, float, float]
    area_m2: float


@dataclass(frozen=True)
class CropGrid:
    cells: tuple
    rows: int
    cols: int
    origin_xy: tuple[float, float]
    resolution_m: float
    flat_index: np.ndarray  # cell -> row-major index into rows x cols
    span_index: np.ndarray  # cell -> zero-based span

    @property
    def centers(self):
        return np.array([c.center_xyz for c in self.cells])


def build_crop_grid(config, resolution_m, height_m):
    """1 m cells over the stepped footprint at the crop reference height, rows along +Y."""
    g = config["greenhouse"]
    width = g["span_count"] * g["span_width"]
    cols, rows = int(g["length"] // resolution_m), int(width // resolution_m)
    x0, y0 = -g["length"] / 2, -width / 2
    bounds = span_bounds(g["span_count"], g["span_width"])
    cells, flat, spans = [], [], []
    for r in range(rows):
        y = y0 + (r + 0.5) * resolution_m
        span = min(max(int(np.searchsorted(bounds, y, side="right")) - 1, 0), g["span_count"] - 1)
        front = span_x_range(g, span + 1)[0]
        for c in range(cols):
            x = x0 + (c + 0.5) * resolution_m
            if x < front:
                continue  # outside the stepped front
            cells.append(CropCell(f"r{r:02d}c{c:03d}", (x, y, height_m), (0.0, 0.0, 1.0), resolution_m**2))
            flat.append(r * cols + c)
            spans.append(span)
    return CropGrid(tuple(cells), rows, cols, (x0, y0), resolution_m, np.array(flat), np.array(spans))


@dataclass
class VentLeaf:
    span: int                 # zero-based
    index: int                # 1 = +Y leaf, 2 = -Y leaf
    channel: str
    mesh_gltf: trimesh.Trimesh  # world (glTF) at the GLB's stored pose
    semantics: np.ndarray
    hinge_gltf: np.ndarray
    stored_angle_rad: float


@dataclass
class ScreenLayer:
    key: str                  # greenhouse.json screen section
    optics_name: str          # optical.json entry
    channel: str              # actuator field
    height_m: float
    travel: str
    gather_sign: int          # -1 / +1: one piece stored at that gutter; 0: halves stored at both gutters
    spans: list = field(default_factory=list)  # (x0, x1, center_y, visible_width)


@dataclass
class PhysicsScene:
    static_mesh: trimesh.Trimesh | None
    static_semantics: np.ndarray
    vents: list
    screens: list
    max_vent_angle_deg: float | None


def _pivot_angle(matrix):
    """Rotation about the hinge (glTF X) stored in a pivot's world matrix."""
    return math.atan2(matrix[2, 1], matrix[1, 1])


def load_scene(config=None, glb_path=GLB_PATH):
    config = config or load_config(PROJECT_ROOT / "config/greenhouse.json")
    scene = trimesh.load(glb_path, force="scene")
    static_parts, static_semantics, leaves = [], [], {}
    for node in scene.graph.nodes_geometry:
        transform, name = scene.graph[node]
        mesh = scene.geometry[name]
        material = getattr(getattr(mesh.visual, "material", None), "name", None)
        vent = VENT_LEAF.match(node)
        if vent:
            key = (int(vent.group(1)) - 1, int(vent.group(2)))
            part = mesh.copy()
            part.apply_transform(transform)
            semantic = OPAQUE if vent.group(3) else COVER  # leaf film and its frame
            leaves.setdefault(key, []).append((part, semantic))
            continue
        semantic = classify(node, material)
        if semantic == DECORATIVE:
            continue
        part = mesh.copy()
        part.apply_transform(GLTF_TO_PHYSICS @ transform)
        static_parts.append(part)
        static_semantics.append(np.full(len(part.faces), semantic))

    vents = []
    for (span, index), parts in sorted(leaves.items()):
        pivot, _ = scene.graph.get(f"GH_VENT_S{span + 1:02d}_{index:02d}_PIVOT")
        mesh = trimesh.util.concatenate([p for p, _ in parts])
        semantics = np.concatenate([np.full(len(p.faces), s) for p, s in parts])
        channel = "roof_vent_left_percent" if index == 1 else "roof_vent_right_percent"
        vents.append(VentLeaf(span, index, channel, mesh, semantics, pivot[:3, 3].copy(), _pivot_angle(pivot)))

    g = config["greenhouse"]
    screens = []
    # Field channels (operator report 2026-10-07): 차광커튼2 = aluminium shade layer, 차광커튼1 = diffuse layer.
    for key, optics_name, channel in (("shade_screen", "shade_screen_2", "shade_screen_2_opening_percent"),
                                      ("diffuse_screen", "shade_screen_1", "shade_screen_1_opening_percent")):
        values = config[key]
        if not values["enabled"]:
            continue
        gather = values.get("gather_side", "negative_y")
        layer = ScreenLayer(key, optics_name, channel, values["height"], values.get("travel", "along_length"),
                            {"negative_y": -1, "positive_y": 1, "both": 0}[gather])
        width = screen_visible_width(config, values["height"])
        for j, c in enumerate(span_centers(g["span_count"], g["span_width"]), 1):
            x0, x1 = span_x_range(g, j)
            layer.spans.append((x0, x1, c, width))
        screens.append(layer)

    static = trimesh.util.concatenate(static_parts) if static_parts else None
    vents_cfg = config["roof_vents"]
    return PhysicsScene(static, np.concatenate(static_semantics) if static_semantics else np.array([]),
                        vents, screens, vents_cfg["max_open_angle_deg"] if vents_cfg["enabled"] else None)
