"""Bake helper-produced transform samples into a separate Blender smoke-test artifact."""
import math
import bpy
from .geometry.vents import set_vent_opening
from .geometry.screens import set_screen_opening
from .geometry.curtains import set_side_curtain_opening
from .scene_setup import owned


def create_motion_smoke_test():
    scene=bpy.context.scene
    objects=[o for o in scene.objects if owned(o) and o.type in ('MESH','EMPTY')]
    expected={}; anchors={o.name:tuple(o.matrix_world.translation) for o in objects if o.get('asset_type') in ('vent_pivot','screen_pivot','side_curtain','sensor_anchor')}
    controls=[o for o in objects if o.get('asset_type') in ('vent_pivot','screen_pivot','side_curtain')]
    scene.frame_start=1; scene.frame_end=120
    # Bake every frame to avoid linear-quaternion/rack interpolation disconnecting the mechanism.
    for frame in range(1,121):
        scene.frame_set(frame)
        percent=(frame-1)*50/59 if frame<=60 else 50+(frame-60)*50/60
        for obj in controls:
            {'vent_pivot':set_vent_opening,'screen_pivot':set_screen_opening,'side_curtain':set_side_curtain_opening}[obj['asset_type']](obj,percent)
        bpy.context.view_layer.update()
        moving=[o for o in objects if o.get('asset_type') in ('vent_pivot','vent_rack','pinion','screen_pivot','screen_bundle','screen_drum','screen_roller','screen_shaft','curtain_panel','curtain_bottom_bar','curtain_roller','curtain_drum')]
        for obj in moving:
            for path in ('location','scale','rotation_quaternion' if obj.rotation_mode=='QUATERNION' else 'rotation_euler'):
                obj.keyframe_insert(data_path=path,frame=frame,group='Opening smoke test')
        for obj in objects:
            if 'opening_percent' in obj:
                obj.keyframe_insert(data_path='["opening_percent"]',frame=frame,group='Opening smoke test')
        if frame in (1,60,120):
            expected[frame]={o.name:[v for row in o.matrix_world for v in row] for o in moving}
            scene.timeline_markers.new(f'{round(percent)} percent',frame=frame)
    # Scrub out of order using only animation evaluation, never the helpers.
    for frame in (120,1,60,1,120):
        scene.frame_set(frame); bpy.context.view_layer.update()
        for name,matrix in expected[frame].items():
            actual=[v for row in bpy.data.objects[name].matrix_world for v in row]
            if not all(math.isclose(a,b,abs_tol=2e-5) for a,b in zip(matrix,actual)):
                raise ValueError('Motion evaluation differs from helper: '+name)
        for name,position in anchors.items():
            if any(abs(a-b)>1e-5 for a,b in zip(position,bpy.data.objects[name].matrix_world.translation)):
                raise ValueError('Motion moved fixed anchor: '+name)
    scene.frame_set(1)
    return {'status':'success','frames':{'1':0,'60':50,'120':100},'baked_frames':120,'controls':len(controls),'fixed_anchors':len(anchors),'scope':'Blender transform smoke test, not web animation or mechanical calibration'}
