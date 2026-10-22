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
        "css_ops_url": versioned("digital_twin/css/ops-status.css"),
        "css_typography_url": versioned("digital_twin/css/typography.css"),
        "motion_url": versioned("digital_twin/vendor/motion/motion.js"),
        "css_recommendation_url": versioned("digital_twin/css/recommendation.css"),
        "recommendation_module_url": versioned("digital_twin/js/recommendation.mjs"),
        "model_url": versioned("digital_twin/models/greenhouse.glb"),
        "viewer_module_url": versioned("digital_twin/js/viewer.mjs"),
        "import_map": json.dumps({"imports": imports}, indent=1),
    }


def _long_axis_azimuth():
    """Greenhouse long-axis azimuth (config/physics/site.json) for the wind arrows; None when unavailable."""
    try:
        from physics.parameters import load_physics_config

        return load_physics_config()[0].orientation.greenhouse_long_axis_azimuth_deg
    except Exception:
        return None


def viewer(request):
    azimuth = _long_axis_azimuth()
    context = {**_asset_urls(), "long_axis_azimuth": "" if azimuth is None else azimuth}
    response = render(request, "digital_twin/viewer.html", context)
    response["Cache-Control"] = "no-cache"
    return response


def live_snapshot(request):
    """Return a source-neutral read-only LIVE snapshot."""

    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    response = JsonResponse(get_live_snapshot(), json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "no-store"
    return response


def ghi_forecast(request):
    """GHI forecast (5-60 min) produced by mpc_lab's live runner; see live_data.forecast."""

    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    from live_data.forecast import get_ghi_forecast

    response = JsonResponse(get_ghi_forecast(), json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "no-store"
    return response


def screen_recommendation(request):
    """Rule-based screen recommendation (recommendation only); see recommendation/engine.py."""

    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    from recommendation.engine import run

    response = JsonResponse(run(), json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "no-store"
    return response


def recommendation_settings(request):
    """GET: values + field metadata + change history. POST JSON {"values": {...}, "changed_by", "note"}."""

    from recommendation import settings_store

    if request.method == "GET":
        payload, status = settings_store.describe(), 200
    elif request.method == "POST":
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
            settings_store.save(body.get("values", {}), changed_by=body.get("changed_by"), note=body.get("note"))
            payload, status = settings_store.describe(), 200
        except settings_store.SettingsError as error:
            payload, status = {"errors": error.errors}, 400
        except (ValueError, AttributeError):
            payload, status = {"errors": {"body": "JSON 객체가 필요합니다"}}, 400
    else:
        return HttpResponseNotAllowed(["GET", "POST"])
    response = JsonResponse(payload, status=status, json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "no-store"
    return response


def recommendation_settings_reset(request):
    """POST JSON {"keys": [...] (optional, all if omitted), "changed_by"}: restore defaults."""

    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    from recommendation import settings_store

    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except ValueError:
        body = {}
    settings_store.reset(body.get("keys"), changed_by=body.get("changed_by"))
    response = JsonResponse(settings_store.describe(), json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "no-store"
    return response


def recommendation_page(request):
    urls = _asset_urls()
    context = {"css_url": urls["css_recommendation_url"], "css_ops_url": urls["css_ops_url"],
               "css_typography_url": urls["css_typography_url"],
               "js_url": urls["recommendation_module_url"], "import_map": urls["import_map"]}
    response = render(request, "digital_twin/recommendation.html", context)
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


def mpc_recommendation(request):
    """MOCK MPC recommendation in the agreed response shape (see digital_twin/mpc_mock.py).

    ``?scenario=ok|degraded|unavailable`` lets the frontend exercise each status.
    """

    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    from .mpc_mock import SCENARIOS, build_payload

    scenario = request.GET.get("scenario", "ok")
    if scenario not in SCENARIOS:
        return HttpResponseBadRequest(f"scenario must be one of {', '.join(SCENARIOS)}")
    now = datetime.now(tz=ZoneInfo("Asia/Seoul")).replace(microsecond=0)
    response = JsonResponse(build_payload(now, scenario, get_live_snapshot()), json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "no-store"
    return response


def _optional_float(request, name, low, high):
    text = request.GET.get(name)
    if text in (None, ""):
        return None
    value = float(text)
    if not (low <= value <= high):
        raise ValueError(f"{name} must be in [{low}, {high}]")
    return value


def radiation_v1(request):
    """Spec-based v1 radiation model (physics.radiation_v1); physics code stays in that package.

    Without ``time`` the current time with LIVE weather and actuators is used. A requested
    ``time`` has no measured weather, so radiation stays None with a ``missing_input`` status
    unless ``ghi`` (e.g. a forecast value, labelled by ``ghi_source``) is given. ``shade_screen_1``
    and ``shade_screen_2`` (opening %) override the LIVE screen positions for previews.
    DNI/DHI are separated from GHI with Engerer2 (estimated, see physics/radiation_v1/decomposition.py).
    """

    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    from physics.radiation_v1.adapters.live_to_physics import actuators_from_live, weather_from_live
    from physics.radiation_v1.service import shared_model

    model = shared_model()
    snapshot = get_live_snapshot()
    zone = ZoneInfo(model.site.timezone)
    try:
        ghi = _optional_float(request, "ghi", 0, 1500)
        overrides = {f"shade_screen_{n}_opening_percent": _optional_float(request, f"shade_screen_{n}", 0, 100) for n in (1, 2)}
    except ValueError as error:
        return HttpResponseBadRequest(str(error))
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
    if ghi is not None:
        weather = {"ghi_W_m2": ghi, "dni_W_m2": None, "dhi_W_m2": None,
                   "source": request.GET.get("ghi_source", "query")[:40]}
    actuators = actuators_from_live(snapshot)
    actuators.update({k: v for k, v in overrides.items() if v is not None})
    response = JsonResponse(model.to_api(when, weather, actuators), json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "no-store"
    return response
