"""LIVE data sources.

``mock_static`` / ``mock_dynamic``: local fixtures.
``field_collector``: the ``latest.json`` written by the read-only field collector
(``field_collector/collector.py`` on the field PC, delivered e.g. through a sync folder).
Path: ``LIVE_DATA_FILE``. Data older than ``LIVE_DATA_MAX_AGE_S`` (default 180 s) or a
missing/unreadable file give the empty DTO (all values null, ``connected: false``) instead
of old values; ``timestamp`` is the collection time.

This module never makes a network request.
"""

from __future__ import annotations

import copy
import json
import math
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from . import psychrometrics
from .adapter import apply_growlink_mock_overrides, normalize_growlink_live, normalize_growlink_status


FIXTURE_PATH = Path(__file__).with_name("fixtures") / "growlink_live_sample.json"
SUPPORTED_SOURCES = frozenset({"mock_static", "mock_dynamic", "field_collector"})
FIELD_MAX_AGE_S = 180.0
SEOUL = ZoneInfo("Asia/Seoul")


def load_mock_raw() -> dict[str, Any]:
    with FIXTURE_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def _wave(seconds: float, minimum: float, maximum: float, period: float, phase: float = 0.0) -> float:
    midpoint = (minimum + maximum) / 2.0
    amplitude = (maximum - minimum) / 2.0
    return midpoint + amplitude * math.sin((seconds / period) * math.tau + phase)


def build_dynamic_raw(now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(tz=SEOUL)
    if current.tzinfo is None:
        current = current.replace(tzinfo=SEOUL)
    seconds = current.timestamp()
    raw = copy.deepcopy(load_mock_raw())
    temperature_c = round(_wave(seconds, 27.0, 31.0, 120.0), 2)
    rh_pct = round(_wave(seconds, 65.0, 80.0, 150.0, 0.7), 2)
    dew_point = psychrometrics.dew_point_c(temperature_c, rh_pct)
    return apply_growlink_mock_overrides(
        raw,
        environment={
            "indoor_temperature_c": temperature_c,
            "indoor_rh_pct": rh_pct,
            "vpd_kpa": round(psychrometrics.vpd_kpa(temperature_c, rh_pct), 3),
            "dew_point_c": None if dew_point is None else round(dew_point, 1),
            "solar_w_m2": round(_wave(seconds, 150.0, 650.0, 180.0, 1.2), 1),
        },
        actuators={
            "roof_vent_left_pct": round(_wave(seconds, 10.0, 80.0, 50.0), 2),
            "roof_vent_right_pct": round(_wave(seconds, 10.0, 80.0, 50.0, 1.1), 2),
            "shade_screen_1_pct": round(_wave(seconds, 0.0, 100.0, 70.0, 0.4), 2),
            "shade_screen_2_pct": round(_wave(seconds, 0.0, 100.0, 90.0, 1.6), 2),
        },
    )


def load_field_snapshot(path: str | Path | None, now: datetime, max_age_s: float = FIELD_MAX_AGE_S) -> dict[str, Any]:
    """Normalized DTO from the collector's latest.json; empty DTO when missing, unreadable or old."""

    empty = normalize_growlink_live({}, timestamp=now, source="field_collector")
    if not path:
        return empty
    try:
        record = json.loads(Path(path).read_text(encoding="utf-8"))
        collected_at = datetime.fromisoformat(record["collected_at"])
    except (OSError, ValueError, KeyError, TypeError):
        return empty
    if collected_at.tzinfo is None:
        collected_at = collected_at.replace(tzinfo=SEOUL)
    age = (now - collected_at).total_seconds()
    if age > max_age_s or age < -max_age_s:
        return normalize_growlink_live({}, timestamp=collected_at, source="field_collector")
    return normalize_growlink_live(record.get("response"), timestamp=collected_at, source="field_collector")


def load_raw_snapshot(source: str, now: datetime | None = None) -> dict[str, Any]:
    """Return raw source data without performing any network request."""

    if source == "mock_static":
        return load_mock_raw()
    if source == "mock_dynamic":
        return build_dynamic_raw(now)
    raise ValueError(f"Unsupported LIVE_DATA_SOURCE {source!r}; expected mock_static, mock_dynamic or field_collector")


def get_live_snapshot(
    source: str | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    selected = source or os.environ.get("LIVE_DATA_SOURCE", "mock_dynamic")
    current = now or datetime.now(tz=SEOUL)
    if current.tzinfo is None:
        current = current.replace(tzinfo=SEOUL)
    if selected == "field_collector":
        max_age = float(os.environ.get("LIVE_DATA_MAX_AGE_S", FIELD_MAX_AGE_S))
        return load_field_snapshot(os.environ.get("LIVE_DATA_FILE"), current, max_age)
    raw = load_raw_snapshot(selected, current)
    return normalize_growlink_live(raw, timestamp=current, source=selected)


def get_live_safety(source: str | None = None, *, now: datetime | None = None) -> dict[str, bool | None]:
    """Rain / strong-wind flags (field_collector only; None for mock sources or stale/missing data)."""

    selected = source or os.environ.get("LIVE_DATA_SOURCE", "mock_dynamic")
    empty = {"rain": None, "strong_wind": None}
    if selected != "field_collector":
        return empty
    current = now or datetime.now(tz=SEOUL)
    path = os.environ.get("LIVE_DATA_FILE")
    try:
        record = json.loads(Path(path).read_text(encoding="utf-8"))
        collected_at = datetime.fromisoformat(record["collected_at"])
    except (OSError, ValueError, KeyError, TypeError):
        return empty
    if collected_at.tzinfo is None:
        collected_at = collected_at.replace(tzinfo=SEOUL)
    if abs((current - collected_at).total_seconds()) > float(os.environ.get("LIVE_DATA_MAX_AGE_S", FIELD_MAX_AGE_S)):
        return empty
    return normalize_growlink_status(record.get("response"))
