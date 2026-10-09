from .primitives import grid_surface, tube_mesh
from .cover import roof_grid
from ..geometry_math import arch_height, roof_arch_radius, span_centers, span_x_range, vent_bounds, vent_sides, vent_angle, clamp_percent
from ..naming import vent_name
import math
import bpy
from mathutils import Vector
from .equipment_primitives import MeshParts, assembly, cylinder, gear, part_box
from ..asset_metadata import annotate


def set_vent_opening(obj, percent, max_angle_deg=None):
    """Accept either the named panel or its hinge Empty, also after GLB import."""
    pivot = obj.parent if obj.get("asset_type") == "roof_vent" else obj
    if pivot.get("asset_type") != "vent_pivot":
        raise ValueError("Expected roof vent panel or vent pivot")
    angle = pivot["max_open_angle_deg"] if max_angle_deg is None else max_angle_deg
    pivot.rotation_mode = "XYZ"
    pivot.rotation_euler.x = vent_angle(percent, angle, pivot["side"])
    pivot["opening_percent"] = clamp_percent(percent)
    for child in pivot.children:
        if child.get("asset_type") == "roof_vent":
            child["opening_percent"] = clamp_percent(percent)
    drive=bpy.data.objects.get(pivot.get("drive_name",""))
    if drive:
        theta=pivot.rotation_euler.x
        for part in drive.children:
            if part.get("asset_type")=="vent_rack":
                y,z=part["attach_y"],part["attach_z"]
                tip=Vector((part["station_x"],y*math.cos(theta)-z*math.sin(theta),y*math.sin(theta)+z*math.cos(theta)))
                fixed=Vector((part["station_x"],part["pinion_y"],part["pinion_z"]))
                axis=(tip-fixed).normalized()
                part.location=tip-axis*part["rack_length"]/2
                part.rotation_mode="QUATERNION"
                part.rotation_quaternion=axis.to_track_quat("Z","Y")
                part["opening_percent"]=clamp_percent(percent)
            elif part.get("asset_type")=="pinion":
                part.rotation_mode='XYZ'
                part.rotation_euler.x=clamp_percent(percent)/100*math.tau
                part["opening_percent"]=clamp_percent(percent)


def create_vents(builder, config, mats):
    v, g = config["roof_vents"], config["greenhouse"]
    if not v["enabled"]:
        return
    _, roof_ys = roof_grid(config)
    z_func = lambda y: arch_height(y,g["span_width"],g["eave_height"]["value"],g["ridge_height"]["value"],roof_arch_radius(g)) - g["ridge_height"]["value"]
    # Index 01 is the first configured side (+Y when paired), keeping Phase 1 names stable.
    for index,side in enumerate(vent_sides(config),1):
        for j,y in enumerate(span_centers(g["span_count"],g["span_width"]),1):
            x0,x1,y1 = vent_bounds(config,side,j)
            xc, half = (x0+x1)/2, (x1-x0)/2
            ys = [y for y in roof_ys if min(0,y1) <= y <= max(0,y1)]
            # Meshes are shared by every span of the same length on the same side.
            offset = span_x_range(g,j)[0] + g["length"]/2
            suffix = ("" if index==1 else f"_{index:02d}") + ("" if offset==0 else f"_{offset:g}")
            panel = grid_surface(builder, "VENT_PANEL"+suffix, [-half,half], ys, z_func, mats.get("vent_panel",mats["cover"]))
            # Perimeter follows the same sampled profile as the panel and roof opening.
            perimeter = [(-half,y,z_func(y)) for y in ys] + [(half,y,z_func(y)) for y in reversed(ys)]
            perimeter.append(perimeter[0])
            frame = tube_mesh(builder, "VENT_FRAME"+suffix, perimeter, config["structure"]["visual_frame_radius"]*0.6, mats["vent"])
            name = vent_name(j,index)
            pivot = builder.object(name+"_PIVOT", None, "GH_VENTS", asset_type="vent_pivot", span_index=j,
                                   controllable=True, control_variable="opening_percent", side=side, max_open_angle_deg=v["max_open_angle_deg"])
            pivot.location = (xc,y,g["ridge_height"]["value"])
            obj = builder.object(name,panel,"GH_VENTS",pivot,"roof_vent",span_index=j,controllable=True,control_variable="opening_percent")
            builder.object(name+"_FRAME",frame,"GH_VENTS",obj,"vent_frame",span_index=j)
            if v["mechanism_enabled"]:
                # Retain the Phase 1 panel name and parent. PANEL is an explicit picking anchor.
                alias=builder.object(name+"_PANEL",None,"GH_VENTS",obj,"vent_panel_anchor",panel_object=name)
                annotate(alias,"drawing_supported",drawing_pages="6,40")
                create_vent_drive(builder,config,mats,pivot,name,half,y1,z_func(y1))
            set_vent_opening(pivot,v["opening_percent"])


def create_vent_drive(builder,config,mats,pivot,name,half,y1,z1):
    drive=assembly(builder,name+"_DRIVE","GH_VENTS","vent_drive",tuple(pivot.location),pages="6,40",control_owner=pivot.name)
    pivot["drive_name"]=drive.name
    stations=(-half*0.55,half*0.55)
    compact=config['visual_refinement']['compact_vent_mechanism']
    if compact:
        # A near-hinge attachment needs less rack travel while retaining the panel pivot.
        y1*=0.45
        g=config['greenhouse']
        z1=arch_height(y1,g['span_width'],g['eave_height']['value'],g['ridge_height']['value'],roof_arch_radius(g))-g['ridge_height']['value']
    py,pz=y1*0.75,z1-0.55
    if compact: py,pz=y1*0.9,z1-0.20
    cylinder(builder,name+"_SHAFT",0.026,stations[1]-stations[0]+0.8,(0,py,pz),"GH_VENTS",mats["frame"],drive,"X","vent_shaft")
    length=1.05+abs(y1)*0.65
    if compact: length=0.34+abs(y1)*0.65
    geo=MeshParts(); geo.box((0,0,0),(0.035,0.055,length))
    for i in range(18): geo.box((0,0.038,-length/2+(i+0.5)*length/18),(0.045,0.04,length/45))
    mesh=geo.build(builder,f"RACK_{length}",[mats["frame"]])
    for idx,x in enumerate(stations):
        suffix="A" if idx==0 else "B"
        rack=builder.object(name+"_RACK_"+suffix,mesh,"GH_VENTS",drive,"vent_rack",station_x=x,attach_y=y1,attach_z=z1,
                            pinion_y=py,pinion_z=pz,rack_length=length,control_owner=pivot.name)
        annotate(rack,"drawing_supported",note="Rack aims at the panel edge; travel and ratio are approximate visual mechanics",drawing_pages="40")
        pinion=gear(builder,name+("_PINION" if idx==0 else "_PINION_B"),0.11,0.085,(x,py,pz),"GH_VENTS",mats["motor"],drive)
        pinion["control_owner"]=pivot.name
        bearing=part_box(builder,name+("_BEARING" if idx==0 else "_BEARING_B"),(0.12,0.22,0.2),(x-0.18,py,pz),"GH_VENTS",mats["cabinet"],drive,"vent_bearing")
        annotate(bearing,"drawing_supported",drawing_pages="40")
    motor=assembly(builder,name+"_MOTOR","GH_VENTS","vent_motor",(stations[0]-0.6,py,pz),drive,pages="40",controllable=True,control_variable="opening_percent",plc_tag_verified=False)
    cylinder(builder,name+"_MOTOR_HOUSING",0.15,0.38,(0,0,0),"GH_VENTS",mats["motor"],motor,"X")
    part_box(builder,name+"_MOTOR_GEARBOX",(0.20,0.25,0.28),(0.26,0,0),"GH_VENTS",mats["pump"],motor)
    part_box(builder,name+"_MOTOR_FOOT",(0.55,0.32,0.045),(0.08,0,-0.18),"GH_VENTS",mats["frame"],motor)
    if compact:
        motor.scale=(0.68,0.68,0.68)
        motor['compact_visual']=True
