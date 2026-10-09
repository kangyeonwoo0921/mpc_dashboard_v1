from .primitives import grid_surface,mesh_data
from ..geometry_math import span_centers, span_x_range, screen_scale, clamp_percent
import math
import bpy
from .equipment_primitives import assembly, cylinder, part_box
from ..refinement_math import screen_visible_width


def set_screen_opening(screen_root, percent):
    """Accept a layer group, one pivot or its panel; do not bake its transform."""
    if screen_root.get("asset_type") in ("shade_screen", "diffuse_screen"):
        pivots = [screen_root.parent]
    elif screen_root.get("asset_type") == "screen_pivot":
        pivots = [screen_root]
    else:
        pivots = [obj for obj in screen_root.children_recursive if obj.get("asset_type") == "screen_pivot"]
    if not pivots:
        raise ValueError("No screen pivots below the supplied object")
    for pivot in pivots:
        # retract_axis is the local axis the fabric shrinks along (x: along the span, y: across it).
        axis = "xy".index(pivot.get("retract_axis", "x"))
        pivot.scale[axis] = screen_scale(percent)
        pivot["opening_percent"] = clamp_percent(percent)
        bundle=bpy.data.objects.get(pivot.get('bundle_name',''))
        if bundle:
            bundle.scale[axis]=0.15+0.85*clamp_percent(percent)/100
            bundle['opening_percent']=clamp_percent(percent)
        for child in pivot.children:
            child["opening_percent"] = clamp_percent(percent)
        drive=bpy.data.objects.get(pivot.get("drive_name",""))
        if drive:
            for child in drive.children:
                if child.get("asset_type") in ("screen_drum","screen_roller","screen_shaft"):
                    child.rotation_mode='XYZ'
                    # Drive shafts lie across the fabric's travel, so they spin about that axis.
                    child.rotation_euler[1-axis]=clamp_percent(percent)/100*math.tau
                    child["opening_percent"]=clamp_percent(percent)


def screen_halves(values):
    """[(gather sign, name suffix, fraction of the span width)] for one span of one screen layer.

    gather_side 'both': two halves run out from both gutters and meet at the span centre; one opening
    percent drives both. A single gather side keeps the original one-piece names."""
    side = values.get("gather_side", "negative_y")
    if side == "both":
        return [(-1, "_N", 0.5), (1, "_P", 0.5)]
    return [(-1 if side == "negative_y" else 1, "", 1.0)]


def create_screens(builder, config, mats):
    g = config["greenhouse"]
    for key, prefix, mat in (("shade_screen","GH_SHADE_SCREEN","shade"),("diffuse_screen","GH_DIFFUSE_SCREEN","diffuse")):
        values = config[key]
        if not values["enabled"]:
            continue
        full_width=screen_visible_width(config,values['height'])
        # across_span: fabric is pulled across the span and gathers along a gutter (drawing pages 27-28).
        across=values.get("travel","along_length")=="across_span"
        halves=screen_halves(values) if across else [(-1,"",1.0)]
        for j,y in enumerate(span_centers(g["span_count"],g["span_width"]),1):
            x0,x1=span_x_range(g,j)
            length=x1-x0
            for gather,half,share in halves:
                width=full_width*share
                name = f"{prefix}_S{j:02d}{half}"
                pivot = builder.object(name+"_PIVOT",None,prefix,asset_type="screen_pivot",span_index=j,
                                       controllable=True,control_variable="opening_percent",screen_type=key,retract_axis="y" if across else "x")
                if across:
                    tag_len=("" if length==g["length"] else f"_{length:g}")+("_ACROSS_N" if gather<0 else "_ACROSS_P")+("" if share==1.0 else "_HALF")
                    mesh = grid_surface(builder, prefix+tag_len, [-length/2,length/2], sorted((0,-gather*width)), lambda y: 0, mats[mat])
                    pivot.location = ((x0+x1)/2,y+gather*full_width/2,values["height"])
                    pivot["gather_side"]="negative_y" if gather<0 else "positive_y"
                    travel=width
                else:
                    mesh = grid_surface(builder, prefix if length==g["length"] else f"{prefix}_{length:g}", [0,length], [-width/2,width/2], lambda y: 0, mats[mat])
                    pivot.location = (x0,y,values["height"])
                    travel=length
                builder.object(name,mesh,prefix,pivot,key,span_index=j,controllable=True,control_variable="opening_percent",full_length=travel,original_width=g['span_width'],visible_width=width,visual_clipping_applied=full_width<g['span_width'],original_height=values['height'])
                if config['visual_refinement']['clip_screens_to_interior']:
                    # A short accordion profile across the travel direction reads as stored fabric, not another shaft.
                    profile=[(-0.24+i*0.06,0.018 if i%2 else -0.005) for i in range(9)]
                    profile += [(0.24,-0.025),(-0.24,-0.025)]
                    count=len(profile)
                    if across:
                        vertices=[(edge,t,z) for edge in (-length/2,length/2) for t,z in profile]
                    else:
                        vertices=[(t,edge,z) for edge in (-width/2,width/2) for t,z in profile]
                    faces=[tuple(reversed(range(count))),tuple(range(count,2*count))]
                    faces += [(i,(i+1)%count,(i+1)%count+count,i+count) for i in range(count)]
                    folded=mesh_data(builder,prefix+'_FOLDED_BUNDLE'+(tag_len if across else ''),vertices,faces,mats[mat])
                    bundle=builder.object(name+'_RETRACT_BUNDLE',folded,prefix,asset_type='screen_bundle')
                    bundle.location=((x0+x1)/2,pivot.location.y-gather*0.24,values['height']-0.025) if across else (x0+0.24,y,values['height']-0.025)
                    bundle['control_owner']=pivot.name
                    pivot['bundle_name']=bundle.name
                if values["drive_enabled"]:
                    tag=("GH_SHADE" if key=="shade_screen" else "GH_DIFFUSE")
                    part=f"S{j:02d}{half}"
                    if across:
                        # The pull shaft runs along the gathering gutter; the drum sits at the front end.
                        drive=assembly(builder,name+"_DRIVE",prefix+"_DRIVE","screen_drive",((x0+x1)/2,pivot.location.y,values["height"]+0.12),pages="25-29",control_owner=pivot.name)
                        cylinder(builder,f"{tag}_DRUM_{part}",0.16,0.38,(-length/2+0.4,0,0),prefix+"_DRIVE",mats["motor"],drive,"X","screen_drum")
                        cylinder(builder,f"{tag}_SHAFT_{part}",0.018,max(0.05,length-0.25),(0,0,0),prefix+"_DRIVE",mats["frame"],drive,"X","screen_shaft")
                        for k,offset in enumerate((-0.38,0.38),1):
                            cylinder(builder,f"{tag}_ROLLER_{part}_{k:02d}",0.055,0.18,(offset*length,0,0),prefix+"_DRIVE",mats["pump"],drive,"X","screen_roller")
                            part_box(builder,f"{tag}_BRACKET_{part}_{k:02d}",(0.06,0.12,0.18),(offset*length,0,-0.1),prefix+"_DRIVE",mats["frame"],drive)
                    else:
                        drive=assembly(builder,name+"_DRIVE",prefix+"_DRIVE","screen_drive",(x0,y,values["height"]+0.12),pages="25-29",control_owner=pivot.name)
                        cylinder(builder,f"{tag}_DRUM_{part}",0.16,0.38,(0,0,0),prefix+"_DRIVE",mats["motor"],drive,"Y","screen_drum")
                        cylinder(builder,f"{tag}_SHAFT_{part}",0.018,max(0.05,width-0.25),(0,0,0),prefix+"_DRIVE",mats["frame"],drive,"Y","screen_shaft")
                        for k,offset in enumerate((-0.38,0.38),1):
                            cylinder(builder,f"{tag}_ROLLER_{part}_{k:02d}",0.055,0.18,(0,offset*width,0),prefix+"_DRIVE",mats["pump"],drive,"Y","screen_roller")
                            part_box(builder,f"{tag}_BRACKET_{part}_{k:02d}",(0.12,0.06,0.18),(0,offset*width,-0.1),prefix+"_DRIVE",mats["frame"],drive)
                    pivot["drive_name"]=drive.name
        set_screen_opening(builder.groups[prefix],values["opening_percent"])
