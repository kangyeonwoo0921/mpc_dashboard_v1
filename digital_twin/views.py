import json
import math
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from django.http import HttpResponseBadRequest, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import render
from django.templatetags.static import static

from live_data.sources import get_live_snapshot

ASSET_ROOT = Path(__file__).resolve().parent / "static"


def _asset_urls():
    """Versioned static URLs so browsers never reuse stale viewer modules.

    The token changes whenever any viewer asset changes. Modules import each other
    by relative path, so the import map also maps those resolved URLs (and the
    bare ``three`` specifiers) to the same versioned URL, keeping one instance each.
    """
    files = [p for p in (ASSET_ROOT / "digital_twin").rglob("*") if p.is_file()]
    version = format(max(p.stat().st_mtime_ns for p in files), "x")[-10:]

    def versioned(relative):
        return f"{static(relative)}?v={version}"

    imports = {"three": versioned("digital_twin/vendor/three/three.module.js")}
    for path in files:
        relative = path.relative_to(ASSET_ROOT).as_posix()
        if path.suffix in (".js", ".mjs"):
            imports[static(relative)] = versioned(relative)
            addon = relative.split("digital_twin/vendor/three/addons/", 1)
            if len(addon) == 2:
                imports["three/addons/" + addon[1]] = versioned(relative)
    return {
        "css_viewer_url": versioned("digital_twin/css/viewer.css"),
        "css_live_panel_url": versioned("digital_twin/css/live-panel.css"),
        "model_url": versioned("digital_twin/models/greenhouse.glb"),
        "viewer_module_url": versioned("digital_twin/js/viewer.mjs"),
        "import_map": json.dumps({"imports": imports}, indent=1),
    }


def viewer(request):
    response = render(request, "digital_twin/viewer.html", _asset_urls())
    response["Cache-Control"] = "no-cache"
    return response


def live_snapshot(request):
    """Return a source-neutral read-only LIVE snapshot."""

    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    response = JsonResponse(get_live_snapshot(), json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "no-store"
    return response


def _rounded(values, digits):
    return [None if not math.isfinite(v) else round(v, digits) for v in values]


def solar_state(request):
    """Sun position and modelled canopy light for the viewer (visual aid, not validated).

    Without ``time`` the current time, LIVE irradiance and actuators are used. With an
    ISO ``time`` the outside irradiance comes from the clear-sky model instead.
    """

    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    # Imported lazily so the viewer and LIVE API never wait for numpy/trimesh.
    from physics.light_model import PAR_FRACTION_OF_GLOBAL, shared_model

    model = shared_model()
    snapshot = get_live_snapshot()
    actuators = snapshot.get("actuators") or {}
    text = request.GET.get("time")
    if text:
        try:
            when = datetime.fromisoformat(text)
        except ValueError:
            return HttpResponseBadRequest("time must be an ISO 8601 timestamp")
        if when.tzinfo is None:
            when = when.replace(tzinfo=ZoneInfo(model.site.timezone))
        irradiance = None
    else:
        when = datetime.now(tz=ZoneInfo(model.site.timezone))
        irradiance = (snapshot.get("environment") or {}).get("solar_w_m2")
    result = model.evaluate(when, actuators, irradiance=irradiance)
    sx, sy, sz = result["sun"]["direction_physics"]
    # Daily sun path (every 20 min while above the horizon) for the viewer's arc.
    from physics.light_model import sun_vector
    from physics.light_sample import solar_position
    axis = model.site.orientation.greenhouse_long_axis_azimuth_deg
    path = []
    for minutes in range(4 * 60, 21 * 60 + 1, 20):
        moment = when.replace(hour=minutes // 60, minute=minutes % 60, second=0, microsecond=0)
        altitude, azimuth = solar_position(moment, model.site.latitude_deg, model.site.longitude_deg)
        if altitude > 0:
            px, py, pz = sun_vector(altitude, azimuth, axis)
            path.append([round(px, 4), round(pz, 4), round(-py, 4)])
    grid = result["grid"]
    payload = {
        "timestamp": result["timestamp"],
        "sun": {**result["sun"], "direction_threejs": [sx, sz, -sy]},
        "sun_path_threejs": path,
        "outside": result["outside"],
        "canopy_height_m": result["canopy_height_m"],
        "mean": result["mean"],
        "grid": {
            "cell_size_m": grid["cell_size_m"], "rows": grid["rows"], "cols": grid["cols"],
            "origin_xy_m": grid["origin_xy_m"],
            "par_w_m2": _rounded(grid["global_w_m2"] * PAR_FRACTION_OF_GLOBAL, 1),
            "sunlit": _rounded(grid["sunlit"], 2),
        },
        "actuators": {k: actuators.get(k) for k in ("roof_vent_left_pct", "roof_vent_right_pct",
                                                    "shade_screen_1_pct", "shade_screen_2_pct")},
        "provenance": {"mock_data": str(snapshot.get("source", "")).startswith("mock"),
                       "validated": False,
                       "note": "Visual aid: unvalidated model on unverified site, optics and channel mappings."},
    }
    response = JsonResponse(payload)
    response["Cache-Control"] = "no-store"
    return response


def radiation_v1(request):
    """Spec-based v1 radiation model (physics.radiation_v1); physics code stays in that package.

    Without ``time`` the current time with LIVE weather and actuators is used. A requested
    ``time`` has no measured weather, so radiation stays None with a ``missing_input`` status.
    """

    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    from physics.radiation_v1.adapters.live_to_physics import actuators_from_live, weather_from_live
    from physics.radiation_v1.service import shared_model

    model = shared_model()
    snapshot = get_live_snapshot()
    zone = ZoneInfo(model.site.timezone)
    text = request.GET.get("time")
    if text:
        try:
            when = datetime.fromisoformat(text)
        except ValueError:
            return HttpResponseBadRequest("time must be an ISO 8601 timestamp")
        when = when if when.tzinfo else when.replace(tzinfo=zone)
        weather = {"ghi_W_m2": None, "dni_W_m2": None, "dhi_W_m2": None,
                   "source": "none: no measurement for a requested time"}
    else:
        when = datetime.now(tz=zone)
        weather = weather_from_live(snapshot)
    response = JsonResponse(model.to_api(when, weather, actuators_from_live(snapshot)),
                            json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "no-store"
    return response
