"""Phase 1.5 checks supplement (never replace) the original Phase 1 gates."""
import math
import bpy
from mathutils import Vector
from .geometry.crops import plant_positions
from .geometry_math import screen_pieces_per_span, span_x_range
from .geometry.curtains import set_side_curtain_opening
from .geometry.vents import set_vent_opening
from .geometry.screens import set_screen_opening
from .geometry.cover import set_cover_visibility
from .scene_setup import owned


def require(value,message):
    if not value:
        raise ValueError("[PHASE 1.5 VALIDATION ERROR] "+message)


def validate_operational_scene(config):
    checks=[]
    objects=[o for o in bpy.context.scene.objects if owned(o)]
    by_kind={}
    for obj in objects: by_kind.setdefault(obj.get("asset_type"),[]).append(obj)
    beds=by_kind.get("crop_bed",[])
    plants=by_kind.get("crop_plant",[])
    c=config["crops"]
    expected=0
    if c["enabled"] and beds:
        def per_bed(bed):
            x0,x1=span_x_range(config["greenhouse"],bed["span_index"])
            return len(plant_positions(x1-x0-2*config["crop_beds"]["length_margin"],c["plant_spacing"],c["max_visual_plants_per_bed"]))
        expected=sum(per_bed(bed) for bed in beds)
        for bed in beds:
            row=[p for p in plants if p["bed_name"]==bed.name]
            require(len(row)==per_bed(bed),f"Missing plants on {bed.name}")
            require(all(p.parent.get("asset_type")=="crop_row" for p in row),"Plant row hierarchy lost")
            require(all(abs(p.parent.location.z-(config["crop_beds"]["z"]+config["crop_beds"]["height"]))<1e-5 for p in row),"Plant bases overlap bed mesh")
        require(len({p.data.name for p in plants})==1,"Plants must share a mesh")
        require(bpy.data.objects.get("GH_PLANT_MASTER") is not None,"Missing plant master")
        mesh=plants[0].data
        material_names={m.name for m in mesh.materials}
        require({"MAT_PLANT_STEM","MAT_PLANT_LEAF","MAT_SUPPORT_STRING"}<=material_names,"Incomplete tomato asset")
        if c["tomato_clusters"]:
            require({"MAT_TOMATO_RED","MAT_TOMATO_GREEN"}<=material_names,"Missing tomato clusters")
        require(sum(len(p.vertices)-2 for p in mesh.polygons)<2000,"Plant mesh is not low-poly")
    require(len(plants)==expected,"Unexpected crop instance count")
    checks += ["all_beds_have_crops_or_disabled","shared_low_poly_plant_mesh"]
    if config["roof_vents"]["enabled"] and config["roof_vents"]["mechanism_enabled"]:
        for vent in by_kind.get("roof_vent",[]):
            for suffix in ("_PANEL","_SHAFT","_RACK_A","_RACK_B","_PINION","_BEARING","_MOTOR"):
                require(bpy.data.objects.get(vent.name+suffix) is not None,f"Missing vent component: {vent.name+suffix}")
            motor=bpy.data.objects[vent.name+"_MOTOR"]
            require(motor.parent.get("asset_type")=="vent_drive" and motor.parent.parent.name=="GH_VENTS","Motor is attached to the moving panel")
        checks.append("vent_drive_components")
    for key,prefix in (("shade_screen","GH_SHADE_SCREEN"),("diffuse_screen","GH_DIFFUSE_SCREEN")):
        if config[key]["enabled"] and config[key]["drive_enabled"]:
            drives=[o for o in bpy.data.objects[prefix+"_DRIVE"].children if o.get("asset_type")=="screen_drive"]
            require(len(drives)==config["greenhouse"]["span_count"]*screen_pieces_per_span(config[key]),"Missing per-span screen drives")
            for drive in drives:
                roles={o.get("asset_type") for o in drive.children}
                require({"screen_shaft","screen_drum","screen_roller"}<=roles,"Incomplete screen drive")
    checks.append("screen_drive_components")
    require(len(by_kind.get("side_curtain",[]))==(2 if config["side_curtains"]["enabled"] else 0),"Curtain count mismatch")
    f=config["fertigation"]
    if f["enabled"]:
        names=["GH_FERTIGATION_UNIT","GH_WATER_PURIFIER","GH_PRESSURE_GAUGE","GH_PRESSURE_VALVE","GH_FLOW_METER"]
        if f["show_tanks"]: names += ["GH_NUTRIENT_TANK_A","GH_NUTRIENT_TANK_B","GH_NUTRIENT_TANK_C","GH_WATER_TANK","GH_MIXING_TANK"]
        if f["show_pumps"]: names.append("GH_FEED_PUMP")
        if f["show_blower"]: names.append("GH_RING_BLOWER")
        if f["show_filters"]: names += ["GH_FILTER_01","GH_FILTER_02"]
        if f["show_control_panel"]: names += ["GH_CONTROL_PANEL","GH_DISPLAY"]
        for name in names:
            obj=bpy.data.objects.get(name)
            require(obj is not None,f"Missing equipment: {name}")
            require(obj.get("verified_position") is False,"Equipment coordinates claimed as verified")
        for flag,kind in (("show_supply_lines","supply_pipe"),("show_drain_lines","drain_pipe")):
            branches=[o for o in by_kind.get(kind,[]) if o.get("bed_name")]
            require(len(branches)==(len(beds) if f[flag] else 0),f"Missing per-bed {kind}")
        checks.append("fertigation_assets_and_bed_connections")
    sensors=by_kind.get("sensor",[])
    require(len(sensors)==(len(config["sensors"]["items"]) if config["sensors"]["enabled"] else 0),"Sensor count mismatch")
    for sensor in sensors:
        require(sensor.get("verified_position") is False and sensor.get("verified") is False,"Sensor position is not explicitly unverified")
        require(sensor.get("source_confidence")=="placeholder" and sensor.get("live_data_ready"),"Sensor placeholder metadata missing")
        require(sensor.parent.name==sensor.name+"_ANCHOR","Sensor anchor lost")
    checks.append("sensor_placeholders_and_anchors")
    if config["scene_cleanup"]["remove_default_cube"]:
        cube=bpy.data.objects.get("Cube")
        require(cube is None or "greenhouse_generator" in cube or cube.type!="MESH","Default Cube was not removed")
    checks.append("default_cube_cleanup_policy")
    return checks


def check_operational_controls():
    checks=[]
    for obj in list(bpy.context.scene.objects):
        kind=obj.get("asset_type")
        if kind=="vent_pivot" and obj.get("drive_name"):
            drive=bpy.data.objects[obj["drive_name"]]
            motor=next(p for p in drive.children if p.get("asset_type")=="vent_motor")
            saved=obj["opening_percent"]
            fixed=motor.matrix_world.copy()
            rack=next(p for p in drive.children if p.get("asset_type")=="vent_rack")
            pinion=next(p for p in drive.children if p.get("asset_type")=="pinion")
            locations=[]; rotations=[]; actual_rotations=[]
            for percent in (0,50,100,100):
                set_vent_opening(obj,percent)
                bpy.context.view_layer.update()
                require(all(abs(a-b)<1e-5 for ra,rb in zip(fixed,motor.matrix_world) for a,b in zip(ra,rb)),"Vent motor moves with the panel")
                tip=rack.matrix_world @ Vector((0,0,rack["rack_length"]/2))
                target=obj.matrix_world @ Vector((rack["station_x"],rack["attach_y"],rack["attach_z"]))
                require((tip-target).length<2e-4,"Rack is disconnected from the panel attachment")
                locations.append(tuple(rack.location)); rotations.append(pinion.rotation_euler.x)
                actual_rotations.append(pinion.matrix_local.to_quaternion())
            if obj["max_open_angle_deg"]>0:
                require(locations[0]!=locations[1] and locations[1]!=locations[2],"Rack does not follow opening")
            require(rotations[0]<rotations[1]<rotations[2] and rotations[2]==rotations[3],"Pinion motion is not absolute")
            require(abs(actual_rotations[0].dot(actual_rotations[1]))<0.01,'Pinion transform did not rotate after helper')
            set_vent_opening(obj,saved)
            checks.append("visual_rack_pinion_motor:"+obj.name)
        elif kind=="screen_pivot" and obj.get("drive_name"):
            drive=bpy.data.objects[obj["drive_name"]]
            saved=obj["opening_percent"]
            drum=next(p for p in drive.children if p.get("asset_type")=="screen_drum")
            origin=drive.matrix_world.translation.copy()
            spin=1-"xy".index(obj.get("retract_axis","x"))
            rotations=[]; actual_rotations=[]
            for percent in (0,50,100):
                set_screen_opening(obj,percent); bpy.context.view_layer.update()
                require((drive.matrix_world.translation-origin).length<1e-5,"Screen drive moved with retraction")
                rotations.append(drum.rotation_euler[spin])
                actual_rotations.append(drum.matrix_local.to_quaternion())
            require(rotations[0]<rotations[1]<rotations[2],"Screen drum does not turn")
            require(abs(actual_rotations[0].dot(actual_rotations[1]))<0.01,'Screen drum transform did not rotate after helper')
            set_screen_opening(obj,saved)
            checks.append("screen_drum:"+obj.name)
        elif kind=="side_curtain":
            saved=obj["opening_percent"]
            panel=bpy.data.objects[obj["panel_name"]]
            origin=obj.matrix_world.translation.copy()
            lengths=[]
            for percent in (0,50,100,50):
                set_side_curtain_opening(obj,percent); bpy.context.view_layer.update()
                require((obj.matrix_world.translation-origin).length<1e-5,"Curtain top anchor moved")
                lengths.append(panel.scale.z*obj["full_height"])
            require(lengths[0]>lengths[1]>lengths[2] and lengths[1]==lengths[3],"Curtain does not retract reversibly")
            set_side_curtain_opening(obj,saved)
            checks.append("curtain_control:"+obj.name)
    bpy.context.view_layer.update()
    return checks


def check_cover_modes():
    root=bpy.data.objects["GH_ROOF_COVER"]
    mode=root.get("cover_mode","transparent")
    covers=[o for o in root.children_recursive if o.get("asset_type")=="roof_cover"]
    for state in ("opaque","hidden","transparent"):
        set_cover_visibility(state)
        for obj in covers:
            require(obj.hide_get()==(state=="hidden") and obj.hide_render==(state=="hidden"),"Cover visibility helper failed")
            alpha=obj.data.materials[0].node_tree.nodes["Principled BSDF"].inputs["Alpha"].default_value
            expected=1 if state=="opaque" else (0 if state=="hidden" else root["transparent_opacity"])
            require(math.isclose(alpha,expected,abs_tol=1e-6),"Cover opacity helper failed")
    set_cover_visibility(mode)
    return ["cover_opaque_transparent_hidden"]
