"""Assertions shared by generation and the standalone Blender acceptance runner."""
import json
import math
import struct
from pathlib import Path
import bpy
from mathutils import Vector
from .scene_setup import GROUPS, owned
from .geometry_math import make_stations, secondary_stations, vent_sides, span_x_range, gridline_x_start, stations_from, screen_pieces_per_span
from .report import object_counts
from .operational_validation import validate_operational_scene
from .refinement_validation import validate_refinement_scene


def require(condition, message):
    if not condition:
        raise ValueError("[VALIDATION ERROR] " + message)


def validate_scene(config):
    g,s = config["greenhouse"],config["structure"]
    n = g["span_count"]
    for name in GROUPS:
        require(bpy.data.collections.get(name) is not None, f"Missing collection: {name}")
        obj = bpy.context.scene.objects.get(name)
        require(obj is not None and obj.type == "EMPTY", f"Missing hierarchy node: {name}")
    expected = {
        "main_columns":sum(len(stations_from(make_stations(g["length"],s["main_column_spacing"]),gridline_x_start(g,j))) for j in range(1,n+2)),
        "secondary_columns":sum(len(stations_from(secondary_stations(g["length"],s["secondary_column_spacing"],s["main_column_spacing"]),gridline_x_start(g,j))) for j in range(1,n+2)),
        "rafters":sum(len(stations_from(make_stations(g["length"],s["rafter_spacing"]),span_x_range(g,j)[0])) for j in range(1,n+1)),
        "roof_vents":n*len(vent_sides(config)) if config["roof_vents"]["enabled"] else 0,
        "shade_screens":n*screen_pieces_per_span(config["shade_screen"]) if config["shade_screen"]["enabled"] else 0,
        "diffuse_screens":n*screen_pieces_per_span(config["diffuse_screen"]) if config["diffuse_screen"]["enabled"] else 0,
        "crop_beds":n*config["crop_beds"]["rows_per_span"] if config["crop_beds"]["enabled"] else 0,
    }
    require(object_counts()==expected, f"Object counts: {object_counts()} != {expected}")
    objs = [o for o in bpy.context.scene.objects if owned(o)]
    names = [o.name for o in objs]
    require(len(names)==len(set(names)), "Duplicate object names")
    for obj in objs:
        require(not (len(obj.name.rsplit('.',1))==2 and obj.name.rsplit('.',1)[1].isdigit()), f"Automatic name suffix: {obj.name}")
        require(all(math.isfinite(v) and v > 0 for v in obj.scale), f"Non-positive or invalid scale: {obj.name}")
        require(all(math.isfinite(v) for row in obj.matrix_world for v in row), f"Invalid transform: {obj.name}")
        if obj.get("asset_type") in ("roof_vent","shade_screen","diffuse_screen"):
            require(obj.parent is not None and obj.parent.type=="EMPTY", f"Missing pivot: {obj.name}")
            require(obj.get("controllable") and obj.get("control_variable")=="opening_percent", f"Missing control metadata: {obj.name}")
    columns = [o for o in objs if o.get("asset_type")=="main_column"]
    for axis,size in ((0,g["length"]),(1,n*g["span_width"])):
        values = [o.location[axis] for o in columns]
        require(math.isclose(min(values),-size/2,abs_tol=1e-5) and math.isclose(max(values),size/2,abs_tol=1e-5),"Column grid dimensions changed")
    require(bpy.context.scene.unit_settings.scale_length==1 and bpy.context.scene.unit_settings.system=="METRIC", "Expected metric meter units")
    return ["required_collections_and_nodes", "object_counts", "unique_names", "finite_positive_transforms", "movable_pivots", "dimensions_and_meter_units"]+validate_operational_scene(config)+validate_refinement_scene(config)


def read_glb(path):
    data = Path(path).read_bytes()
    require(len(data)>=20,"GLB is too short")
    magic, version, length = struct.unpack_from("<4sII",data)
    require(magic==b"glTF" and version==2 and length==len(data),"Invalid glTF 2.0 GLB header")
    size, kind = struct.unpack_from("<I4s",data,12)
    require(kind==b"JSON", "GLB first chunk must be JSON")
    return json.loads(data[20:20+size])


def validate_outputs(outputs):
    for key in ("blend_path","glb_path"):
        require(outputs[key].is_file() and outputs[key].stat().st_size>0,f"Missing/empty output: {outputs[key]}")
    with outputs["blend_path"].open("rb") as handle:
        require(handle.read(7)==b"BLENDER","Invalid BLEND header")
    gltf = read_glb(outputs["glb_path"])
    nodes = gltf.get("nodes",[])
    names = [node.get("name") for node in nodes]
    require(len(names)==len(set(names)),"Duplicate GLB node names")
    expected = {o.name for o in bpy.context.scene.objects if owned(o) and o.type in ("MESH","EMPTY")}
    require(set(names)==expected,f"GLB node names differ: missing={expected-set(names)}, extra={set(names)-expected}")
    parents = {child:i for i,node in enumerate(nodes) for child in node.get("children",[])}
    for i,node in enumerate(nodes):
        obj = bpy.context.scene.objects[node["name"]]
        require(node.get("extras",{}).get("asset_type")==obj.get("asset_type"),f"Lost extras: {obj.name}")
        if obj.parent:
            require(i in parents and nodes[parents[i]]["name"]==obj.parent.name,f"Lost hierarchy: {obj.name}")
    return ["blend_header", "glb_2_header", "glb_names", "glb_hierarchy", "glb_extras"]


def scene_snapshot():
    bpy.context.view_layer.update()
    result = {}
    for obj in bpy.context.scene.objects:
        if owned(obj) and obj.type in ("MESH","EMPTY"):
            info = {"parent":obj.parent.name if obj.parent else None,
                    "asset_type":obj.get("asset_type"),
                    "properties":{k:(v.to_list() if hasattr(v,'to_list') else v) for k,v in obj.items()},
                    "matrix":[v for row in obj.matrix_world for v in row]}
            if obj.type=="MESH":
                points = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
                info["bounds"] = [min(p[i] for p in points) for i in range(3)]+[max(p[i] for p in points) for i in range(3)]
                info["materials"] = [m.name for m in obj.data.materials]
                info["triangles"] = sum(len(p.vertices)-2 for p in obj.data.polygons)
                info["material_values"] = []
                for material in obj.data.materials:
                    shader = next(n for n in material.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
                    info["material_values"].extend(shader.inputs["Base Color"].default_value[:3])
                    info["material_values"].extend(shader.inputs[k].default_value for k in ("Metallic","Roughness","Alpha"))
            result[obj.name] = info
    return result


def validate_roundtrip(glb_path):
    """Destructive only in the standalone validation process; never called by GUI generation."""
    before = scene_snapshot()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(glb_path))
    after = scene_snapshot()
    require(before.keys()==after.keys(),"Roundtrip changed names or ownership extras")
    for name, info in before.items():
        actual = after[name]
        for key in ("parent","asset_type","properties","materials","triangles"):
            require(info.get(key)==actual.get(key),f"Roundtrip changed {key}: {name}")
        for key in ("matrix","bounds","material_values"):
            if key in info:
                require(all(math.isclose(a,b,abs_tol=2e-4,rel_tol=1e-5) for a,b in zip(info[key],actual[key])),f"Roundtrip changed {key}: {name}")
    return ["roundtrip_names", "roundtrip_geometry_bounds", "roundtrip_materials", "roundtrip_hierarchy", "roundtrip_transforms_and_extras"]
