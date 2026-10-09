"""Export only owned model objects, preserving their movable node transforms."""
import bpy
from ..scene_setup import owned


def export_glb(path, apply_modifiers=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    selection = list(bpy.context.selected_objects)
    active = bpy.context.view_layer.objects.active
    hidden={obj:obj.hide_get() for obj in bpy.context.view_layer.objects if owned(obj)}
    try:
        if bpy.context.object and bpy.context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        for obj in bpy.context.view_layer.objects:
            if obj in hidden:
                obj.hide_set(False)
            obj.select_set(owned(obj) and obj.type in ("MESH", "EMPTY"))
        requested = dict(filepath=str(path), export_format="GLB", use_selection=True,
                         export_apply=apply_modifiers, export_extras=True,
                         export_yup=True, export_animations=False, export_materials="EXPORT",
                         export_cameras=False, export_lights=False,
                         export_hierarchy_flatten_objs=False, export_hierarchy_full_collections=False)
        supported = bpy.ops.export_scene.gltf.get_rna_type().properties.keys()
        result = bpy.ops.export_scene.gltf(**{k:v for k,v in requested.items() if k in supported})
        if "FINISHED" not in result:
            raise RuntimeError(f"GLB export did not finish: {result}")
    finally:
        for obj in bpy.context.view_layer.objects:
            obj.select_set(obj in selection)
            if obj in hidden:
                obj.hide_set(hidden[obj])
        bpy.context.view_layer.objects.active = active
