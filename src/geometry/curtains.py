"""Side curtains retract upward; fixed drive hardware never scales with fabric."""
import math
import bpy
from .equipment_primitives import assembly, cylinder, part_box
from .primitives import mesh_data
from ..geometry_math import screen_scale,clamp_percent
from ..asset_metadata import annotate
from ..geometry_math import span_x_range


def set_side_curtain_opening(obj,percent):
    root=obj.parent if obj.get("asset_type")=="curtain_panel" else obj
    if root.get("asset_type")!="side_curtain":
        raise ValueError("Expected a side curtain root or panel")
    panel=bpy.data.objects[root["panel_name"]]
    panel.scale.z=screen_scale(percent)
    root["opening_percent"]=clamp_percent(percent)
    panel["opening_percent"]=clamp_percent(percent)
    for part in root.children:
        if part.get("asset_type") in ("curtain_roller","curtain_drum"):
            part.rotation_mode='XYZ'
            part.rotation_euler.x=clamp_percent(percent)/100*math.tau
        if part.get("asset_type")=="curtain_bottom_bar":
            part.location.z=-root["full_height"]*screen_scale(percent)


def create_curtains(builder,config,mats):
    c,g=config["side_curtains"],config["greenhouse"]
    if not c["enabled"]:
        return
    bottom=config['sidewalls']['fixed_lower_wall_height'] if config['sidewalls']['enabled'] else c['bottom_height']
    height=g["eave_height"]["value"]-bottom
    for label,sign in (("LEFT",-1),("RIGHT",1)):
        # Each long side follows its outer span, so a stepped front shortens one side.
        x0,x1=span_x_range(g,1 if sign<0 else g["span_count"])
        half,length=(x1-x0)/2,x1-x0
        mesh=mesh_data(builder,"SIDE_CURTAIN_PANEL" if length==g["length"] else f"SIDE_CURTAIN_PANEL_{length:g}",[(-half,0,0),(half,0,0),(half,0,-height),(-half,0,-height)],[(0,1,2,3)],mats["curtain"])
        name="GH_SIDE_CURTAIN_"+label
        root=assembly(builder,name,"GH_CURTAINS","side_curtain",((x0+x1)/2,sign*(g["span_count"]*g["span_width"]/2+c["frame_clearance"]),g["eave_height"]["value"]),pages="28-29",controllable=True,control_variable="opening_percent",full_height=height)
        if config['sidewalls']['enabled']:
            root.parent=builder.groups['GH_SIDEWALL_'+label]
        panel=builder.object(name+"_PANEL",mesh,"GH_CURTAINS",root,"curtain_panel",controllable=True,control_variable="opening_percent")
        annotate(panel,"drawing_supported",drawing_pages="28-29")
        root["panel_name"]=panel.name
        cylinder(builder,name+"_ROLLER",0.065,length,(0,0,0.10),"GH_CURTAINS",mats["frame"],root,"X","curtain_roller")
        cylinder(builder,name+"_DRUM",0.16,0.22,(-half+0.35,0,0.10),"GH_CURTAINS",mats["motor"],root,"X","curtain_drum")
        cylinder(builder,name+"_BOTTOM_BAR",0.023,length,(0,0,-height),"GH_CURTAINS",mats["frame"],root,"X","curtain_bottom_bar")
        for idx,x in enumerate((-half+0.5,half-0.5),1):
            part_box(builder,f"{name}_BRACKET_{idx:02d}",(0.12,0.18,0.22),(x,0,0),"GH_CURTAINS",mats["frame"],root)
            if config['sidewalls']['enabled']:
                cylinder(builder,f'{name}_GUIDE_{idx:02d}',0.008,height,(x,0.04,-height/2),'GH_CURTAINS',mats['frame'],root,'Z','curtain_guide')
        if config['sidewalls']['enabled']:
            cylinder(builder,name+'_SHAFT',0.025,length,(0,0,0.10),'GH_CURTAINS',mats['frame'],root,'X','curtain_shaft')
        set_side_curtain_opening(root,c["opening_percent"])
