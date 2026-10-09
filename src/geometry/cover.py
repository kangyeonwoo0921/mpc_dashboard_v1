from .primitives import grid_surface
from ..geometry_math import generate_arch_points, arch_height, roof_arch_radius, span_centers, span_x_range, vent_bounds, vent_sides
import bpy


def set_cover_visibility(mode,opacity=None):
    """Blender preview visibility plus explicit GLB metadata; meshes are retained."""
    if mode not in ("opaque","transparent","hidden"):
        raise ValueError("cover mode must be opaque, transparent or hidden")
    root=bpy.data.objects.get("GH_ROOF_COVER")
    if root is None:
        return
    if opacity is not None:
        if not 0<=opacity<=1:
            raise ValueError("cover opacity must be between 0 and 1")
        root["transparent_opacity"]=opacity
    alpha=1.0 if mode=="opaque" else (0.0 if mode=="hidden" else root.get("transparent_opacity",0.15))
    root["cover_mode"]=mode
    root["preview_hidden"]=mode=="hidden"
    for obj in root.children_recursive:
        if obj.get("asset_type")=="roof_cover":
            obj.hide_set(mode=="hidden")
            obj.hide_render=mode=="hidden"
            obj["cover_mode"]=mode
            obj["preview_hidden"]=mode=="hidden"
            for mat in obj.data.materials:
                mat.node_tree.nodes.get("Principled BSDF").inputs["Alpha"].default_value=alpha
                mat.diffuse_color=(*mat.diffuse_color[:3],alpha)
                if hasattr(mat,"surface_render_method"):
                    mat.surface_render_method="BLENDED" if alpha<1 else "DITHERED"
                else:
                    mat.blend_method="BLEND" if alpha<1 else "OPAQUE"


def roof_grid(config, span=1):
    g = config["greenhouse"]
    ys = [p[0] for p in generate_arch_points(g["span_width"], g["eave_height"]["value"], g["ridge_height"]["value"], g["roof"]["segments_per_span"], roof_arch_radius(g))]
    xs = list(span_x_range(g, span))
    if config["roof_vents"]["enabled"]:
        for side in vent_sides(config):
            x0, x1, y1 = vent_bounds(config, side, span)
            xs = sorted(set(xs + [x0,x1]))
            ys = sorted(set(ys + [0,y1]))
    return xs, ys


def create_cover(builder, config, mats):
    if not config["cover"]["enabled"]:
        return
    g = config["greenhouse"]
    for j,y in enumerate(span_centers(g["span_count"],g["span_width"]),1):
        xs, ys = roof_grid(config, j)
        skip = None
        if config["roof_vents"]["enabled"]:
            openings = [vent_bounds(config, side, j) for side in vent_sides(config)]
            skip = lambda x,y,openings=openings: any(x0 < x < x1 and min(0,y1) < y < max(0,y1) for x0,x1,y1 in openings)
        # Spans of equal length share one cover mesh.
        offset = span_x_range(g, j)[0] + g["length"]/2
        mesh = grid_surface(builder, "COVER" if offset == 0 else f"COVER_{offset:g}", xs, ys,
                            lambda y: arch_height(y,g["span_width"],g["eave_height"]["value"],g["ridge_height"]["value"],roof_arch_radius(g)), mats["cover"], skip)
        obj = builder.object(f"GH_ROOF_COVER_S{j:02d}", mesh, "GH_ROOF_COVER", asset_type="roof_cover", span_index=j)
        obj.location.y = y
