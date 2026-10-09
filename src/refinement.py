"""Reversible view presets. Hidden nodes remain exported; extras describe visibility."""
import bpy
from .scene_setup import owned
from .geometry.cover import set_cover_visibility

PRESETS=('exterior','interior','equipment','control_devices')


def apply_view_preset(name):
    if name not in PRESETS: raise ValueError('Unknown view preset: '+str(name))
    root=bpy.data.objects['GH_ROOT']
    for obj in bpy.context.scene.objects:
        if not owned(obj) or obj.type not in ('MESH','EMPTY'): continue
        hide=(name in ('equipment','control_devices') and obj.get('asset_type')=='crop_plant')
        ancestors=[]; parent=obj.parent
        while parent:
            ancestors.append(parent.name); parent=parent.parent
        if name=='equipment' and any(group in ancestors for group in ('GH_STRUCTURE','GH_ROOF_FRAME','GH_SCREENS','GH_VENTS')): hide=True
        if name=='control_devices' and 'GH_FERTIGATION' in ancestors: hide=True
        obj.hide_set(hide); obj.hide_render=hide
        obj['preset_hidden']=hide
    for mat_name in ('MAT_SIDEWALL_FIXED','MAT_CURTAIN'):
        mat=bpy.data.materials.get(mat_name)
        if mat:
            node=mat.node_tree.nodes.get('Principled BSDF')
            if 'exterior_opacity' not in mat: mat['exterior_opacity']=node.inputs['Alpha'].default_value
            alpha=mat['exterior_opacity'] if name=='exterior' else 0.08
            node.inputs['Alpha'].default_value=alpha
            mat.diffuse_color=(*mat.diffuse_color[:3],alpha)
    set_cover_visibility('transparent' if name=='exterior' else 'hidden')
    root['view_preset']=name
    bpy.context.view_layer.update()
