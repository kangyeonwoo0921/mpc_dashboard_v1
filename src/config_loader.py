"""Dependency-free validation of the JSON Schema subset used by this project."""
import copy
import json
import math
import re
from pathlib import Path

from .geometry_math import vent_half_length_ratio, vent_rotation_from_post_deg

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ConfigError(ValueError):
    pass


def _fail(path, rule, value):
    raise ConfigError(f"[CONFIG ERROR]\n{path or 'config'} {rule}.\nReceived: {value!r}")


def _validate(value, schema, root, path=""):
    if "$ref" in schema:
        target = root
        for part in schema["$ref"][2:].split("/"):
            target = target[part]
        return _validate(value, target, root, path)
    kind = schema.get("type")
    valid = {
        "object": isinstance(value, dict), "array": isinstance(value, list),
        "string": isinstance(value, str), "boolean": isinstance(value, bool),
        "number": type(value) in (int, float), "integer": type(value) is int,
    }
    if kind and not valid[kind]:
        _fail(path, f"must be {kind}", value)
    if type(value) in (int, float):
        if not math.isfinite(value):
            _fail(path, "must be finite", value)
        for key, bad in (("minimum", lambda n: value < n), ("maximum", lambda n: value > n),
                         ("exclusiveMinimum", lambda n: value <= n), ("multipleOf", lambda n: value % n != 0)):
            if key in schema and bad(schema[key]):
                _fail(path, f"must satisfy {key}={schema[key]}", value)
    if "const" in schema and value != schema["const"]:
        _fail(path, f"must equal {schema['const']!r} (supported configuration value)", value)
    if "enum" in schema and value not in schema["enum"]:
        _fail(path, f"must be one of {schema['enum']}", value)
    if isinstance(value, str) and len(value) < schema.get("minLength", 0):
        _fail(path, "must not be empty", value)
    if isinstance(value, str) and "pattern" in schema and not re.search(schema["pattern"],value):
        _fail(path, f"must match {schema['pattern']}",value)
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                _fail(f"{path}.{key}".strip("."), "is required", "missing")
        for key in list(value):
            field = f"{path}.{key}".strip(".")
            if key not in props and schema.get("additionalProperties") is False:
                _fail(field, "is not a recognized field", value[key])
            if key in props:
                _validate(value[key], props[key], root, field)
        for key, prop in props.items():
            if key not in value and "default" in prop:
                value[key] = copy.deepcopy(prop["default"])
                _validate(value[key],prop,root,f"{path}.{key}".strip("."))
    if isinstance(value, list):
        if len(value)<schema.get("minItems",0) or len(value)>schema.get("maxItems",math.inf):
            _fail(path,"has an invalid number of items",value)
        for i, item in enumerate(value):
            _validate(item, schema["items"], root, f"{path}[{i}]")


def validate_config(config):
    result = copy.deepcopy(config)
    schema = json.loads((PROJECT_ROOT / "config/greenhouse.schema.json").read_text(encoding="utf-8"))
    _validate(result, schema, schema)
    g, beds, vent = result["greenhouse"], result["crop_beds"], result["roof_vents"]
    if g["ridge_height"]["value"] <= g["eave_height"]["value"]:
        _fail("greenhouse.ridge_height.value", "must be greater than greenhouse.eave_height.value",
              {"ridge": g["ridge_height"]["value"], "eave": g["eave_height"]["value"]})
    if g["roof"]["profile"] == "circular_pointed_arch":
        radius = g["roof"].get("arch_radius")
        half_chord = math.hypot(g["span_width"] / 2, g["ridge_height"]["value"] - g["eave_height"]["value"]) / 2
        if radius is None or radius < half_chord:
            _fail("greenhouse.roof.arch_radius", f"is required for circular_pointed_arch and must be >= {half_chord:.3f}", radius)
    if beds["enabled"] and beds["rows_per_span"]:
        if 2 * beds["length_margin"] >= g["length"]:
            _fail("crop_beds.length_margin", "must leave positive bed length", beds["length_margin"])
        if beds["rows_per_span"] * beds["width"] >= g["span_width"]:
            _fail("crop_beds.width", "must leave space between rows and span boundaries", beds["width"])
    offsets = g.get("span_start_offsets")
    if offsets is not None:
        if len(offsets) != g["span_count"] or min(offsets) != 0:
            _fail("greenhouse.span_start_offsets", "must list one offset per span with at least one full-length span", offsets)
        if max(offsets) >= g["length"] - 2 * max(beds["length_margin"], vent.get("end_clearance") or 0):
            _fail("greenhouse.span_start_offsets", "must leave every span room for beds and vents", offsets)
    if "max_open_angle_from_post_deg" in vent:
        # Field reference (angle between the vertical ridge post and the opened leaf) -> leaf rotation.
        # The rotation is always derived from it, so a re-validated config stays consistent.
        vent["max_open_angle_deg"] = vent_rotation_from_post_deg(g, vent["panel_width_ratio"],
                                                                 vent["max_open_angle_from_post_deg"])
    elif "max_open_angle_deg" not in vent:
        _fail("roof_vents", "needs max_open_angle_deg or max_open_angle_from_post_deg", vent)
    if vent["max_open_angle_deg"] <= 0:
        _fail("roof_vents.max_open_angle_deg", "must be positive (leaf must open)", vent["max_open_angle_deg"])
    if vent.get("end_clearance") is not None and not 0 <= vent["end_clearance"] < g["length"] / 2:
        _fail("roof_vents.end_clearance", "must leave a positive vent length", vent["end_clearance"])
    half = vent_half_length_ratio(result)
    if vent["enabled"] and not half <= vent["x_center_ratio"] <= 1 - half:
        _fail("roof_vents.x_center_ratio", "must keep the complete panel within the roof", vent["x_center_ratio"])
    result["visualization"].setdefault("cover_opacity",result["cover"]["opacity"])
    sensors=result["sensors"]
    ids=[item["id"] for item in sensors["items"]]
    if len(ids)!=len(set(ids)):
        _fail("sensors.items","must have unique sensor ids",ids)
    if any(item["position"][2]<0 for item in sensors["items"]):
        _fail("sensors.items.position","must be above ground",sensors["items"])
    crops=result["crops"]
    if crops["enabled"] and beds["enabled"] and beds["rows_per_span"]:
        top=beds["z"]+beds["height"]+crops["plant_height"]
        limit=min([g["eave_height"]["value"]]+[result[k]["height"] for k in ("shade_screen","diffuse_screen") if result[k]["enabled"]])
        if top>=limit:
            _fail("crops.plant_height","must leave clearance below the roof and screen layers",top)
    curtains=result["side_curtains"]
    if result['sidewalls']['enabled'] and result['sidewalls']['fixed_lower_wall_height']>=g['eave_height']['value']:
        _fail('sidewalls.fixed_lower_wall_height','must be below the eave',result['sidewalls']['fixed_lower_wall_height'])
    if result['visual_refinement']['clip_screens_to_interior']:
        for key in ('shade_screen','diffuse_screen'):
            if result[key]['enabled'] and result[key]['height']+0.025>=g['ridge_height']['value']:
                _fail(key+'.height','must leave 0.025 m of visual clearance below the ridge for clipping',result[key]['height'])
    if curtains["enabled"] and curtains["bottom_height"]>=g["eave_height"]["value"]:
        _fail("side_curtains.bottom_height","must be below the eave",curtains["bottom_height"])
    if result["fertigation"]["enabled"] and result["fertigation"]["placement"]["mode"]=="end_service_strip":
        scale=result["fertigation"]["asset_scale"]
        minimum=3.0 if result['visual_refinement']['service_zone_layout'] else 2.8
        if beds["enabled"] and beds["rows_per_span"] and beds["length_margin"]<minimum*scale:
            _fail("crop_beds.length_margin",f"must leave at least {minimum}*fertigation.asset_scale meters for the service strip",beds["length_margin"])
    return result


def load_config(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ConfigError(f"[CONFIG ERROR]\nCannot read {path}: {exc}") from exc
    return validate_config(data)


def resolve_outputs(config, output_dir=None):
    result = {}
    for key in ("blend_path", "glb_path", "report_path"):
        path = Path(config["export"][key])
        if output_dir is not None:
            path = Path(output_dir) / path.name
        result[key] = (PROJECT_ROOT / path).resolve()
    if len({str(p).casefold() for p in result.values()}) != 3:
        _fail("export", "must use three distinct output paths", result)
    for key, suffix in (("blend_path", ".blend"), ("glb_path", ".glb"), ("report_path", ".json")):
        if result[key].suffix.lower() != suffix:
            _fail(f"export.{key}", f"must end with {suffix}", str(result[key]))
    return result
