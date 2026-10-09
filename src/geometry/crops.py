"""One shared multi-material plant mesh, linked by every visible plant object."""
import math
from mathutils import Vector
from .equipment_primitives import MeshParts, assembly
from ..asset_metadata import annotate
from ..geometry_math import span_x_range


def plant_positions(length,spacing,cap):
    count=min(cap,max(1,int(math.floor(length/spacing))))
    # Equal cells leave end clearance; spacing grows only when the cap is reached.
    return [-length/2+(i+0.5)*length/count for i in range(count)]


def plant_mesh(builder,config,mats):
    c=config["crops"]; h=c["plant_height"]
    geo=MeshParts()
    geo.cylinder((0,0,0),(0.035,0,h*0.94),0.012,0,6)
    geo.cylinder((0.045,0,0),(0.045,0,h),0.004,4,4)
    leaf_count=14 if c["detail_level"]=="medium" else 6
    dashboard=c['lod']=='dashboard'
    if dashboard: leaf_count=8 if c['detail_level']=='medium' else 5
    for i in range(leaf_count):
        angle=i*2.39996
        z=h*(0.12+0.73*i/max(1,leaf_count-1))
        direction=Vector((math.cos(angle),math.sin(angle),0.22))
        start=Vector((0,0,z)); end=start+direction*(0.29 if i<leaf_count-2 else 0.21)
        geo.cylinder(start,end,0.006,0,5)
        for fraction in ((0.38,0.78) if c["detail_level"]=="medium" and not dashboard else (0.67,)):
            for side in (-1,1):
                mid=start.lerp(end,fraction)
                d=Vector((direction.x,direction.y,0)).normalized()
                lateral=Vector((-d.y,d.x,0))*side
                tip=mid+d*0.23+lateral*0.18+Vector((0,0,0.055))
                center=(mid+tip)/2+Vector((0,0,0.025))
                vertices=[mid,center-lateral*0.10,tip,center+lateral*0.10,center+Vector((0,0,0.025))]
                geo.add(vertices,[(0,1,4),(1,2,4),(2,3,4),(3,0,4)],1)
    if c["tomato_clusters"]:
        for i in range(3):
            z=h*(0.25+0.19*i)
            angle=i*2.3
            center=Vector((0.16*math.cos(angle),0.16*math.sin(angle),z))
            geo.cylinder((0,0,z+0.15),center,0.004,0,5)
            for j in range(2 if dashboard else 4):
                p=center+Vector(((j%2)*0.065,(j//2)*0.055,-j*0.035))
                geo.sphere(p,0.038,2 if i==2 else 3,sides=7,rings=3)
    return geo.build(builder,"CHERRY_TOMATO_SHARED",[mats[k] for k in ("stem","leaf","tomato_green","tomato_red","string")])


def create_crops(builder,config,mats):
    if not config["crops"]["enabled"]:
        return
    beds=[o for o in builder.groups["GH_BEDS"].children if o.get("asset_type")=="crop_bed"]
    if not beds:
        return
    mesh=plant_mesh(builder,config,mats)
    master=assembly(builder,"GH_PLANT_MASTER","GH_CROPS","plant_master",source="approximate")
    master["shared_mesh_name"]=mesh.name
    master["components"]="stem,leaves,support_string,tomato_clusters"
    c=config["crops"]
    for bed in beds:
        span,row=bed["span_index"],bed["row_index"]
        x0,x1=span_x_range(config["greenhouse"],span)
        length=x1-x0-2*config["crop_beds"]["length_margin"]
        positions=plant_positions(length,c["plant_spacing"],c["max_visual_plants_per_bed"])
        root=assembly(builder,f"GH_CROP_ROW_S{span:02d}_R{row:02d}","GH_CROPS","crop_row",source="approximate",span_index=span,row_index=row,bed_name=bed.name)
        root.location=((x0+x1)/2,bed.location.y,config["crop_beds"]["z"]+config["crop_beds"]["height"])
        root["visual_spacing"]=length/len(positions)
        for i,x in enumerate(positions,1):
            plant=builder.object(f"GH_PLANT_S{span:02d}_R{row:02d}_P{i:03d}",mesh,"GH_CROPS",root,"crop_plant",
                                 span_index=span,row_index=row,plant_index=i,bed_name=bed.name,crop_type="cherry_tomato",instance_mode="linked",master_name=master.name)
            plant.location.x=x
            plant['lod']=c['lod']
            if c['lod']=='dashboard': plant.location.y=0.035*math.sin(i*2.39996+row+span)
            plant.rotation_euler.z=(i%5)*0.23
            annotate(plant,"approximate",note="Visual cherry tomato instance; height and density are not measured crop observations")
