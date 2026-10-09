from .equipment_primitives import assembly,part_box,cylinder
from ..asset_metadata import annotate


def create_sensors(builder,config,mats):
    if not config["sensors"]["enabled"]:
        return
    for item in config["sensors"]["items"]:
        name="GH_SENSOR_"+item["id"]
        root=assembly(builder,name+"_ANCHOR","GH_SENSORS","sensor_anchor",item["position"],source="placeholder",sensor_id=item["id"])
        annotate(root,"placeholder",item["note"],position="placeholder",live_data_ready=True)
        root.empty_display_type='SPHERE'
        root.empty_display_size=0.22
        root.show_in_front=True
        root['label_anchor']=True
        if item["type"]=="solar_radiation":
            body=cylinder(builder,name,0.12,0.055,(0,0,0),"GH_SENSORS",mats["sensor"],root,role="sensor")
            cylinder(builder,name+"_DOME",0.055,0.05,(0,0,0.045),"GH_SENSORS",mats["display"],body)
        else:
            body=part_box(builder,name,(0.18,0.14,0.26),(0,0,0),"GH_SENSORS",mats["sensor"],root,"sensor")
            for i in range(4):
                part_box(builder,f"{name}_VENT_{i}",(0.12,0.012,0.012),(0,-0.076,-0.07+i*0.04),"GH_SENSORS",mats["motor"],body)
            cylinder(builder,name+"_PROBE",0.018,0.15,(0,0,-0.19),"GH_SENSORS",mats["frame"],body)
        annotate(body,"placeholder",item["note"],position="placeholder",sensor_type=item["type"],sensor_id=item["id"],live_data_ready=True,plc_tag_verified=False)
        # Short mounting bracket, not an invented permanent support pole.
        part_box(builder,name+"_MOUNT",(0.24,0.06,0.05),(0,0.11,-0.05),"GH_SENSORS",mats["frame"],root)
