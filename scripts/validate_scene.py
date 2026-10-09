"""Run in a separate headless Blender process: may replace the current scene."""
import argparse
import copy
import json
import math
from pathlib import Path
import sys
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from src.config_loader import load_config, resolve_outputs, ConfigError
from src.main import generate
from src.scene_setup import owned,cleanup_defaults,OWNER_KEY
from src.validation import require, validate_scene, validate_outputs, validate_roundtrip, scene_snapshot, read_glb
from src.geometry.vents import set_vent_opening
from src.geometry.screens import set_screen_opening
from src.geometry_math import vent_angle, screen_scale, vent_bounds, vent_sides
from src.report import object_counts
from src.operational_validation import check_operational_controls,check_cover_modes,validate_operational_scene
from src.preview import render_operational_previews
from src.refinement_validation import validate_refinement_scene,check_view_presets,check_end_wall_failure_detection


def check_controls():
    checks = []
    for obj in list(bpy.context.scene.objects):
        kind = obj.get("asset_type")
        if kind == "roof_vent":
            pivot = obj.parent
            saved = float(pivot["opening_percent"])
            origin = pivot.matrix_world.translation.copy()
            points = [v.co.copy() for v in obj.data.vertices]
            edge = max(points,key=lambda p: abs(p.y))
            heights = []
            for percent in (0,50,100,100):
                set_vent_opening(obj,percent)
                bpy.context.view_layer.update()
                require((pivot.matrix_world.translation-origin).length<1e-5,f"Vent hinge moved: {obj.name}")
                expected = vent_angle(percent,pivot["max_open_angle_deg"],pivot["side"])
                require(math.isclose(pivot.rotation_euler.x,expected,abs_tol=1e-6),f"Wrong vent rotation: {obj.name}")
                heights.append((obj.matrix_world @ edge).z)
            if 0 < pivot["max_open_angle_deg"] <= 90:
                require(heights[0]<heights[1]<heights[2],f"Vent opened downward: {obj.name}")
            require(math.isclose(heights[2],heights[3],abs_tol=1e-6),"Vent helper accumulates rotation")
            # Direct panel rotation must also keep the hinge line fixed.
            old_rotation = obj.rotation_euler.copy()
            obj.rotation_euler.x += 0.2
            bpy.context.view_layer.update()
            require((obj.matrix_world.translation-origin).length<1e-5,"Panel origin is not on hinge")
            obj.rotation_euler = old_rotation
            require(all((v.co-p).length<1e-7 for v,p in zip(obj.data.vertices,points)),"Control baked the panel mesh")
            set_vent_opening(obj,saved)
            checks.append("vent_control:"+obj.name)
        elif kind in ("shade_screen","diffuse_screen"):
            pivot = obj.parent
            saved = float(pivot["opening_percent"])
            origin = pivot.matrix_world.translation.copy()
            full_length = float(obj["full_length"])
            axis = "xy".index(pivot.get("retract_axis","x"))
            for percent in (0,50,100,50):
                set_screen_opening(obj,percent)
                bpy.context.view_layer.update()
                require((pivot.matrix_world.translation-origin).length<1e-5,"Screen fixed end moved")
                require(math.isclose(pivot.scale[axis],screen_scale(percent),abs_tol=1e-7),"Wrong screen scale")
                points = [obj.matrix_world @ v.co for v in obj.data.vertices]
                actual_length = max(p[axis] for p in points)-min(p[axis] for p in points)
                require(math.isclose(actual_length,full_length*screen_scale(percent),abs_tol=1e-5),"Screen width failed to retract")
            set_screen_opening(obj,saved)
            checks.append("screen_control:"+obj.name)
    bpy.context.view_layer.update()
    return checks


def check_cover_and_materials(config,outputs):
    checks = []
    if config["cover"]["enabled"]:
        g = config["greenhouse"]
        for cover in (o for o in bpy.context.scene.objects if o.get("asset_type")=="roof_cover"):
            area = sum(poly.area for poly in cover.data.polygons)
            require(area>0,"Roof cover has no surface")
            if config["roof_vents"]["enabled"]:
                for x0,x1,y1 in (vent_bounds(config,side,cover["span_index"]) for side in vent_sides(config)):
                    for face in cover.data.polygons:
                        x,y,_ = face.center
                        require(not (x0<x<x1 and min(0,y1)<y<max(0,y1)),"Cover overlaps the closed vent")
        checks.append("cover_openings")
    gltf = read_glb(outputs["glb_path"])
    viz=config.get("visualization",{})
    mode=viz.get("cover_mode","transparent")
    cover_alpha=1.0 if mode=="opaque" else (0.0 if mode=="hidden" else viz.get("cover_opacity",config["cover"]["opacity"]))
    expected = {"MAT_COVER":cover_alpha,"MAT_VENT_PANEL":config["cover"]["opacity"],"MAT_SCREEN_SHADE":config["shade_screen"]["visual_opacity"],"MAT_SCREEN_DIFFUSE":config["diffuse_screen"]["visual_opacity"]}
    for material in gltf.get("materials",[]):
        if material["name"] in expected:
            alpha = expected[material["name"]]
            require(math.isclose(material["pbrMetallicRoughness"]["baseColorFactor"][3],alpha,abs_tol=1e-6),"GLB alpha changed")
            require(material.get("doubleSided",False),"GLB layer is not double-sided")
            if alpha==0:
                # Blender 5.2 deliberately exports constant zero alpha as MASK.
                # A positive cutoff makes this fully invisible while retaining the node.
                require(material.get("alphaMode") in ("BLEND","MASK"),"Zero-alpha GLB layer became opaque")
                if material.get("alphaMode")=="MASK":
                    require(material.get("alphaCutoff",0.5)>0,"Hidden layer has a non-hiding alpha cutoff")
            elif alpha<1:
                require(material.get("alphaMode")=="BLEND","GLB transparency was lost")
    return checks+["glb_material_alpha_and_double_sided"]


def render_previews(directory):
    directory.mkdir(parents=True,exist_ok=True)
    scene=bpy.context.scene
    require(scene.camera is not None,"Preview rendering needs a generated camera")
    # Only generated geometry is evaluated here; user's objects remain in their file.
    for obj in scene.objects:
        if not owned(obj):
            obj.hide_render=True
    scene.render.resolution_x=1000
    scene.render.resolution_y=600
    scene.cycles.samples=8
    def render(name):
        scene.render.filepath=str(directory/(name+".png"))
        bpy.ops.render.render(write_still=True)
    render("01_default")
    for obj in scene.objects:
        if obj.get("asset_type")=="roof_cover":
            obj.hide_render=True
    for percent in (0,50,100):
        for name in ("GH_SHADE_SCREEN","GH_DIFFUSE_SCREEN"):
            if bpy.data.objects[name].children:
                set_screen_opening(bpy.data.objects[name],percent)
        for obj in scene.objects:
            if obj.get("asset_type")=="roof_vent":
                set_vent_opening(obj,percent)
        render(f"02_controls_{percent:03d}")
    # Front elevation shows all four roof arches and hinge directions.
    cam=scene.camera
    cfg=json.loads(bpy.data.objects["GH_ROOT"]["config_json"])
    g=cfg["greenhouse"]
    target=Vector((0,0,g["ridge_height"]["value"]/2))
    cam.location=(-g["length"]*1.5,0,target.z)
    cam.rotation_euler=(target-cam.location).to_track_quat("-Z","Y").to_euler()
    cam.data.ortho_scale=g["span_count"]*g["span_width"]*1.15
    render("03_front_open")


def data_counts():
    return {key:sum(owned(o) for o in getattr(bpy.data,key))
            for key in ("objects","collections","meshes","materials","cameras","lights","worlds")}


def acceptance(config_path,directory):
    directory.mkdir(parents=True,exist_ok=True)
    config=load_config(config_path)
    results={}
    # A user-owned child in a generated collection must survive a rerun.
    generate(config_path,directory/"rerun")
    baseline=data_counts()
    sentinel=bpy.data.objects.new("User_Preservation_Check",None)
    bpy.data.collections["GH_VENTS"].objects.link(sentinel)
    sentinel.parent=bpy.data.objects["GH_VENT_S01_01_PIVOT"]
    sentinel.location=(0.3,0.4,0.5)
    bpy.context.view_layer.update()
    world=sentinel.matrix_world.copy()
    generate(config_path,directory/"rerun")
    require(data_counts()==baseline,f"Generated data accumulated: {baseline} -> {data_counts()}")
    require(bpy.data.objects.get(sentinel.name)==sentinel,"User object was deleted")
    require(all(math.isclose(a,b,abs_tol=1e-5) for ra,rb in zip(world,sentinel.matrix_world) for a,b in zip(ra,rb)),"User world transform changed")
    results["rerun_preserves_user_objects"]=data_counts()
    # Invalid config must fail before clearing an existing scene.
    invalid=copy.deepcopy(config)
    invalid["greenhouse"]["ridge_height"]["value"]=1
    invalid_path=directory/"invalid.json"
    invalid_path.write_text(json.dumps(invalid),encoding="utf-8")
    before=scene_snapshot()
    try:
        generate(invalid_path,directory/"invalid")
    except ConfigError:
        pass
    else:
        raise ValueError("Invalid config was accepted")
    require(scene_snapshot()==before,"Invalid config mutated scene")
    results["invalid_config_preserves_scene"]=True
    cases={}
    three=copy.deepcopy(config); three["greenhouse"]["span_count"]=3
    if "span_start_offsets" in three["greenhouse"]:
        three["greenhouse"]["span_start_offsets"]=three["greenhouse"]["span_start_offsets"][:3]
    cases["three_spans"]=three
    short=copy.deepcopy(config); short["greenhouse"]["length"]=60
    cases["length_60"]=short
    negative=copy.deepcopy(config); negative["roof_vents"]["side"]="negative_y"
    cases["negative_vent_side"]=negative
    disabled=copy.deepcopy(config)
    for key in ("cover","roof_vents","shade_screen","diffuse_screen","crop_beds","ground"):
        disabled[key]["enabled"]=False
    disabled["render"]["add_camera"]=False
    disabled["render"]["add_lights"]=False
    cases["optional_geometry_disabled"]=disabled
    zero=copy.deepcopy(config); zero["crop_beds"]["rows_per_span"]=0
    cases["zero_bed_rows"]=zero
    no_vent=copy.deepcopy(config); no_vent["roof_vents"]["enabled"]=False
    cases["cover_without_vents"]=no_vent
    no_cover=copy.deepcopy(config); no_cover["cover"]["enabled"]=False
    cases["vents_without_cover"]=no_cover
    if config["metadata"]["phase"]>=1.5:
        cases["legacy_phase1"]=load_config(ROOT/"tests/fixtures/phase1.json")
        hidden=copy.deepcopy(config); hidden["visualization"]["cover_mode"]="hidden"
        cases["hidden_cover_export"]=hidden
        opaque=copy.deepcopy(config); opaque["visualization"]["cover_mode"]="opaque"
        cases["opaque_cover_export"]=opaque
        low=copy.deepcopy(config)
        low["crops"].update(detail_level="low",tomato_clusters=False,max_visual_plants_per_bed=8)
        cases["low_detail_capped_crops"]=low
        off=copy.deepcopy(config)
        for key in ("crops","fertigation","sensors","side_curtains"):
            off[key]["enabled"]=False
        off["roof_vents"]["mechanism_enabled"]=False
        off["shade_screen"]["drive_enabled"]=False
        off["diffuse_screen"]["drive_enabled"]=False
        cases["operational_assets_disabled"]=off
    if config['metadata']['phase']>=1.6:
        cases['legacy_phase1_5']=load_config(ROOT/'tests/fixtures/phase1_5.json')
        off=copy.deepcopy(config)
        off['sidewalls']['enabled']=False
        off['visual_refinement']={key:False for key in off['visual_refinement']}
        off['crops']['lod']='standard'
        cases['refinement_disabled']=off
        closed=copy.deepcopy(config); closed['side_curtains']['opening_percent']=0
        cases['sidewall_closed']=closed
        opened=copy.deepcopy(config); opened['side_curtains']['opening_percent']=100
        cases['sidewall_open']=opened
    for name,cfg in cases.items():
        path=directory/(name+".json")
        path.write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding="utf-8")
        result=generate(path,directory/name)
        checks=check_controls()+check_operational_controls()+check_cover_and_materials(cfg,resolve_outputs(cfg,directory/name))
        if name=="three_spans":
            require(result["dimensions"]["width"]==24 and object_counts()["roof_vents"]==3*len(vent_sides(cfg)) and object_counts()["crop_beds"]==15,"3-span acceptance failed")
        if name=="length_60":
            # A full-length span (zero front offset) carries the full 60 m - 2 x 4 m bed.
            offsets=cfg["greenhouse"].get("span_start_offsets") or [0.0]*cfg["greenhouse"]["span_count"]
            full_span=offsets.index(0)+1
            bed=next(o for o in bpy.context.scene.objects if o.get("asset_type")=="crop_bed" and o["span_index"]==full_span)
            require(math.isclose(bed.dimensions.x,52,abs_tol=1e-5),"60m bed length must be 52m")
        if name=="low_detail_capped_crops":
            require(result["operational_objects"]["crop_plant"]==160,"Crop cap was not applied to all 20 beds")
        if name=="legacy_phase1":
            require(result["objects"]["crop_beds"]==20 and result["operational_objects"]["crop_plant"]==0,"Legacy config unexpectedly enabled crops")
        checks+=validate_roundtrip(directory/name/"greenhouse.glb")
        checks+=check_controls()+check_operational_controls()+validate_refinement_scene(cfg)
        results[name]={"counts":result["objects"],"checks":checks}
    if config['metadata']['phase']>=1.6:
        from src.refinement import apply_view_preset
        from src.export.export_glb import export_glb
        for preset in ('exterior','interior','equipment','control_devices'):
            bpy.ops.wm.open_mainfile(filepath=str(directory/'rerun/greenhouse.blend'))
            apply_view_preset(preset)
            path=directory/('preset_'+preset+'.glb')
            export_glb(path,config['export']['apply_modifiers'])
            checks=validate_roundtrip(path)+check_controls()+check_operational_controls()+validate_refinement_scene(config)
            require(bpy.data.objects['GH_ROOT']['view_preset']==preset,'Preset metadata lost on roundtrip')
            results['preset_'+preset]={'checks':checks}
    # Existing names are rejected instead of silently creating GH_ROOT.001.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    conflict=bpy.data.objects.new("GH_ROOT",None)
    bpy.context.scene.collection.objects.link(conflict)
    try:
        generate(config_path,directory/"name_collision")
    except ValueError as exc:
        require("name collision" in str(exc),"Unexpected collision failure")
    else:
        raise ValueError("User name collision was silently accepted")
    require(bpy.data.objects.get("GH_ROOT")==conflict,"Name collision deleted user object")
    require(bpy.data.objects.get("GH_ROOT.001") is None,"Name collision created a suffixed object")
    results["user_name_collision_rejected"]=True
    # Explicit Cube exception must not spread to similarly named/custom objects.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mesh=bpy.data.meshes.new("Cleanup_Test_Mesh")
    objects={name:bpy.data.objects.new(name,mesh) for name in ("Cube","Cube.001","User_Custom_Cube")}
    for obj in objects.values(): bpy.context.scene.collection.objects.link(obj)
    cfg=copy.deepcopy(config)
    cfg["scene_cleanup"]["remove_default_cube"]=False
    cleanup_defaults(cfg)
    require(bpy.data.objects.get("Cube") is objects["Cube"],"Opt-out Cube was removed")
    objects["Cube"][OWNER_KEY]="user_metadata"
    cfg["scene_cleanup"]["remove_default_cube"]=True
    cleanup_defaults(cfg)
    require(bpy.data.objects.get("Cube") is objects["Cube"],"Cube with metadata was removed")
    del objects["Cube"][OWNER_KEY]
    cleanup_defaults(cfg)
    require(bpy.data.objects.get("Cube") is None,"Opt-in Cube was not removed")
    require(all(bpy.data.objects.get(name) is objects[name] for name in ("Cube.001","User_Custom_Cube")),"Cleanup removed a custom object")
    results["default_cube_opt_in_and_custom_preservation"]=True
    return results


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",default="config/greenhouse.json")
    parser.add_argument("--output-dir",default=None)
    parser.add_argument("--roundtrip",action="store_true")
    parser.add_argument("--acceptance",action="store_true")
    parser.add_argument("--render-previews",action="store_true")
    args=parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
    config_path=ROOT/args.config
    config=load_config(config_path)
    outputs=resolve_outputs(config,args.output_dir)
    directory=ROOT/"tmp/validation"
    directory.mkdir(parents=True,exist_ok=True)
    results={"status":"running","blender_version":bpy.app.version_string}
    try:
        bpy.ops.wm.open_mainfile(filepath=str(outputs["blend_path"]))
        checks=validate_scene(config)+validate_outputs(outputs)+check_cover_and_materials(config,outputs)+check_controls()+check_operational_controls()+check_cover_modes()+check_view_presets()+check_end_wall_failure_detection(config)
        results["base"]=checks
        if args.render_previews:
            if config["metadata"]["phase"]>=1.5:
                results["previews"]=render_operational_previews(directory/"previews",config)
            else:
                render_previews(directory/"previews")
            bpy.ops.wm.open_mainfile(filepath=str(outputs["blend_path"]))
        if args.roundtrip or args.acceptance:
            results["roundtrip"]=validate_roundtrip(outputs["glb_path"])+check_controls()+check_operational_controls()+validate_refinement_scene(config)
        if args.acceptance:
            if config['metadata']['phase']>=1.6:
                from src.motion import create_motion_smoke_test
                results['motion_smoke_test']=create_motion_smoke_test()
            results["acceptance"]=acceptance(config_path,directory/"cases")
        results["status"]="success"
        print("[VALIDATION SUCCESS] base checks:",len(checks),"acceptance cases:",len(results.get("acceptance",{})))
        print(directory/"acceptance_report.json")
    except Exception as exc:
        results["status"]="failed"
        results["error"]=str(exc)
        raise
    finally:
        (directory/"acceptance_report.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")


if __name__=="__main__":
    main()
