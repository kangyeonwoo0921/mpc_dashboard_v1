"""Translate a Growlink-shaped payload into the source-neutral LIVE DTO."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any


ENVIRONMENT_FIELDS = (
    "indoor_temperature_c",
    "indoor_rh_pct",
    "vpd_kpa",
    "co2_ppm",
    "dew_point_c",
    "setpoint_temperature_c",
    "outdoor_temperature_c",
    "solar_w_m2",
    "wind_speed_m_s",
    "wind_direction_text",
    "accumulated_solar",
)

ACTUATOR_FIELDS = (
    "roof_vent_left_pct",
    "roof_vent_right_pct",
    "side_vent_front_pct",
    "side_vent_rear_pct",
    "side_vent_left_pct",
    "side_vent_right_pct",
    "vertical_curtain_front_pct",
    "vertical_curtain_rear_pct",
    "vertical_curtain_left_pct",
    "vertical_curtain_right_pct",
    "shade_screen_1_pct",
    "shade_screen_2_pct",
    "boiler_on",
    "circulation_fan_on",
    "exhaust_fan_on",
)

_MOCK_ENVIRONMENT_PATHS = {
    "indoor_temperature_c": ("meas", "실내온도"),
    "indoor_rh_pct": ("meas", "내부습도"),
    "vpd_kpa": ("meas", "VPD"),
    "dew_point_c": ("meas", "이슬점"),
    "solar_w_m2": ("outside", "일사량"),
}

_MOCK_ACTUATOR_PATHS = {
    "roof_vent_left_pct": "천창 좌(L)",
    "roof_vent_right_pct": "천창 우(R)",
    "shade_screen_1_pct": "차광커튼1",
    "shade_screen_2_pct": "차광커튼2",
}


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _percent(value: Any) -> float | None:
    result = _number(value)
    return None if result is None else min(100.0, max(0.0, result))


def _boolean(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _find_numbered(items: Any, key: str, expected: int) -> dict[str, Any] | None:
    if not isinstance(items, list):
        return None
    return next(
        (item for item in items if isinstance(item, dict) and item.get(key) == expected),
        None,
    )


STATUS_FIELDS = ("operation_mode", "rain", "strong_wind", "alarm", "caution", "alarm_count")


def _empty_dto(timestamp: str, source: str) -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "source": source,
        "connected": False,
        "environment": {key: None for key in ENVIRONMENT_FIELDS},
        "actuators": {key: None for key in ACTUATOR_FIELDS},
        "status": {key: None for key in STATUS_FIELDS},
    }


def _on_off(value: Any) -> bool | None:
    return {"ON": True, "OFF": False}.get(str(value).strip().upper()) if value is not None else None


def _count(value: Any) -> int | None:
    """'0개' / 3 / '3' -> int; anything else -> None."""
    text = str(value).strip().rstrip("개").strip() if value is not None else ""
    return int(text) if text.isdigit() else None


def normalize_status_block(raw: Any) -> dict[str, Any]:
    """Farm-level status block (운전모드, 감우, 강풍, 전체경보, 전체주의, 알람 발생횟수); None when absent."""
    status = _mapping(_mapping(raw).get("status"))
    mode = status.get("운전모드")
    return {
        "operation_mode": mode.strip() if isinstance(mode, str) and mode.strip() else None,
        "rain": _on_off(status.get("감우")),
        "strong_wind": _on_off(status.get("강풍")),
        "alarm": _on_off(status.get("전체경보")),
        "caution": _on_off(status.get("전체주의")),
        "alarm_count": _count(status.get("알람 발생횟수")),
    }


def apply_growlink_mock_overrides(
    raw: dict[str, Any],
    *,
    environment: dict[str, float] | None = None,
    actuators: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Apply normalized-name mock values while keeping raw keys in this adapter."""

    farm = _mapping(raw.get("farm"))
    zone = _find_numbered(farm.get("zones"), "zone", 1)
    house = _find_numbered(_mapping(zone).get("houses"), "house", 1)
    if house is None:
        return raw
    outside = _mapping(farm.get("outside"))
    measurements = _mapping(house.get("meas"))
    raw_actuators = _mapping(house.get("acts"))
    targets = {"outside": outside, "meas": measurements}
    for key, value in (environment or {}).items():
        path = _MOCK_ENVIRONMENT_PATHS.get(key)
        if path:
            targets[path[0]][path[1]] = value
    for key, value in (actuators or {}).items():
        raw_key = _MOCK_ACTUATOR_PATHS.get(key)
        if raw_key:
            raw_actuators[raw_key] = value
    return raw


def normalize_growlink_live(
    raw: Any,
    *,
    timestamp: str | datetime | None = None,
    source: str = "mock_static",
) -> dict[str, Any]:
    """Return the English normalized DTO for zone 1 / house 1.

    Missing structure and invalid values are represented as ``None``.  The
    adapter deliberately owns every Growlink Korean-key lookup so callers and
    the browser never depend on the source schema.
    """

    if isinstance(timestamp, datetime):
        timestamp_text = timestamp.isoformat()
    elif isinstance(timestamp, str):
        timestamp_text = timestamp
    else:
        timestamp_text = datetime.now().astimezone().isoformat()

    dto = _empty_dto(timestamp_text, source)
    dto["status"] = normalize_status_block(raw)
    farm = _mapping(_mapping(raw).get("farm"))
    zone = _find_numbered(farm.get("zones"), "zone", 1)
    house = _find_numbered(_mapping(zone).get("houses"), "house", 1)
    if house is None:
        return dto

    outside = _mapping(farm.get("outside"))
    measurements = _mapping(house.get("meas"))
    actuators = _mapping(house.get("acts"))
    onoff = _mapping(house.get("onoff"))

    dto["connected"] = house.get("connected") is True
    dto["environment"] = {
        "indoor_temperature_c": _number(measurements.get("실내온도")),
        "indoor_rh_pct": _number(measurements.get("내부습도")),
        "vpd_kpa": _number(measurements.get("VPD")),
        "co2_ppm": _number(measurements.get("CO2")),
        "dew_point_c": _number(measurements.get("이슬점")),
        "setpoint_temperature_c": _number(measurements.get("설정온도")),
        "outdoor_temperature_c": _number(outside.get("외부기온")),
        "solar_w_m2": _number(outside.get("일사량")),
        "wind_speed_m_s": _number(outside.get("풍속")),
        "wind_direction_text": outside.get("풍향") if isinstance(outside.get("풍향"), str) else None,
        "accumulated_solar": _number(outside.get("누적일사")),
    }
    dto["actuators"] = {
        "roof_vent_left_pct": _percent(actuators.get("천창 좌(L)")),
        "roof_vent_right_pct": _percent(actuators.get("천창 우(R)")),
        "side_vent_front_pct": _percent(actuators.get("측창정후 정면")),
        "side_vent_rear_pct": _percent(actuators.get("측창정후 후면")),
        "side_vent_left_pct": _percent(actuators.get("측창좌우 좌측")),
        "side_vent_right_pct": _percent(actuators.get("측창좌우 우측")),
        "vertical_curtain_front_pct": _percent(actuators.get("전면수직커튼")),
        "vertical_curtain_rear_pct": _percent(actuators.get("후면수직커튼")),
        "vertical_curtain_left_pct": _percent(actuators.get("좌면수직커튼")),
        "vertical_curtain_right_pct": _percent(actuators.get("우면수직커튼")),
        "shade_screen_1_pct": _percent(actuators.get("차광커튼1")),
        "shade_screen_2_pct": _percent(actuators.get("차광커튼2")),
        "boiler_on": _boolean(onoff.get("보일러")),
        "circulation_fan_on": _boolean(onoff.get("유동팬")),
        "exhaust_fan_on": _boolean(onoff.get("배기팬")),
    }
    return dto


_STATUS_KEYS = {"rain": "감우", "strong_wind": "강풍"}


def normalize_growlink_status(raw: Any) -> dict[str, bool | None]:
    """Rain / strong-wind flags from the dashboard ``status`` block ("ON"/"OFF"); None when absent."""

    status = _mapping(_mapping(raw).get("status"))
    out: dict[str, bool | None] = {}
    for key, raw_key in _STATUS_KEYS.items():
        value = status.get(raw_key)
        out[key] = {"ON": True, "OFF": False}.get(str(value).strip().upper()) if value is not None else None
    return out
