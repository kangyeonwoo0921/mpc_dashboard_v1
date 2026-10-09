"""Visual supply/drain connectivity only; no hydraulic or manufacturing claims."""
import bpy
from mathutils import Vector
from .primitives import tube_mesh
from ..asset_metadata import annotate
from ..geometry_math import span_x_range


def pipe(builder,name,points,group,material,role,**props):
    # Remove repeated endpoints before sweeping a tube.
    clean=[]
    for p in points:
        if not clean or (Vector(p)-Vector(clean[-1])).length>1e-6:
            clean.append(p)
    if len(clean)<2:
        return None
    radius=(0.042 if role=='supply_pipe' else 0.055) if props.get('line_role')=='header' else (0.022 if role=='supply_pipe' else 0.032)
    mesh=tube_mesh(builder,name,clean,radius,material,8)
    obj=builder.object(name,mesh,group,asset_type=role,**props)
    return annotate(obj,"drawing_supported","Routing and diameters are approximate visual connections, not hydraulic design","30-31")


def create_pipes(builder,config,mats):
    f,g=config["fertigation"],config["greenhouse"]
    if not f["enabled"]:
        return
    beds=[o for o in builder.groups["GH_BEDS"].children if o.get("asset_type")=="crop_bed"]
    if not beds:
        return
    margin=config["crop_beds"]["length_margin"]
    starts={b.name:span_x_range(g,b["span_index"])[0]+margin for b in beds}
    # The header sits where every span exists, so a stepped front never places it outdoors.
    x0,x1=max(starts.values()),g["length"]/2-margin
    ys=[b.location.y for b in beds]
    bedtop=config["crop_beds"]["z"]+config["crop_beds"]["height"]
    bpy.context.view_layer.update()
    if f["show_supply_lines"]:
        headerx=x0-0.5
        headerz=bedtop+0.08
        yoffset=-config["crop_beds"]["width"]*0.34
        pipe(builder,"GH_SUPPLY_HEADER",[(headerx,min(ys)+yoffset,headerz),(headerx,max(ys)+yoffset,headerz)],"GH_IRRIGATION_SUPPLY",mats["supply"],"supply_pipe",line_role="header")
        source=bpy.data.objects.get("GH_FEED_PUMP_OUTLET")
        if source:
            p=source.matrix_world.translation
            pipe(builder,"GH_SUPPLY_FEED",[tuple(p),(headerx,p.y,p.z),(headerx,p.y,headerz)],"GH_IRRIGATION_SUPPLY",mats["supply"],"supply_pipe",connects_from="GH_FEED_PUMP",connects_to="GH_SUPPLY_HEADER")
    if f["show_drain_lines"]:
        pipe(builder,"GH_DRAIN_HEADER",[(x1+0.5,min(ys),0.35),(x1+0.5,max(ys),0.35)],"GH_IRRIGATION_DRAIN",mats["drain"],"drain_pipe",line_role="header")
    for bed in beds:
        span,row=bed["span_index"],bed["row_index"]
        if f["show_supply_lines"]:
            y=bed.location.y+yoffset
            pipe(builder,f"GH_SUPPLY_S{span:02d}_R{row:02d}",[(x,y,headerz) for x in sorted({headerx,starts[bed.name],x1})],"GH_IRRIGATION_SUPPLY",mats["supply"],"supply_pipe",bed_name=bed.name,span_index=span,row_index=row,line_role='bed_branch',connects_from='GH_SUPPLY_HEADER',connects_to=bed.name)
        if f["show_drain_lines"]:
            y=bed.location.y
            z=max(0.12,config["crop_beds"]["z"]-0.08)
            pipe(builder,f"GH_DRAIN_S{span:02d}_R{row:02d}",[(starts[bed.name],y,z),(x1,y,z),(x1+0.5,y,z),(x1+0.5,y,0.35)],"GH_IRRIGATION_DRAIN",mats["drain"],"drain_pipe",bed_name=bed.name,span_index=span,row_index=row,line_role='bed_branch',connects_from=bed.name,connects_to='GH_DRAIN_HEADER')
