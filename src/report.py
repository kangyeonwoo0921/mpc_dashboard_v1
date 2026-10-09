import json
from collections import Counter
from datetime import datetime, timezone
import bpy
from .scene_setup import owned

COUNT_TYPES = {"main_columns":"main_column", "secondary_columns":"secondary_column", "rafters":"rafter",
               "roof_vents":"roof_vent", "shade_screens":"shade_screen", "diffuse_screens":"diffuse_screen", "crop_beds":"crop_bed"}


def object_counts():
    counts = Counter(o.get("asset_type") for o in bpy.context.scene.objects if owned(o))
    return {key: counts[value] for key,value in COUNT_TYPES.items()}


def config_warnings(config):
    warnings = list(config["metadata"].get("assumptions", []))
    g = config["greenhouse"]
    for key in ("eave_height","ridge_height"):
        if not g[key]["verified"]:
            warnings.append(f"greenhouse.{key}={g[key]['value']} m is provisional: {g[key]['note']}")
    if config["roof_vents"]["enabled"]:
        warnings.append(config["roof_vents"]["assumption"])
    for key in ("shade_screen","diffuse_screen"):
        if config[key]["enabled"] and config[key]["height"] > g["eave_height"]["value"]:
            action='visual width clipped to the sampled interior envelope; input height unchanged' if config['visual_refinement']['clip_screens_to_interior'] else 'full width retained'
            warnings.append(f"{key}: input layer at {config[key]['height']} m conflicts with the provisional roof; {action}.")
    if g["roof"]["segments_per_span"] > 32:
        warnings.append("Roof sampling exceeds the recommended 16-32 segments; file size may increase.")
    if config["crops"]["enabled"]:
        warnings.append("Crop geometry is approximate. Visual plant count is capped per bed; it is not the actual crop census.")
    if config["fertigation"]["enabled"]:
        warnings.append(config["fertigation"]["placement"]["note"])
    if config["sensors"]["enabled"]:
        warnings.append("All environment sensors and their positions are placeholders, verified=false. No live data or verified PLC tags.")
    return warnings


def write_report(path, config, outputs, status, checks=None, error=None,elapsed=None):
    g = config["greenhouse"]
    report = {
        "status": status, "project": config["metadata"]["project_name"],
        "generated_at": datetime.now(timezone.utc).isoformat(), "blender_version": bpy.app.version_string,
        "dimensions": {"length":g["length"], "width":g["span_count"]*g["span_width"], "span_count":g["span_count"]},
        "objects": object_counts(),
        "orientation":dict(config['orientation'],front_world_x=-g['length']/2,rear_world_x=g['length']/2),
        "outputs": {"blend":str(outputs["blend_path"]), "glb":str(outputs["glb_path"])},
        "warnings": config_warnings(config), "checks": checks or [],
    }
    generated=[o for o in bpy.context.scene.objects if owned(o)]
    plants=[o for o in generated if o.get("asset_type")=="crop_plant"]
    counts=Counter(o.get("asset_type") for o in generated)
    report["operational_objects"]={key:counts[key] for key in ("crop_plant","crop_row","vent_drive","vent_rack","pinion","vent_motor","screen_drive","side_curtain","tank","pump","blower","filter","sensor","supply_pipe","drain_pipe")}
    report["source_confidence"]={
        "drawing_supported":["roof vent shaft/rack/pinion/bearing/motor (pages 6,40)","shade/diffuse screens and curtain roller/drum systems (pages 25-29)","fertigation tanks, pump, blower, filters, instruments, supply/drain lines (pages 30-31)","5 tomato beds per span (page 30)"],
        "approximate":["equipment dimensions and low-poly shapes","crop height, shape and capped visual spacing","drive travel and rotation; no calibrated gear ratio","pipe diameter and routing","provisional roof heights and curvature"],
        "placeholder":["environment sensor positions and enclosures","provisional end-aisle equipment placement (not a surveyed drawing coordinate)","purifier/control cabinet/instrument detailed shapes","PLC tags are not assigned"],
    }
    report["source_confidence_scope"]="Evidence classification of the modeled systems; enabled instance counts are in objects/operational_objects. Drawing support proves existence, not coordinates or dimensions."
    report['source_confidence']['drawing_supported'].append('windbreak, side curtain, end closure and entrance existence (Phase 1.6 drawing interpretation)')
    report['source_confidence']['drawing_supported'].append('front=X1 (drawing page 6), rear=X23 (drawing page 10), longitudinal grid X1-X23 (page 30)')
    report['source_confidence']['approximate'] += ['lower wall height and closure geometry','screen interior clipping and folded bundle','compact vent drive dimensions']
    report['source_confidence']['placeholder'].append('front door coordinates and one-sided service equipment zoning')
    report['visual_clipping_applied']=any(o.get('visual_clipping_applied',False) for o in generated)
    report['screen_visual_layers']=[{'object':o.name,'original_height':o.get('original_height'),'original_width':o.get('original_width'),'visible_width':o.get('visible_width')} for o in generated if o.get('asset_type') in ('shade_screen','diffuse_screen')]
    report['visual_scale_exaggerated']=False
    report['circulation_fans_generated']=False
    report["performance"]={"generated_objects":len(generated),"unique_meshes":len({o.data.name for o in generated if o.type=="MESH"}),
                           "plant_instances":len(plants),"unique_plant_meshes":len({o.data.name for o in plants}),
                           "generation_seconds":elapsed}
    if error:
        report["error"] = str(error)
    if status == "success":
        report["output_bytes"] = {key:outputs[key+"_path"].stat().st_size for key in ("blend","glb")}
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary = path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    temporary.replace(path)
    return report
