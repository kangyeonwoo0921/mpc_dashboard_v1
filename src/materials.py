"""Simple glTF-compatible Principled materials, with Blender API compatibility."""
import bpy
from .scene_setup import mark, owned


def material(name, color, metallic=0.0, roughness=0.5, opacity=1.0):
    mat = bpy.data.materials.get(name)
    if mat and not owned(mat):
        raise ValueError(f"[SCENE ERROR] Material name collision: {name}")
    if mat is None:
        mat = mark(bpy.data.materials.new(name))
    mat.use_nodes = True
    node = mat.node_tree.nodes.get("Principled BSDF")
    node.inputs["Base Color"].default_value = (*color, 1)
    node.inputs["Metallic"].default_value = metallic
    node.inputs["Roughness"].default_value = roughness
    node.inputs["Alpha"].default_value = opacity
    mat.diffuse_color = (*color, opacity)
    mat.use_backface_culling = False
    if opacity < 1:
        if hasattr(mat, "surface_render_method"):
            mat.surface_render_method = "BLENDED"
        else:
            mat.blend_method = "BLEND"
    return mat


def create_materials(config):
    mats = {
        "frame": material("MAT_FRAME_METAL", (0.42, 0.48, 0.52), 0.8, 0.4),
        "cover": material("MAT_COVER", (0.73, 0.86, 0.89), roughness=config["cover"]["roughness"], opacity=config["cover"]["opacity"]),
        "vent": material("MAT_VENT_FRAME", (0.30, 0.38, 0.42), 0.75, 0.4),
        "shade": material("MAT_SCREEN_SHADE", (0.24, 0.29, 0.28), opacity=config["shade_screen"]["visual_opacity"]),
        "diffuse": material("MAT_SCREEN_DIFFUSE", (0.80, 0.83, 0.78), opacity=config["diffuse_screen"]["visual_opacity"]),
        "bed": material("MAT_BED", (0.50, 0.46, 0.36), roughness=0.75),
        "ground": material("MAT_GROUND", (0.15, 0.18, 0.18), roughness=0.9),
    }
    if config['sidewalls']['enabled'] or config["metadata"]["phase"]>=1.5 or any(config[k]["enabled"] for k in ("crops","fertigation","sensors","side_curtains")) or config["roof_vents"]["mechanism_enabled"] or any(config[k]["drive_enabled"] for k in ("shade_screen","diffuse_screen")):
        for key,name,color,metallic in (
            ("stem","MAT_PLANT_STEM",(0.12,0.25,0.055),0),
            ("leaf","MAT_PLANT_LEAF",(0.10,0.30,0.045),0),
            ("tomato_green","MAT_TOMATO_GREEN",(0.31,0.42,0.055),0),
            ("tomato_red","MAT_TOMATO_RED",(0.65,0.035,0.018),0),
            ("string","MAT_SUPPORT_STRING",(0.64,0.61,0.47),0),
            ("supply","MAT_PIPE_SUPPLY",(0.075,0.21,0.27),0.25),
            ("drain","MAT_PIPE_DRAIN",(0.22,0.24,0.22),0.1),
            ("tank","MAT_TANK",(0.62,0.69,0.64),0.15),
            ("pump","MAT_PUMP",(0.13,0.25,0.28),0.6),
            ("cabinet","MAT_CONTROL_PANEL",(0.61,0.65,0.63),0.5),
            ("sensor","MAT_SENSOR",(0.78,0.77,0.61),0.15),
            ("motor","MAT_MOTOR",(0.15,0.20,0.23),0.65),
            ("display","MAT_DISPLAY",(0.015,0.065,0.075),0.1),
        ):
            mats[key]=material(name,color,metallic,0.55)
        mats["curtain"]=material("MAT_CURTAIN",(0.71,0.78,0.77),roughness=0.6,opacity=0.48 if config['sidewalls']['enabled'] else 0.28)
        mats['sidewall_fixed']=material('MAT_SIDEWALL_FIXED',(0.57,0.65,0.63),roughness=0.6,opacity=config['sidewalls']['material_opacity'])
        mats['end_cladding']=material('MAT_END_CLADDING',(0.64,0.68,0.65),roughness=0.75,opacity=config['end_walls']['cladding_opacity'])
        mats['end_windbreak']=material('MAT_END_WINDBREAK',(0.67,0.76,0.74),roughness=0.6,opacity=config['end_walls']['windbreak_opacity'])
        mats["vent_panel"]=material("MAT_VENT_PANEL",(0.73,0.86,0.89),roughness=config["cover"]["roughness"],opacity=config["cover"]["opacity"])
    return mats
