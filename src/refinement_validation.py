"""Phase 1.6 geometry and contract assertions, including imported GLB nodes."""
import math
import bpy
from mathutils import Vector
from .refinement_math import screen_visible_width
from .geometry_math import screen_pieces_per_span
from .scene_setup import owned
from .orientation import end_positions,door_dimensions
from .geometry_math import front_x_at


def require(condition,message):
    if not condition: raise ValueError('[PHASE 1.6 VALIDATION ERROR] '+message)


def validate_refinement_scene(config):
    checks=[]; objects=[o for o in bpy.context.scene.objects if owned(o)]
    root=bpy.data.objects['GH_ROOT']
    for key in ('front_axis_reference','rear_axis_reference','front_end','rear_end'):
        require(root.get(key)==config['orientation'][key],'Root orientation metadata changed: '+key)
    if config['sidewalls']['enabled']:
        for side in ('LEFT','RIGHT'):
            group=bpy.data.objects['GH_SIDEWALL_'+side]
            fixed=bpy.data.objects.get(group.name+'_FIXED')
            require(fixed is not None and fixed.parent==group,'Missing fixed windbreak')
            if config['side_curtains']['enabled']:
                curtain=bpy.data.objects['GH_SIDE_CURTAIN_'+side]
                require(curtain.parent==group,'Curtain sidewall hierarchy lost')
                panel=bpy.data.objects[curtain['panel_name']]
                full_bottom=curtain.matrix_world.translation.z+min(v.co.z for v in panel.data.vertices)
                require(math.isclose(full_bottom,config['sidewalls']['fixed_lower_wall_height'],abs_tol=1e-5),'Closed curtain leaves a lower gap')
        for name in ('GH_FRONT_WALL','GH_REAR_WALL','GH_FRONT_DOOR'):
            require(bpy.data.objects.get(name) is not None,'Missing end closure '+name)
        require(bpy.data.objects['GH_FRONT_DOOR']['verified_position'] is False,'Door position claimed verified')
        for end,position in end_positions(config).items():
            wall=bpy.data.objects['GH_'+end.upper()+'_WALL']
            require((wall.matrix_world.translation-Vector(position)).length<1e-5,'Front/Rear reversed or misplaced: '+wall.name)
            require(wall['axis_reference']==('X1' if end=='front' else 'X23'),'Wall axis reference reversed')
            shell=bpy.data.objects[wall.name+'_SHELL']
            require(shell.parent==wall and sum(p.area for p in shell.data.polygons)>config['greenhouse']['span_count']*config['greenhouse']['span_width']*config['greenhouse']['eave_height']['value']*0.8,'End wall is open/frame-only')
            # A stepped front keeps each strip on its own span's front plane.
            planes=(lambda y:front_x_at(config['greenhouse'],y)) if end=='front' else (lambda y:{position[0]})
            require(all(any(abs((shell.matrix_world@v.co).x-x)<1e-4 for x in planes((shell.matrix_world@v.co).y)) for v in shell.data.vertices),'End shell is off its drawing plane')
            require(all(m.node_tree.nodes['Principled BSDF'].inputs['Alpha'].default_value>=0.25 for m in shell.data.materials),'End wall surface became invisible')
        door=bpy.data.objects['GH_FRONT_DOOR']; front=bpy.data.objects['GH_FRONT_WALL']
        require(door.parent==front,'Door must be integrated in front wall assembly')
        y,w,h=door_dimensions(config)
        require(any(abs(door.matrix_world.translation.x-x)<1e-5 for x in front_x_at(config['greenhouse'],y)) and abs(door.matrix_world.translation.y-y)<1e-5,'Door is detached from end-wall plane/location')
        require(bpy.data.objects['GH_FRONT_DOOR_PANEL'].parent==door,'Door leaf is detached')
        front_area=sum(p.area for p in bpy.data.objects['GH_FRONT_WALL_SHELL'].data.polygons)
        rear_area=sum(p.area for p in bpy.data.objects['GH_REAR_WALL_SHELL'].data.polygons)
        require(math.isclose(front_area+w*h,rear_area,abs_tol=0.001),'Front cladding does not surround the exact doorway aperture')
        checks += ['front_X1_rear_X23_world_positions','integrated_front_door_and_surrounding_cladding','rear_visible_complete_end_surface']
        checks.append('refinement_sidewalls_closed_envelope_and_end_closures')
    for obj in objects:
        kind=obj.get('asset_type')
        if kind in ('shade_screen','diffuse_screen') and config['visual_refinement']['clip_screens_to_interior']:
            width=max(v.co.y for v in obj.data.vertices)-min(v.co.y for v in obj.data.vertices)
            require(math.isclose(width,screen_visible_width(config,config[kind]['height'])/screen_pieces_per_span(config[kind]),abs_tol=1e-5),'Screen visual clipping differs from roof envelope')
            require(math.isclose(obj.parent.matrix_world.translation.z,config[kind]['height'],abs_tol=1e-5),'Screen height was changed')
            bundle=bpy.data.objects.get(obj.parent.get('bundle_name',''))
            require(bundle is not None and bundle.parent!=obj.parent,'Bundle missing or scales with fabric')
        if kind=='blower':
            require(obj.get('is_circulation_fan') is False and obj.get('system')=='fertigation','Ring blower classified as a fan')
            require({'GH_BLOWER_MOTOR','GH_BLOWER_HOUSING','GH_BLOWER_INLET','GH_BLOWER_OUTLET','GH_BLOWER_BASE'}<={p.name for p in obj.children},'Blower parts missing')
        require(not obj.name.startswith('GH_CIRCULATION_FAN'),'Unverified circulation fan generated')
        if kind=='sensor_anchor':
            item=next(i for i in config['sensors']['items'] if i['id']==obj['sensor_id'])
            require((obj.matrix_world.translation-Vector(item['position'])).length<1e-4,'Sensor anchor moved')
            require(obj.get('label_anchor') and obj.get('verified_position') is False,'Sensor label contract missing')
    checks += ['refinement_screen_clipping_and_bundle','refinement_blower_not_circulation_fan','refinement_sensor_label_anchors']
    if config['visual_refinement']['service_zone_layout'] and config['fertigation']['enabled']:
        unit=bpy.data.objects['GH_FERTIGATION_UNIT']
        roots=[o for o in unit.children if o.get('service_zone')]
        require(bool(roots),'Service zoning missing')
        if config['fertigation']['placement']['mode']=='end_service_strip':
            require(all(o.matrix_world.translation.y<0 for o in roots),'Equipment not on one side of service strip')
        for obj in roots: require(obj.get('verified_position') is False,'Service position verified')
        boxes=[]
        for obj in roots:
            points=[part.matrix_world@Vector(c) for part in obj.children_recursive if part.type=='MESH' for c in part.bound_box]
            if points: boxes.append((obj.name,[min(p[i] for p in points) for i in (0,1)],[max(p[i] for p in points) for i in (0,1)]))
        for i,(name,low,high) in enumerate(boxes):
            for other,lo,hi in boxes[i+1:]:
                gap=math.sqrt(sum(max(0,low[k]-hi[k],lo[k]-high[k])**2 for k in (0,1)))
                require(gap>=0.35*unit['visual_asset_scale']-1e-4,f'Service clearance below 0.35 scaled meters: {name}, {other}, {gap}')
        checks.append('refinement_one_sided_provisional_service_zone')
    return checks


def check_view_presets():
    from .refinement import apply_view_preset,PRESETS
    from .geometry.cover import set_cover_visibility
    # Preserve every property/material/hide state: validation must not change the GLB snapshot.
    objects=[o for o in bpy.context.scene.objects if owned(o)]
    saved={o:(o.hide_get(),o.hide_render,dict(o.items())) for o in objects}
    mats={m:(m.diffuse_color[:],m.node_tree.nodes['Principled BSDF'].inputs['Alpha'].default_value,dict(m.items())) for m in bpy.data.materials if m.use_nodes and m.node_tree.nodes.get('Principled BSDF')}
    try:
        for preset in PRESETS:
            apply_view_preset(preset)
            for obj in objects:
                if obj.get('asset_type')=='crop_plant': require(obj.hide_render==(preset in ('equipment','control_devices')),'Preset crop visibility failed')
                if obj.get('asset_type')=='roof_cover': require(obj.hide_render==(preset!='exterior'),'Preset roof visibility failed')
    finally:
        for obj,(hidden,render,props) in saved.items():
            obj.hide_set(hidden); obj.hide_render=render
            for key in list(obj.keys()):
                if key not in props: del obj[key]
            for key,value in props.items(): obj[key]=value
        for mat,(color,alpha,props) in mats.items():
            mat.diffuse_color=color; mat.node_tree.nodes['Principled BSDF'].inputs['Alpha'].default_value=alpha
            for key in list(mat.keys()):
                if key not in props: del mat[key]
    return ['refinement_four_reversible_view_presets']


def check_end_wall_failure_detection(config):
    """Prove reversed ends, detached doors and missing cladding are rejected."""
    if not config['sidewalls']['enabled']: return []
    front=bpy.data.objects['GH_FRONT_WALL']; rear=bpy.data.objects['GH_REAR_WALL']
    door=bpy.data.objects['GH_FRONT_DOOR']; shell=bpy.data.objects['GH_REAR_WALL_SHELL']
    checks=[]
    def rejected(name):
        bpy.context.view_layer.update()
        try: validate_refinement_scene(config)
        except ValueError: checks.append(name)
        else: raise ValueError('Invalid end-wall scene was accepted: '+name)
    front_x,rear_x=front.location.x,rear.location.x
    try:
        front.location.x,rear.location.x=rear_x,front_x
        rejected('reject_reversed_front_rear')
    finally: front.location.x,rear.location.x=front_x,rear_x
    parent=door.parent
    try:
        door.parent=None
        rejected('reject_standalone_door')
    finally: door.parent=parent
    material=shell.data.materials[1]
    alpha=material.node_tree.nodes['Principled BSDF'].inputs['Alpha']
    previous=alpha.default_value
    try:
        alpha.default_value=0
        rejected('reject_invisible_rear_cladding')
    finally: alpha.default_value=previous
    bpy.context.view_layer.update()
    validate_refinement_scene(config)
    return checks
