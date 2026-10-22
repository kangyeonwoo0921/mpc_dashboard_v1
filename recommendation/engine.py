"""Rule-based screen recommendation (user decisions 2026-10-12; markdown/screen_recommendation.md).

Positions are **open %** (100 = retracted, 0 = fully deployed), as in the live API.

Shade screen (차광커튼2, aluminium 70 %), priority order:
    safety (rain / strong wind)            hold the current position
    night insulation (mode auto/cold)      sunset + start offset .. sunrise + end offset -> closure %
    day shading (mode auto/hot)            hybrid single threshold:
        deploy  if the next ``persistence`` min of forecast GHI all >= threshold
                or the measured mean of the last ``persistence`` min >= threshold
        retract if no available source is at/above the threshold (forecast all < and measured mean <)
        no change within ``min_hold`` min of the last recommended change
    otherwise                               retracted (100 %), light preservation
Diffuse screen (차광커튼1, 10 %): deployed (0 %) inside its night window when T_out < threshold and the
mode is not ``hot``; once deployed it stays until T_out >= threshold + release band (no flip-flop while T_out
hovers at the threshold); otherwise retracted. Missing T_out -> no recommendation.

GHI is the outside sensor reading (it reads low near noon and high at low sun); the threshold is applied on
that scale. The engine never actuates anything.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from . import settings_store

SEOUL = ZoneInfo("Asia/Seoul")
STEP = timedelta(minutes=5)
SCHEMA_VERSION = "screen-recommendation/0.1"
SITE_FILE = settings_store.PROJECT_DIR / "config" / "radiation_v1" / "site.json"
MOVE_TOLERANCE = 5.0          # % difference treated as "no change"

GROWTH_GUIDE = {
    "establishment": "8월 가이드: 활착기에는 차광 허용, 활착 후 4–5일마다 차광 시간·비율을 단계적으로 줄임",
    "vegetative": "10월 가이드: 활발한 생육기, 불필요한 차광 피하기",
    "flowering": "10월 가이드: 개화·착과기, 빛 유지",
    "harvest": "12월 가이드: 저온·저일사기, 빛 보존 우선",
}


# ------------------------------------------------------------------ sun

@lru_cache(maxsize=1)
def _site():
    data = json.loads(SITE_FILE.read_text(encoding="utf-8"))
    return float(data["latitude_deg"]), float(data["longitude_deg"])


@lru_cache(maxsize=64)
def sun_events(day: date):
    """(sunrise, sunset) for a local date, NREL SPA via pvlib."""
    import pvlib
    lat, lon = _site()
    noon = pd.DatetimeIndex([pd.Timestamp(day.isoformat() + " 12:00", tz=SEOUL)])
    events = pvlib.solarposition.sun_rise_set_transit_spa(noon, lat, lon)
    return (events["sunrise"].iloc[0].floor("s").to_pydatetime(), events["sunset"].iloc[0].floor("s").to_pydatetime())


def in_window(t: datetime, start_offset_h: float, end_offset_h: float, events=sun_events) -> tuple[bool, datetime, datetime]:
    """Is t inside [sunset(d)+start, sunrise(d+1)+end) for the night that contains t? Returns the window."""
    today = t.astimezone(SEOUL).date()
    for evening_day in (today - timedelta(days=1), today):
        sunset = events(evening_day)[1]
        sunrise_next = events(evening_day + timedelta(days=1))[0]
        start = sunset + timedelta(hours=start_offset_h)
        end = sunrise_next + timedelta(hours=end_offset_h)
        if start <= t < end:
            return True, start, end
    sunset = events(today)[1]
    return False, sunset + timedelta(hours=start_offset_h), events(today + timedelta(days=1))[0] + timedelta(hours=end_offset_h)


# ------------------------------------------------------------------ inputs

@dataclass
class Inputs:
    now: datetime
    live: dict                     # normalized live DTO
    safety: dict                   # {"rain": bool|None, "strong_wind": bool|None}
    forecast: dict | None          # latest_forecast.json payload (via /api/forecast/ghi/)
    settings: dict                 # settings values
    state: dict                    # previous recommendation state (min hold)


def _hm(t: datetime) -> str:
    return t.astimezone(SEOUL).strftime("%H:%M")


def _forecast_series(forecast):
    """{target_time: ghi} for usable horizons (status ok)."""
    if not forecast or forecast.get("status") != "ok" or not forecast.get("horizons"):
        return {}
    out = {}
    for h in forecast["horizons"]:
        if h.get("ghi_w_m2") is not None:
            out[datetime.fromisoformat(h["target_time"])] = float(h["ghi_w_m2"])
    return out


def _measured_mean(forecast, bins, now):
    """Mean of the last ``bins`` measured bins (all observed, newest within 15 min of ``now``), or None.
    Stale forecast files (collector or sync stopped) give None."""
    if not forecast or forecast.get("status") not in ("ok", "unavailable") or forecast.get("reason") == "data_stale":
        return None
    recent = forecast.get("recent_observations") or []
    window = recent[-bins:]
    if len(window) < bins or any(r.get("ghi_w_m2") is None for r in window):
        return None
    if now - datetime.fromisoformat(window[-1]["time"]) > timedelta(minutes=15):
        return None
    return sum(r["ghi_w_m2"] for r in window) / bins


def _next_forecast(series, t, bins):
    values = [series.get(t + STEP * (k + 1)) for k in range(bins)]
    return None if any(v is None for v in values) else values


# ------------------------------------------------------------------ rules

def shade_rule(t, s, live, safety, series, measured_mean, prev_target, held_until, is_now):
    """(target open %, state, reasons) for the shade screen at time t."""
    reasons = []
    current = live.get("actuators", {}).get("shade_screen_2_pct")
    if is_now and (safety.get("rain") or safety.get("strong_wind")):
        what = "감우" if safety.get("rain") else "강풍"
        return current, "SAFETY_OVERRIDE", [f"안전: {what} 감지 → 현재 위치 유지"]
    mode = s["operation_mode"]
    night, start, end = in_window(t, s["shade_night_start_offset_h"], s["shade_night_end_offset_h"])
    if night:
        if mode == "hot":
            return 100.0, "NIGHT_OPEN", ["고온기 모드: 밤 보온 끔 → 걷음"]
        closure = float(s["shade_night_closure_percent"])
        return 100.0 - closure, "NIGHT_INSULATION", [
            f"밤 보온 시간 {_hm(start)}–{_hm(end)} (일몰 {s['shade_night_start_offset_h']:+g} h, 일출 {s['shade_night_end_offset_h']:+g} h) → {closure:g}% 닫힘"]
    if mode == "cold":
        return 100.0, "DAY_LIGHT_PRESERVATION", ["저온기 모드: 낮 차광 끔 (빛 보존)"]

    threshold = float(s["shade_threshold_w_m2"])
    bins = int(s["persistence_min"]) // 5
    fut = _next_forecast(series, t, bins)
    deployed = prev_target is not None and prev_target <= MOVE_TOLERANCE
    high_f = fut is not None and min(fut) >= threshold
    low_f = fut is not None and max(fut) < threshold
    mm = measured_mean if is_now else None
    high_m = mm is not None and mm >= threshold
    low_m = mm is not None and mm < threshold
    if fut is not None:
        reasons.append(f"앞으로 {bins * 5}분 예측 일사 {min(fut):.0f}–{max(fut):.0f} W/m² (기준 {threshold:g})")
    elif is_now:
        reasons.append("앞으로의 일사 예측 없음 (밤·저고도·데이터 끊김)")
    if mm is not None:
        reasons.append(f"최근 {bins * 5}분 측정 평균 {mm:.0f} W/m²")
    want_deploy = high_f or high_m
    want_retract = (low_f or fut is None) and (low_m or mm is None) and (fut is not None or mm is not None)
    if deployed:
        target = 0.0 if not want_retract else 100.0
    else:
        target = 0.0 if want_deploy else 100.0
    if prev_target is not None and held_until is not None and t < held_until and abs(target - prev_target) > MOVE_TOLERANCE:
        reasons.append(f"최소 유지 시간: {_hm(held_until)} 이후 변경 가능 → 유지")
        target = prev_target
    if target <= MOVE_TOLERANCE:
        return target, "DAY_SHADE_ASSIST", reasons + [f"일사가 기준 {threshold:g} W/m² 이상으로 지속 → 차광"]
    if fut is None and mm is None:
        current = live.get("actuators", {}).get("shade_screen_2_pct") if is_now else prev_target
        hold = current if current is not None else prev_target
        if hold is not None:
            return hold, "DAY_HOLD", reasons + ["판단할 일사 정보 없음 → 지금 위치 유지"]
    return 100.0, "DAY_VENTILATION", reasons + ["차광 불필요 (빛 보존)"]


def diffuse_rule(t, s, live, safety, is_now, prev_target=None):
    current = live.get("actuators", {}).get("shade_screen_1_pct")
    if is_now and (safety.get("rain") or safety.get("strong_wind")):
        what = "감우" if safety.get("rain") else "강풍"
        return current, "SAFETY_OVERRIDE", [f"안전: {what} 감지 → 현재 위치 유지"]
    night, start, end = in_window(t, s["diffuse_night_start_offset_h"], s["diffuse_night_end_offset_h"])
    if not night:
        return 100.0, "DAY", ["산광 보온 시간 아님 → 걷음"]
    if s["operation_mode"] == "hot":
        return 100.0, "NIGHT_OPEN", ["고온기 모드: 산광 보온 끔 → 걷음"]
    t_out = live.get("environment", {}).get("outdoor_temperature_c")
    if t_out is None:
        return None, "NO_DATA", [f"산광 보온 시간 {_hm(start)}–{_hm(end)}, 외기 온도 없음 → 판단 불가"]
    limit = float(s["diffuse_tout_threshold_c"])
    release = limit + float(s["diffuse_tout_release_band_c"])
    if t_out < limit:
        return 0.0, "NIGHT_INSULATION", [f"산광 보온 시간 {_hm(start)}–{_hm(end)}, 외기 {t_out:.1f} °C < {limit:g} °C → 펼침"]
    if prev_target is not None and prev_target <= MOVE_TOLERANCE and t_out < release:
        return 0.0, "NIGHT_INSULATION", [f"산광 보온 시간 {_hm(start)}–{_hm(end)}, 펼친 상태: 외기 {t_out:.1f} °C가 {release:g} °C 미만 → 유지"]
    return 100.0, "NIGHT_OPEN", [f"산광 보온 시간이지만 외기 {t_out:.1f} °C ≥ {limit:g} °C → 걷음"]


def _action(current, target):
    if target is None:
        return "unavailable"
    if current is None:
        return "set"
    if abs(target - current) <= MOVE_TOLERANCE:
        return "hold"
    return "deploy" if target < current else "retract"


ACTION_LABEL = {"hold": "유지", "deploy": "펼침", "retract": "걷음", "set": "설정", "unavailable": "판단 불가"}


# ------------------------------------------------------------------ main

def recommend(inp: Inputs) -> tuple[dict, dict]:
    """(payload, new_state). Pure: no file access."""
    s, live, now = inp.settings, inp.live, inp.now
    issue = now.replace(second=0, microsecond=0) - timedelta(minutes=now.minute % 5)
    series = _forecast_series(inp.forecast)
    bins = int(s["persistence_min"]) // 5
    measured = _measured_mean(inp.forecast, bins, now)
    state = dict(inp.state or {})
    prev = state.get("shade_target")
    held_until = datetime.fromisoformat(state["shade_held_until"]) if state.get("shade_held_until") else None

    shade_target, shade_state, shade_reasons = shade_rule(issue, s, live, inp.safety, series, measured, prev, held_until, True)
    # previous diffuse recommendation; before the first one, the screen's actual position
    prev_diffuse = state.get("diffuse_target", live.get("actuators", {}).get("shade_screen_1_pct"))
    diffuse_target, diffuse_state, diffuse_reasons = diffuse_rule(issue, s, live, inp.safety, True, prev_diffuse)
    if diffuse_target is not None:
        state["diffuse_target"] = diffuse_target

    if shade_target is not None and (prev is None or abs(shade_target - prev) > MOVE_TOLERANCE):
        state["shade_target"] = shade_target
        state["shade_changed_at"] = issue.isoformat()
        state["shade_held_until"] = (issue + timedelta(minutes=int(s["min_hold_min"]))).isoformat()

    # 60-min plan: forecast only (measured values are not known ahead), same rules step by step
    plan_times, plan_shade, plan_diffuse = [], [], []
    p_target = state.get("shade_target")
    p_hold = datetime.fromisoformat(state["shade_held_until"]) if state.get("shade_held_until") else None
    p_diffuse = diffuse_target
    for k in range(13):
        t = issue + STEP * k
        if k == 0:
            st, dt_ = shade_target, diffuse_target
        else:
            st, _, _ = shade_rule(t, s, live, inp.safety, series, None, p_target, p_hold, False)
            dt_, _, _ = diffuse_rule(t, s, live, inp.safety, False, p_diffuse)
            p_diffuse = dt_ if dt_ is not None else p_diffuse
            if st is not None and p_target is not None and abs(st - p_target) > MOVE_TOLERANCE:
                p_hold = t + timedelta(minutes=int(s["min_hold_min"]))
            p_target = st if st is not None else p_target
        plan_times.append(t.isoformat())
        plan_shade.append(st)
        plan_diffuse.append(dt_)

    env, acts = live.get("environment", {}), live.get("actuators", {})
    connected = bool(live.get("connected"))
    reasons = []
    if not connected:
        reasons.append("live_disconnected")
    if inp.forecast is None or inp.forecast.get("status") != "ok":
        reasons.append("forecast_" + ((inp.forecast or {}).get("status") or "missing"))
    status = "ok" if not reasons else "degraded"

    advisories = []                     # the sensor basis note is shown once, under the GHI chart
    rh = env.get("indoor_rh_pct")
    if rh is not None and rh >= 99.0:
        advisories.append("실내 습도 센서 점검 필요 (99% 이상 고정): 습도 관련 규칙은 꺼져 있습니다.")
    if inp.safety.get("rain") or inp.safety.get("strong_wind"):
        advisories.append("천창(보조): 안전 규칙에 따라 닫힘 권장")

    transplant = date.fromisoformat(s["transplant_date"])
    days_after = (issue.date() - transplant).days
    sunrise, sunset = sun_events(issue.date())

    def screen(key, label, current, target, st, why, plan):
        action = _action(current, target)
        return {"label": label, "current_open_percent": current, "recommended_open_percent": target,
                "action": action, "action_label": ACTION_LABEL[action], "state": st, "reasons": why, "plan_open_percent": plan}

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.isoformat(timespec="seconds"),
        "issue_time": issue.isoformat(),
        "mode": "recommendation_only",
        "status": status,
        "status_reasons": reasons,
        "settings": {"operation_mode": s["operation_mode"], "growth_stage": s["growth_stage"],
                     "growth_guide": GROWTH_GUIDE.get(s["growth_stage"]), "days_after_transplant": days_after,
                     "shade_threshold_w_m2": s["shade_threshold_w_m2"], "persistence_min": s["persistence_min"],
                     "min_hold_min": s["min_hold_min"]},
        "screens": {
            "shade_screen": screen("shade_screen", "차광커튼2 (알루미늄 70%)", acts.get("shade_screen_2_pct"),
                                   shade_target, shade_state, shade_reasons, plan_shade),
            "diffuse_screen": screen("diffuse_screen", "차광커튼1 (산광 10%)", acts.get("shade_screen_1_pct"),
                                     diffuse_target, diffuse_state, diffuse_reasons, plan_diffuse),
        },
        "plan_times": plan_times,
        "inputs": {
            "live_source": live.get("source"), "live_connected": connected, "live_timestamp": live.get("timestamp"),
            "outdoor_temperature_c": env.get("outdoor_temperature_c"), "solar_w_m2": env.get("solar_w_m2"),
            "measured_mean_w_m2": None if measured is None else round(measured, 1),
            "forecast_status": (inp.forecast or {}).get("status"), "forecast_reason": (inp.forecast or {}).get("reason"),
            "sunrise": sunrise.isoformat(), "sunset": sunset.isoformat(),
            "safety": inp.safety,
        },
        "advisories": advisories,
    }
    return payload, state


# ------------------------------------------------------------------ IO wrapper

def _state_path() -> Path:
    return settings_store.data_dir() / "recommendation_state.json"


def load_state() -> dict:
    try:
        return json.loads(_state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def run(now: datetime | None = None) -> dict:
    from live_data.forecast import get_ghi_forecast
    from live_data.sources import get_live_safety, get_live_snapshot

    now = now or datetime.now(SEOUL)
    forecast = get_ghi_forecast(now)
    inp = Inputs(now=now, live=get_live_snapshot(now=now), safety=get_live_safety(now=now), forecast=forecast,
                 settings=settings_store.load()["values"], state=load_state())
    payload, state = recommend(inp)
    if state != inp.state:
        save_state(state)
    payload["forecast"] = {"status": forecast.get("status"), "horizons": forecast.get("horizons"),
                           "recent_observations": forecast.get("recent_observations")}
    payload["crop_light"] = crop_light(now, inp.live, payload)
    return payload


def crop_light(now, live, payload):
    """Estimated direct beam on the crop plane with the current and the recommended screen positions.

    Uses the ray-traced radiation model (physics.radiation_v1) with GHI separated by Engerer2.
    Diffuse light is not included (diffuse transmittances unknown). Never raises: the
    recommendation must not depend on the physics model being available.
    """
    try:
        from physics.radiation_v1.adapters.live_to_physics import actuators_from_live, weather_from_live
        from physics.radiation_v1.service import shared_model

        weather = weather_from_live(live)
        if weather.get("ghi_W_m2") is None or not (live or {}).get("connected", True):
            return {"status": "unavailable", "reason": "no_ghi"}
        model = shared_model()
        current = actuators_from_live(live)
        screens = payload["screens"]
        recommended = {**current,
                       "shade_screen_2_opening_percent": screens["shade_screen"]["recommended_open_percent"],
                       "shade_screen_1_opening_percent": screens["diffuse_screen"]["recommended_open_percent"]}
        first = model.evaluate(now, weather, current)
        second = first if recommended == current else model.evaluate(now, weather, recommended)
        decomposition = first["weather"].get("decomposition") or {}

        def mean(outcome):
            value = outcome["summary"]["direct_resolved_mean_W_m2"]
            return None if value is None else round(value, 1)

        return {"status": "ok" if mean(first) is not None else "unavailable",
                "reason": None if mean(first) is not None else decomposition.get("status"),
                "estimated": True, "part": "direct",
                "current_direct_mean_W_m2": mean(first), "recommended_direct_mean_W_m2": mean(second),
                "resolved_fraction": round(first["summary"]["direct_resolved_fraction"], 3),
                "sunlit_fraction": round(first["summary"]["sunlit_fraction"], 3),
                "dni_W_m2": None if first["weather"].get("dni_W_m2") is None else round(first["weather"]["dni_W_m2"], 1),
                "dhi_W_m2": None if first["weather"].get("dhi_W_m2") is None else round(first["weather"]["dhi_W_m2"], 1),
                "separation_model": decomposition.get("model"), "statuses": first["statuses"]}
    except Exception as error:  # noqa: BLE001 - physics is optional for the recommendation
        return {"status": "unavailable", "reason": f"model_error:{type(error).__name__}"}
