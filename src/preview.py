"""Reproducible Phase 1.5 review views, rendered by the standalone validator."""
from pathlib import Path
import bpy
from mathutils import Vector
from .scene_setup import owned
from .geometry.cover import set_cover_visibility
from .geometry.vents import set_vent_opening
from .geometry.screens import set_screen_opening
from .geometry.curtains import set_side_curtain_opening

PREVIEW_NAMES=("exterior_perspective","interior_cover_hidden","interior_crop_view","fertigation_view",
               "roof_vent_closed","roof_vent_open","screen_open","screen_closed")
REFINEMENT_PREVIEW_NAMES=('sidewall_closed','sidewall_half_open','sidewall_open','screen_full_deployed','screen_retracted','vent_mechanism_closeup','ring_blower_closeup','fertigation_service_zone','sensor_placeholder_view')
END_PREVIEW_NAMES=('front_elevation','rear_elevation','front_door_closeup')


def render_operational_previews(directory,config,only=None):
    directory=Path(directory); directory.mkdir(parents=True,exist_ok=True)
    scene=bpy.context.scene
    camera=scene.camera
    if not camera:
        raise ValueError("Preview requires render.add_camera=true")
    scene.render.resolution_x=1280
    scene.render.resolution_y=800
    scene.render.resolution_percentage=100
    scene.cycles.samples=24
    scene.cycles.use_denoising=True
    scene.view_settings.exposure=0.5
    for obj in scene.objects:
        if not owned(obj): obj.hide_render=True
    original_camera=(camera.location.copy(),camera.rotation_euler.copy(),camera.data.ortho_scale)
    paths=[]

    def render(name):
        if only is not None and name not in only: return
        bpy.context.view_layer.update()
        scene.render.filepath=str(directory/(name+".png"))
        bpy.ops.render.render(write_still=True)
        paths.append(scene.render.filepath)

    def aim(target,offset,scale):
        target=Vector(target)
        camera.location=target+Vector(offset)
        camera.rotation_euler=(target-camera.location).to_track_quat("-Z","Y").to_euler()
        camera.data.type="ORTHO"
        camera.data.ortho_scale=scale

    def overview():
        camera.location,camera.rotation_euler,camera.data.ortho_scale=original_camera

    def screens(percent):
        for name in ("GH_SHADE_SCREEN","GH_DIFFUSE_SCREEN"):
            root=bpy.data.objects[name]
            if any(o.get("asset_type")=="screen_pivot" for o in root.children_recursive):
                set_screen_opening(root,percent)

    set_cover_visibility("transparent",config["visualization"]["cover_opacity"])
    render("exterior_perspective")
    set_cover_visibility("hidden")
    if config["visualization"]["interior_preview"]:
        screens(100)
        for obj in scene.objects:
            if obj.get("asset_type")=="side_curtain": set_side_curtain_opening(obj,100)
    bpy.context.view_layer.update()
    render("interior_cover_hidden")

    plants=[o for o in scene.objects if o.get("asset_type")=="crop_plant"]
    crop_cutaway={o:o.hide_render for o in scene.objects if o.get("asset_type") in ("main_column","secondary_column","rafter","roof_frame","truss","gutter")}
    for obj in crop_cutaway: obj.hide_render=True
    if plants:
        plant=bpy.data.objects.get("GH_PLANT_S01_R02_P004",plants[0])
        target=plant.matrix_world.translation+Vector((0.4,0,config["crops"]["plant_height"]*0.50))
        aim(target,(-5,-3.5,1.0),6.5)
    render("interior_crop_view")
    for obj,hidden in crop_cutaway.items(): obj.hide_render=hidden

    unit=bpy.data.objects.get("GH_FERTIGATION_UNIT")
    if unit and unit.children:
        points=[o.matrix_world@Vector(p) for o in unit.children_recursive if o.type=="MESH" for p in o.bound_box]
        low=Vector(tuple(min(p[i] for p in points) for i in range(3)))
        high=Vector(tuple(max(p[i] for p in points) for i in range(3)))
        center=(low+high)/2
        extent=(high-low).length
        aim(center,(-extent*0.6, -extent*0.35, extent*1.7),extent*1.10)
    render("fertigation_view")

    # Close views intentionally isolate the target drive from screens/crops behind it.
    previous={obj:obj.hide_render for obj in scene.objects}
    for obj in scene.objects:
        if obj.get("asset_type") in ("crop_plant","shade_screen","diffuse_screen"):
            obj.hide_render=True
    vent=bpy.data.objects.get("GH_VENT_S01_01")
    motor=bpy.data.objects.get("GH_VENT_S01_01_MOTOR")
    if vent:
        target=(motor.matrix_world.translation+Vector((0.6,0.3,0.4))) if motor else vent.matrix_world.translation
        aim(target,(3.5,-4,2.4),4.7)
        set_vent_opening(vent,0)
    render("roof_vent_closed")
    if vent: set_vent_opening(vent,100)
    render("roof_vent_open")
    for obj,hidden in previous.items(): obj.hide_render=hidden
    overview()
    screens(100)
    render("screen_open")
    screens(0)
    render("screen_closed")
    if config['preview']['generate_refinement_views']:
        from .refinement import apply_view_preset
        g=config['greenhouse']; width=g['span_count']*g['span_width']
        apply_view_preset('exterior')
        screens(100)
        # Side view includes an end jamb but focuses on a readable 15m wall section.
        aim((-g['length']*0.30,-width/2,g['eave_height']['value']/2),(-8,-20,4),19)
        for percent,name in ((0,'sidewall_closed'),(50,'sidewall_half_open'),(100,'sidewall_open')):
            for obj in scene.objects:
                if obj.get('asset_type')=='side_curtain': set_side_curtain_opening(obj,percent)
            render(name)
        apply_view_preset('interior')
        # Look down the rows from the retract edge: both fabric heights and bundles are visible.
        aim((-g['length']/2+9,-width/2+g['span_width'],4.5),(-15,-12,9),24)
        screens(0); render('screen_full_deployed')
        screens(100); render('screen_retracted')
        apply_view_preset('control_devices')
        if vent and motor:
            set_vent_opening(vent,50); bpy.context.view_layer.update()
            aim(motor.matrix_world.translation+Vector((0.65,0.1,0.15)),(1.0,-3,-0.5),2.4)
        render('vent_mechanism_closeup')
        apply_view_preset('equipment')
        # Hide enclosure only for equipment inspection, keep the normal exterior intact.
        for obj in bpy.data.objects['GH_SIDEWALLS'].children_recursive:
            obj.hide_render=True
        blower=bpy.data.objects.get('GH_RING_BLOWER')
        if blower:
            isolated={o:o.hide_render for o in scene.objects}
            visible={blower,*blower.children_recursive}
            for o in scene.objects:
                if o.type=='MESH' and o not in visible and o.get('asset_type')!='ground': o.hide_render=True
            aim(blower.matrix_world.translation+Vector((0,0,0.4)),(-1.7,-2.3,1.3),1.6)
        render('ring_blower_closeup')
        if blower:
            for o,hidden in isolated.items(): o.hide_render=hidden
        if unit and unit.children:
            points=[o.matrix_world@Vector(p) for o in unit.children_recursive if o.type=='MESH' for p in o.bound_box]
            low=Vector(tuple(min(p[i] for p in points) for i in range(3)))
            high=Vector(tuple(max(p[i] for p in points) for i in range(3)))
            aim((low+high)/2,(-7,-5,21),(high-low).length*1.12)
        render('fertigation_service_zone')
        apply_view_preset('control_devices')
        sensor=bpy.data.objects.get('GH_SENSOR_T_RH_01_ANCHOR')
        if sensor: aim(sensor.matrix_world.translation,(-1.4,-2,0.7),1.25)
        render('sensor_placeholder_view')
    if config['sidewalls']['enabled']:
        from .refinement import apply_view_preset
        apply_view_preset('exterior')
        g=config['greenhouse']; width=g['span_count']*g['span_width']
        key_light=bpy.data.objects.get('Light_Key')
        saved_light=key_light.rotation_euler.copy() if key_light else None
        def light_end(sign):
            if key_light: key_light.rotation_euler=Vector((-sign,0,-1)).to_track_quat('-Z','Y').to_euler()
        # True exterior elevations: Front looks +X, Rear looks -X, Z remains up.
        for end,sign in (('front',-1),('rear',1)):
            light_end(sign)
            aim((sign*g['length']/2,0,g['ridge_height']['value']/2),(sign*20,0,0),width*1.12)
            render(end+'_elevation')
        door=bpy.data.objects['GH_FRONT_DOOR']
        from .orientation import door_dimensions
        _,door_width,door_height=door_dimensions(config)
        light_end(-1)
        aim(door.matrix_world.translation+Vector((0,0,door_height/2)),(-9,-1.8,1.2),max(door_width,door_height)*2.1)
        render('front_door_closeup')
        if key_light: key_light.rotation_euler=saved_light
    for path in paths:
        if not Path(path).is_file() or Path(path).stat().st_size<1000:
            raise ValueError(f"Missing/empty preview: {path}")
    return paths
