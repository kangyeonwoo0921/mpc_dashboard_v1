"""Orchestration only: config -> structured scene -> verified files -> report."""
import json
import time
import bpy
from .config_loader import load_config, resolve_outputs
from .scene_setup import clear_previous_generated_scene, cleanup_defaults, SceneBuilder, setup_units, setup_camera_lights
from .materials import create_materials
from .geometry.frame import create_frame, create_ground
from .geometry.roof import create_roof
from .geometry.cover import create_cover,set_cover_visibility
from .geometry.vents import create_vents
from .geometry.screens import create_screens
from .geometry.beds import create_beds
from .geometry.crops import create_crops
from .geometry.fertigation import create_fertigation
from .geometry.pipes import create_pipes
from .geometry.sensors import create_sensors
from .geometry.curtains import create_curtains
from .geometry.sidewalls import create_sidewalls
from .validation import validate_scene, validate_outputs
from .export.export_glb import export_glb
from .export.save_blend import save_blend
from .report import write_report
from .orientation import end_positions


def generate(config_path, output_dir=None):
    started=time.perf_counter()
    config = load_config(config_path)
    outputs = resolve_outputs(config,output_dir)
    try:
        clear_previous_generated_scene()
        cleanup_defaults(config)
        setup_units(config)
        builder = SceneBuilder()
        builder.groups["GH_ROOT"]["config_json"] = json.dumps(config,ensure_ascii=False)
        for key,value in config['orientation'].items(): builder.groups['GH_ROOT'][key]=value
        for end,position in end_positions(config).items(): builder.groups['GH_ROOT'][end+'_world_position']=list(position)
        mats = create_materials(config)
        for creator in (create_ground,create_frame,create_roof,create_cover,create_vents,create_screens,create_beds,
                        create_crops,create_sidewalls,create_curtains,create_fertigation,create_pipes,create_sensors):
            creator(builder,config,mats)
        set_cover_visibility(config["visualization"]["cover_mode"],config["visualization"]["cover_opacity"])
        setup_camera_lights(builder,config)
        bpy.context.view_layer.update()
        checks = validate_scene(config)
        export_glb(outputs["glb_path"],config["export"]["apply_modifiers"])
        save_blend(outputs["blend_path"])
        checks += validate_outputs(outputs)
        report = write_report(outputs["report_path"],config,outputs,"success",checks,elapsed=time.perf_counter()-started)
        print("[SUCCESS] Greenhouse generated:",report["objects"])
        for path in outputs.values():
            print(path)
        return report
    except Exception as exc:
        write_report(outputs["report_path"],config,outputs,"failed",error=exc)
        raise
