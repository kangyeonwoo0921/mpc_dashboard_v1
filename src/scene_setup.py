"""Generated-object ownership, portable hierarchy, metric scene and preview setup."""
import math
import bpy
from mathutils import Vector

OWNER_KEY = "greenhouse_generator"
OWNER = "phase1"
GROUPS = {
    "GH_ROOT": None,
    "GH_STRUCTURE": "GH_ROOT",
    "GH_COLUMNS_MAIN": "GH_STRUCTURE", "GH_COLUMNS_SECONDARY": "GH_STRUCTURE",
    "GH_RAFTERS": "GH_STRUCTURE", "GH_TRUSSES": "GH_STRUCTURE", "GH_GUTTERS": "GH_STRUCTURE",
    "GH_ROOF": "GH_ROOT", "GH_ROOF_FRAME": "GH_ROOF", "GH_ROOF_COVER": "GH_ROOF",
    "GH_VENTS": "GH_ROOT", "GH_SCREENS": "GH_ROOT",
    "GH_SHADE_SCREEN": "GH_SCREENS", "GH_DIFFUSE_SCREEN": "GH_SCREENS",
    "GH_INTERIOR": "GH_ROOT", "GH_BEDS": "GH_INTERIOR", "GH_GROUND": "GH_ROOT", "GH_SCENE": "GH_ROOT",
    "GH_CROPS": "GH_INTERIOR", "GH_CURTAINS": "GH_ROOT",
    "GH_SHADE_SCREEN_DRIVE": "GH_SHADE_SCREEN", "GH_DIFFUSE_SCREEN_DRIVE": "GH_DIFFUSE_SCREEN",
    "GH_FERTIGATION": "GH_ROOT", "GH_FERTIGATION_UNIT": "GH_FERTIGATION",
    "GH_IRRIGATION_SUPPLY": "GH_FERTIGATION", "GH_IRRIGATION_DRAIN": "GH_FERTIGATION",
    "GH_SENSORS": "GH_ROOT",
    "GH_SIDEWALLS": "GH_ROOT", "GH_SIDEWALL_LEFT": "GH_SIDEWALLS", "GH_SIDEWALL_RIGHT": "GH_SIDEWALLS",
}


def owned(block):
    return block.get(OWNER_KEY) == OWNER


def mark(block):
    block[OWNER_KEY] = OWNER
    return block


def cleanup_defaults(config):
    """Explicit opt-in exception to user preservation; exact names and types only."""
    for key,name,kind in (("remove_default_cube","Cube","MESH"),("remove_default_camera","Camera","CAMERA"),("remove_default_light","Light","LIGHT")):
        obj=bpy.data.objects.get(name)
        if config["scene_cleanup"][key] and obj and obj.type==kind and OWNER_KEY not in obj:
            bpy.data.objects.remove(obj,do_unlink=True)


def clear_previous_generated_scene():
    # Preserve user children attached to generated parents, including their world transform.
    for obj in list(bpy.data.objects):
        if not owned(obj) and obj.parent and owned(obj.parent):
            matrix = obj.matrix_world.copy()
            obj.parent = None
            obj.matrix_world = matrix
        if not owned(obj):
            for collection in list(obj.users_collection):
                if owned(collection) and obj.name not in bpy.context.scene.collection.objects:
                    bpy.context.scene.collection.objects.link(obj)
    for obj in list(bpy.data.objects):
        if owned(obj):
            bpy.data.objects.remove(obj, do_unlink=True)
    # Unlink user collections before deleting generated collection containers.
    for collection in list(bpy.data.collections):
        if owned(collection):
            for child in list(collection.children):
                if not owned(child) and child.name not in bpy.context.scene.collection.children:
                    bpy.context.scene.collection.children.link(child)
            bpy.data.collections.remove(collection)
    for blocks in (bpy.data.meshes, bpy.data.curves, bpy.data.cameras, bpy.data.lights, bpy.data.materials, bpy.data.worlds):
        for block in list(blocks):
            if owned(block) and block.users == 0:
                blocks.remove(block)


class SceneBuilder:
    def __init__(self):
        self.collections = {}
        self.groups = {}
        self.mesh_cache = {}
        for name, parent in GROUPS.items():
            if bpy.data.collections.get(name):
                raise ValueError(f"[SCENE ERROR] Collection name belongs to user data: {name}")
            collection = mark(bpy.data.collections.new(name))
            (self.collections[parent] if parent else bpy.context.scene.collection).children.link(collection)
            self.collections[name] = collection
            self.groups[name] = self.object(name, None, name, self.groups.get(parent), "group")
        self.groups["GH_ROOT"]["coordinate_system"] = "X=length,Y=width,Z=height; meters"

    def object(self, name, data, group, parent=None, asset_type=None, **properties):
        if bpy.data.objects.get(name):
            raise ValueError(f"[SCENE ERROR] Object name collision: {name}")
        obj = mark(bpy.data.objects.new(name, data))
        self.collections[group].objects.link(obj)
        obj.parent = parent if parent is not None else self.groups.get(group)
        if asset_type:
            obj["asset_type"] = asset_type
        for key, value in properties.items():
            obj[key] = value
        return obj


def setup_units(config):
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.length_unit = "METERS"
    scene.unit_settings.scale_length = 1.0
    scene.render.resolution_x = config["render"]["preview_resolution_x"]
    scene.render.resolution_y = config["render"]["preview_resolution_y"]
    scene.render.resolution_percentage = 100
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 16
    scene.cycles.use_denoising = True
    scene.render.image_settings.file_format = "PNG"


def fit_camera_to_bounds(builder):
    bpy.context.view_layer.update()
    points = [obj.matrix_world @ Vector(corner) for obj in bpy.context.scene.objects
              if owned(obj) and obj.type == "MESH" and obj.get("asset_type") != "ground"
              for corner in obj.bound_box]
    low = Vector(tuple(min(p[i] for p in points) for i in range(3)))
    high = Vector(tuple(max(p[i] for p in points) for i in range(3)))
    center = (low + high) / 2
    direction = Vector((1.3, -1.5, 1.05)).normalized()
    data = mark(bpy.data.cameras.new("Camera_Main_Data"))
    obj = builder.object("Camera_Main", data, "GH_SCENE", asset_type="camera")
    obj.location = center + direction * (high - low).length * 1.6
    obj.rotation_euler = (-direction).to_track_quat("-Z", "Y").to_euler()
    data.type = "ORTHO"
    rotation = obj.rotation_euler.to_matrix()
    right, up = rotation @ Vector((1, 0, 0)), rotation @ Vector((0, 1, 0))
    extent_x = max(abs((p - center).dot(right)) for p in points) * 2
    extent_y = max(abs((p - center).dot(up)) for p in points) * 2
    scene = bpy.context.scene
    aspect = scene.render.resolution_x / scene.render.resolution_y
    data.ortho_scale = max(extent_x, extent_y * aspect) * 1.15
    data.clip_end = max(1000, (high - low).length * 10)
    scene.camera = obj
    # Save a useful opening view in the .blend without selecting hundreds of objects.
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                space = area.spaces.active
                space.clip_end = data.clip_end
                space.region_3d.view_location = center
                space.region_3d.view_rotation = obj.rotation_euler.to_quaternion()
                space.region_3d.view_distance = (high-low).length
                space.region_3d.view_perspective = "PERSP"
    return obj


def setup_camera_lights(builder, config):
    if config["render"]["add_camera"]:
        fit_camera_to_bounds(builder)
    if not config["render"]["add_lights"]:
        return
    world = bpy.data.worlds.get("GH_WORLD")
    if world and not owned(world):
        raise ValueError("[SCENE ERROR] World name collision: GH_WORLD")
    if not world:
        world = mark(bpy.data.worlds.new("GH_WORLD"))
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.18, 0.21, 0.25, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.7
    bpy.context.scene.world = world
    length = config["greenhouse"]["length"]
    for name, kind, energy, position in (
        ("Light_Key", "SUN", 3.0, (length * 0.3, -length * 0.4, length * 0.6)),
        ("Light_Fill", "AREA", 1800.0 * (length / 97.5) ** 2, (-length * 0.2, length * 0.3, length * 0.4)),
    ):
        data = mark(bpy.data.lights.new(name + "_Data", kind))
        data.energy = energy
        if kind == "AREA":
            data.shape = "DISK"
            data.size = length * 0.5
        else:
            data.angle = math.radians(12)
        obj = builder.object(name, data, "GH_SCENE", asset_type="light")
        obj.location = position
        obj.rotation_euler = (-Vector(position)).to_track_quat("-Z", "Y").to_euler()
