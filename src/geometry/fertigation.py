"""Drawing-supported equipment types with explicitly provisional shapes/placement."""
from .equipment_primitives import assembly,part_box,cylinder,MeshParts
from ..asset_metadata import annotate
from ..geometry_math import span_x_range


def equipment_layout(config):
    g,f=config["greenhouse"],config["fertigation"]
    total=g["span_count"]*g["span_width"]
    scale=min(f["asset_scale"],total/24)
    if config['visual_refinement']['service_zone_layout']:
        scale=min(f['asset_scale'],total/26)
    p=f["placement"]
    if p["mode"]=="absolute":
        origin=(p["x"],p["y"],p["z"])
    else:
        margin=config["crop_beds"]["length_margin"] if config["crop_beds"]["enabled"] else 4*scale
        y=-total/2+0.65*scale if config['visual_refinement']['service_zone_layout'] else 0
        # The strip sits in the end margin of the span it stands in, so a stepped front keeps it indoors.
        span=min(g["span_count"],max(1,int((y+total/2)//g["span_width"])+1))
        origin=(span_x_range(g,span)[0]+margin/2,y,p["z"])
    return origin,scale,total


def create_fertigation(builder,config,mats):
    f=config["fertigation"]
    if not f["enabled"]:
        return
    group="GH_FERTIGATION_UNIT"
    unit=builder.groups[group]
    origin,s,total=equipment_layout(config)
    unit.location=origin
    annotate(unit,"drawing_supported",f["placement"]["note"],"30-31",position="placeholder",asset_type="fertigation_unit",visual_asset_scale=s)
    unit['front_axis_reference']='X1'
    unit['equipment_access_facing']='negative_x'
    unit['placement_review']='Front service strip retained as provisional; drawing page 30 places equipment near Y5 and middle X stations, not this simplified end strip.'

    def root(name,kind,x,y,source="drawing_supported",**props):
        if config['visual_refinement']['service_zone_layout']:
            layout={'GH_NUTRIENT_TANK_A':(-0.65,0.55,'tanks'),'GH_NUTRIENT_TANK_B':(-0.65,1.95,'tanks'),'GH_NUTRIENT_TANK_C':(-0.65,3.35,'tanks'),
                    'GH_WATER_TANK':(-0.65,5.05,'tanks'),'GH_MIXING_TANK':(-0.65,6.8,'tanks'),
                    'GH_FEED_PUMP':(0.90,6.8,'pump_filter_blower'),'GH_FILTER_01':(0.90,5.7,'pump_filter_blower'),'GH_FILTER_02':(0.90,4.8,'pump_filter_blower'),
                    'GH_RING_BLOWER':(0.90,3.5,'pump_filter_blower'),'GH_WATER_PURIFIER':(-0.65,8.35,'water_treatment'),
                    'GH_CONTROL_PANEL':(-0.65,9.8,'controls'),'GH_PRESSURE_GAUGE':(0.70,8.2,'instruments'),
                    'GH_PRESSURE_VALVE':(0.70,9.0,'instruments'),'GH_FLOW_METER':(0.70,9.8,'instruments')}
            x,local_y,zone=layout[name]; y=local_y*s
            props['service_zone']=zone
        obj=assembly(builder,name,group,kind,(x*s,y,0),unit,source,pages="30-31",**props)
        annotate(obj,source,f["placement"]["note"],"30-31",position="placeholder")
        return obj

    def box(name,size,loc,parent,mat="frame"):
        return part_box(builder,name,tuple(v*s for v in size),tuple(v*s for v in loc),group,mats[mat],parent)

    def cyl(name,r,l,loc,parent,mat="tank",axis="Z"):
        return cylinder(builder,name,r*s,l*s,tuple(v*s for v in loc),group,mats[mat],parent,axis)

    def tank(name,y,radius,height):
        obj=root(name,"tank",-0.35,y,controllable=False)
        cyl(name+"_BODY",radius,height,(0,0,0.18+height/2),obj)
        cyl(name+"_BASE",radius*1.03,0.10,(0,0,0.13),obj,"frame")
        cyl(name+"_CAP",radius*0.92,0.09,(0,0,0.225+height),obj)
        cyl(name+"_LID",radius*0.32,0.08,(0,0,0.31+height),obj,"pump")
        for i,yoff in enumerate((-radius*0.7,radius*0.7),1):
            box(f"{name}_SUPPORT_{i}",(radius*1.3,0.09,0.12),(0,yoff,0.06),obj)
        cyl(name+"_CONNECTOR",0.045,0.22,(radius+0.09,0,0.4),obj,"supply","X")
        cyl(name+'_INLET',0.045,0.16,(0,0,0.39+height),obj,'supply')
        box(name+"_LABEL_PLATE",(0.025,radius*0.9,0.22),(-radius-0.012,0,0.7),obj,"cabinet")
        if config['visual_refinement']['service_zone_layout']:
            # Small raised glyphs are meshes for a stable GLB contract (no font dependency).
            label=name.rsplit('_',1)[-1] if 'NUTRIENT' in name else ('W' if 'WATER' in name else 'M')
            strokes={'A':[((-0.09,-0.08),(0,0.09)),((0,0.09),(0.09,-0.08)),((-0.05,0),(0.05,0))],
                     'B':[((-0.06,-0.08),(-0.06,0.08)),((-0.06,0.08),(0.06,0.04)),((0.06,0.04),(-0.06,0)),((-0.06,0),(0.06,-0.04)),((0.06,-0.04),(-0.06,-0.08))],
                     'C':[((0.06,0.08),(-0.06,0.08)),((-0.06,0.08),(-0.06,-0.08)),((-0.06,-0.08),(0.06,-0.08))],
                     'W':[((-0.09,0.08),(-0.05,-0.08)),((-0.05,-0.08),(0,0)),((0,0),(0.05,-0.08)),((0.05,-0.08),(0.09,0.08))],
                     'M':[((-0.08,-0.08),(-0.08,0.08)),((-0.08,0.08),(0,0)),((0,0),(0.08,0.08)),((0.08,0.08),(0.08,-0.08))]}
            geo=MeshParts()
            for a,b in strokes[label]: geo.cylinder(((-radius-0.03)*s,-a[0]*s,(0.7+a[1])*s),((-radius-0.03)*s,-b[0]*s,(0.7+b[1])*s),0.009*s,sides=4)
            builder.object(name+'_LABEL',geo.build(builder,name+'_GLYPH',[mats['motor']]),group,obj,'equipment_label',label=label)
            if label=='M':
                box(name+'_MIXER_BRIDGE',(0.7,0.10,0.10),(0,0,height+0.36),obj)
                cyl(name+'_MIXER_DRIVE',0.10,0.20,(0,0,height+0.5),obj,'motor')
        return obj

    if f["show_tanks"]:
        for letter,factor in (("A",-0.40),("B",-0.28),("C",-0.16)):
            obj=tank("GH_NUTRIENT_TANK_"+letter,total*factor,0.48,1.28)
            obj["tank_role"]="nutrient_"+letter
        tank("GH_WATER_TANK",total*0.04,0.68,1.85)["tank_role"]="raw_water"
        tank("GH_MIXING_TANK",total*0.21,0.53,1.3)["tank_role"]="mixing"
    purifier=root("GH_WATER_PURIFIER","purifier",-0.3,total*0.35,source="placeholder")
    box("GH_PURIFIER_CABINET",(0.65,0.70,1.45),(0,0,0.8),purifier,"cabinet")
    for i,y in enumerate((-0.23,0,0.23),1):
        cyl(f"GH_PURIFIER_CARTRIDGE_{i}",0.065,0.7,(-0.39,y,0.78),purifier,"tank")
    if f["show_control_panel"]:
        cabinet=root("GH_CONTROL_PANEL","control_panel",-0.3,total*0.45,source="placeholder",controllable=False,plc_tag_verified=False)
        box("GH_CONTROL_CABINET",(0.5,0.74,1.65),(0,0,0.90),cabinet,"cabinet")
        box("GH_CONTROL_DOOR",(0.035,0.66,1.48),(-0.27,0,0.91),cabinet,"tank")
        display=box("GH_DISPLAY",(0.045,0.42,0.30),(-0.30,0,1.24),cabinet,"display")
        display["asset_type"]="display"
        for i,y in enumerate((-0.20,0,0.20),1):
            cyl(f"GH_CONTROL_INDICATOR_{i}",0.035,0.035,(-0.315,y,0.9),cabinet,"tomato_green" if i==1 else "motor","X")
        box("GH_CONTROL_HANDLE",(0.04,0.025,0.18),(-0.31,-0.26,0.72),cabinet,"motor")
    if f["show_pumps"]:
        pump=root("GH_FEED_PUMP","pump",0.70,total*-0.32,controllable=True,control_variable="on_off",plc_tag_verified=False)
        box("GH_FEED_PUMP_BASE",(0.85,0.48,0.12),(0,0,0.06),pump)
        cyl("GH_FEED_PUMP_MOTOR",0.19,0.45,(-0.17,0,0.35),pump,"motor","X")
        cyl("GH_FEED_PUMP_HOUSING",0.24,0.22,(0.23,0,0.35),pump,"pump","X")
        cyl("GH_FEED_PUMP_INLET",0.07,0.2,(0.43,0,0.35),pump,"supply","X")
        cyl("GH_FEED_PUMP_OUTLET",0.06,0.23,(0.23,0,0.65),pump,"supply")
    if f["show_blower"]:
        blower=root("GH_RING_BLOWER","blower",0.65,total*-0.09,controllable=True,control_variable="on_off",plc_tag_verified=False,system='fertigation',is_circulation_fan=False)
        box("GH_BLOWER_BASE",(0.72,0.56,0.12),(0,0,0.06),blower)
        cyl("GH_BLOWER_HOUSING",0.29,0.18,(0,0,0.4),blower,"pump","Y")
        cyl("GH_BLOWER_HUB",0.17,0.21,(0,0,0.4),blower,"frame","Y")
        cyl("GH_BLOWER_MOTOR",0.16,0.30,(0,0.30,0.4),blower,"motor","Y")
        cyl("GH_BLOWER_PORT",0.045,0.12,(-0.24,-0.08,0.60),blower,"supply")
        cyl('GH_BLOWER_INLET',0.065,0.22,(-0.24,-0.08,0.75),blower,'pump')
        cyl('GH_BLOWER_OUTLET',0.065,0.22,(0.24,-0.08,0.75),blower,'pump')
        geo=MeshParts(); geo.torus_y((0,-0.12*s,0.4*s),0.24*s,0.075*s)
        builder.object('GH_BLOWER_SIDE_CHANNEL',geo.build(builder,'BLOWER_RING',[mats['pump']]),group,blower,'blower_housing')
        # Sealed side-channel casing; no propeller, blades or fan grille.
        cyl('GH_BLOWER_COVER',0.18,0.045,(0,-0.17,0.4),blower,'pump','Y')
    if f["show_filters"]:
        for i,factor in ((1,0.09),(2,0.15)):
            name=f"GH_FILTER_{i:02d}"
            filtr=root(name,"filter",0.8,total*factor)
            cyl(name+"_BODY",0.14,0.75,(0,0,0.53),filtr,"pump")
            cyl(name+"_CAP",0.17,0.12,(0,0,0.97),filtr,"motor")
            cyl(name+"_CONNECTOR",0.045,0.46,(0,0,0.78),filtr,"supply","Y")
            box(name+"_FOOT",(0.30,0.30,0.15),(0,0,0.075),filtr)
    # Instruments are drawing-supported in existence; enclosure/dial geometry is placeholder.
    gauge=root("GH_PRESSURE_GAUGE","pressure_gauge",0.80,total*0.27,source="placeholder")
    cyl("GH_GAUGE_STEM",0.025,0.6,(0,0,0.4),gauge,"frame")
    cyl("GH_GAUGE_CASE",0.12,0.07,(0,0,0.79),gauge,"motor","X")
    cyl("GH_GAUGE_DIAL",0.105,0.012,(-0.042,0,0.79),gauge,"cabinet","X")
    box("GH_GAUGE_NEEDLE",(0.012,0.012,0.085),(-0.051,0,0.815),gauge,"tomato_red")
    valve=root("GH_PRESSURE_VALVE","valve",0.80,total*0.33,controllable=True,control_variable="opening_percent",plc_tag_verified=False)
    cyl("GH_VALVE_BODY",0.075,0.35,(0,0,0.48),valve,"pump","Y")
    cyl("GH_VALVE_STEM",0.025,0.18,(0,0,0.62),valve,"frame")
    box("GH_VALVE_LEVER",(0.045,0.3,0.025),(0,0.06,0.73),valve,"motor")
    meter=root("GH_FLOW_METER","flow_meter",0.80,total*0.40,source="placeholder")
    cyl("GH_FLOW_METER_PIPE",0.05,0.45,(0,0,0.48),meter,"supply","Y")
    box("GH_FLOW_METER_BODY",(0.17,0.25,0.28),(0,0,0.66),meter,"cabinet")
    box("GH_FLOW_METER_DISPLAY",(0.02,0.18,0.12),(-0.095,0,0.69),meter,"display")
