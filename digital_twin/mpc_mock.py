"""MOCK MPC recommendation payload for frontend development.

The real controller lives in ``mpc_lab/`` and is not built yet. This module only produces a payload
with the agreed response shape (contract: markdown/frontend_api_contract.md, mpc_lab
ARCHITECTURE.md §7) so the frontend can build its MPC screens now. Every number is synthetic:
smooth functions of the clock, not a prediction, and the payload says so (``is_mock``).
"""

import math
from datetime import timedelta

SCHEMA_VERSION = "mpc-recommendation/0.1"
SAMPLING_MINUTES = 5
PREDICTION_HORIZON_MINUTES = 60
CONTROL_HORIZON_MINUTES = 20
SCENARIOS = ("ok", "degraded", "unavailable")

# Field channel each recommended quantity drives (operator report 2026-10-07; mpc_lab actuators.yaml).
FIELD_CHANNELS = {
    "roof_vent_percent": {"live_keys": ["roof_vent_left_pct", "roof_vent_right_pct"],
                          "field_names": ["천창 좌(L)", "천창 우(R)"],
                          "note": "one common command for both leaves (OD-1)"},
    "diffuse_screen_open_percent": {"live_keys": ["shade_screen_1_pct"], "field_names": ["차광커튼1"],
                                    "note": "10 % 'Ultra' diffuse screen, 4.55 m"},
    "shade_screen_open_percent": {"live_keys": ["shade_screen_2_pct"], "field_names": ["차광커튼2"],
                                  "note": "70 % aluminium shade / night thermal screen, 4.8 m"},
}


def _day_phase(hour):
    if hour < 6 or hour >= 19:
        return "NIGHT_INSULATION"
    if hour < 9:
        return "MORNING_SOLAR_GAIN"
    if hour < 16:
        return "DAY_VENTILATION"
    return "EVENING_TRANSITION"


def _daylight(hour):
    """0 at night, 1 at 12:30; a synthetic shape, not a solar model."""
    return max(0.0, math.sin(math.pi * (hour - 6.0) / 13.0)) if 6.0 <= hour <= 19.0 else 0.0


def _controls(hour):
    light = _daylight(hour)
    if light == 0.0:                       # night: vents shut, aluminium screen mostly closed
        return 0.0, 20.0, 100.0
    return round(10 + 50 * light, 1), 100.0, 100.0   # vent, shade open %, diffuse open %


def _round(value, digits=2):
    return None if value is None else round(value, digits)


def _current(snapshot):
    actuators = (snapshot or {}).get("actuators") or {}
    left, right = actuators.get("roof_vent_left_pct"), actuators.get("roof_vent_right_pct")
    vent = None if left is None or right is None else (left + right) / 2
    return {"roof_vent_percent": _round(vent),
            "diffuse_screen_open_percent": _round(actuators.get("shade_screen_1_pct")),
            "shade_screen_open_percent": _round(actuators.get("shade_screen_2_pct"))}


def build_payload(now, scenario="ok", snapshot=None):
    if scenario not in SCENARIOS:
        raise ValueError(f"scenario must be one of {SCENARIOS}")
    base = {
        "schema_version": SCHEMA_VERSION,
        "is_mock": True,
        "source": "mock: synthetic values for frontend development, not a controller output",
        "timestamp": now.isoformat(),
        "mode": "recommendation_only",
        "sampling_minutes": SAMPLING_MINUTES,
        "prediction_horizon_minutes": PREDICTION_HORIZON_MINUTES,
        "control_horizon_minutes": CONTROL_HORIZON_MINUTES,
        "field_channels": FIELD_CHANNELS,
        "current": _current(snapshot),
    }
    hour = now.hour + now.minute / 60
    supervisor = {"day_phase_state": _day_phase(now.hour), "active_constraints": [], "overrides_applied": []}
    if scenario == "unavailable":
        return {**base, "status": "recommendation_unavailable",
                "reasons": ["missing_sensor:outdoor_relative_humidity"],
                "recommendation": None, "trajectory": None, "predicted": None, "diagnostics": None,
                "supervisor": supervisor, "source_status": {"model": "mock"}, "confidence": None}

    steps = PREDICTION_HORIZON_MINUTES // SAMPLING_MINUTES
    control_steps = CONTROL_HORIZON_MINUTES // SAMPLING_MINUTES
    times = [now + timedelta(minutes=SAMPLING_MINUTES * k) for k in range(steps + 1)]
    moves = []
    for k in range(steps):                   # moves after the control horizon are held
        h = hour + SAMPLING_MINUTES * min(k, control_steps - 1) / 60
        moves.append(_controls(h % 24))
    trajectory = {"times": [t.isoformat() for t in times[:-1]],
                  "roof_vent_percent": [m[0] for m in moves],
                  "shade_screen_open_percent": [m[1] for m in moves],
                  "diffuse_screen_open_percent": [m[2] for m in moves]}
    temperature, humidity, vpd, radiation, q_vent = [], [], [], [], []
    for k, t in enumerate(times):
        h = (hour + SAMPLING_MINUTES * k / 60) % 24
        light = _daylight(h)
        T = 17.0 + 8.0 * light - 0.15 * k
        rh = 82.0 - 25.0 * light
        e_s = 0.6112 * math.exp(17.67 * T / (T + 243.5))   # display-only kPa for the mock VPD
        temperature.append(round(T, 2))
        humidity.append(round(rh, 1))
        vpd.append(round(e_s * (1 - rh / 100), 3))
        radiation.append(round(450.0 * light, 1))
        q_vent.append(round(150.0 * light * moves[min(k, steps - 1)][0] / 60, 1))   # per m2 floor
    payload = {
        **base,
        "status": "ok" if scenario == "ok" else "degraded",
        "reasons": [] if scenario == "ok" else ["parameter_missing:screen_diffuse_transmittance"],
        "recommendation": {"roof_vent_percent": moves[0][0], "shade_screen_open_percent": moves[0][1],
                           "diffuse_screen_open_percent": moves[0][2]},
        "trajectory": trajectory,
        "predicted": {"times": [t.isoformat() for t in times], "T_air_C": temperature,
                      "RH_air_percent": humidity, "VPD_air_kPa": vpd,
                      "radiation_crop_W_m2": radiation, "Q_vent_W_m2": q_vent},
        "diagnostics": {"objective_total": 1.0, "objective_temperature": 0.4, "objective_humidity": 0.3,
                        "objective_light": 0.15, "objective_heat_loss": 0.1, "objective_movement": 0.05},
        "supervisor": supervisor,
        "source_status": {"model": "mock", "weights": "unknown", "radiation": "mock"},
        "confidence": "mock" if scenario == "ok" else "low",
    }
    return payload
